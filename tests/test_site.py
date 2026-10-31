#!/usr/bin/env python3
"""
Que cada página indexable tenga cuerpo, y que las noticias no repitan cierre.

Existe por dos fallos que nadie vio en el feed porque no estaban en el feed:

- `site.write_article` buscaba frames con roles del renderer de Pillow
  (`evidence`, `reading`, `thesis`). El motor HTML usa `hook`, `data` y
  `close`, así que 24 de 25 páginas salieron con título y fuentes y nada en
  el medio. Un carrusel pasaba todos los tests y su página quedaba vacía.
- El cierre de una noticia salía de un hash de la URL. De seis noticias
  publicadas, tres cerraron con la misma frase.

Sin red y sin modelo.

    python -m tests.test_site
"""
from __future__ import annotations

import re
from unittest.mock import patch
import json
import xml.etree.ElementTree as ET
import sys
import tempfile
from pathlib import Path

from pipeline import bitacora, llm, plan, site

bitacora.RUTA = Path(tempfile.gettempdir()) / "bitacora-de-prueba.jsonl"
from pipeline.generate import generate
from pipeline.sources import CIERRES_NOTICIA, _pick
from pipeline.spec import PostSpec, Slide, Stat
from pipeline.themes import CATALOG


def _cuerpo(html: str) -> str:
    return html.split('<p class="meta">', 1)[1].split("<h2>Fuentes</h2>", 1)[0]


def _escribir(spec: PostSpec) -> str:
    real = site.DOCS
    with tempfile.TemporaryDirectory() as tmp:
        site.DOCS = Path(tmp)
        try:
            return site.write_article(spec, "2026-10-10").read_text()
        finally:
            site.DOCS = real


def probar_paginas_con_cuerpo() -> list[str]:
    """Un post de datos y uno evergreen, por el camino real de generate."""
    errs = []
    facts = plan.load_facts()
    casos = []
    for tema in CATALOG:
        fs = [f for f in facts if tema.id in f.get("themes", [])][:2]
        if len(fs) == 2:
            casos.append(("datos", plan.post_from_theme(tema, fs)))
            break
    casos.append(("evergreen", plan.post_from_block(plan.load_evergreen()[0])))

    with llm.sin_modelo():
        for tipo, post in casos:
            spec = generate(post)
            html = _escribir(spec)
            cuerpo = _cuerpo(html)
            if not re.search(r"<p>|<div class=\"stat\"|<li>", cuerpo):
                errs.append(f"la página de {tipo} '{spec.slug}' sale sin cuerpo")
            cierre = next(s for s in spec.slides if s.role == "close").headline
            if cierre not in html:
                errs.append(f"la página de {tipo} no trae el cierre '{cierre}'")
            # Cada texto una sola vez: el frame de datos repetía su lectura.
            parrafos = re.findall(r"<p>(.*?)</p>", cuerpo)
            dup = {p for p in parrafos if parrafos.count(p) > 1}
            if dup:
                errs.append(f"la página de {tipo} repite párrafos: {sorted(dup)[:2]}")
    return errs


def probar_pagina_noticia() -> list[str]:
    """Forma de una noticia armada a mano: puntos, nota y cita con URL."""
    url = "https://adanews.ada.org/ada-news/2026/october/x/"
    spec = PostSpec(
        slug="news-1", caption_es="", commentary_en="", title_en="X",
        citations=[f"ADA News · Science — {url}"], mode="news",
        slides=[
            Slide("hook", "Gancho", body="Publicado esta semana en ADA News."),
            Slide("data", "Titular", bullets=["Resumen.", "«Original»"],
                  body="Título original, en inglés."),
            Slide("close", "La IA apoya.", accent="El odontólogo decide.",
                  kicker="Cómo lo leemos"),
        ])
    html = _escribir(spec)
    errs = []
    if "—" in html:
        errs.append("la página de noticia trae raya larga (brand guide)")
    if f'href="{url}"' not in html:
        errs.append("la cita de la noticia no enlaza a la nota")
    if "esta semana" in html:
        errs.append("una página permanente dice 'esta semana'")
    if "«Original»" not in html:
        errs.append("la página de noticia no trae el resumen")
    elif html.index("«Original»") > html.find("Título original, en inglés."):
        errs.append("la nota 'Título original' queda antes del título que describe")
    return errs


