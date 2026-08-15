#!/usr/bin/env python3
"""
Que el que elige, elija bien.

El sistema tomaba la PRIMERA propuesta que no fallaba. "No falla" no es
"buena": así salió publicado "Expansión del beneficio y aranceles", que cumple
todas las reglas duras y no dice nada. Ahora se piden varios candidatos y se
elige el mejor, que es el best-of-N clásico.

**Esto es el paso 0, no el último.** Un agente que genera N candidatos y no
sabe cuál es bueno no mejoró nada: gastó N veces más. La ganancia de pedir más
candidatos está limitada por lo que el selector pueda distinguir, así que el
selector se mide ANTES de escalar la generación.

El set son casos reales de esta sesión, no inventados: a la izquierda lo que
Santiago aprobó o lo que ya estaba en el catálogo, a la derecha lo que rechazó
o lo que salió publicado y hubo que arreglar. Es chico —14 pares— y eso hay
que decirlo: alcanza para detectar un selector roto, no para afirmar que el
selector es bueno.

    python -m tests.test_seleccion
"""
from __future__ import annotations

import sys

from pipeline.redaccion import puntuar

CIERRE = "Ampliar cobertura llena la agenda. Terminar el tratamiento es otro problema."
HECHOS = ("En 2025, 38 estados y Washington DC ofrecen beneficios dentales "
          "ampliados para adultos en Medicaid. En la mayoría de los estados el "
          "reembolso de Medicaid queda por debajo del 50% del honorario.")

# (mejor, peor, por qué)
#
# El "peor" de cada par PASA el verificador: son publicables. La diferencia es
# de calidad, que es justo lo que el verificador no mide.
PARES = [
    ("Cubrir no es lo mismo que pagar",
     "Expansión del beneficio y aranceles",
     "contraste contra etiqueta de sección"),
    ("Estar cubierto no alcanza",
     "Los niños son el grupo mejor cubierto",
     "abre una brecha contra enunciar y cerrarla"),
    ("Nadie manda en este mercado",
     "Dónde va cada dólar dental",
     "tensión contra rótulo de tema"),
    ("Nadie compró un CBCT para esto",
     "Cada año se toman más volúmenes",
     "escena contra dato plano"),
    ("Nadie viene por la encía",
     "La enfermedad más común de la boca",
     "brecha contra definición"),
    ("Producir no es cobrar",
     "La economía de la clínica dental",
     "contraste contra título de capítulo"),
    ("Al hospital por una muela",
     "Visitas a urgencias por causas dentales",
     "escena concreta contra descripción"),
    ("El software mide a los que ya van",
     "Utilización de servicios dentales",
     "reencuadre contra nomenclatura"),
    ("La primera barrera no es clínica",
     "Barreras de acceso a la atención",
     "brecha contra enumeración"),
    ("Nada nuevo en el sillón",
     "Actualización de códigos CDT 2026",
     "intriga contra anuncio"),
    ("Entusiasmo afuera, cautela adentro",
     "Percepción de la IA en odontología",
     "contraste contra sustantivo abstracto"),
    ("La compra la firma la administración",
     "Adopción tecnológica en clínicas",
     "concreto contra abstracción corporativa"),
    ("Cada vacante cuesta agenda",
     "Escasez de personal auxiliar",
     "consecuencia contra rótulo"),
    ("Medicare no cubre al dentista",
     "Cobertura dental en adultos mayores",
     "hecho con filo contra descripción neutra"),
]


def main() -> int:
    aciertos, fallos = 0, []
    for mejor, peor, motivo in PARES:
        pm = puntuar({"gancho": mejor, "titular_datos": "Donde hay beneficio, hay visita"},
                     cierre=CIERRE, hechos_texto=HECHOS)
        pp = puntuar({"gancho": peor, "titular_datos": "Donde hay beneficio, hay visita"},
                     cierre=CIERRE, hechos_texto=HECHOS)
        if pm > pp:
            aciertos += 1
        else:
            fallos.append(f"{mejor!r} ({pm:.1f}) no le gana a {peor!r} ({pp:.1f})"
                          f"\n      esperado: {motivo}")

    tasa = aciertos / len(PARES)
    print(f"selector: {aciertos}/{len(PARES)} pares bien ordenados ({tasa:.0%})")
    if fallos:
        print()
        print("\n".join(f"  ✗ {f}" for f in fallos))

    # El umbral es 70%, no 100%, y es deliberado.
    #
    # Un selector perfecto sobre 14 pares escritos por la misma persona que
    # escribió el selector no prueba nada: prueba que se memorizó el set. Lo
    # que interesa es que ordene mejor que una moneda por un margen claro. Si
    # sube a 100% conviene sospechar, no celebrar.
    if tasa < 0.70:
        print(f"\n✗ el selector ordena peor que el umbral de 70%: elegir entre "
              f"varios candidatos no está agregando nada")
        return 1
    print("✓ el selector distingue calidad por encima del umbral")
    return 0


if __name__ == "__main__":
    sys.exit(main())
