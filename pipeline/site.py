"""
Sitio estático: el único activo que compone.

Un carrusel desaparece del feed en 48 horas y no lo indexa nadie. Instagram
no expone texto indexable y un document post de LinkedIn es texto dentro de
un PDF dentro de un feed. Para ChatGPT, Perplexity o Claude el valor es cero:
citan URLs.

Este módulo escribe, por cada post, una página HTML con `schema.org/Article`
y sus citas. Más un índice de datos —cada hecho con su fuente— que es
exactamente lo que un motor de IA busca citar.

Sale a `docs/`, que Cloudflare Pages sirve gratis. Sin framework, sin build.

**Bilingüe (desde 2026-10-11).** El cliente objetivo es el mini-DSO de EE.UU.,
que busca en inglés: el inglés va en la raíz (`/<slug>/`) y el español en
`/es/<slug>/`, cada uno con `hreflang` hacia el otro. Las cifras en inglés
son las curadas a mano en `facts.json` (`number_en`, `statement_en`), nunca
una traducción del modelo. Los cierres aprobados no tienen versión en inglés
revisada todavía, así que la página en inglés no los muestra.

    python -m pipeline.site --rebuild     # regenera índices y sitemap
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from datetime import date
from pathlib import Path

from pipeline.generate import sin_em_dash
from pipeline.plan import load_facts
from pipeline.spec import PostSpec, Slide
from pipeline.themes import CATALOG

DOCS = Path("docs")
# Cloudflare Pages, como el resto de los proyectos (dentlife-cl, radar-salud).
# Estuvo en "https://insights.dentread.app", un subdominio que nunca se creó:
# cada página declaraba como canónica una URL que no cargaba. Después pasó
# por la de GitHub Pages (santivivallo.github.io/dentread-social), que sigue
# sirviendo lo mismo desde docs/ pero ya no es la canónica. Si se cambia de
# nuevo: tocar acá y correr `python -m tools.rehacer_paginas --todas`.
BASE_URL = "https://dentread-social.pages.dev"
SITE_NAME = "DentRead Insights"
LOGO_URL = f"{BASE_URL}/logo.png"
AUTHOR = {
    "@type": "Person", "@id": f"{BASE_URL}/about/#person",
    "name": "Santiago Vivallo", "honorificSuffix": "DDS", "jobTitle": "CEO",
    "worksFor": {"@id": "https://dentread.app/#org"},
    "url": f"{BASE_URL}/about/",
    "sameAs": ["https://www.linkedin.com/in/santivivallo",
               "https://santiagovivallo.pages.dev"],
    "knowsAbout": ["Dental radiography", "Artificial intelligence in dentistry",
                   "Digital dentistry", "Dental practice management",
                   "Dental public health", "Salivary biomarkers"],
    "description": "Dentist. Digital dentistry, healthcare management and research. CEO of DentRead.",
}
ORG = {
    "@type": "Organization", "@id": "https://dentread.app/#org",
    "name": "DentRead", "url": "https://dentread.app",
    "sameAs": ["https://www.instagram.com/dentread_/"],
    "founder": {"@id": AUTHOR["@id"]},
    "logo": {"@type": "ImageObject", "url": LOGO_URL},
}
LINKEDIN_ARTICLES = [
    "accuracy-robotic-computer-assisted-implant-surgery-santiago-vivallo--gmn9e",
    "ai-dentistry-update-santiago-vivallo--qbnte",
    "dental-education-practice-past-present-future-trends-vivallo--eyk6e",
    "future-dentistry-brief-santiago-vivallo--nkzoe",
    "haptic-virtual-reality-dental-education-santiago-vivallo--ovnue",
    "nanotech-dentistry-santiago-vivallo--ghqfe",
    "next-generation-regenerative-dentistry-santiago-vivallo--hnhze",
    "public-dental-imaging-datasets-ai-development-santiago-vivallo--pwsre",
    "salivary-biomarkers-caries-santiago-vivallo--zda3e",
]
TAGLINE = ("Datos verificados sobre el mercado dental de Estados Unidos, "
           "con su fuente.")
TAGLINE_EN = "Verified data on the US dental market, with sources."
ES_DIR = "es"

CSS = """
:root{--ink:#0d1b2a;--paper:#f7f6f3;--accent:#2e6ae0;--muted:#7a8492}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
 font:17px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:48px 24px 96px}
a{color:var(--accent)}
h1{font-size:2.1rem;line-height:1.2;margin:.2em 0 .4em;letter-spacing:-.02em}
h2{font-size:1.25rem;margin:2.4em 0 .6em;letter-spacing:-.01em}
.kicker{text-transform:uppercase;letter-spacing:.08em;font-size:.78rem;
 color:var(--accent);font-weight:700}
