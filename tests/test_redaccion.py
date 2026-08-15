#!/usr/bin/env python3
"""
Que los tres frames digan tres cosas distintas.

Existe por un post publicado. `prevencion` decía, en orden:

    frame 1   Lo preventivo es lo más cubierto y lo menos completado
    frame 2   Lo más cubierto y lo menos completado
    frame 3   Lo preventivo se cubre y no se completa

Las tres frases son ciertas y ninguna rompe nada. El carrusel igual no
avanza: gira. Santiago lo describió como "no veo un hook claro", y la causa
era mecánica —el titular del frame 1 salía de partir el ángulo del tema en el
primer punto, así que el gancho era la tesis, y la tesis es justamente lo que
el frame 2 y el cierre vuelven a decir con otras palabras.

Medido sobre los 22 temas, 14 tenían el problema. Por eso esto no es una
revisión editorial sino un test: la repetición no se ve leyendo un post, se ve
comparando los tres frames del mismo post, y eso lo hace mejor una máquina.

El umbral es 0,40 de solapamiento de palabras de contenido entre cualquier par
de los tres. Es holgado a propósito: dos frames del mismo post COMPARTEN tema
y van a compartir vocabulario. Lo que se persigue es la paráfrasis, no la
coherencia.

    python -m tests.test_redaccion
"""
from __future__ import annotations

import re
import sys
import unicodedata

from pipeline.themes import CATALOG

UMBRAL = 0.40

# Palabras de función que aparecen en cualquier frase y no dicen de qué habla.
VACIAS = {"donde", "cuando", "sobre", "entre", "para", "desde", "cada",
          "como", "esta", "este", "esto", "pero", "mientras", "todo", "toda"}

# Largo máximo del gancho. A 88px entra en dos líneas de unos 26 caracteres;
# más que eso baja el cuerpo de fuente y deja de leerse de un vistazo.
MAX_HOOK = 52
MAX_KICKER = 24


def palabras(texto: str) -> set[str]:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return set(re.findall(r"[a-z]{4,}", t)) - VACIAS


def solape(a: str, b: str) -> float:
    """
    Proporción de la frase MÁS CORTA que reaparece en la otra.

    Se divide por el mínimo y no por la unión a propósito: un titular de tres
    palabras metido entero dentro de uno de doce es exactamente el caso que
    hay que atrapar, y con Jaccard daría un número bajo y tranquilizador.
    """
    A, B = palabras(a), palabras(b)
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))


def main() -> int:
    errores: list[str] = []
    for t in CATALOG:
        cierre = f"{t.close} {t.close_accent}"
        pares = (
            ("gancho", t.hook, "titular del frame 2", t.data_title),
            ("gancho", t.hook, "cierre", cierre),
            ("titular del frame 2", t.data_title, "cierre", cierre),
        )
        for na, a, nb, b in pares:
            v = solape(a, b)
            if v >= UMBRAL:
                errores.append(
                    f"{t.id}: el {na} y el {nb} dicen lo mismo ({v:.0%})\n"
                    f"      {na:20}: {a}\n"
                    f"      {nb:20}: {b}")

        if not t.hook:
            errores.append(f"{t.id}: sin gancho propio")
        elif len(t.hook) > MAX_HOOK:
            errores.append(f"{t.id}: gancho de {len(t.hook)} chars "
                           f"(máximo {MAX_HOOK}): {t.hook}")
        if not t.kicker:
            errores.append(f"{t.id}: sin etiqueta de tema")
        elif len(t.kicker) > MAX_KICKER:
            errores.append(f"{t.id}: etiqueta de {len(t.kicker)} chars "
                           f"(máximo {MAX_KICKER}): {t.kicker}")

    # El gancho tampoco puede repetirse ENTRE temas: dos posts distintos que
    # abren igual se leen como el mismo post.
    vistos: dict[str, list[str]] = {}
    for t in CATALOG:
        vistos.setdefault(t.hook.lower().strip(), []).append(t.id)
    for texto, quienes in vistos.items():
        if len(quienes) > 1:
            errores.append(f"gancho repetido en {quienes}: \"{texto}\"")

    if errores:
        print(f"✗ {len(errores)} problema(s) de redacción:\n")
        print("\n".join(f"  {e}" for e in errores))
        return 1
    print(f"✓ {len(CATALOG)} temas: gancho, datos y cierre dicen cosas "
          f"distintas (solape < {UMBRAL:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
