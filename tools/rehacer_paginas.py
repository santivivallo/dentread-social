#!/usr/bin/env python3
"""
Rehace las páginas de docs/ que quedaron sin cuerpo.

Desde el cambio de motor (Pillow → HTML), `site.write_article` buscaba frames
con roles que ya no existían y escribía solo el título y las fuentes. Al
10-10-2026 eran 24 de 25 páginas. El generador ya está arreglado; esto
rellena las que se publicaron vacías.

`out/` no se versiona, así que el post.json de esos días no está. Se
reconstruye cada post con el mismo material que salió:

- datos: el tema, con los hechos que `rotation.json` marca como usados ese
  día. Texto curado, sin modelo: es el aprobado y no varía.
- evergreen: el bloque, también curado.
- noticias: la nota se vuelve a bajar por la URL que la página ya cita, y el
  resumen pasa por los mismos controles que en producción. El cierre es el
  que salió (la regla vieja, solo hash), no uno nuevo.
- papers: por pmid, mismo camino que noticias.

El slug de la página se conserva: es la URL que ya está indexada.

    python -m tools.rehacer_paginas            # solo las vacías
    python -m tools.rehacer_paginas --dry-run  # qué haría
    python -m tools.rehacer_paginas --todas    # también las que ya tienen cuerpo
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from pipeline import llm, plan, site
from pipeline.generate import generate
from pipeline.themes import CATALOG

DOCS = Path("docs")
NO_SON_POSTS = {"datos"}


def _vacia(html: str) -> bool:
    """Sin un solo párrafo, tarjeta ni lista entre el título y las fuentes."""
    cuerpo = html.split('<p class="meta">', 1)[-1].split("<h2>Fuentes</h2>", 1)[0]
    return not re.search(r"<p>|<div class=\"stat\"|<li>", cuerpo)


def _fecha(slug: str, rot: dict) -> str | None:
    for k in ("themes", "evergreen", "externos"):
        if slug in rot.get(k, {}):
            return rot[k][slug]
    carpetas = sorted(Path("out").glob(f"*-{slug}"))
    return carpetas[-1].name[:10] if carpetas else None


def _post_datos(slug: str, fecha: str, rot: dict):
    tema = next(t for t in CATALOG if t.id == slug)
    usados = {f for f, d in rot["facts"].items() if d == fecha}
    fs = [f for f in plan.load_facts()
          if f["id"] in usados and slug in f.get("themes", [])]
    if len(fs) < 2:
        raise ValueError(f"solo {len(fs)} hecho(s) de '{slug}' usados el {fecha}")
    return plan.post_from_theme(tema, fs[:2])


def _post_evergreen(slug: str):
    bloque = next(b for b in plan.load_evergreen() if b["id"] == slug)
    return plan.post_from_block(bloque)


def _post_noticia(html: str):
    from pipeline import ada_news
    from pipeline.sources import post_from_article
    url = re.search(r"https://adanews\.ada\.org/[^\"<\s]+", html).group(0)
    art = ada_news.fetch_article(url)
    if not art:
        raise ValueError(f"no se pudo bajar {url}")
    return post_from_article(ada_news.con_cuerpo(art))


def _post_paper(slug: str):
    from pipeline import journals
    from pipeline.sources import post_from_signpost
    pmid = slug.split("-", 1)[1]
    a = next(iter(journals.summarize([pmid])), None)
    if not a:
        raise ValueError(f"PubMed no devolvió {pmid}")
    design, design_es = journals._design(a["type"])
    sp = journals.Signpost(
        pmid=pmid, title=a["title"], journal=a["journal"], year=a["year"],
        url=a["url"], design=design, design_es=design_es,
        n=journals._extract_n(a["abstract"]), abstract=a.get("abstract", ""))
    return post_from_signpost(sp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--todas", action="store_true",
                    help="rehace también las que ya tienen cuerpo (tras "
                         "cambiar el formato de la página)")
    args = ap.parse_args()

    rot = json.loads(Path("data/rotation.json").read_text())
    temas = {t.id for t in CATALOG}
    bloques = {b["id"] for b in plan.load_evergreen()}

    hechas, fallidas = 0, []
    for pagina in sorted(DOCS.glob("*/index.html")):
        slug = pagina.parent.name
        html = pagina.read_text()
        if slug in NO_SON_POSTS or not (args.todas or _vacia(html)):
            continue
        fecha = _fecha(slug, rot)
        print(f"· {slug} ({fecha or 'sin fecha'})")
        if args.dry_run:
            continue
        try:
            if slug in temas:
                with llm.sin_modelo():
                    spec = generate(_post_datos(slug, fecha, rot))
            elif slug in bloques:
                with llm.sin_modelo():
                    spec = generate(_post_evergreen(slug))
            elif slug.startswith("news-"):
                spec = generate(_post_noticia(html))
            elif slug.startswith("paper-"):
                spec = generate(_post_paper(slug))
            else:
                raise ValueError("no se reconoce el tipo de post")
        except Exception as exc:                       # una no frena las demás
            fallidas.append(f"{slug}: {exc}")
            print(f"   ✗ {exc}")
            continue
        spec.slug = slug
        site.write_article(spec, fecha)
        if _vacia(pagina.read_text()):
            fallidas.append(f"{slug}: sigue vacía")
            continue
        hechas += 1
        print("   ✓ rehecha")

    if not args.dry_run:
        site.rebuild_indexes()
    print(f"\n{hechas} página(s) rehechas · {len(fallidas)} con problema")
    for f in fallidas:
        print(f"  ✗ {f}")
    return 1 if fallidas else 0


if __name__ == "__main__":
    sys.exit(main())
