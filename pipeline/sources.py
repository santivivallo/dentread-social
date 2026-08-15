"""
ADA News y literatura científica como fuentes de post.

Los dos módulos existían desde el principio y nunca estuvieron enchufados al
camino de publicación: el sistema rotaba sobre 21 hechos curados y 15 bloques
y la cobertura no crecía. Esto los conecta.

Las dos fuentes entran **intercaladas** con las otras, no cuando las otras se
agotan. Ver `CICLO` en pipeline/plan.py: un lector no debería poder anticipar
de qué va el post por el día de la semana, y esperar a que un pozo se seque
para abrir otro deja huecos justo cuando el inventario está bajo.

Las dos llevan un resumen propio, escrito y verificado en `pipeline/summarize`.

- **Noticia**: qué pasó y a quién le cambia algo, con palabras propias. El
  límite es copyright, y lo mide `publisher/newsguard`.
- **Paper**: qué se preguntó, con qué diseño y qué reportó, siempre atribuido
  al estudio. Con una excepción: si el estudio mide **rendimiento diagnóstico
  de IA**, solo se señaliza. Un resultado de precisión publicado en la cuenta
  de una empresa de IA para radiografías no se lee como cita ajena, se lee
  como claim propio, y DentRead no tiene FDA clearance para sostenerlo.
"""
from __future__ import annotations

from pipeline.plan import Post

# Cierres por familia temática de la noticia. Son varios por familia para que
# dos noticias del mismo tipo no cierren igual; se elige por hash estable del
# identificador, así el mismo artículo siempre da el mismo cierre.
CIERRES_NOTICIA: dict[str, list[tuple[str, str]]] = {
    "datos": [
        ("Un dato del sector no cambia una agenda.",
         "Cambia qué preguntar en la reunión del lunes."),
        ("El promedio del país no es tu promedio.",
         "Medí el tuyo antes de compararte."),
        ("La cifra describe. No decide.",
         "La decisión sigue siendo de quien atiende."),
    ],
    "ai": [
        ("La herramienta se adopta rápido.",
         "El flujo alrededor tarda mucho más."),
        ("La discusión ya no es si la IA sirve.",
         "Es qué queda registrado cuando se usa."),
        ("Automatizar una lectura es lo fácil.",
         "Lo difícil es que alguien actúe sobre ella."),
    ],
    "workflow": [
        ("El proceso se cambia una vez.",
         "Se sostiene todas las semanas."),
        ("Nadie cambia un flujo por una demo.",
         "Lo cambia por una cifra propia."),
    ],
    "clinica": [
        ("El hallazgo clínico es el principio del recorrido.",
         "El final es un tratamiento terminado."),
        ("La evidencia clínica avanza despacio.",
         "El flujo que la aplica, más despacio todavía."),
    ],
}

# Cierres por diseño de estudio. El diseño es lo que se puede decir sin entrar
# en resultados, así que el cierre habla de cuánto peso tiene la pregunta.
CIERRES_PAPER: dict[str, tuple[str, str]] = {
    "ensayo aleatorizado": ("Un ensayo responde una pregunta acotada.",
                            "Sirve para saber qué mirar, no qué comprar."),
    "revisión sistemática": ("Una revisión ordena lo que ya se sabía.",
                             "Ahí se ve qué sigue sin estudiarse."),
    "metaanálisis": ("Juntar estudios reduce el ruido.",
                     "No convierte una señal débil en certeza."),
    "estudio multicéntrico": ("Varios centros, un mismo protocolo.",
                              "Es lo más cerca de la práctica real."),
    "estudio observacional": ("Observar no es demostrar.",
                              "Alcanza para decidir qué medir después."),
    "estudio comparativo": ("Comparar dos caminos aclara el propio.",
                            "Aunque ninguno de los dos sea el tuyo."),
}

FALLBACK = ("La literatura marca la dirección.",
            "La decisión clínica sigue siendo de quien atiende.")


def _pick(opciones: list[tuple[str, str]], clave: str) -> tuple[str, str]:
    """Elección estable: el mismo artículo siempre da el mismo cierre."""
    return opciones[sum(ord(c) for c in clave) % len(opciones)]


def post_from_article(article) -> Post:
    """
    Noticia de ADA News → Post.

    El encuadre depende de `is_fresh`. Un artículo del stock de 2026 no puede
    presentarse como novedad: `newsguard` bloquea "nuevo" o "esta semana" si
    la nota no es reciente, y con razón — publicar un artículo de marzo como
    si fuera de esta semana es un error de credibilidad barato de evitar.
    """
    familia = next((b for b in article.buckets if b in CIERRES_NOTICIA), "datos")
    close, accent = _pick(CIERRES_NOTICIA[familia], article.url)

    marco = ("Publicado esta semana en ADA News."
             if article.is_fresh
             else f"Publicado en ADA News el {article.published[:10]}.")

    return Post(
        kind="news",
        id=f"news-{abs(hash(article.url)) % 10**8}",
        title=article.title,
        audience="es",
        angle=article.title.rstrip("."),
        angle_en=article.title.rstrip("."),
        family=familia,
        body=marco,
        messages=[article.summary] if article.summary else [],
        close=close,
        close_accent=accent,
        source_url=article.url,
        source_label=f"ADA News · {article.category}" if article.category else "ADA News",
        source_text=f"{article.title}. {article.summary} {article.body}".strip(),
        es_reciente=article.is_fresh,
        publicado=article.published,
    )


def post_from_signpost(sp) -> Post:
    """
    Estudio → Post señalizador: qué se preguntó y con qué diseño.

    Nunca el resultado. `journals.FORBIDDEN` descarta cualquier título que ya
    traiga la conclusión adentro, porque un hallazgo suelto en un carrusel es
    un claim clínico con la cita de otro.
    """
    close, accent = CIERRES_PAPER.get(sp.design_es, FALLBACK)
    detalle = sp.design_es or "estudio"
    if sp.n:
        detalle += f", {sp.n} participantes"

    return Post(
        kind="paper",
        id=f"paper-{sp.pmid}",
        title=sp.title,
        audience="es",
        angle=sp.question_es(),
        angle_en=sp.question_es(),
        family="evidencia",
        body=f"{detalle.capitalize()}. Publicado en {sp.journal}, {sp.year}.",
        messages=[f"Qué se preguntó: {sp.question_es()}."],
        close=close,
        close_accent=accent,
        source_url=sp.url,
        source_label=f"{sp.journal} {sp.year}",
        source_text=f"{sp.title}. {getattr(sp, 'abstract', '')}".strip(),
    )
