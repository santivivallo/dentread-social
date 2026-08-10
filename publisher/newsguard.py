"""
News guard — controles obligatorios cuando el carrusel se deriva de una
fuente de terceros (ADA News y similares).

Publicar automáticamente contenido derivado sin revisión humana concentra
tres riesgos que el guard de claims no cubre:

  1. Copyright   — reproducir texto del artículo original.
  2. Marca       — usar "ADA" de forma que sugiera respaldo o afiliación.
  3. Credibilidad — publicar un resumen sin aporte propio.

Este módulo los convierte en checks mecánicos. No es asesoría legal.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Máxima cantidad de palabras consecutivas que pueden coincidir con la fuente.
# Por encima de esto deja de ser paráfrasis.
MAX_SHARED_NGRAM = 7

# Una cita textual está permitida si es corta y va entrecomillada.
MAX_QUOTE_WORDS = 15
MAX_QUOTES = 1

# Proporción mínima del copy que debe ser aporte propio de DentRead.
MIN_ORIGINAL_RATIO = 0.60

# Solapamiento léxico total máximo con la fuente.
MAX_LEXICAL_OVERLAP = 0.35


# --------------------------------------------------------------------------
# Marca y afiliación
# --------------------------------------------------------------------------

TRADEMARK_RULES: list[tuple[str, str, str]] = [
    (r"\bADA[\s-]?(approved|aprobad[oa]|endorsed|respaldad[oa]|certified|certificad[oa])",
     "Sugiere aprobación de la ADA. 'ADA Accepted' y el Seal son marcas registradas "
     "con un proceso formal que DentRead no atravesó.",
     "Eliminar. No existe redacción segura de esto."),

    (r"\bADA\s+Seal( of Acceptance)?\b",
     "El ADA Seal of Acceptance es una marca registrada con proceso propio.",
     "No mencionar salvo que se esté describiendo el programa en tercera persona."),

    (r"\b(in partnership with|partnered with|together with|junto a|en alianza con|"
     r"en colaboración con)\s+(the\s+)?ADA\b",
     "Afirma una relación institucional inexistente.",
     "Eliminar."),

    (r"\bADA\s+(recommends?|recomienda|says|dice)\s+(DentRead|us|nosotros)",
     "Atribuye a la ADA una declaración sobre DentRead.",
     "Eliminar."),

    (r"\b(we are|somos|DentRead is)\s+(an?\s+)?ADA\b",
     "Se autoadscribe a la ADA.",
     "Eliminar."),

    (r"\bmember of the ADA\b(?!\s+community)",
     "Membresía institucional: verificable y fácil de desmentir.",
     "Solo si es literalmente cierto y relevante."),
]

# Frases de atribución aceptables. Al menos una debe estar presente.
# Vocabulario de novedad. Aceptable en un artículo de esta semana; falso en
# uno de febrero. El stock de 2026 es material válido, pero enmarcado como
# contexto con su fecha, nunca como "nuevo".
RECENCY_WORDS = re.compile(
    r"\b(nuevo|nueva|reciente|recientemente|esta semana|este mes|acaba de|"
    r"acaban de|ú?ltim[oa]s?\s+(noticia|hora|d[íi]as)|ahora mismo|"
    r"new|newly|just\s+(announced|released|published)|this week|this month|"
    r"breaking|latest|recently|has\s+just)\b",
    re.I,
)

ATTRIBUTION_PATTERNS = [
    # "Vía" con tilde es la forma normal en español y no matcheaba: bloqueaba
    # todo el copy en castellano por falta de atribución que sí estaba.
    r"\b(v[íi]a|seg[úu]n|fuente|source|reported by|reportado por|informa|per)"
    r"\s*:?\s*ADA\s?News\b",
    r"\bADA\s?News\s*[:,]?\s*(reports?|reporta|inform[óo]|reported|dice)?\b",
    r"adanews\.ada\.org",
]

# Palabras vacías que no cuentan para el solapamiento léxico.
STOPWORDS = set("""
the a an and or but of to in on for with by from as at is are was were be been
being that this these those it its their his her our your my we you they he she
not no nor so if then than when while which who whom what where how all any both
each few more most other some such only own same too very can will just should now
el la los las un una unos unas y o pero de del a en para con por como que se su sus
es son fue fueron ser sido siendo este esta estos estas lo le les nos te me mi tu
no ni si entonces cuando mientras cual quien donde como todo todos alguna algunos
más muy solo mismo también ya hay han ha
""".split())


@dataclass
class NewsFinding:
    level: str
    rule: str
    detail: str
    why: str
    fix: str

    def __str__(self) -> str:
        return (f"  {self.level:<6} {self.rule:<20} {self.detail}\n"
                f"         por qué: {self.why}\n"
                f"         arreglo: {self.fix}")


@dataclass
class NewsResult:
    ok: bool
    findings: list[NewsFinding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def report(self) -> str:
        head = (f"  stats: solapamiento léxico {self.stats.get('overlap', 0):.0%} · "
                f"n-grama compartido más largo {self.stats.get('longest_ngram', 0)} palabras · "
                f"original {self.stats.get('original_ratio', 0):.0%}")
        body = "\n".join(str(f) for f in self.findings) or "  sin hallazgos"
        return f"{head}\n{body}"


# --------------------------------------------------------------------------

def _norm(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", text)


def _ngrams(words: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def _longest_shared_ngram(a: list[str], b: list[str], cap: int = 30) -> int:
    """Longitud del n-grama más largo que comparten (búsqueda binaria)."""
    lo, hi, best = 1, min(cap, len(a), len(b)), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if _ngrams(a, mid) & _ngrams(b, mid):
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    return best


def _quotes(text: str) -> list[str]:
    return re.findall(r"[\"“”«»]([^\"“”«»]{3,})[\"“”«»]", text)


def check_derived(post_text: str, source_text: str, source_url: str = "",
                  *, is_fresh: bool = True, published: str = "") -> NewsResult:
    """
    post_text   copy que se va a publicar
    source_text cuerpo del artículo original
    is_fresh    False si el artículo viene del stock del año y no es novedad
    """
    findings: list[NewsFinding] = []

    # ---- 0. Novedad falsa -------------------------------------------------
    if not is_fresh:
        for m in RECENCY_WORDS.finditer(post_text):
            findings.append(NewsFinding(
                "BLOCK", "recency.false",
                f"“{m.group(0)}” sobre un artículo de {published or 'meses atrás'}",
                "Presentar material del archivo como novedad es inexacto y se "
                "verifica en un clic: el artículo tiene fecha visible.",
                "Enmarcalo con su fecha: «en febrero la ADA pidió…». El stock "
                "sirve como contexto, no como primicia.",
            ))
            break
    pw, sw = _norm(post_text), _norm(source_text)

    # ---- 1. Reproducción literal ----------------------------------------
    longest = _longest_shared_ngram(pw, sw) if pw and sw else 0
    if longest > MAX_SHARED_NGRAM:
        findings.append(NewsFinding(
            "BLOCK", "copyright.verbatim",
            f"{longest} palabras consecutivas idénticas a la fuente",
            "Por encima de ~7 palabras seguidas deja de ser paráfrasis y pasa a "
            "ser reproducción.",
            "Reescribí con tus propias palabras o entrecomillá y atribuí una cita corta.",
        ))

    # ---- 2. Solapamiento léxico global ----------------------------------
    p_set = {w for w in pw if w not in STOPWORDS}
    s_set = {w for w in sw if w not in STOPWORDS}
    overlap = len(p_set & s_set) / len(p_set) if p_set else 0.0
    if overlap > MAX_LEXICAL_OVERLAP:
        findings.append(NewsFinding(
            "REVIEW", "copyright.overlap",
            f"{overlap:.0%} del vocabulario del post viene de la fuente",
            "Solapamiento alto indica resumen cercano, no comentario propio.",
            "Agregá análisis de DentRead y recortá el recuento de la noticia.",
        ))

    original_ratio = 1.0 - overlap
    if original_ratio < MIN_ORIGINAL_RATIO:
        findings.append(NewsFinding(
            "BLOCK", "quality.original",
            f"solo {original_ratio:.0%} de aporte propio (mínimo {MIN_ORIGINAL_RATIO:.0%})",
            "Un carrusel que reformula la noticia no dice nada que la fuente no "
            "haya dicho mejor. Publicarlo resta credibilidad.",
            "El post debe responder 'y esto qué significa para una clínica'.",
        ))

    # ---- 3. Citas --------------------------------------------------------
    qs = _quotes(post_text)
    if len(qs) > MAX_QUOTES:
        findings.append(NewsFinding(
            "BLOCK", "copyright.quotes",
            f"{len(qs)} citas textuales (máximo {MAX_QUOTES})",
            "Varias citas de una misma fuente acumulan reproducción.",
            "Dejá una sola cita corta.",
        ))
    for q in qs:
        n = len(q.split())
        if n > MAX_QUOTE_WORDS:
            findings.append(NewsFinding(
                "BLOCK", "copyright.quotelen",
                f"cita de {n} palabras (máximo {MAX_QUOTE_WORDS})",
                "Cita larga = reproducción sustancial.",
                "Acortala o parafraseala.",
            ))

    # ---- 4. Atribución obligatoria --------------------------------------
    has_attr = any(re.search(p, post_text, re.I) for p in ATTRIBUTION_PATTERNS)
    if not has_attr:
        findings.append(NewsFinding(
            "BLOCK", "attribution.missing",
            "el post no atribuye la fuente",
            "Publicar contenido derivado sin crédito es lo que convierte una "
            "paráfrasis discutible en un problema.",
            f"Agregá 'Source: ADA News' + link ({source_url or 'adanews.ada.org'}).",
        ))

    # ---- 5. Marca y afiliación -------------------------------------------
    for pattern, why, fix in TRADEMARK_RULES:
        m = re.search(pattern, post_text, re.I)
        if m:
            findings.append(NewsFinding(
                "BLOCK", "trademark", f"“{m.group(0).strip()}”", why, fix,
            ))

    # ---- 6. Imágenes de la fuente ----------------------------------------
    if re.search(r"adanews\.ada\.org/media/|ada\.org/-/media/", post_text, re.I):
        findings.append(NewsFinding(
            "BLOCK", "copyright.image",
            "referencia a una imagen alojada por la ADA",
            "Las imágenes del artículo tienen su propia licencia y no están "
            "cubiertas por ningún uso justo del texto.",
            "Usá arte propio de DentRead. Nunca reutilices la imagen del artículo.",
        ))

    ok = not any(f.level in ("BLOCK", "REVIEW") for f in findings)
    return NewsResult(ok=ok, findings=findings, stats={
        "overlap": overlap,
        "longest_ngram": longest,
        "original_ratio": original_ratio,
        "quotes": len(qs),
        "attributed": has_attr,
    })
