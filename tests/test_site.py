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


def main() -> int:
    errores = (probar_paginas_con_cuerpo() + probar_pagina_noticia()
               + probar_cierres_no_se_repiten())
    if errores:
        print("✗ las páginas o los cierres no están bien:\n")
        print("\n".join(f"  {e}" for e in errores))
        return 1
    print("✓ cada página trae cuerpo y las noticias no repiten cierre")
    return 0


if __name__ == "__main__":
    sys.exit(main())
