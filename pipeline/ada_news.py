"""
Ingesta de ADA News.

Reglas duras de este módulo:
  - Excluye todo lo patrocinado (`isSponsored`, /ada-pubplus/). Republicar
    contenido pagado de otro como si fuera noticia es un problema aparte.
  - Nunca descarga ni referencia imágenes de la ADA.
  - Guarda el cuerpo del artículo SOLO para que `newsguard` pueda medir
    solapamiento. No se publica, no se cachea más allá de la corrida.
  - Un fetch cada 1.5 s, User-Agent identificable, y respeta el estado
    previo para no releer lo ya visto.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = "https://adanews.ada.org"
LISTING = f"{BASE}/latest-news/?page={{page}}"
UA = "DentReadNewsBot/1.0 (+https://dentread.com; contact@dentread.com)"
DELAY = 1.5
ARTICLE_RE = re.compile(r"/ada-news/(\d{4})/([a-z]+)/([a-z0-9-]+)/?$", re.I)
STATE = Path("data/seen_articles.json")

# --- Relevancia: "ambos, con IA priorizada" -------------------------------
# El score es la suma de pesos de los términos presentes en título+bajada.
TOPIC_WEIGHTS: dict[str, tuple[float, str]] = {
    # IA y odontología digital — prioridad alta
    r"\b(artificial intelligence|\bAI\b|machine learning|algorithm)": (5.0, "ai"),
    r"\b(radiograph|radiology|imaging|x-ray|CBCT)": (4.5, "ai"),
    r"\b(digital dentistry|software|platform|technology|digitali)": (3.0, "ai"),
    r"\b(FDA|clearance|510\(k\)|device regulation|SaMD)": (4.0, "ai"),
    r"\b(data privacy|privacy|HIPAA|cybersecurity|interoperab)": (3.0, "ai"),

    # Workflow, pagadores, case acceptance — prioridad media
    r"\b(treatment plan|case acceptance|treatment acceptance)": (4.0, "workflow"),
    r"\b(claim|denial|denied|downcod|reimbursement|EOB|coding|CDT)": (3.5, "workflow"),
    # Los adjuntos de reclamo SON radiografías: ángulo directo de DentRead.
    r"\b(attachment|documentation requirement|narrative|prior auth)": (4.0, "workflow"),
    r"\b(insurance|payer|Aetna|Delta Dental|carrier|transparen)": (3.0, "workflow"),
    r"\b(Medicaid|CMS|Medicare|CHIP|coverage|benefit)": (2.5, "workflow"),
    r"\b(DSO|group practice|practice management|workflow|productivity)": (3.5, "workflow"),
    r"\b(credentialing|administrative burden|staffing|workforce)": (2.5, "workflow"),
    r"\b(patient communication|recall|follow-up|no-show|treatment plan)": (4.0, "workflow"),
    r"\b(standard|interoperab|prior authorization|utilization review)": (3.0, "workflow"),

    # Odontología, mercado, tendencias y datos — el grueso del contenido.
    # El foco no es solo IA: estos temas son los que el corpus sostiene mejor.
    r"\b(survey|study|report|data|statistics|findings|HPI|Health Policy Institute)":
        (3.5, "datos"),
    r"\b(access to care|underserved|disparit|barrier|uninsured|out-of-pocket)":
        (3.5, "datos"),
    r"\b(utilization|visits?|patients? seen|appointment|demand)": (3.0, "datos"),
    r"\b(economy|economic|revenue|spending|expenditure|cost of care|inflation)":
        (3.0, "datos"),
    r"\b(trend|outlook|forecast|growth|market)": (2.5, "datos"),
    r"\b(oral health|periodontal|caries|preventive|prevention|hygiene)":
        (2.5, "clinica"),
    r"\b(children|pediatric|older adults|seniors|geriatric)": (2.5, "clinica"),
    r"\b(dental school|education|graduate|student debt|training)": (2.0, "clinica"),
    r"\b(teledentistry|remote|virtual care)": (3.0, "ai"),
}

# Familias que pueden abrir un post. Sin al menos una, el artículo no tiene
# ángulo aunque acumule puntaje por términos sueltos.
REQUIRED_BUCKETS = {"ai", "workflow", "datos", "clinica"}

# Temas sin ángulo posible para DentRead: se descartan aunque puntúen.
# Temas sin ángulo posible: vida institucional de la ADA y notas de color.
# Ojo: acá NO van los temas clínicos ni de mercado — esos ahora sí puntúan.
EXCLUDE = re.compile(
    r"\b(plaque returns|historic|obituary|in memoriam|dies at|scholarship winner|"
    r"award recipient|golf|anniversary|election results|house of delegates|"
    r"governance|volunteers for|preorder|impact factor|bancorp|acquires ADA)\b",
    re.I,
)

# Calibrado contra 20 titulares reales de ADA News (ago 2026).
# MIN_SCORE es un piso, no el selector: el selector real es `limit` sobre el
# ranking. Con 3.5 pasan ~35% y solo ~15% superan 5.0.
# Traducción: la oferta de noticias verdaderamente relevantes es de 3-4 por
# semana. Eso limita la cadencia sostenible a ~2 posts/semana, no el código.
MIN_SCORE = 3.5


@dataclass
class Article:
    url: str
    title: str
    summary: str
    category: str
    published: str
    author: str
    score: float = 0.0
    buckets: list[str] = field(default_factory=list)
    body: str = ""          # solo en memoria, para newsguard
    # False = viene del stock de 2026, no es novedad. Cambia cómo se redacta:
    # se enmarca como contexto con su fecha, nunca como "nuevo" o "esta semana".
    is_fresh: bool = True

    def to_public(self) -> dict:
        d = asdict(self)
        d.pop("body")
        return d


def _get(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    time.sleep(DELAY)
    return r.text


def _meta(html: str, name: str) -> str:
    m = re.search(
        rf'<meta[^>]+(?:name|property)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)',
        html, re.I,
    )
    if m:
        return m.group(1).strip()
    m = re.search(
        rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:name|property)=["\']{re.escape(name)}["\']',
        html, re.I,
    )
    return m.group(1).strip() if m else ""


def _strip_html(html: str) -> str:
    body = re.search(r"<article[^>]*>(.*?)</article>", html, re.S | re.I)
    chunk = body.group(1) if body else html
    chunk = re.sub(r"<(script|style|nav|aside|figure)[^>]*>.*?</\1>", " ", chunk, flags=re.S | re.I)
    chunk = re.sub(r"<[^>]+>", " ", chunk)
    chunk = re.sub(r"&nbsp;?", " ", chunk)
    return re.sub(r"\s+", " ", chunk).strip()


def discover(pages: int = 2) -> list[str]:
    urls: list[str] = []
    for p in range(1, pages + 1):
        try:
            html = _get(LISTING.format(page=p))
        except requests.RequestException:
            break
        for href in re.findall(r'href=["\']([^"\']+)["\']', html):
            full = urljoin(BASE, href)
            if ARTICLE_RE.search(full) and "/ada-pubplus/" not in full:
                if full not in urls:
                    urls.append(full)
    return urls


def fetch_article(url: str) -> Article | None:
    html = _get(url)
    if _meta(html, "isSponsored").lower() == "true":
        return None
    title = _meta(html, "og:title") or _meta(html, "twitter:title")
    if not title:
        return None
    return Article(
        url=url,
        title=title,
        summary=_meta(html, "description"),
        category=_meta(html, "category") or "",
        published=_meta(html, "publicationDate") or _meta(html, "datePublished"),
        author=_meta(html, "creator"),
        body=_strip_html(html),
    )


def score(article: Article) -> Article:
    haystack = f"{article.title} {article.summary} {article.category}"
    if EXCLUDE.search(haystack):
        article.score = 0.0
        return article
    total, buckets = 0.0, set()
    for pattern, (weight, bucket) in TOPIC_WEIGHTS.items():
        if re.search(pattern, haystack, re.I):
            total += weight
            buckets.add(bucket)
    if not buckets & REQUIRED_BUCKETS:
        article.score = 0.0
        return article
    if "ai" in buckets:
        total *= 1.25            # IA priorizada dentro de un alcance amplio
    article.score = round(total, 2)
    article.buckets = sorted(buckets)
    return article


# --------------------------------------------------------------------------
# Archivo acumulativo
# --------------------------------------------------------------------------
# La cobertura tiene que crecer semana a semana, no quedarse en las dos
# primeras páginas del listado. Cada corrida:
#   1. escanea más profundo que la anterior, hasta MAX_PAGES
#   2. registra TODO lo que ve, con su score, aunque no se publique
#   3. nunca vuelve a proponer algo ya publicado
#
# El archivo es además el registro de por qué NO se publicó algo, que es la
# única forma de darse cuenta de que el scorer está mal calibrado.

ARCHIVE = Path("data/ada_archive.json")
BASE_PAGES = 2
MAX_PAGES = 12
PAGES_GROWTH_PER_RUN = 1


def _empty_archive() -> dict:
    return {"articles": {}, "weeks": {}, "runs": 0, "deepest_page": 0}


def load_archive() -> dict:
    if ARCHIVE.exists():
        return {**_empty_archive(), **json.loads(ARCHIVE.read_text())}
    return _empty_archive()


def save_archive(arch: dict) -> None:
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVE.write_text(json.dumps(arch, indent=1, ensure_ascii=False))


def pages_for_run(arch: dict) -> int:
    """Cada corrida entra un poco más hondo en el histórico."""
    return min(MAX_PAGES, BASE_PAGES + arch.get("runs", 0) * PAGES_GROWTH_PER_RUN)


def _load_seen() -> set[str]:
    """Publicados: no se vuelven a proponer."""
    arch = load_archive()
    return {u for u, a in arch["articles"].items() if a.get("used")}


def _save_seen(urls: set[str], keep: int = 0) -> None:   # compat
    arch = load_archive()
    for u in urls:
        arch["articles"].setdefault(u, {}).update({"used": True})
    save_archive(arch)


# Un artículo de hace más de 21 días ya no es noticia. Pero sigue siendo
# material válido si se enmarca como contexto en vez de como novedad.
# Medido sobre 20 titulares reales de ene-mar 2026: el 50% supera el piso de
# relevancia. Proyectado a los ~150 artículos de 2026, son ~75 en stock.
FRESH_DAYS = 21


def _age_days(published: str) -> int:
    try:
        return (date.today() - datetime.fromisoformat(str(published)[:10]).date()).days
    except (ValueError, TypeError):
        return 10_000


def latest_relevant(
    *, pages: int | None = None, max_age_days: int = 21, limit: int = 5,
    skip_seen: bool = True,
) -> list[Article]:
    """
    Escanea, archiva todo lo que ve y devuelve los candidatos publicables.

    `pages=None` usa la profundidad progresiva: cada corrida entra una página
    más que la anterior, hasta MAX_PAGES. Así el archivo se completa hacia
    atrás mientras el pipeline sigue funcionando hacia adelante.
    """
    arch = load_archive()
    depth = pages if pages is not None else pages_for_run(arch)
    week = date.today().strftime("%G-W%V")
    seen_used = {u for u, a in arch["articles"].items() if a.get("used")}
    cutoff = date.today() - timedelta(days=max_age_days)

    candidates: list[Article] = []
    new_this_run: list[str] = []

    for url in discover(depth):
        known = arch["articles"].get(url)
        if known and not known.get("needs_refetch"):
            record = known
        else:
            try:
                art = fetch_article(url)
            except requests.RequestException:
                continue
            if art is None:                       # patrocinado o sin título
                arch["articles"][url] = {"skipped": "sponsored",
                                         "first_seen": week}
                continue
            art = score(art)
            record = {
                "title": art.title, "published": art.published,
                "category": art.category, "score": art.score,
                "buckets": art.buckets, "first_seen": week,
            }
            arch["articles"][url] = record
            new_this_run.append(url)

        if url in seen_used or record.get("skipped"):
            continue
        if record.get("score", 0) < MIN_SCORE:
            continue
        try:
            if datetime.fromisoformat(str(record.get("published"))[:10]).date() < cutoff:
                continue
        except (ValueError, TypeError):
            pass

        art = Article(
            url=url, title=record["title"], summary="",
            category=record.get("category", ""),
            published=record.get("published", ""), author="",
            score=record.get("score", 0.0), buckets=record.get("buckets", []),
        )
        art.is_fresh = _age_days(record.get("published", "")) <= FRESH_DAYS
        candidates.append(art)

    arch["runs"] = arch.get("runs", 0) + 1
    arch["deepest_page"] = max(arch.get("deepest_page", 0), depth)
    arch["weeks"].setdefault(week, [])
    arch["weeks"][week] = sorted(set(arch["weeks"][week]) | set(new_this_run))
    save_archive(arch)

    print(f"[ada] profundidad {depth} págs · {len(new_this_run)} artículos "
          f"nuevos · {len(arch['articles'])} en archivo · "
          f"{len(candidates)} candidatos")

    candidates.sort(key=lambda a: a.score, reverse=True)
    return candidates[:limit]


def mark_published(url: str) -> None:
    arch = load_archive()
    arch["articles"].setdefault(url, {})["used"] = True
    save_archive(arch)


def coverage_report() -> str:
    arch = load_archive()
    arts = arch["articles"]
    scored = [a for a in arts.values() if "score" in a]
    passing = [a for a in scored if a["score"] >= MIN_SCORE]
    lines = [
        f"archivo: {len(arts)} artículos · {len(arch['weeks'])} semanas · "
        f"profundidad máxima alcanzada: {arch.get('deepest_page', 0)} págs "
        f"de {MAX_PAGES}",
        f"pasan el piso de relevancia: {len(passing)}/{len(scored)}"
        + (f" ({len(passing)/len(scored):.0%})" if scored else ""),
        f"ya publicados por DentRead: {sum(1 for a in arts.values() if a.get('used'))}",
    ]
    for w in sorted(arch["weeks"])[-8:]:
        lines.append(f"  {w}: +{len(arch['weeks'][w])} nuevos")
    return "\n".join(lines)


def backlog(*, year: int | None = None, limit: int = 20,
            pages: int | None = None) -> list[Article]:
    """
    El stock del año: artículos relevantes que ya no son noticia.

    Medido: el 50% de los titulares de ene-mar 2026 supera el piso, lo que
    proyecta ~75 publicables sobre los ~150 artículos de 2026. Eso es más de
    un año de contenido a razón de uno por semana, incluso si ADA News no
    publicara nada nuevo.

    Los dos de mayor puntaje del backlog —estándares de interoperabilidad
    para imagenología dental y la respuesta de la ADA a HHS sobre adopción de
    IA— son exactamente el territorio de DentRead.

    REGLA DE REDACCIÓN: estos artículos NO son novedad. `is_fresh=False` y el
    generador debe enmarcarlos con su fecha ("en febrero la ADA pidió…"),
    nunca como "nuevo" o "esta semana". `publisher.newsguard` lo verifica.
    """
    year = year or date.today().year
    # profundidad suficiente para cubrir el año entero: ~50 artículos/página
    depth = pages or MAX_PAGES
    latest_relevant(pages=depth, max_age_days=400, limit=0)  # solo para archivar

    arch = load_archive()
    out = []
    for url, a in arch["articles"].items():
        if a.get("used") or a.get("skipped"):
            continue
        if a.get("score", 0) < MIN_SCORE:
            continue
        if not str(a.get("published", "")).startswith(str(year)):
            continue
        art = Article(
            url=url, title=a["title"], summary="", category=a.get("category", ""),
            published=a.get("published", ""), author="",
            score=a.get("score", 0.0), buckets=a.get("buckets", []),
        )
        art.is_fresh = _age_days(a.get("published", "")) <= FRESH_DAYS
        out.append(art)

    out.sort(key=lambda x: (-x.score, x.published))
    return out[:limit]
