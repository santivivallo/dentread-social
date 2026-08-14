#!/usr/bin/env python3
"""
Contraste y tamaño de texto: se verifica, no se confía.

Existe porque personas reales miraron los primeros carruseles y dijeron que
costaba leerlos. Medido: el gris secundario daba 3,2:1 sobre el fondo oscuro
—WCAG AA pide 4,5:1— y el cuerpo quedaba en 8 pt al verse en un teléfono.
Ninguna de las dos cosas se nota mirando el PNG en un monitor grande.

    python -m tests.test_legibility

Devuelve 1 si algo no llega al mínimo. Corre en CI.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "pipeline" / "render_html.py"

# El lienzo mide 1440 px de ancho y en el feed de Instagram se ve a unos
# 390 pt. Todo lo que se dibuja encoge a poco más de un cuarto.
SCALE = 0.271

# Mínimos en pt percibidos. El cuerpo apunta a 14: por debajo de 12 la
# lectura deja de ser cómoda en un teléfono sostenido a distancia normal.
MIN_PT = {
    "S_H1": 20.0,
    "S_SUB": 13.0,      # cuerpo
    "S_LABEL": 11.0,    # etiqueta junto a una cifra
    "S_SRC": 8.5,       # fuente al pie
    "S_FOOT": 7.5,      # señalética: número de frame, "Desliza"
    "S_KICKER": 6.5,    # mayúsculas con tracking amplio, tolera menos
}


def _hex(name: str, src: str) -> str:
    m = re.search(rf'^{name} = "(#[0-9A-Fa-f]{{6}})"', src, re.M)
    if not m:
        raise SystemExit(f"no se encontró el color {name} en render_html.py")
    return m.group(1)


def _px(name: str, src: str) -> int:
    m = re.search(rf"^{name} = (\d+)", src, re.M)
    if not m:
        raise SystemExit(f"no se encontró el tamaño {name} en render_html.py")
    return int(m.group(1))


def _luminance(h: str) -> float:
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def main() -> int:
    src = SRC.read_text()
    c = lambda n: _hex(n, src)
    problems: list[str] = []

    # (qué, frente, fondo, mínimo WCAG)
    # 4.5 para texto normal; 3.0 para texto grande y elementos gráficos.
    pares = [
        ("cuerpo sobre oscuro", "SLATE_ON_DARK", "MIDNIGHT", 4.5),
        ("cuerpo sobre claro", "SLATE", "MIST", 4.5),
        ("titular sobre oscuro", "MIST", "MIDNIGHT", 4.5),
        ("titular sobre claro", "NAVY", "MIST", 4.5),
        ("acento sobre oscuro", "CYAN_DARK", "MIDNIGHT", 3.0),
        ("acento sobre claro", "CYAN_TEXT", "MIST", 3.0),
    ]
    print("Contraste")
    for label, fg, bg, need in pares:
        r = contrast(c(fg), c(bg))
        ok = r >= need
        print(f"  {'✓' if ok else '✗'} {label:<22} {r:5.2f}:1  (mínimo {need})")
        if not ok:
            problems.append(f"{label}: {r:.2f}:1, hace falta {need}:1")

    print("\nTamaño percibido en teléfono")
    for name, minimum in MIN_PT.items():
        pt = _px(name, src) * SCALE
        ok = pt >= minimum
        print(f"  {'✓' if ok else '✗'} {name:<9} {pt:4.1f} pt  (mínimo {minimum})")
        if not ok:
            problems.append(f"{name}: {pt:.1f} pt, hace falta {minimum} pt")

    if problems:
        print(f"\n✗ {len(problems)} problema(s) de legibilidad:")
        for p in problems:
            print(f"  {p}")
        return 1
    print("\n✓ contraste y tamaños dentro de lo legible sin esfuerzo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