.meta{color:var(--muted);font-size:.85rem;margin-bottom:2.4em}
.stat{border-left:3px solid var(--accent);padding:.2em 0 .2em 1.1em;margin:1.8em 0}
.stat .n{font-size:2.1rem;font-weight:800;letter-spacing:-.02em;
 color:var(--accent);display:block}
.stat .src{color:var(--muted);font-size:.8rem;margin-top:.5em}
ul.facts{list-style:none;padding:0}
ul.facts li{border-bottom:1px solid #e4e2dd;padding:1.1em 0}
ul.facts .n{font-weight:800;color:var(--accent);margin-right:.5em}
ul.facts .src{display:block;color:var(--muted);font-size:.8rem;margin-top:.35em}
footer{margin-top:4em;padding-top:1.5em;border-top:1px solid #e4e2dd;
 color:var(--muted);font-size:.85rem}
.note{background:#fff;border:1px solid #e4e2dd;padding:1em 1.2em;
 border-radius:6px;font-size:.9rem;color:var(--muted)}
"""

DISCLAIMER = (
    "DentRead es software de apoyo al flujo de trabajo clínico. No es un "
    "dispositivo diagnóstico y no cuenta con autorización de la FDA. Las "
    "cifras citadas provienen de las fuentes indicadas; no son resultados "
    "de DentRead."
)
DISCLAIMER_EN = (
    "DentRead is clinical workflow support software. It is not a diagnostic "
    "device and is not FDA cleared. Figures cited come from the sources "
    "shown; they are not DentRead results."
)

# Textos fijos por idioma. Lo que dice qué es DentRead sale del bloque
# evergreen `que-es-dentread` (mensaje aprobado), no de acá.
TXT = {
    "es": {"author_route": "sobre", "author_link": "Sobre el autor",
           "byline": 'Por <a href="/es/sobre/">Santiago Vivallo, DDS</a> · CEO de DentRead',
           "author_description": "Odontólogo. Odontología digital, gestión en salud e investigación. CEO de DentRead.",
           "linkedin_articles": "Artículos en LinkedIn", "personal_site": "Sitio personal",
           "datos": "Índice de datos", "fuentes": "Fuentes",
           "implica": "Qué implica", "otro": "Read in English",
           "home_cta": "Ver el índice completo de datos →",
           "pubs": "Publicaciones", "vacio": "Todavía no hay publicaciones.",
           "sobre": "Sobre DentRead", "mas": "Conocer DentRead →",
           "data_kicker": "Índice de datos",
           "data_h1": "Datos del mercado dental de EE.UU., con su fuente",
           "data_meta": "cifras verificadas · actualizado",
           "data_intro": ("Cada cifra fue leída en su fuente primaria antes de "
                          "publicarse. Se indica publicación, página y fecha. "
                          "Ninguna es un resultado de DentRead."),
           "data_title": "Datos del mercado dental de EE.UU."},
    "en": {"author_route": "about", "author_link": "About the author",
           "byline": 'By <a href="/about/">Santiago Vivallo, DDS</a> · CEO, DentRead',
           "author_description": AUTHOR["description"],
           "linkedin_articles": "Articles on LinkedIn", "personal_site": "Personal site",
           "datos": "Data index", "fuentes": "Sources",
           "implica": "Why it matters", "otro": "Leer en español",
           "home_cta": "See the full data index →",
           "pubs": "Posts", "vacio": "No posts yet.",
           "sobre": "About DentRead", "mas": "Learn about DentRead →",
           "data_kicker": "Data index",
           "data_h1": "US dental market data, with sources",
           "data_meta": "verified figures · updated",
           "data_intro": ("Every figure was read in its primary source before "
                          "publication, with publication, page and date. None "
                          "is a DentRead result."),
           "data_title": "US dental market data"},
}


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _url(lang: str, ruta: str = "") -> str:
    """URL pública de una ruta en un idioma. `ruta` sin barras: 'datos', 'slug'."""
    pre = "" if lang == "en" else f"/{ES_DIR}"
    return f"{BASE_URL}{pre}/{ruta + '/' if ruta else ''}"


def _sobre(lang: str) -> str:
    """
    Qué es DentRead y a dónde ir. Antes ninguna página enlazaba a dentread.app:
    quien llegaba desde un buscador no tenía un paso siguiente.
    """
    try:
        from pipeline.plan import load_evergreen
        b = next(x for x in load_evergreen() if x["id"] == "que-es-dentread")
        clave = "approved_messages_en" if lang == "en" else "approved_messages"
        texto = (b.get(clave) or b.get("approved_messages") or [""])[0]
    except (StopIteration, OSError, ValueError):
        return ""
    t = TXT[lang]
    return (f'<h2>{t["sobre"]}</h2><p>{_esc(texto)}</p>'
            f'<p><a href="https://dentread.app">{t["mas"]}</a></p>')


def _ld_script(value: dict) -> str:
    return ('<script type="application/ld+json">'
            + json.dumps(value, ensure_ascii=False).replace("<", "\\u003c") + '</script>')


def _social_head(title: str, description: str, canonical: str, lang: str,
                 article: dict | None = None) -> str:
    tags = {"og:type": "article" if article else "website", "og:title": title,
            "og:description": description, "og:url": canonical,
            "og:image": LOGO_URL, "og:site_name": SITE_NAME,
            "og:locale": "en_US" if lang == "en" else "es_ES"}
    if article:
        tags.update({"article:published_time": article["datePublished"],
                     "article:author": AUTHOR["url"]})
    out = [f'<meta property="{key}" content="{_esc(value)}">' for key, value in tags.items()]
    out += [f'<meta name="twitter:{key}" content="{_esc(value)}">'
            for key, value in {"card": "summary", "title": title,
                               "description": description, "image": LOGO_URL}.items()]
    return "\n".join(out) + '\n<link rel="icon" href="/logo.png">'


def _breadcrumb_ld(title: str, url: str, lang: str) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1,
                 "name": "Home" if lang == "en" else "Inicio", "item": _url(lang)},
                {"@type": "ListItem", "position": 2, "name": title, "item": url}]}


def _questions() -> dict:
    return json.loads(Path("data/preguntas.json").read_text())["preguntas"]


def _questions_section(facts: list[dict], lang: str) -> str:
    questions = _questions()
    links = "".join(
        f'<li><a href="/{"" if lang == "en" else "es/"}{_ruta_datos(lang)}/#{_esc(f["id"])}">'
        f'{_esc(questions[f["id"]][lang])}</a></li>'
        for f in facts if questions.get(f["id"], {}).get(lang))
    heading = "Questions this answers" if lang == "en" else "Preguntas que responde"
    return f'<section id="questions"><h2>{heading}</h2><ul>{links}</ul></section>\n' if links else ""


def _shell(title: str, description: str, body: str, canonical: str,
           jsonld: dict | None = None, *, lang: str = "es",
           alternas: dict[str, str] | None = None, sobre: bool = True) -> str:
    ld = _ld_script(jsonld) if jsonld else ""
    article = jsonld if jsonld and jsonld.get("@type") == "Article" else None
    if article:
        ld += "\n" + _ld_script(_breadcrumb_ld(title, canonical, lang))
    t = TXT[lang]
    alternas = alternas or {}
    hreflang = "".join(f'\n<link rel="alternate" hreflang="{l}" href="{u}">'
                       for l, u in alternas.items())
    if "en" in alternas:
        hreflang += f'\n<link rel="alternate" hreflang="x-default" href="{alternas["en"]}">'
    otro = next((u for l, u in alternas.items() if l != lang), "")
    enlace_otro = f' · <a href="{otro}" hreflang="{"es" if lang == "en" else "en"}">{t["otro"]}</a>' if otro else ""
    return f"""<!doctype html>
<html lang="{lang}">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}{(" · " + SITE_NAME) if title != SITE_NAME else ""}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{canonical}">{hreflang}
{_social_head(title, description, canonical, lang, article)}
<style>{CSS}</style>
{ld}
<body><div class="wrap">
{body}
{_sobre(lang) if sobre else ""}
<footer>
<p class="note">{DISCLAIMER_EN if lang == "en" else DISCLAIMER}</p>
<p><a href="{_url(lang)}">{SITE_NAME}</a> · <a href="{_url(lang, "data" if lang == "en" else "datos")}">{t["datos"]}</a> · <a href="{_url(lang, t["author_route"])}">{t["author_link"]}</a>{enlace_otro}</p>
</footer>
</div></body></html>
"""


def _citation_ld(cite: str) -> dict:
    """Cada cita como CreativeWork: es lo que hace la página citable."""
    m = re.match(r"^(.*?)\s*[—–]\s*(https?://\S+)\s*$", cite)
    if m:
        # Noticias: "ADA News · Categoría — https://…". La URL va en `url`,
        # no pegada al nombre con una raya larga.
        return {"@type": "CreativeWork", "name": m.group(1), "url": m.group(2),
                "publisher": {"@type": "Organization", "name": "ADA News"}}
    publisher = cite.split(",")[0].strip()
    name = cite.split(",", 1)[1].split("(")[0].strip() if "," in cite else cite
    year = re.search(r"(20\d\d)", cite)
    d = {"@type": "CreativeWork", "name": name,
         "publisher": {"@type": "Organization", "name": publisher}}
    if year:
        d["datePublished"] = year.group(1)
    return d


# --------------------------------------------------------------------------

def _cita_html(cite: str) -> str:
    """
    Una cita como ítem de lista, con la URL como enlace.

    Las citas de noticias vienen como "ADA News · Categoría — https://…". La
    raya larga está prohibida por el brand guide y una URL desnuda no se puede
    clickear, así que se separan: el texto queda como etiqueta del enlace.
    """
    m = re.match(r"^(.*?)\s*[—–-]\s*(https?://\S+)\s*$", cite)
    if m:
        return f'<li><a href="{_esc(m.group(2))}">{_esc(m.group(1))}</a></li>'
    return f"<li>{_esc(cite.replace(' — ', ', '))}</li>"


def _frame_html(s: Slide) -> str:
    """
    El contenido de un frame, como HTML legible fuera del carrusel.

    En el frame del gancho la cifra y su enunciado van juntos en una tarjeta.
    En los demás, primero lo que se afirma (tarjetas, puntos) y después la
    lectura o la nota: "Título original, en inglés." describe la última línea
    de la lista y antes quedaba arriba de ella.
    """
    if s.stat:
        return (f'<div class="stat"><span class="n">{_esc(s.stat)}</span>'
                f'{_esc(s.body)}<div class="src">{_esc(s.source)}</div></div>\n')
    out = ""
    for st in s.stats:
        out += (f'<div class="stat"><span class="n">{_esc(st.number)}</span>'
                f'{_esc(st.label)}<div class="src">{_esc(st.source)}</div></div>\n')
    if s.bullets:
        out += "<ul>" + "".join(f"<li>{_esc(b)}</li>" for b in s.bullets) + "</ul>\n"
    if s.body:
        # "Esta semana" es cierto el día que sale el carrusel; en una página
        # que queda indexada años deja de serlo. La fecha ya va en .meta.
        out += f"<p>{_esc(s.body.replace('Publicado esta semana en', 'Publicado en'))}</p>\n"
    return out


def write_article(spec: PostSpec, post_date: str | None = None,
                  post=None) -> Path:
    """
    Las páginas indexables de un post: español en /es/<slug>/ y, si llega el
    `post`, inglés en /<slug>/. Devuelve la de español.

    Leía los frames por los roles `evidence`, `reading` y `thesis`, que eran
    los del renderer de Pillow. El motor HTML usa `hook`, `data` y `close`, así
    que desde el cambio de motor ningún frame coincidía: 24 de las 25 páginas
    publicadas salían con el título y las fuentes, sin una línea de cuerpo.
    Por eso ahora se recorre por rol conocido y `tests/test_site.py` exige
    cuerpo en cada página.
    """
    post_date = post_date or date.today().isoformat()
    url = _url("es", spec.slug)
    en = _articulo_en(spec, post, post_date) if post is not None else None
    alternas = {"en": _url("en", spec.slug), "es": url} if en else {"es": url}
    t = TXT["es"]

    por_rol = {s.role: s for s in spec.slides}
    hook_s, data_s, close_s = (por_rol.get(r) for r in ("hook", "data", "close"))

    hook = hook_s.headline if hook_s else spec.title_en
    partes = []
    if hook_s:
        partes.append(_frame_html(hook_s))
    if data_s:
        partes.append(f"<h2>{_esc(data_s.headline)}</h2>\n{_frame_html(data_s)}")
    if close_s:
        cierre = " ".join(x for x in (close_s.headline, close_s.accent) if x)
        partes.append(f"<h2>{_esc(close_s.kicker or t['implica'])}</h2>\n"
                      f"<p><strong>{_esc(cierre)}</strong></p>\n"
                      + (f"<p>{_esc(close_s.body)}</p>\n" if close_s.body else ""))
    sources = "".join(_cita_html(c) for c in spec.citations)

    body = f"""<p class="kicker">{_esc(hook_s.kicker if hook_s and hook_s.kicker else spec.mode)}</p>
