#!/usr/bin/env python3
"""
Orquestador: de cero a carpeta lista para publicar.

    python -m pipeline.run                 # tanda de la semana, 2 posts
    python -m pipeline.run --slots 1
    python -m pipeline.run --theme cdt-sin-codigo-ia
    python -m pipeline.run --inventory     # cuánto contenido queda

Produce por cada post:

    out/2026-08-09-<slug>/
        01.png … 06.png    slides
        post.json          para publish.py
    docs/<slug>/index.html página indexable con schema.org  ← el activo

Después:

    python publish.py out/2026-08-09-<slug> --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from pipeline import plan, site
from pipeline.generate import SinMaterial, generate
from pipeline.plan import Post
from pipeline import render_html
from pipeline.render_html import write_html, frames_for
from pipeline.themes import CATALOG
from publisher import guard

OUT = Path("out")


def run_guard(spec) -> tuple[bool, list[str]]:
    meta = {
        "caption_es": spec.caption_es,
        "commentary_en": spec.commentary_en,
        "title_en": spec.title_en,
        **spec.declarations,
    }
    problems = []
    for label, res in guard.check_post(meta).items():
        problems += [f"{label}: {f.rule.id} → {f.match}"
                     for f in res.findings if f.rule.level in ("BLOCK", "REVIEW")]
    return (not problems), problems


def build_one(post: Post, today: str, *, preview: bool = False) -> Path | None:
    print(f"\n[{post.kind}] {post.title}")
    print(f"   hechos: {', '.join(post.fact_ids())}")

    try:
        spec = generate(post)
    except SinMaterial as exc:
        # No es un fallo: esa fuente no tiene con qué hoy. Sale como aviso y
        # el ciclo prueba la siguiente, igual que cuando ADA no publicó nada
        # relevante. Antes esto no existía y una noticia sin resumen salía
        # igual, con el titular en inglés como único contenido del frame 2.
        print(f"   SIN MATERIAL · {exc}")
        return None
    except ValueError as exc:
        print(f"   ABORTA · {exc}")
        return None

    ok, problems = run_guard(spec)
    if not ok:
        for p in problems:
            print(f"   BLOQUEADO · {p}")
        return None

    folder = OUT / f"{today}-{spec.slug}"
    html_files = write_html(frames_for(spec), folder)
    render_html.render(html_files)
    (folder / "post.json").write_text(json.dumps({
        "slug": spec.slug, "mode": spec.mode, "redaccion": spec.redaccion,
        **spec.declarations,
        "caption_es": spec.caption_es, "commentary_en": spec.commentary_en,
        "title_en": spec.title_en, "citations": spec.citations,
        "fact_ids": post.fact_ids(),
        "article_url": f"{site.BASE_URL}/{spec.slug}/",
    }, indent=2, ensure_ascii=False))

    # En preview no se escribe la pagina ni se marca el tema como usado.
    #
    # Correr el pipeline localmente para mirar como quedan los slides dejaba
    # el arbol sucio: paginas nuevas en docs/ y rotation.json modificado. Eso
    # choca con los commits que hace el bot en cada corrida del cron y traba
    # el proximo rebase. Un preview solo deberia producir imagenes.
    if preview:
        print(f"   OK · {len(spec.slides)} slides → {folder}  (preview)")
        return folder

    page = site.write_article(spec, today)
    plan.mark_used(post)

    print(f"   OK · {len(spec.slides)} slides → {folder}")
    print(f"        página → {page}")
    return folder


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slots", type=int, default=2)
    ap.add_argument("--theme")
    ap.add_argument("--inventory", action="store_true")
    ap.add_argument("--preview", action="store_true",
                    help="solo genera los PNG: no escribe docs/ ni consume "
                         "el tema. Para mirar como queda sin ensuciar el repo")
    args = ap.parse_args()

    if args.inventory:
        inv = plan.inventory()
        for k, v in inv.items():
            print(f"  {k.replace('_', ' '):<24} {v}")
        if inv["semanas_de_runway"] < 4:
            print("\n  ⚠ menos de 4 semanas de contenido: curar más hechos")
        return

    if args.theme:
        match = [t for t in CATALOG if t.id == args.theme]
        if not match:
            sys.exit(f"[error] tema desconocido: {args.theme}")
        t = match[0]
        state = plan._state()
        fs = plan.facts_for(t.id, state)
        if len(fs) < 2:
            sys.exit(f"[error] '{t.id}' no tiene 2 hechos disponibles hoy")
        # Vía `plan.post_from_theme`, NO armando el Post a mano.
        #
        # Acá había una tercera copia de esa construcción y le faltaban close,
        # close_accent, data_title, kicker y hook: todo lo que se le fue
        # agregando al tema después de que se escribió. El síntoma fue que
        # `--theme` abortaba con "no trae cierre" mientras la corrida normal
        # funcionaba, o sea que el camino que se usa para revisar un post a
        # mano era el único roto.
        posts = [plan.post_from_theme(t, fs)]
    else:
        # Se piden dos de más: son los reemplazos si alguno se cae al
        # construirse. Pedirlos no consume nada — el tema se marca como usado
        # recién en `build_one`, cuando el post existe de verdad.
        posts = plan.next_posts(args.slots + 2)

    if not posts:
        sys.exit("[error] no hay nada publicable. Correr --inventory")

    today = date.today().isoformat()

    # Se construye hasta juntar los posts pedidos, no hasta agotar la lista.
    #
    # Antes se pedían exactamente `slots` posts y se intentaba construir esos.
    # Si uno se caía —el guard lo bloqueó, la noticia no tenía resumen, el
    # modelo no dio nada publicable— el día se perdía, aunque hubiera material
    # de sobra en las otras fuentes. Un candidato rechazado no es una razón
    # para no publicar: es una razón para probar el siguiente.
    #
    # El margen es chico a propósito. Si hacen falta más de dos reemplazos, el
    # problema no es el candidato sino el generador, y ahí conviene que la
    # corrida termine en rojo y se mire.
    made: list[Path] = []
    descartados = 0
    for post in posts:
        if len(made) >= args.slots:
            break
        carpeta = build_one(post, today, preview=args.preview)
        if carpeta:
            made.append(carpeta)
        else:
            descartados += 1

    if descartados:
        print(f"\n[reemplazos] {descartados} candidato(s) descartado(s), "
              f"cubiertos con la fuente siguiente del ciclo")

    if not args.preview:
        site.rebuild_indexes()

    print(f"\n[resumen] {len(made)}/{args.slots} listos")
    for f in made:
        print(f"   python publish.py {f} --dry-run")
    inv = plan.inventory()
    print(f"[inventario] {inv['temas_publicables']} temas · "
          f"{inv['hechos_disponibles']}/{inv['hechos_totales']} hechos · "
          f"~{inv['semanas_de_runway']} semanas de runway")
    if not made:
        sys.exit(1)


if __name__ == "__main__":
    main()
