#!/usr/bin/env python3
"""
Que no se pueda cambiar QUÉ MIDE una cifra.

El caso real: los hechos dicen que el reembolso de Medicaid queda bajo el 50%
de lo que cobra el dentista, y el modelo escribió "cubriendo solo una fracción
del costo operativo real". Honorario no es costo. El número está bien, la cita
está bien, y la frase es falsa.

El control se aplica SOLO a la "lectura": la frase que interpreta las cifras,
que es donde vive la afirmación factual y donde ocurrió el fallo. Los ganchos
y los cierres quedan afuera a propósito. Son cortos y retóricos, y uno puede
apuntar legítimamente a algo que la fuente no mide: "Terminar el tratamiento
es otro problema" es exactamente eso, y es un cierre que Santi aprobó.

Este test mide las dos direcciones, y las dos importan:

  FALSOS NEGATIVOS  desvíos que se dejan pasar → se publica algo falso.
  FALSOS POSITIVOS  paráfrasis legítimas que se rechazan → se descarta texto
                    bueno y el post cae al curado.

El segundo grupo son textos que efectivamente se generaron o se aprobaron en
esta sesión, no ejemplos cómodos escritos para que pasen.

    python -m tests.test_referentes
"""
from __future__ import annotations

import sys

from pipeline.referentes import desvios

FUENTE_MEDICAID = (
    "En la mayoría de los estados, el reembolso de Medicaid queda muy por "
    "debajo del 50% de lo que cobra el dentista y del 60% de lo que paga el "
    "seguro privado. En 2025, 38 estados y Washington DC ofrecen beneficios "
    "dentales ampliados para adultos en Medicaid."
)
FUENTE_PREVENCION = (
    "El 45% de los adultos no fue al dentista en el último año. La limpieza "
    "preventiva es el servicio con mayor cobertura en los planes dentales."
)
FUENTE_IMAGEN = (
    "La concordancia entre lectores en la detección de caries proximales "
    "varía entre estudios. El diagnóstico radiográfico depende del lector."
)

# Una noticia real de ADA News, para el camino de resúmenes. Este camino
# estuvo sin control hasta que se notó que era el que más lo necesita: el
# lector no tiene el artículo delante, así que un desvío no se contrasta con
# nada.
FUENTE_NOTICIA = (
    "The ADA is calling out UnitedHealthcare over its credentialing portal, "
    "which the association says has doubled the paperwork dentists must "
    "submit to stay in network. The ADA asked the insurer to simplify the "
    "process and restore the previous submission flow."
)

# (texto, fuente, motivo). Todos DEBEN ser rechazados.
DESVIOS = [
    ("Los aranceles de Medicaid cubren solo una fracción del costo operativo real.",
     FUENTE_MEDICAID,
     "el caso que salió publicado: honorario contado como costo"),
    ("La cobertura amplia mejora la rentabilidad de la clínica.",
     FUENTE_MEDICAID,
     "de reembolso a margen, que nadie midió"),
    ("Más cobertura significa más visitas al dentista.",
     FUENTE_MEDICAID,
     "cobertura contada como uso: es justo la brecha que el post discute"),
    ("La lectura radiográfica define qué tratamiento se hace.",
     FUENTE_IMAGEN,
     "de diagnóstico a tratamiento, que además es riesgo regulatorio"),
    ("Hay menos dentistas por hora de agenda disponible.",
     FUENTE_PREVENCION,
     "inventa una magnitud de capacidad que la fuente no mide"),
    ("El nuevo portal reduce el reembolso que reciben los dentistas.",
     FUENTE_NOTICIA,
     "la nota habla de papeleo, no de pagos"),
    ("El cambio mejora el diagnóstico en la red del asegurador.",
     FUENTE_NOTICIA,
     "la nota no mide diagnóstico"),
]

# (texto, fuente, motivo). Todos DEBEN pasar.
LEGITIMOS = [
    ("El reembolso de Medicaid no llega a la mitad de lo que cobra el dentista.",
     FUENTE_MEDICAID,
     "paráfrasis directa, misma magnitud"),
    ("Los aranceles públicos quedan lejos de los honorarios privados.",
     FUENTE_MEDICAID,
     "arancel y honorario son la misma familia"),
    ("Cubrir no es lo mismo que pagar.",
     FUENTE_MEDICAID,
     "el gancho que Santi aprobó"),
    ("Casi la mitad de los adultos no pisó una consulta en el año.",
     FUENTE_PREVENCION,
     "visita y consulta son la misma familia"),
    ("El servicio más cubierto es el que menos se completa.",
     FUENTE_PREVENCION,
     "habla de cobertura, que la fuente nombra"),
    ("Dos lectores pueden ver cosas distintas en la misma radiografía.",
     FUENTE_IMAGEN,
     "diagnóstico y lectura, misma familia"),
    ("La ADA pidió simplificar un portal que duplicó el papeleo de los "
     "dentistas para seguir en la red.",
     FUENTE_NOTICIA,
     "resumen fiel de la noticia, sin magnitudes nuevas"),
]


def main() -> int:
    fn, fp = [], []

    for texto, fuente, motivo in DESVIOS:
        if not desvios(texto, fuente):
            fn.append(f"NO detecta: {texto!r}\n      {motivo}")

    for texto, fuente, motivo in LEGITIMOS:
        d = desvios(texto, fuente)
        if d:
            fp.append(f"rechaza de más: {texto!r} por {d}\n      {motivo}")

    print(f"desvíos detectados : {len(DESVIOS) - len(fn)}/{len(DESVIOS)}")
    print(f"legítimos aceptados: {len(LEGITIMOS) - len(fp)}/{len(LEGITIMOS)}")

    if fn or fp:
        print()
        print("\n".join(f"  ✗ {x}" for x in fn + fp))

    # Los dos lados se exigen al 100%, y eso solo es razonable porque el set
    # es chico y concreto. Si más adelante hay que aflojar uno, que sea el de
    # detección: dejar pasar un desvío publica algo falso, rechazar de más
    # solo cuesta un candidato de cuatro.
    if fn or fp:
        return 1
    print("✓ distingue cambio de magnitud de paráfrasis legítima")
    return 0


if __name__ == "__main__":
    sys.exit(main())
