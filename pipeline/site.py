"""
Sitio estático: el único activo que compone.

Un carrusel desaparece del feed en 48 horas y no lo indexa nadie. Instagram
no expone texto indexable y un document post de LinkedIn es texto dentro de
un PDF dentro de un feed. Para ChatGPT, Perplexity o Claude el valor es cero:
citan URLs.

Este módulo escribe, por cada post, una página HTML con `schema.org/Article`
y sus citas. Más un índice de datos —cada hecho con su fuente— que es
exactamente lo que un motor de IA busca citar.

Sale a `docs/`, que GitHub Pages sirve gratis. Sin framework, sin build.

    python -m pipeline.site --rebuild     # regenera índices y sitemap
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import date
from pathlib import Path

from pipeline.plan import load_facts
from pipeline.spec import PostSpec
from pipeline.themes import CATALOG

DOCS = Path("docs")
BASE_URL = "https://insights.dentread.app"   # subdominio propio sobre GitHub Pages
SITE_NAME = "DentRead Insights"
TAGLINE = ("Datos verificados sobre el mercado dental de Estados Unidos, "
           "con su fuente.")

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


def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _shell(title: str, description: str, body: str, canonical: str,
           jsonld: dict | None = None) -> str:
    ld = (f'<script type="application/ld+json">'
          f'{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else "")
    return f"""<!doctype html>
<html lang="es">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)} · {SITE_NAME}</title>
<meta name="description" content="{_esc(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="article">
<meta property="og:title" content="{_esc(title)}">
<meta property="og:description" content="{_esc(description)}">
<meta property="og:url" content="{canonical}">
<style>{CSS}</style>
{ld}
<body><div class="wrap">
{body}
<footer>
<p class="note">{DISCLAIMER}</p>
<p><a href="{BASE_URL}/">{SITE_NAME}</a> · <a href="{BASE_URL}/datos/">Índice de datos</a></p>
</footer>
</div></body></html>
"""


def _citation_ld(cite: str) -> dict:
    """Cada cita como CreativeWork: es lo que hace la página citable."""
    publisher = cite.split(",")[0].strip()
    name = cite.split(",", 1)[1].split("(")[0].strip() if "," in cite else cite
    year = re.search(r"(20\d\d)", cite)
    d = {"@type": "CreativeWork", "name": name,
         "publisher": {"@type": "Organization", "name": publisher}}
    if year:
        d["datePublished"] = year.group(1)
    return d


# --------------------------------------------------------------------------

def write_article(spec: PostSpec, post_date: str | None = None) -> Path:
    post_date = post_date or date.today().isoformat()
    url = f"{BASE_URL}/{spec.slug}/"
    facts_html = ""
    for s in spec.slides:
        if s.role == "evidence":
            facts_html += (
                f'<div class="stat"><span class="n">{_esc(s.stat)}</span>'
                f'{_esc(s.headline)}<div class="src">{_esc(s.source)}</div></div>\n'
            )

    hook = spec.slides[0].headline if spec.slides else spec.title_en
    prose = "\n".join(
        f"<p>{_esc(s.body or s.headline)}</p>"
        for s in spec.slides if s.role in ("reading", "thesis") and (s.body or s.headline)
    )
    sources = "".join(f"<li>{_esc(c)}</li>" for c in spec.citations)

    body = f"""<p class="kicker">{_esc(spec.mode)}</p>
<h1>{_esc(hook)}</h1>
<p class="meta">{post_date} · DentRead</p>
{facts_html}
{prose}
<h2>Fuentes</h2>
<ul>{sources}</ul>
"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": hook[:110],
        "datePublished": post_date,
        "dateModified": post_date,
        "inLanguage": "es",
        "author": {"@type": "Organization", "name": "DentRead"},
        "publisher": {"@type": "Organization", "name": "DentRead"},
        "mainEntityOfPage": url,
        "citation": [_citation_ld(c) for c in spec.citations],
        "isAccessibleForFree": True,
    }

    out = DOCS / spec.slug / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_shell(hook, _clip_meta(spec.caption_es), body, url, jsonld))
    return out