def probar_version_en_ingles() -> list[str]:
    """
    La página en inglés de un post de datos: cifras curadas en inglés, enlace
    al español, y nada del texto aprobado en español que no tiene traducción
    revisada (el cierre).
    """
    errs = []
    facts = plan.load_facts()
    tema = next(t for t in CATALOG
                if len([f for f in facts if t.id in f.get("themes", [])]) >= 2)
    fs = [f for f in facts if tema.id in f.get("themes", [])][:2]
    post = plan.post_from_theme(tema, fs)
    with llm.sin_modelo():
        spec = generate(post)
    real = site.DOCS
    with tempfile.TemporaryDirectory() as tmp:
        site.DOCS = Path(tmp)
        try:
            es = site.write_article(spec, "2026-10-11", post).read_text()
            en_path = Path(tmp) / spec.slug / "index.html"
            en = en_path.read_text() if en_path.exists() else ""
        finally:
            site.DOCS = real
    if not en:
        return ["el post de datos no generó página en inglés"]
    if '<html lang="en">' not in en:
        errs.append("la página en inglés no declara lang=en")
    for f in fs:
        if f["number_en"] not in en:
            errs.append(f"la página en inglés no trae la cifra curada '{f['number_en']}'")
    if tema.close and tema.close in en:
        errs.append("la página en inglés publica el cierre en español sin traducción revisada")
    for html_, otro in ((en, f"/es/{spec.slug}/"), (es, f"/{spec.slug}/")):
        if f'hreflang' not in html_ or otro not in html_:
            errs.append("falta el enlace hreflang entre idiomas")
            break
    if "dentread.app" not in en or "dentread.app" not in es:
        errs.append("las páginas no enlazan a dentread.app")
    return errs


def probar_traduccion_cuida_cifras() -> list[str]:
    """Una traducción que cambia una cifra se descarta."""
    errs = []
    real = llm.pedir
    try:
        llm.pedir = lambda *a, **k: "About 72 million adults lack coverage."
        if site.traducir(["Cerca de 72 millones de adultos no tienen cobertura."]) is None:
            errs.append("descartó una traducción correcta")
        llm.pedir = lambda *a, **k: "About 27 million adults lack coverage."
        if site.traducir(["Cerca de 72 millones de adultos no tienen cobertura."]) is not None:
            errs.append("aceptó una traducción que cambió la cifra")
    finally:
        llm.pedir = real
    return errs


def probar_cierres_no_se_repiten() -> list[str]:
    errs = []
    ops = CIERRES_NOTICIA["ai"]
    url = "https://adanews.ada.org/a"
    primero = _pick(ops, url)
    segundo = _pick(ops, url, [" ".join(primero)])
    if segundo == primero:
        errs.append("una noticia repite el cierre de la anterior")
    # Sin historial, la regla es la vieja: así se reconstruye lo publicado.
    if _pick(ops, url, []) != primero:
        errs.append("sin historial el cierre ya no es estable")
    # Con toda la familia usada gana la más antigua, no la primera.
    usados = [" ".join(o) for o in ops]           # del más nuevo al más viejo
    if _pick(ops, url, usados) != ops[-1]:
        errs.append("con la familia agotada no gana el cierre más antiguo")
    return errs


