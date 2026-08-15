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

# Puentes para la segunda línea del caption. La regla del brand guide es que
# el caption EXTIENDE el gancho, no lo resume: el lector ya leyó el frame 1,
# repetírselo lo hace irse. Estos conectores obligan a que la línea siguiente
# aporte algo, en vez de reformular. Rotan por hash del id.
PUENTES_ES = (
    "Lo que no se ve en la cifra:",
    "El detalle que cambia la lectura:",
    "Lo incómodo del dato:",
    "Lo que suele pasarse por alto:",
)
PUENTES_EN = (
    "What the number leaves out:",
    "The detail that changes the reading:",
    "The uncomfortable part:",
    "What usually gets missed:",
)


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
    # El cierre es del POST, no de su origen. Hoy lo llenan el catálogo de
    # temas y los bloques evergreen; mañana lo tendrá que llenar el artículo de
    # ADA News o el paper. Se exige acá para que ninguna fuente nueva pueda
    # publicar sin uno y caer otra vez en una frase genérica compartida.
    if not post.close:
        raise ValueError(
            f"'{post.id}' no trae cierre. Cada post lo define según su fuente: "
            f"el tema en pipeline/themes.py, el bloque en data/evergreen.json, "
            f"y una noticia o paper, a partir de su propio contenido."
        )

    if post.kind == "evergreen":
        return _generate_evergreen(post)
    if post.kind in ("news", "paper"):
        return _generate_externo(post)

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
        # El cierre sale del tema, no de una frase global. Antes los doce
        # posts de datos terminaban con la misma línea genérica.
        Slide("close", post.close, accent=post.close_accent,
              kicker="Qué implica", chain=CHAIN,
              body="La IA apoya, el odontólogo decide."),
    ]

    # El caption NO repite el gancho ni la cifra: los dos ya están en los
    # frames 1 y 2. Arranca por la implicación —el cierre del post, que es
    # lo único que el lector no vio todavía si no deslizó— y sigue con la
    # lectura del dato. Antes reproducía el slide 1 palabra por palabra.
    caption_es = (
        f"{post.close} {post.close_accent} {EMOJI}\n\n"
        f"{PUENTES_ES[idx]} {_clip(rest, 200)}\n\n"
        f"{CTAS_ES[idx]}\n\n"
        f"Las dos cifras y sus fuentes, en el carrusel. {sources}.\n\n"
        f"{HASHTAGS}"
    )

    commentary_en = (
        f"{hook_en}.\n\n"
        f"{PUENTES_EN[idx]} {_clip(rest_en, 200)}\n\n"
        f"{CTAS_EN[idx]}\n\n"
        f"Both figures and their sources are in the carousel. {sources}."
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
        Slide("close", post.close, accent=post.close_accent,
              kicker="Cómo trabajamos", chain=CHAIN,
              body=_clip(post.body, 220)),
    ]

    # Abre por el cierre, que es la idea que el lector no vio si no deslizó,
    # y sigue con el mensaje matizado. El gancho ya está en el frame 1.
    caption_es = (
        f"{post.close} {post.close_accent} {EMOJI}\n\n"
        f"{_clip(post.body or extra, 200)}\n\n"
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


def _generate_externo(post: Post) -> PostSpec:
    """
    Noticia de ADA News o estudio científico → PostSpec.

    Estos posts no llevan cifras propias: llevan el tema, el encuadre y la
    fuente. La regla que los separa del resto es que **no publican
    conclusiones**. De una noticia sale el tema; de un paper, qué se preguntó
    y con qué diseño. Nunca qué se encontró: un hallazgo suelto en un carrusel
    es un claim clínico con la cita de otro.

    **El titular original va entrecomillado, no como titular del slide.** ADA
    News y PubMed publican en inglés, y la cuenta de Instagram es en español.
    Poner el título en inglés a 88 px en el primer frame se ve como un error
    de traducción, no como una cita. Acá el frame 1 abre con texto propio en
    español y el título original aparece entre comillas en el frame 2, que es
    donde corresponde citarlo con su fuente.
    """
    idx = sum(ord(c) for c in post.id) % len(CTAS_ES)
    etiqueta = post.source_label or "Fuente"
    titular = post.angle.strip().rstrip(".")
    es_noticia = post.kind == "news"

    # Gancho en español, propio. Para una noticia, el encuadre; para un
    # paper, la pregunta enmarcada.
    gancho = post.close if es_noticia else "Qué se está estudiando"
    acento = post.close_accent if es_noticia else ""

    # Resumen propio, escrito por el modelo y verificado contra copyright y
    # claims. Si no pasa —o no hay token, o la API falló— el post sale con el
    # formato señalizador de siempre. El peor caso es un post más pobre, nunca
    # uno con texto sin verificar.
    from pipeline import summarize
    resumen = summarize.resumen_verificado(
        post.source_text, es_paper=not es_noticia, url=post.source_url,
        atribucion=etiqueta, es_reciente=post.es_reciente,
        publicado=post.publicado)

    puntos = []
    if resumen:
        puntos += [linea.strip() for linea in resumen.split("\n") if linea.strip()]
    puntos.append(f"«{titular}»")
    if not resumen and post.messages and post.messages[0] != titular:
        puntos.insert(0, _clip(post.messages[0], 170))

    slides = [
        Slide("hook", gancho, accent=acento,
              kicker="ADA News" if es_noticia else "Evidencia",
              body=post.body, source=etiqueta),
        Slide("data",
              "Lo que se publicó" if es_noticia else "Qué se preguntó",
              kicker=etiqueta, bullets=puntos,
              body="Título original, en inglés." if es_noticia else "",
              source=f"Fuente: {etiqueta}"),
        Slide("close", post.close if not es_noticia else "La IA apoya.",
              accent=post.close_accent if not es_noticia else "El odontólogo decide.",
              kicker="Cómo lo leemos", chain=CHAIN,
              body=""),
    ]

    cuerpo = resumen if resumen else post.body
    caption_es = (
        f"{post.close} {post.close_accent} {EMOJI}\n\n"
        f"{cuerpo}\n\n"
        f"{post.body if resumen else ''}"
        f"{'' if not resumen else chr(10) + chr(10)}"
        f"{CTAS_ES[idx]}\n\n"
        f"Fuente: {etiqueta}. Enlace en el perfil.\n\n"
        f"{HASHTAGS}"
    )
    commentary_en = (
        f"{titular}.\n\n{post.body}\n\n"
        f"{CTAS_EN[idx]}\n\nSource: {etiqueta}."
    )

    return PostSpec(
        slug=slugify(post.id),
        slides=slides,
        caption_es=caption_es.strip(),
        commentary_en=commentary_en.strip(),
        title_en=post.title,
        citations=[f"{etiqueta} — {post.source_url}" if post.source_url else etiqueta],
        mode=post.kind,
        declarations={
            "has_source": True,
            "model_metrics_documented": False,
            "regulatory_status_verified": False,
            "traction_verified": False,
            "head_to_head_study": False,
            "no_patient_imagery": True,
            # Se señaliza, no se concluye: ningún resultado del estudio ni
            # del artículo entra en el texto publicado.
            "findings_withheld": True,
        },
    )
