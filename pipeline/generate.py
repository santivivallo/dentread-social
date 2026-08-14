"""
Generador: Post (plan) → PostSpec (slides + copy).

Determinista. Sin modelo de lenguaje, sin extracción automática de cifras.

La extracción de cifras desde texto de PDF se probó y se eliminó: producía
frases sin sentido ("142 of a total of 153 periapical lesions… 92.") que
pasaban los cuatro guards, porque los guards miden riesgo regulatorio y de
copyright, no si algo significa algo. La única defensa es que un humano haya
leído la cifra en su fuente. Por eso el contenido sale exclusivamente de
data/facts.json.
"""
from __future__ import annotations

import re
import unicodedata

from pipeline.plan import Post
from pipeline.spec import PostSpec, Slide, Stat

# Tres frames: hook · datos · cierre. Lo fija el brand guide, no el código.
N_SLIDES = 3

# El ciclo va SIEMPRE en este orden y el seguimiento va último, después del
# tratamiento (brand-and-compliance.md). Ojo: la plantilla `prob-03.html` del
# kit lo tiene mal ("Follow-up → Treatment"); manda el brand guide.
CHAIN = "Diagnóstico &rarr; Explicación &rarr; Tratamiento &rarr; Seguimiento"

CTAS_ES = [
    "¿Cómo lo ven en tu clínica?",
    "¿Te pasa lo mismo donde trabajás?",
    "¿Coincide con lo que ves a diario?",
    "¿Qué te parece que falta acá?",
]
CTAS_EN = [
    "How are you seeing this play out?",
    "Does this match what you see day to day?",
    "Curious what operators make of this.",
    "What do you think is missing here?",
]

# Caption: 2-4 líneas + 1 emoji dental + CTA + 4-6 hashtags (brand guide).
# Un solo emoji, siempre dental — la regla de "sin emoji" aplica al diseño de
# las slides, no al caption.
EMOJI = "🦷"
HASHTAGS = "#odontologia #saluddental #gestiondental #DSO #IAdental"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:48]


def _clip(text: str, limit: int) -> str:
    """Corta en el límite de oración más cercano, no a mitad de palabra."""
    text = (text or "").strip().rstrip(".")
    if not text:
        return ""
    if len(text) <= limit:
        return text + "."
    cut = text[:limit]
    for sep in (". ", "; ", ", "):
        i = cut.rfind(sep)
        if i > limit * 0.5:
            return cut[:i] + "."
    return cut[:cut.rfind(" ")] + "…"


def short_cite(cite: str) -> str:
    """Publisher + año. La página exacta vive en el slide y en la página web."""
    pub = cite.split(",")[0].strip()
    year = re.search(r"(20\d\d)", cite)
    return f"{pub}{' ' + year.group(1) if year else ''}"


def _tail(text: str) -> str:
    return ". ".join(s.strip() for s in text.split(".")[1:] if s.strip())


def generate(post: Post) -> PostSpec:
    """
    Un post de datos se construye sobre dos cifras; uno de posicionamiento,
    sobre mensajes aprobados. Exigirle cifras a un post que explica qué es
    la empresa era lo que obligaba a llenar el banco evergreen de estadísticas
    prestadas.
    """
    if post.kind == "evergreen":
        return _generate_evergreen(post)

    if len(post.facts) < 2:
        raise ValueError(
            f"'{post.id}' no tiene 2 hechos disponibles. Curar más en "
            f"data/facts.json o esperar el enfriamiento"
        )

    f1, f2 = post.facts[0], post.facts[1]
    hook = post.angle.split(".")[0].strip()
    hook_en = post.angle_en.split(".")[0].strip()
    rest = post.body or _tail(post.angle)
    rest_en = post.body_en or _tail(post.angle_en)

    # El CTA rota por hash del id: estable para el mismo post, distinto entre
    # posts. Evita que veinte publicaciones cierren con la misma frase.
    idx = sum(ord(c) for c in post.id) % len(CTAS_ES)

    citations = list(dict.fromkeys([f1["cite"], f2["cite"]]))
    sources = " · ".join(dict.fromkeys(short_cite(c) for c in citations))

    # 01 gancho (oscuro) · 02 datos (claro) · 03 cierre (oscuro)
    slides = [
        # El gancho lleva la cifra y el titular, sin el enunciado del hecho:
        # ese texto vuelve en la tarjeta del slide 2 y repetirlo dos frames
        # seguidos hace que el carrusel se sienta corto.
        Slide("hook", hook, kicker=post.family.replace("_", " "),
              stat=f1["number"], source=short_cite(f1["cite"])),
        # La segunda cifra va primera y destacada: la primera ya fue el número
        # grande del gancho, y repetirla como tarjeta inicial hacía que el
        # slide de datos pareciera el mismo frame otra vez.
        Slide("data", "Lo que dicen las cifras", kicker="En EE.UU.",
              stats=[Stat(f2["number"], _clip(f2["statement"], 120),
                          short_cite(f2["cite"])),
                     Stat(f1["number"], _clip(f1["statement"], 120),
                          short_cite(f1["cite"]))],
              body=_clip(rest, 240), source=f"Fuentes: {sources}"),
        Slide("close", "El dato describe el contexto.",
              accent="La decisión está en el flujo.",
              kicker="Qué implica", chain=CHAIN,
              body="Entre el hallazgo y el tratamiento terminado hay un "
                   "recorrido que casi nadie mide. La IA apoya, el "
                   "odontólogo decide."),
    ]

    caption_es = (
        f"{hook}. {EMOJI}\n\n"
        f"{f1['number']}: {_clip(f1['statement'], 150)}\n\n"
        f"{_clip(rest, 190)}\n\n"
        f"{CTAS_ES[idx]}\n\n"
        f"Cifras y fuentes en el carrusel. {sources}.\n\n"
        f"{HASHTAGS}"
    )

    commentary_en = (
        f"{hook_en}.\n\n"
        f"{f1.get('number_en', f1['number'])}: "
        f"{_clip(f1.get('statement_en') or f1['statement'], 150)}\n\n"
        f"{_clip(rest_en, 190)}\n\n"
        f"{CTAS_EN[idx]}\n\n"
        f"Figures and sources in the carousel. {sources}."
    )

    return PostSpec(
        slug=slugify(post.id),
        slides=slides,
        caption_es=caption_es.strip(),
        commentary_en=commentary_en.strip(),
        title_en=post.title,
        citations=citations,
        mode=post.kind,
        declarations={
            "has_source": True,
            "model_metrics_documented": False,
            "imagery_cleared": False,
            "pilots_verified": False,
            # Slides puramente tipográficos: no hay imagen de paciente que
            # de-identificar. Cambiar a False si se insertan imágenes clínicas.
            "no_patient_imagery": True,
        },
    )