<h1>{_esc(hook)}</h1>
<p class="byline">{t["byline"]}</p>
<p class="meta">{post_date} · DentRead</p>
{"".join(partes)}
<h2>{t["fuentes"]}</h2>
<ul>{sources}</ul>
"""
    body += _questions_section(getattr(post, "facts", []), "es")
    jsonld = _article_ld(hook, post_date, url, spec.citations, "es")
    out = DOCS / ES_DIR / spec.slug / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_shell(hook, _clip_meta(spec.caption_es), body, url, jsonld,
                          lang="es", alternas=alternas,
                          sobre=spec.slug != "que-es-dentread"))

    if en:
        titulo, descripcion, cuerpo_en = en
        cuerpo_en += _questions_section(post.facts, "en")
        url_en = _url("en", spec.slug)
        destino = DOCS / spec.slug / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(_shell(
            titulo, descripcion, cuerpo_en, url_en,
            _article_ld(titulo, post_date, url_en, spec.citations, "en"),
            lang="en", alternas=alternas,
            sobre=getattr(post, "id", "") != "que-es-dentread"))
    return out


def _article_ld(headline: str, post_date: str, url: str, citas: list[str],
                lang: str) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": headline[:110],
        "datePublished": post_date,
        "dateModified": post_date,
        "inLanguage": lang,
        "author": {k: AUTHOR[k] for k in ("@type", "@id", "name", "url")},
        "publisher": {k: ORG[k] for k in ("@type", "@id", "name", "url", "logo")},
        "image": LOGO_URL,
        "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": _url(lang)},
        "mainEntityOfPage": url,
        "citation": [_citation_ld(c) for c in citas],
        "isAccessibleForFree": True,
    }


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _numeros(texto: str) -> list[str]:
    """Las cifras de un texto, sin separadores: '1.250' y '1,250' son la misma."""
    return sorted(re.sub(r"[.,]", "", n) for n in _NUM.findall(texto))


def traducir(lineas: list[str]) -> list[str] | None:
    """
    Traduce al inglés un resumen YA verificado. None si no se puede confiar.

    El resumen en español pasó los controles de exactitud contra la fuente.
    Una traducción puede romper justo eso, así que se acepta solo si trae
    exactamente las mismas cifras y la misma cantidad de líneas. Ante la duda,
    la página en inglés sale sin resumen: mejor corta que falsa.
    """
    from pipeline import llm
    if not lineas:
        return None
    reglas = ("Translate each line from Spanish to plain US English. Keep every "
              "number exactly as written. Do not add, remove or soften any "
              "claim. Return only the translated lines, one per line, in the "
              "same order. No numbering, no quotes, no em dashes.")
    salida = llm.pedir(reglas, "\n".join(lineas))
    if not salida:
        return None
    out = [l.strip() for l in salida.strip().split("\n") if l.strip()]
    # Un resumen de una sola línea con varias oraciones vuelve partido en una
    # oración por línea. No es un error de contenido: se vuelve a juntar.
    if len(lineas) == 1 and len(out) > 1:
        out = [" ".join(out)]
    if len(out) != len(lineas) or _numeros(" ".join(out)) != _numeros(" ".join(lineas)):
        return None
    return [sin_em_dash(l) for l in out]


def _articulo_en(spec: PostSpec, post, post_date: str):
    """
    (titulo, descripción, cuerpo) de la página en inglés, o None.

    Sale de textos que ya existen en inglés y fueron aprobados o curados:
    `angle_en` del tema, `statement_en` y `number_en` de cada cifra, los
    mensajes `_en` del bloque evergreen, y el título original de la noticia o
    el paper. Lo único que traduce un modelo es el resumen de una fuente
    externa, y pasa por `traducir`.
    """
    t = TXT["en"]
    citas = "".join(_cita_html(c) for c in spec.citations)
    fuentes = f'<h2>{t["fuentes"]}</h2>\n<ul>{citas}</ul>\n'
    meta = (f'<p class="byline">{t["byline"]}</p>\n'
            f'<p class="meta">{post_date} · DentRead</p>')

    if post.kind == "data":
        partes = [x.strip() for x in re.split(r"(?<=[.:])\s+", post.angle_en, 1)]
        titulo = partes[0].rstrip(":.") or post.angle_en
        resto = partes[1] if len(partes) > 1 else ""
        cards = "".join(
            f'<div class="stat"><span class="n">{_esc(f.get("number_en") or f["number"])}</span>'
            f'{_esc(sin_em_dash(f.get("statement_en") or f["statement"]))}'
            f'<div class="src">{_esc(f["cite"])}</div></div>\n'
            for f in post.facts)
        cuerpo = (f'<p class="kicker">US dental market</p>\n<h1>{_esc(titulo)}</h1>\n'
                  f'{meta}\n{cards}'
                  + (f'<h2>{t["implica"]}</h2>\n<p>{_esc(resto)}</p>\n' if resto else "")
                  + fuentes)
        return titulo, _clip_meta(post.angle_en), cuerpo

    if post.kind == "evergreen":
        from pipeline.plan import load_evergreen
        b = next((x for x in load_evergreen() if x["id"] == post.id), {})
        titulo = b.get("title_en") or post.angle_en
        puntos = [m for m in [post.angle_en, *post.messages_en] if m]
        cards = "".join(
            f'<div class="stat"><span class="n">{_esc(f.get("number_en") or f["number"])}</span>'
            f'{_esc(sin_em_dash(f.get("statement_en") or f["statement"]))}'
            f'<div class="src">{_esc(f["cite"])}</div></div>\n'
            for f in post.facts)
        cuerpo = (f'<p class="kicker">DentRead</p>\n<h1>{_esc(titulo)}</h1>\n{meta}\n'
                  + "".join(f"<p>{_esc(sin_em_dash(m))}</p>\n" for m in puntos)
                  + (f"<p>{_esc(sin_em_dash(post.body_en))}</p>\n" if post.body_en else "")
                  + cards + (fuentes if spec.citations else ""))
        return titulo, _clip_meta(post.angle_en or titulo), cuerpo

    if post.kind in ("news", "paper"):
        data_s = next((s for s in spec.slides if s.role == "data"), None)
        lineas = [b for b in (data_s.bullets if data_s else [])
                  if not b.startswith("«")]
        resumen = traducir(lineas)
        titulo = post.title.rstrip(".")
        kicker = "ADA News" if post.kind == "news" else (post.source_label or "Research")
        nota = ("Summary by DentRead, translated from our Spanish edition. "
                "Read the original for full context.")
        cuerpo = (f'<p class="kicker">{_esc(kicker)}</p>\n<h1>{_esc(titulo)}</h1>\n{meta}\n'
                  + ("<ul>" + "".join(f"<li>{_esc(l)}</li>" for l in resumen) + "</ul>\n"
                     f'<p class="note">{nota}</p>\n' if resumen else
                     "<p>Original article in English, linked below.</p>\n")
                  + fuentes)
        return titulo, _clip_meta(" ".join(resumen) if resumen else titulo), cuerpo
    return None


def _clip_meta(text: str, limit: int = 155) -> str:
    first = text.split("\n")[0]
    return first if len(first) <= limit else first[:limit - 1] + "…"


def _ruta_datos(lang: str) -> str:
    return "data" if lang == "en" else "datos"


def write_data_index(lang: str = "es") -> Path:
    """
    El activo de AEO. Hechos discretos, con cifra, fuente, página y fecha,
    sobre un nicho con poca cobertura autoritativa. Es lo que un motor de IA
    quiere citar, y crece solo con la curación que ya se hace. En inglés usa
    `number_en` y `statement_en`, curados a mano igual que el español.
    """
    t = TXT[lang]
    facts = load_facts()
    by_family: dict[str, list[dict]] = {}
    theme_family = {th.id: th.family for th in CATALOG}
    for f in facts:
        fam = next((theme_family[x] for x in f.get("themes", [])
                    if x in theme_family), "otros" if lang == "es" else "other")
        by_family.setdefault(fam, []).append(f)

    def num(f): return f.get("number_en") or f["number"] if lang == "en" else f["number"]
    def txt(f): return f.get("statement_en") or f["statement"] if lang == "en" else f["statement"]

    questions = _questions()
    sections = ""
    for fam in sorted(by_family):
        items = "".join(
            (f'<li id="{_esc(f["id"])}"><h3>{_esc(questions[f["id"]][lang])}</h3>'
             f'<p>{_esc(txt(f))}</p><span class="src">{_esc(f["cite"])}</span></li>'
             if questions.get(f["id"], {}).get(lang) else
            f'<li><span class="n">{_esc(num(f))}</span>'
            f'{_esc(sin_em_dash(txt(f)))}'
            f'<span class="src">{_esc(f["cite"])}</span></li>')
            for f in by_family[fam]
        )
        sections += f"<h2>{_esc(fam.replace('_', ' ').title())}</h2><ul class=\"facts\">{items}</ul>"

    body = f"""<p class="kicker">{t["data_kicker"]}</p>