def probar_entidades() -> list[str]:
    errs = []
    real = site.DOCS
    post = plan.post_from_block(plan.load_evergreen()[0])
    with llm.sin_modelo(), tempfile.TemporaryDirectory() as tmp:
        site.DOCS = Path(tmp)
        try:
            spec = generate(post)
            site.write_article(spec, "2026-01-02", post)
            site.rebuild_indexes()
            site.rebuild_indexes()  # author pages must never become articles
            def ld(content):
                return json.loads(re.search(
                    r'<script type="application/ld\+json">(.*?)</script>', content, re.S).group(1))
            llms = (site.DOCS / "llms.txt").read_text()
            for lang in ("en", "es"):
                pages = site._paginas(lang)
                if len(pages) != 1:
                    errs.append(f"{lang}: el índice incluye páginas que no son artículos")
                for page in pages:
                    content = page.read_text()
                    author = ld(content)["author"]
                    if author != {k: site.AUTHOR[k] for k in ("@type", "@id", "name", "url")}:
                        errs.append(f"{lang}: autor Person incorrecto")
                    if ld(content)["publisher"]["@id"] != site.ORG["@id"]:
                        errs.append(f"{lang}: publisher incorrecto")
                    if f'</h1>\n<p class="byline">{site.TXT[lang]["byline"]}</p>' not in content:
                        errs.append(f"{lang}: falta firma bajo el título")
                    if site._url(lang, page.parent.name) not in llms:
                        errs.append(f"{lang}: artículo ausente en llms.txt")
                base = site.DOCS if lang == "en" else site.DOCS / "es"
                about = base / site.TXT[lang]["author_route"] / "index.html"
                if not about.exists() or ld(about.read_text()) != {
                    "@context": "https://schema.org", "@type": "ProfilePage", "mainEntity": site.AUTHOR}:
                    errs.append(f"{lang}: falta ProfilePage del autor")
                graph = ld((base / "index.html").read_text())["@graph"]
                if graph[0]["@type"] != "WebSite" or graph[1] != site.ORG:
                    errs.append(f"{lang}: falta WebSite/Organization")
            ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            entries = ET.parse(site.DOCS / "sitemap.xml").findall("s:url", ns)
            dates = {e.findtext("s:loc", namespaces=ns): e.findtext("s:lastmod", namespaces=ns) for e in entries}
            for lang in ("en", "es"):
                if dates.get(site._url(lang, spec.slug)) != "2026-01-02":
                    errs.append(f"{lang}: sitemap perdió datePublished")
                if site._url(lang, site.TXT[lang]["author_route"]) not in dates:
                    errs.append(f"{lang}: autor ausente en sitemap")
        finally:
            site.DOCS = real
    return errs


