"""
Generador: Post (plan) → PostSpec (slides + copy).

**Las cifras son deterministas. La prosa que las enmarca, no.**

La extracción de cifras desde texto de PDF se probó y se eliminó: producía
frases sin sentido ("142 of a total of 153 periapical lesions… 92.") que
pasaban los cuatro guards, porque los guards miden riesgo regulatorio y de
copyright, no si algo significa algo. La única defensa es que un humano haya
leído la cifra en su fuente. Por eso el CONTENIDO sale exclusivamente de
data/facts.json y acá no se genera un solo número.

Los titulares son otra cosa. Salían de partir el ángulo del tema en el primer
punto, así que el gancho era la tesis, y la tesis es justo lo que el frame 2 y
el cierre vuelven a decir con otras palabras: 14 de los 22 temas parafraseaban.
Eso sí lo escribe un modelo, y solo se usa si cruza los controles de
`pipeline/redaccion.py`. Si no hay token o la propuesta falla, se cae a la
versión curada del tema. Es el mismo trato que `summarize` le da a las
noticias y los papers.
"""
from __future__ import annotations

import re
import unicodedata

from pipeline import redaccion
from pipeline.plan import Post
from pipeline.spec import PostSpec, Slide, Stat

class SinMaterial(Exception):
    """
    Esta fuente no tiene con qué armar un post publicable hoy.

    No es un error: el ciclo lo espera y pasa a la fuente siguiente. Existe
    para que "no hay material" y "algo se rompió" no se traten igual, que es
    como salió publicada una noticia sin resumen, con el titular en inglés
    como único contenido.
    """


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

# Kickers por tipo de post. El kicker es la etiqueta chica de arriba a la
# izquierda: es lo primero que ubica al lector.
#
# `hook-writer.md` define cinco tipos de gancho y dice que el tipo tiene que
# corresponder al contenido: contraste e insight drop para datos, pregunta y
# confesión para lo propio. Los cuatro tipos de post usaban la misma
# plantilla, así que el gancho de un post sobre DentRead sonaba igual que uno
# de mercado. El kicker es donde esa diferencia se hace visible sin tocar el
# titular, que ya viene escrito y aprobado.
KICKERS = {
    "data": ("El dato", "En números", "Lo medido", "El contraste"),
    "evergreen": ("Cómo lo vemos", "Nuestra lectura", "En qué creemos"),
    "news": ("Novedad", "Lo que se movió", "En la industria"),
    "paper": ("Evidencia", "Qué se estudió", "Literatura"),
}


def kicker_para(kind: str, clave: str) -> str:
    """Rota dentro del tipo: dos posts seguidos no abren con la misma palabra."""
    opciones = KICKERS.get(kind) or KICKERS["data"]
    return opciones[sum(ord(c) for c in clave) % len(opciones)]


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
    # " y " y " ni " cierran una coordinación: cortar ahí deja una oración
    # entera en vez de un colgajo. Sin ellas, un enunciado con dos cláusulas
    # unidas por "y" terminaba en "…y del…", que es lo que se vio publicado.
    for sep in (". ", "; ", ", ", " y ", " ni "):
        i = cut.rfind(sep)
        if i > limit * 0.5:
            return cut[:i] + "."
    return cut[:cut.rfind(" ")] + "…"