<h1>{t["data_h1"]}</h1>
<p class="meta">{len(facts)} {t["data_meta"]} {date.today().isoformat()}</p>
<p>{t["data_intro"]}</p>
{sections}
"""
    url = _url(lang, _ruta_datos(lang))
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "US dental market data, with sources",
        "description": TAGLINE_EN if lang == "en" else TAGLINE,
        "inLanguage": lang,
        "creator": {"@type": "Organization", "name": "DentRead"},
        "dateModified": date.today().isoformat(),
        "isAccessibleForFree": True,
        "citation": [_citation_ld(f["cite"]) for f in facts],
    }
    faq = {"@type": "FAQPage", "inLanguage": lang, "mainEntity": [
        {"@type": "Question", "name": questions[f["id"]][lang],
         "acceptedAnswer": {"@type": "Answer", "text": txt(f) + " Source: " + f["cite"]}}
        for f in facts if questions.get(f["id"], {}).get(lang)]}
    jsonld = {"@context": "https://schema.org", "@graph": [jsonld, faq]}
    alternas = {"en": _url("en", "data"), "es": _url("es", "datos")}
    destino = (DOCS / "data") if lang == "en" else (DOCS / ES_DIR / "datos")
    out = destino / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_shell(t["data_title"], TAGLINE_EN if lang == "en" else TAGLINE,
                          body, url, jsonld, lang=lang, alternas=alternas))
    return out


def _paginas(lang: str) -> list[Path]:
    """Las páginas de post de un idioma, de la más nueva a la más vieja."""
    base = DOCS if lang == "en" else DOCS / ES_DIR
    fuera = {"data", "datos", "about", "sobre", ES_DIR}
    out = [p for p in base.glob("*/index.html") if p.parent.name not in fuera]

    def fecha(p: Path) -> str:
        m = re.search(r'"datePublished": "([^"]+)"', p.read_text())
        return m.group(1) if m else ""
    return sorted(out, key=lambda p: (fecha(p), p.parent.name), reverse=True)


def write_home(lang: str = "es") -> Path:
    t = TXT[lang]
    items = ""
    for a in _paginas(lang):
        slug = a.parent.name
        m = re.search(r"<h1>(.*?)</h1>", a.read_text(), re.S)
        title = html.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip()) if m else slug
        items += f'<li><a href="{_url(lang, slug)}">{_esc(title)}</a></li>'

    tagline = TAGLINE_EN if lang == "en" else TAGLINE
    body = f"""<p class="kicker">DentRead</p>