def probar_seo_aeo() -> list[str]:
    def schemas(content):
        return [json.loads(raw) for raw in re.findall(
            r'<script type="application/ld\+json">(.*?)</script>', content, re.S)]

    facts = {f["id"]: f for f in plan.load_facts()}
    questions = site._questions()
    assert set(questions) <= set(facts), "pregunta sin hecho verificado"
    with tempfile.TemporaryDirectory() as tmp, patch.object(site, "DOCS", Path(tmp)):
        site.rebuild_indexes()
        assert (site.DOCS / "logo.png").read_bytes() == Path("brand/logo-ink.png").read_bytes()
        robots = (site.DOCS / "robots.txt").read_text()
        for bot in ("*", "GPTBot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot",
                    "ClaudeBot", "Claude-SearchBot", "Google-Extended", "Applebot-Extended"):
            assert f"User-agent: {bot}\nAllow: /" in robots
        assert f"Sitemap: {site.BASE_URL}/sitemap.xml" in robots
        llms_text = (site.DOCS / "llms.txt").read_text()
        for lang in ("en", "es"):
            content = site.write_data_index(lang).read_text()
            graph = schemas(content)[0]["@graph"]
            faq = next(node for node in graph if node["@type"] == "FAQPage")
            answers = {q["name"]: q["acceptedAnswer"]["text"] for q in faq["mainEntity"]}
            assert len(answers) == len(questions)
            for fid, question in questions.items():
                statement = facts[fid]["statement_en" if lang == "en" else "statement"]
                assert answers[question[lang]] == statement + " Source: " + facts[fid]["cite"]
                assert f'<li id="{fid}"><h3>{site._esc(question[lang])}</h3><p>{site._esc(statement)}</p>' in content
                assert f'[{question[lang]}]({site._url(lang, site._ruta_datos(lang))}#{fid})' in llms_text
            assert 'property="og:type" content="website"' in content
            assert f'property="og:locale" content="{"en_US" if lang == "en" else "es_ES"}"' in content
            for tag in ('property="og:image"', 'property="og:site_name"', 'name="twitter:card"',
                        'name="twitter:title"', 'name="twitter:description"', 'name="twitter:image"'):
                assert tag in content
            assert '<link rel="icon" href="/logo.png">' in content
            # No question: retain the old rendering and omit it from FAQPage.
            fid = next(iter(questions))
            with patch.object(site, "_questions", return_value={k: v for k, v in questions.items() if k != fid}):
                fallback = site.write_data_index(lang).read_text()
                assert f'<li id="{fid}">' not in fallback
                assert site._esc(site.sin_em_dash(facts[fid]["statement_en" if lang == "en" else "statement"])) in fallback

        theme = next(t for t in CATALOG if sum(t.id in f["themes"] for f in facts.values()) >= 2)
        used = [f for f in facts.values() if theme.id in f["themes"]][:2]
        post = plan.post_from_theme(theme, used)
        with llm.sin_modelo():
            spec = generate(post)
            site.write_article(spec, "2026-10-01", post)
        for lang in ("en", "es"):
            page = (site.DOCS if lang == "en" else site.DOCS / "es") / spec.slug / "index.html"
            content = page.read_text()
            for f in used:
                assert f'/#{f["id"]}' in content
            article, breadcrumb = schemas(content)
            assert article["image"] == site.LOGO_URL
            assert article["publisher"]["logo"] == site.ORG["logo"]
            assert article["isPartOf"]["@type"] == "WebSite" and "about" not in article
            assert breadcrumb["itemListElement"][1]["item"] == site._url(lang, spec.slug)
            assert 'property="article:published_time" content="2026-10-01"' in content
            assert f'property="article:author" content="{site.AUTHOR["url"]}"' in content
            # Simulate a hand-patched historical page with no questions or new metadata.
            legacy = re.sub(r'<section id="questions">.*?</section>\n', '', content, flags=re.S)
            legacy = legacy.replace(site._ld_script(breadcrumb) + "\n", "")
            legacy_body = legacy.split("<body>", 1)[1]
            page.write_text(legacy)
            site.upgrade_article(page)
            once = page.read_bytes()
            site.upgrade_article(page)
            assert page.read_bytes() == once, "upgrade no es idempotente"
            body = page.read_text().split("<body>", 1)[1]
            assert re.sub(r'<section id="questions">.*?</section>\n', '', body, flags=re.S) == legacy_body
            assert '<section id="questions">' in body
            assert len(schemas(page.read_text())) == 2
        assert "image" not in site.AUTHOR
        assert len(site.AUTHOR["knowsAbout"]) == 6
        escaped = site._ld_script({"text": '</script><p> & "'})
        assert schemas(escaped)[0]["text"] == '</script><p> & "'
    return []


def main() -> int:
    errores = (probar_paginas_con_cuerpo() + probar_pagina_noticia()
               + probar_version_en_ingles() + probar_traduccion_cuida_cifras()
               + probar_cierres_no_se_repiten() + probar_entidades() + probar_seo_aeo())
    if errores:
        print("✗ las páginas o los cierres no están bien:\n")
        print("\n".join(f"  {e}" for e in errores))
        return 1
    print("✓ cada página trae cuerpo, la versión en inglés usa cifras curadas, y las noticias no repiten cierre")
    return 0


if __name__ == "__main__":
    sys.exit(main())