def card_text(f: dict) -> str:
    """
    El texto que va en la tarjeta de cifra del frame 2.

    La tarjeta tiene lugar para unas 120 caracteres y 6 de los 21 hechos son
    más largos que eso. Recortarlos por código daba frases cortadas al medio
    ("…de lo que cobra el dentista y del…") o, con el corte por cláusula, una
    versión que perdía una de las dos cifras del titular. Por eso los hechos
    largos traen un campo `card` curado a mano: la misma afirmación, dicha
    corta, sin cifras que no estén en el enunciado completo. `verify` lo
    controla.
    """
    return _clip(f.get("card") or f["statement"], 120)


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

    # Gancho, titular de datos y lectura: los escribe el modelo a partir de las
    # dos cifras ya verificadas, y solo se usan si cruzan los controles de
    # `redaccion.verificar` —sin cifras inventadas, sin parafrasear el cierre,
    # sin claims—. Si no hay token o la propuesta no pasa, se usa la versión
    # curada del tema. Un post siempre sale.
    hook = (post.hook or post.angle.split(".")[0]).strip()
    data_title = post.data_title or "Lo que dicen las cifras"
    rest = post.body or _tail(post.angle)

    redactado = redaccion.redactar(
        tema=post.title, angulo=post.angle, hechos=[f1, f2],
        cierre=f"{post.close} {post.close_accent}")
    origen_redaccion = "curada"
    if redactado:
        hook = redactado["gancho"]
        data_title = redactado["titular_datos"]
        rest = redactado["lectura"]
        origen_redaccion = "modelo"
    hook_en = post.angle_en.split(".")[0].strip()
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
        # El frame 1 dice QUÉ ES su cifra, debajo del titular.
        #
        # Antes mostraba el número solo. Salió publicado un "5%" gigante sobre
        # "Cubrir no es lo mismo que pagar": el 5% mide cuántos beneficiarios
        # de Medicaid tienen además seguro privado, y el titular habla de
        # reembolsos. El lector veía una cifra huérfana y una frase que no la
        # explicaba. Con "38 estados" pasaba lo mismo.
        #
        # No se arregla escribiendo mejor el titular: el titular es del TEMA y
        # los hechos rotan, así que ninguna frase fija puede explicar una cifra
        # que cambia. Lo que explica la cifra es su propio enunciado.
        Slide("hook", hook, kicker=post.kicker or kicker_para("data", post.id),
              stat=f1["number"], body=card_text(f1),
              source=short_cite(f1["cite"])),
        # El frame 2 lleva UNA sola tarjeta, y es la de la segunda cifra.
        #
        # Antes llevaba las dos, así que el número del gancho aparecía dos
        # veces en tres frames: gigante en el 01 y otra vez como tarjeta en
        # el 02. Con solo dos hechos por post, mostrar los dos acá garantiza
        # esa repetición. El enunciado del hecho del gancho no se pierde: pasa
        # al cuerpo, que es donde tiene que estar —el frame 1 promete una
        # cifra, el 2 la explica y suma la que el lector todavía no vio.
        #
        # El titular del frame de datos sale del tema. Era "Lo que dicen las
        # cifras" en los doce: una etiqueta de sección, no una afirmación.
        Slide("data", data_title,
              kicker="En EE.UU.",
              stats=[Stat(f2["number"], card_text(f2), short_cite(f2["cite"]))],
              # Cada frame explica su propia cifra: el enunciado del hecho del
              # gancho ya está en el frame 1, así que acá va la lectura, que es
              # lo que une las dos.
              #
              # Se omite si repite el titular de este mismo frame. Con el
              # modelo eso no pasa —`lectura` se verifica contra el titular—,
              # pero por el camino curado `rest` es la segunda mitad del ángulo
              # del tema y suele ser una paráfrasis. Mejor un frame más corto
              # que uno que dice dos veces lo mismo.
              body="" if redaccion.solape(rest, data_title) >= redaccion.UMBRAL_SOLAPE
                   else _clip(rest, 200),
              source=f"Fuentes: {sources}"),
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
        redaccion=origen_redaccion,
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
    stats = [Stat(f["number"], card_text(f), short_cite(f["cite"]))
             for f in post.facts[:2]]

    # El frame del medio es SIEMPRE de rol `data`, tenga cifras o no. El rol
    # decide el fondo, y antes un bloque sin cifras caía en `close`: los tres
    # frames salían oscuros y se perdía la alternancia que pide el brand guide.
    # Nueve de los quince bloques no traen cifras, así que era el caso normal,
    # no el borde.
    puntos = [m for m in post.messages if m][:3]
    slides = [
        Slide("hook", hook, kicker=kicker_para("evergreen", post.id),
              body=_clip(extra, 150)),
        Slide("data", post.data_title or "Lo que hacemos", kicker="DentRead",
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

    # Resumen propio, escrito por el modelo y verificado contra copyright y
    # claims.
    from pipeline import summarize
    resumen = summarize.resumen_verificado(
        post.source_text, es_paper=not es_noticia, url=post.source_url,
        atribucion=etiqueta, es_reciente=post.es_reciente,
        publicado=post.publicado)

    # Sin resumen no hay post.
    #
    # Antes salía igual, en "formato señalizador": el frame 2 mostraba el
    # titular original entrecomillado y nada más. En inglés, en una cuenta en
    # español, sobre una nota que el lector no puede entender sin abrirla. Eso
    # no es un post más pobre, es un post vacío, y ocupa una de las tres
    # publicaciones de la semana.
    #
    # `SinMaterial` hace que el ciclo pase a la fuente siguiente, que es lo
    # mismo que ya pasa cuando ADA no publicó nada relevante.
    if not resumen:
        raise SinMaterial(
            f"'{post.id}': sin resumen verificado, no hay nada que contar "
            f"que el lector pueda leer en español")

    # Gancho y titular a partir de ESTE resumen.
    #
    # El gancho era `post.close`, una frase elegida por familia temática. Una
    # nota sobre un portal de credencialización abría con "El promedio del
    # país no es tu promedio": servía para cualquier noticia, o sea para
    # ninguna.
    titulares = redaccion.redactar_externo(
        titulo=titular, resumen=resumen,
        cierre=f"{post.close} {post.close_accent}")
    if not titulares:
        raise SinMaterial(f"'{post.id}': no se pudo redactar un gancho propio")

    # El titular original va entrecomillado al final, como cita con su fuente,
    # nunca como contenido principal.
    puntos = [linea.strip() for linea in resumen.split("\n") if linea.strip()]
    puntos.append(f"«{titular}»")

    slides = [
        Slide("hook", titulares["gancho"],
              kicker=kicker_para("news" if es_noticia else "paper", post.id),
              body=post.body, source=etiqueta),
        Slide("data", titulares["titular_datos"],
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