<h1>{SITE_NAME}</h1>
<p>{tagline}</p>
<p><a href="{_url(lang, _ruta_datos(lang))}">{t["home_cta"]}</a></p>
<h2>{t["pubs"]}</h2>
<ul>{items or f"<li>{t['vacio']}</li>"}</ul>
"""
    alternas = {"en": _url("en"), "es": _url("es")}
    out = (DOCS if lang == "en" else DOCS / ES_DIR) / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebSite", "name": SITE_NAME, "url": _url(lang),
         "inLanguage": lang, "publisher": {"@id": ORG["@id"]}}, ORG]}
    out.write_text(_shell(SITE_NAME, tagline, body, _url(lang), jsonld, lang=lang,
                          alternas=alternas))
    return out


def write_about(lang: str) -> Path:
    t = TXT[lang]
    links = "".join(
        f'<li><a href="https://www.linkedin.com/pulse/{slug}/">'
        f'{_esc(re.sub(r"\bai\b", "AI", re.split(r"-(?:santiago-)?vivallo--", slug)[0].replace("-", " ").capitalize(), flags=re.I))}</a></li>'
        for slug in LINKEDIN_ARTICLES)
    articles = ""
    for page in _paginas(lang):
        title = re.search(r"<h1>(.*?)</h1>", page.read_text(), re.S)
        articles += (f'<li><a href="{_url(lang, page.parent.name)}">'
                     f'{title.group(1) if title else _esc(page.parent.name)}</a></li>')
    body = (f'<h1>{AUTHOR["name"]}</h1><p>{t["author_description"]}</p>'
            f'<p><a href="{AUTHOR["sameAs"][0]}">LinkedIn</a> · '
            f'<a href="{AUTHOR["sameAs"][1]}">{t["personal_site"]}</a> · '
            f'<a href="{ORG["url"]}">DentRead</a></p>'
            f'<h2>{t["linkedin_articles"]}</h2><ul>{links}</ul>'
            f'<h2>{t["pubs"]}</h2><ul>{articles}</ul>')
    alternas = {l: _url(l, TXT[l]["author_route"]) for l in ("en", "es")}
    jsonld = {"@context": "https://schema.org", "@type": "ProfilePage",
              "mainEntity": AUTHOR}
    out = (DOCS if lang == "en" else DOCS / ES_DIR) / t["author_route"] / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_shell(AUTHOR["name"], t["author_description"], body,
                          alternas[lang], jsonld, lang=lang, alternas=alternas))
    return out


def write_sitemap() -> Path:
    body = ""
    llms = (f"# {SITE_NAME}\n\n"
            "> US dental market data with sources, by Santiago Vivallo, DDS, CEO of DentRead\n\n"
            f"## Author\n\n- [Santiago Vivallo, DDS]({_url('en', 'about')})\n\n"
            f"## Data\n\n- [Data index]({_url('en', 'data')})\n")
    for lang in ("en", "es"):
        for route in ("", _ruta_datos(lang), TXT[lang]["author_route"]):
            body += (f"<url><loc>{_esc(_url(lang, route))}</loc>"
                     f"<lastmod>{date.today().isoformat()}</lastmod></url>")
        llms += "\n" if lang == "en" else "\n## Español\n\n"
        llms += ("## Key questions" if lang == "en" else "### Preguntas clave") + "\n\n"
        llms += "".join(f'- [{q[lang]}]({_url(lang, _ruta_datos(lang))}#{fid})\n'
                        for fid, q in _questions().items() if q.get(lang))
        llms += "\n" + ("## Articles" if lang == "en" else "### Artículos") + "\n\n"
        for page in _paginas(lang):
            content = page.read_text()
            ld = json.loads(re.search(
                r'<script type="application/ld\+json">(.*?)</script>', content, re.S).group(1))
            published = ld.get("datePublished")
            lastmod = f"<lastmod>{_esc(published)}</lastmod>" if published else ""
            url = _url(lang, page.parent.name)
            body += f"<url><loc>{_esc(url)}</loc>{lastmod}</url>"
            title = html.unescape(re.search(r"<title>(.*?)</title>", content, re.S).group(1))
            description = html.unescape(re.search(
                r'<meta name="description" content="([^"]*)">', content).group(1))
            llms += f"- [{title}]({url}): {description}\n"
    (DOCS / "llms.txt").write_text(llms)
    out = DOCS / "sitemap.xml"
    out.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    )
    (DOCS / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n"
        + "".join(f"User-agent: {bot}\nAllow: /\n\n" for bot in (
            "GPTBot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot",
            "ClaudeBot", "Claude-SearchBot", "Google-Extended", "Applebot-Extended"))
        + f"Sitemap: {BASE_URL}/sitemap.xml\n")
    (DOCS / ".nojekyll").write_text("")
    # El índice de datos en español vivía en /datos/. Cloudflare Pages lee
    # este archivo y responde 301, así no se pierde lo que ya esté indexado.
    (DOCS / "_redirects").write_text(f"/datos/ /{ES_DIR}/datos/ 301\n")
    return out


def upgrade_article(path: Path) -> None:
    """Upgrade generated metadata; preserve existing prose byte for byte."""
    original = path.read_text()
    head, body = original.split("<body>", 1)
    scripts = list(re.finditer(r'<script type="application/ld\+json">(.*?)</script>', head, re.S))
    article_match = next((m for m in scripts if json.loads(m[1]).get("@type") == "Article"), None)
    if article_match is None:
        return
    article = json.loads(article_match[1])
    lang = article["inLanguage"]
    title = html.unescape(re.sub(r"<[^>]+>", "", re.search(r"<h1>(.*?)</h1>", body, re.S)[1]))
    url = _url(lang, path.parent.name)
    description = html.unescape(re.search(r'<meta name="description" content="([^"]*)">', head)[1])
    article.update({"image": LOGO_URL,
                    "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": _url(lang)}})
    article["publisher"] = {k: ORG[k] for k in ("@type", "@id", "name", "url", "logo")}
    article.pop("about", None)
    head = head[:article_match.start()] + _ld_script(article) + head[article_match.end():]
    head = re.sub(r'<script type="application/ld\+json">(.*?)</script>\n?',
                  lambda m: "" if json.loads(m[1]).get("@type") == "BreadcrumbList" else m[0], head, flags=re.S)
    head = re.sub(r'<meta (?:property|name)="(?:og:|twitter:|article:)[^"]*"[^>]*>\n?', "", head)
    head = re.sub(r'<link rel="icon"[^>]*>\n?', "", head)
    # Keep insertion points stable across repeated upgrades.
    head = head.replace("<style>", _social_head(title, description, url, lang, article) + "\n<style>", 1)
    head = head.rstrip() + "\n" + _ld_script(_breadcrumb_ld(title, url, lang)) + "\n"
    if '<section id="questions">' not in body:
        # Historical theme pages lack Post.facts; only link facts visible on the page.
        plain = html.unescape(re.sub(r"<[^>]+>", " ", body))
        normalize = lambda text: " ".join(sin_em_dash(text).split())
        visible = normalize(plain)
        facts = [f for f in load_facts() if path.parent.name in f.get("themes", [])
                 and any(normalize(f[key]) in visible
                         for key in (("statement_en",) if lang == "en" else ("statement", "card"))
                         if f.get(key))]
        section = _questions_section(facts, lang)
        body = body.replace(f'<h2>{TXT[lang]["fuentes"]}</h2>',
                            section + f'<h2>{TXT[lang]["fuentes"]}</h2>', 1)
    updated = head + "<body>" + body
    if updated != original:
        path.write_text(updated)


def rebuild_indexes() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    shutil.copyfile("brand/logo-ink.png", DOCS / "logo.png")
    for lang in ("en", "es"):
        for page in _paginas(lang):
            upgrade_article(page)
    for lang in ("en", "es"):
        write_data_index(lang)
        write_home(lang)
        write_about(lang)
    write_sitemap()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.parse_args()
    rebuild_indexes()
    print(f"[site] índices y sitemap regenerados en {DOCS}/")


if __name__ == "__main__":
    main()
