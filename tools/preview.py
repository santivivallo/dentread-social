#!/usr/bin/env python3
"""
Abre los slides al tamaño exacto que van a tener en el feed.

Mirar un PNG de 1440x1800 en un monitor engaña: todo se ve grande y legible.
En el feed de Instagram esa imagen se muestra a unos 390 pt de ancho, o sea
poco más de un cuarto. Un cuerpo de 30 px queda en 8 pt y las fuentes al pie
en 4,6 pt, que es donde estaba el problema de legibilidad.

Esto arma una página con los slides a 390 px reales, al lado de la versión
grande. No hace falta pasar nada al teléfono para juzgarlo.

    python -m tools.preview                       # la carpeta más reciente
    python -m tools.preview out/2026-08-14-slug
"""
from __future__ import annotations

import subprocess
import sys
import webbrowser
from pathlib import Path

# Ancho al que Instagram muestra la imagen en el feed de un teléfono actual.
PHONE_PT = 390


def _latest() -> Path:
    folders = sorted(Path("out").glob("*/"), key=lambda p: p.stat().st_mtime)
    if not folders:
        sys.exit("No hay nada en out/. Corré: python -m pipeline.run --slots 1 --preview")
    return folders[-1]


def build(folder: Path) -> Path:
    slides = sorted(folder.glob("slide-*.png"))
    if not slides:
        sys.exit(f"No hay slide-*.png en {folder}. ¿Falta renderizar?")

    feed = "".join(
        f'<img src="{p.name}" alt="{p.stem}">' for p in slides
    )
    full = "".join(
        f'<figure><img src="{p.name}" alt="{p.stem}">'
        f'<figcaption>{p.stem} · 1440x1800</figcaption></figure>'
        for p in slides
    )

    html = f"""<!doctype html><html lang="es"><meta charset="utf-8">
<title>Vista previa · {folder.name}</title>
<style>
 body{{margin:0;background:#111;color:#eee;
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
 .wrap{{max-width:1100px;margin:0 auto;padding:40px 24px 80px}}
 h1{{font-size:1.3rem;margin:0 0 4px}}
 p.note{{color:#9aa7b4;margin:0 0 36px}}
 h2{{font-size:.95rem;color:#9aa7b4;font-weight:600;margin:44px 0 14px;
  text-transform:uppercase;letter-spacing:.08em}}
 .feed{{display:flex;gap:14px;flex-wrap:wrap}}
 .feed img{{width:{PHONE_PT}px;height:auto;border-radius:10px;
  box-shadow:0 2px 14px rgba(0,0,0,.6)}}
 .full{{display:flex;gap:20px;flex-wrap:wrap;margin-top:10px}}
 figure{{margin:0}}
 .full img{{width:340px;height:auto;border-radius:8px;opacity:.9}}
 figcaption{{color:#7a8492;font-size:.78rem;margin-top:6px}}
 .ruler{{margin-top:10px;color:#7a8492;font-size:.8rem}}
</style>
<div class="wrap">
<h1>{folder.name}</h1>
<p class="note">Arriba, el tamaño real en el feed ({PHONE_PT} px de ancho).
Si algo no se lee acá, tampoco se lee en el teléfono.</p>

<h2>Tamaño real en el feed</h2>
<div class="feed">{feed}</div>
<p class="ruler">Cada imagen mide 1440 px y se muestra a {PHONE_PT}:
todo encoge a un {PHONE_PT / 1440:.0%}.</p>

<h2>Tamaño de trabajo (referencia)</h2>
<div class="full">{full}</div>
</div>
</html>"""

    out = folder / "_preview.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else _latest()
    page = build(folder)
    print(f"  {page}")
    # `open` en macOS respeta el navegador por defecto; webbrowser es el
    # respaldo para cualquier otro sistema.
    try:
        subprocess.run(["open", str(page)], check=True)
    except Exception:
        webbrowser.open(page.resolve().as_uri())


if __name__ == "__main__":
    main()
