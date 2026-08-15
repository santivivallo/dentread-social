"""
Siglas explicadas la primera vez que aparecen en un carrusel.

**Por qué.** Salió publicado un post cuyo frame 1 decía "CDT 2026 trae 60
cambios de código" sin decir en ningún lado qué es CDT. Un dentista en EE.UU.
lo sabe; la cuenta es en español y la lee también gente que administra
clínicas, estudia, o mira desde otro país. Una sigla sin explicar no es un
detalle de estilo: es el punto donde el lector deja de entender y se va.

**Por qué no se arregla escribiendo mejor los hechos.** Los enunciados de
`data/facts.json` están curados y verificados contra su fuente, y meterles la
explicación adentro los alarga justo donde el espacio es escaso. Además la
misma sigla aparece en 11 lugares distintos: explicarla a mano es explicarla
once veces y olvidarse la doceava.

Las glosas son cortas a propósito. No son definiciones de manual: son lo
mínimo para que la frase siguiente se entienda.
"""
from __future__ import annotations

import re

# Sigla → cómo se dice en una línea, para alguien que no está en el rubro.
#
# Se escriben en minúscula y sin punto final: se insertan dentro de una
# oración armada, no como entrada de diccionario.
GLOSAS: dict[str, str] = {
    "CDT": "el catálogo de códigos con que se factura cada procedimiento "
           "dental en EE.UU.",
    "CHIP": "el seguro público de salud para niños en EE.UU.",
    "DSO": "una organización que administra la parte no clínica de varias "
           "clínicas a la vez",
    "CBCT": "la tomografía dental en 3D",
    "FQHC": "un centro de salud comunitario con financiamiento federal",
    "EOB": "el detalle que manda el seguro explicando qué pagó y qué no",
    "PMS": "el software con que la clínica maneja agenda y facturación",
}

# Siglas que no necesitan glosa: o son de conocimiento general, o son parte
# del nombre de la fuente y se entienden por contexto.
CONOCIDAS = {"EE", "UU", "DC", "IA", "AI", "ADA", "OK", "US", "USA", "FDA",
             "HIPAA", "SOC"}

_SIGLA = re.compile(r"\b([A-Z]{2,}(?:[-/][A-Z]{2,})?)\b")


def siglas_en(texto: str) -> list[str]:
    """Siglas presentes que tienen glosa disponible, sin repetir y en orden."""
    vistas: list[str] = []
    for s in _SIGLA.findall(texto or ""):
        base = s.split("/")[0].split("-")[0]
        if base in CONOCIDAS or base not in GLOSAS:
            continue
        if base not in vistas:
            vistas.append(base)
    return vistas


def sin_explicar(texto_del_post: str) -> list[str]:
    """
    Siglas que aparecen y cuya glosa NO está en el post.

    Es lo que mira el test. Se busca un fragmento distintivo de la glosa y no
    la glosa entera, porque el texto puede haberla reformulado.
    """
    faltan = []
    plano = (texto_del_post or "").lower()
    for s in siglas_en(texto_del_post):
        pista = GLOSAS[s].split(",")[0].split(" con ")[0].strip().lower()
        if pista[:22] not in plano:
            faltan.append(s)
    return faltan


def glosa_para(texto: str, *, maximo: int = 1) -> str:
    """
    La línea que explica las siglas de este texto. Vacía si no hace falta.

    `maximo` existe porque dos glosas en un frame lo convierten en un
    glosario. Si un post usa tres siglas, el problema es el post.
    """
    encontradas = siglas_en(texto)[:maximo]
    if not encontradas:
        return ""
    # Nada de .capitalize(): comía las mayúsculas de la propia sigla y de
    # "EE.UU.", y dejaba "ee.uu..". La frase ya empieza con la sigla, que va
    # en mayúscula por definición.
    partes = [f"{s} es {GLOSAS[s].rstrip('.')}" for s in encontradas]
    return "; ".join(partes) + "."