def _clip_meta(text: str, limit: int = 155) -> str:
    first = text.split("\n")[0]
    return first if len(first) <= limit else first[:limit - 1] + "…"


def write_data_index() -> Path:
    """
    El activo de AEO. Hechos discretos, con cifra, fuente, página y fecha,
    sobre un nicho con poca cobertura autoritativa. Es lo que un motor de IA
    quiere citar, y crece solo con la curación que ya se hace.
    """
    facts = load_facts()
    by_family: dict[str, list[dict]] = {}
    theme_family = {t.id: t.family for t in CATALOG}
    for f in facts:
        fam = next((theme_family[t] for t in f.get("themes", [])
                    if t in theme_family), "otros")
        by_family.setdefault(fam, []).append(f)

    sections = ""
    for fam in sorted(by_family):
        items = "".join(
            f'<li><span class="n">{_esc(f["number"])}</span>'
            f'{_esc(f["statement"])}'
            f'<span class="src">{_esc(f["cite"])}</span></li>'
            for f in by_family[fam]
        )
        sections += f"<h2>{_esc(fam.title())}</h2><ul class=\"facts\">{items}</ul>"

    body = f"""<p class="kicker">Índice de datos</p>
<h1>Datos del mercado dental de EE.UU., con su fuente</h1>
<p class="meta">{len(facts)} cifras verificadas · actualizado {date.today().isoformat()}</p>
<p>Cada cifra fue leída en su fuente primaria antes de publicarse. Se indica
publicación, página y fecha. Ninguna es un resultado de DentRead.</p>
{sections}
"""
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "US dental market data, with sources",
        "description": TAGLINE,
        "creator": {"@type": "Organization", "name": "DentRead"},
        "dateModified": date.today().isoformat(),
        "isAccessibleForFree": True,
        "citation": [_citation_ld(f["cite"]) for f in facts],
    }
    out = DOCS / "datos" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_shell("Datos del mercado dental de EE.UU.", TAGLINE,
                          body, f"{BASE_URL}/datos/", jsonld))
    return out


def write_home() -> Path:
    articles = sorted(
        (p for p in DOCS.glob("*/index.html")
         if p.parent.name not in ("datos",)),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    items = ""
    for a in articles:
        slug = a.parent.name
        m = re.search(r"<h1>(.*?)</h1>", a.read_text(), re.S)
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else slug
        items += f'<li><a href="{BASE_URL}/{slug}/">{_esc(title)}</a></li>'

    body = f"""<p class="kicker">DentRead</p>
<h1>{SITE_NAME}</h1>
<p>{TAGLINE}</p>
<p><a href="{BASE_URL}/datos/">Ver el índice completo de datos →</a></p>
<h2>Publicaciones</h2>
<ul>{items or "<li>Todavía no hay publicaciones.</li>"}</ul>
"""
    out = DOCS / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_shell(SITE_NAME, TAGLINE, body, f"{BASE_URL}/"))
    return out


def write_sitemap() -> Path:
    urls = [f"{BASE_URL}/", f"{BASE_URL}/datos/"]
    urls += [f"{BASE_URL}/{p.parent.name}/" for p in DOCS.glob("*/index.html")
             if p.parent.name != "datos"]
    body = "".join(
        f"<url><loc>{u}</loc><lastmod>{date.today().isoformat()}</lastmod></url>"
        for u in dict.fromkeys(urls)
    )
    out = DOCS / "sitemap.xml"
    out.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>'
    )
    (DOCS / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n")
    (DOCS / ".nojekyll").write_text("")
    return out


def rebuild_indexes() -> None:
    write_data_index()
    write_home()
    write_sitemap()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.parse_args()
    rebuild_indexes()
    print(f"[site] índices y sitemap regenerados en {DOCS}/")


if __name__ == "__main__":
    main()
