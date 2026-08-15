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

import sys

from pipeline.plan import load_evergreen
from pipeline.redaccion import UMBRAL_SOLAPE as UMBRAL
from pipeline.redaccion import solape, verificar
from pipeline.themes import CATALOG

# Largo máximo del gancho. A 88px entra en dos líneas de unos 26 caracteres;
# más que eso baja el cuerpo de fuente y deja de leerse de un vistazo.
MAX_HOOK = 52
MAX_KICKER = 24

# --------------------------------------------------------------------------
# El verificador
#
# `redaccion.redactar` le pide los titulares a un modelo, así que la garantía
# no está en lo que el modelo escriba sino en lo que el verificador rechace.
# Un verificador que aprueba todo es peor que no tener modelo: da la impresión
# de control sin ejercerlo. Estos casos corren sin red y sin token.

HECHOS = {"38", "2025", "50", "60"}
CIERRE = "Ampliar cobertura llena la agenda. Terminar el tratamiento es otro problema."

BUENA = {
    "gancho": "Cubrir no es lo mismo que pagar",
    "titular_datos": "Donde hay beneficio, hay visita",
    "lectura": "La cobertura fija el volumen de la agenda, y el reembolso "
               "fija cuánto de ese volumen deja margen.",
}

RECHAZOS = [
    ("cifra inventada",
     {**BUENA, "lectura": "El 73% de las clínicas ya lo aplica."},
     "cifra que no está"),
    ("parafrasea el cierre",
     {**BUENA, "gancho": "Ampliar cobertura llena la agenda"},
     "dicen lo mismo"),
    ("gancho igual al titular",
     {**BUENA, "titular_datos": "Cubrir no es lo mismo que pagar"},
     "dicen lo mismo"),
    ("gancho que no entra",
     {**BUENA, "gancho": "Cubrir a un paciente no es lo mismo que pagarle "
                         "el tratamiento completo al dentista"},
     "el máximo es"),
    ("falta una clave",
     {"gancho": "Cubrir no es lo mismo que pagar", "titular_datos": "", "lectura": "x"},
     "falta"),
    ("em dash",
     {**BUENA, "lectura": "La cobertura fija el volumen — el reembolso, el margen."},
     "em dash"),
    # hook-writer.md, "what doesn't work": corporate framing.
    ("lenguaje corporativo",
     {**BUENA, "lectura": "Una solución integral para optimizar la clínica."},
     "corporativo"),
]


def probar_verificador() -> list[str]:
    errs = []
    fallas = verificar(BUENA, cifras_permitidas=HECHOS, cierre=CIERRE)
    if fallas:
        errs.append(f"el verificador rechaza una propuesta correcta: {fallas}")

    for nombre, prop, esperado in RECHAZOS:
        fallas = verificar(prop, cifras_permitidas=HECHOS, cierre=CIERRE)
        if not fallas:
            errs.append(f"el verificador ACEPTA '{nombre}', que debería rechazar")
        elif not any(esperado in f for f in fallas):
            errs.append(f"'{nombre}' se rechaza por el motivo equivocado: {fallas}")
    return errs


def main() -> int:
    errores: list[str] = probar_verificador()
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

    # Los evergreen, con el mismo criterio.
    #
    # Tenían el problema igual —7 de 15, cuatro al 100%— y no se veía porque
    # el post que lo destapó era de datos. La diferencia es que acá NO
    # interviene el modelo: un evergreen dice qué es DentRead, y eso lo
    # escribe la empresa. Lo único que hace este test es impedir que los tres
    # frames lo digan tres veces.
    for b in load_evergreen():
        cierre = f"{b.get('close', '')} {b.get('close_accent', '')}"
        titulo = b.get("data_title", "")
        v = solape(titulo, cierre)
        if v >= UMBRAL:
            errores.append(
                f"evergreen/{b['id']}: el titular del frame 2 y el cierre "
                f"dicen lo mismo ({v:.0%})\n"
                f"      titular: {titulo}\n"
                f"      cierre : {cierre}")
        if not titulo:
            errores.append(f"evergreen/{b['id']}: sin titular de frame 2")
        if not b.get("close"):
            errores.append(f"evergreen/{b['id']}: sin cierre")

    if errores:
        print(f"✗ {len(errores)} problema(s) de redacción:\n")
        print("\n".join(f"  {e}" for e in errores))
        return 1
    print(f"✓ verificador: acepta lo correcto y rechaza {len(RECHAZOS)} formas "
          f"de fallar")
    print(f"✓ {len(CATALOG)} temas y {len(load_evergreen())} evergreen: los "
          f"tres frames dicen cosas distintas (solape < {UMBRAL:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