def _generate_evergreen(post: Post) -> PostSpec:
    """
    Post de posicionamiento a partir de un bloque de mensajes.

    Estructura: mensaje aprobado como gancho · uno o dos mensajes más ·
    dato de contexto si el bloque lo trae · mensaje matizado · pregunta.
    Las cifras son opcionales y van como anclaje, nunca como el contenido.
    """
    hook = post.angle.split(".")[0].strip()
    hook_en = post.angle_en.split(".")[0].strip()
    idx = sum(ord(c) for c in post.id) % len(CTAS_ES)

    citations = [f["cite"] for f in post.facts]
    sources = " · ".join(dict.fromkeys(short_cite(c) for c in citations))
    tail = f"\n\nDato de contexto: {sources}." if sources else ""

    extra = post.messages[0] if post.messages else post.body
    stats = [Stat(f["number"], _clip(f["statement"], 120), short_cite(f["cite"]))
             for f in post.facts[:2]]

    # El frame del medio es SIEMPRE de rol `data`, tenga cifras o no. El rol
    # decide el fondo, y antes un bloque sin cifras caía en `close`: los tres
    # frames salían oscuros y se perdía la alternancia que pide el brand guide.
    # Nueve de los quince bloques no traen cifras, así que era el caso normal,
    # no el borde.
    puntos = [m for m in post.messages if m][:3]
    slides = [
        Slide("hook", hook, kicker=post.family.replace("_", " "),
              body=_clip(extra, 150)),
        Slide("data", "Lo que hacemos", kicker="DentRead",
              stats=stats, bullets=[] if stats else puntos,
              body=_clip(post.body, 200) if stats else "",
              source=f"Fuentes: {sources}" if sources else ""),
        Slide("close", "La IA apoya.", accent="El odontólogo decide.",
              kicker="Cómo trabajamos", chain=CHAIN,
              body=_clip(post.body, 220)),
    ]

    caption_es = (
        f"{hook}. {EMOJI}\n\n"
        f"{_clip(extra, 190)}\n\n"
        f"{_clip(post.body, 170)}\n\n"
        f"{CTAS_ES[idx]}{tail}\n\n"
        f"{HASHTAGS}"
    )
    commentary_en = (
        f"{hook_en}.\n\n"
        f"{_clip(post.messages_en[0], 190) if post.messages_en else _clip(post.body_en, 190)}\n\n"
        f"{_clip(post.body_en, 170)}\n\n"
        f"{CTAS_EN[idx]}"
        + (f"\n\nContext: {sources}." if sources else "")
    )

    assert len(slides) == N_SLIDES, f"evergreen armó {len(slides)} frames"
    return PostSpec(
        slug=slugify(post.id),
        slides=slides,
        caption_es=caption_es.strip(),
        commentary_en=commentary_en.strip(),
        title_en=post.title,
        citations=citations,
        mode="evergreen",
        declarations={
            "has_source": bool(citations),
            "model_metrics_documented": False,
            "regulatory_status_verified": False,
            "traction_verified": False,
            "head_to_head_study": False,
            "no_patient_imagery": True,
        },
    )
