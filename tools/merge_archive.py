#!/usr/bin/env python3
"""
Une dos versiones del archivo de ADA News en vez de declarar conflicto.

**Por qué existe.** Desde que el workflow versiona `data/ada_archive.json`
—necesario, o el flag `used` de la nota publicada se pierde y el mismo
artículo vuelve a salir— hay dos escritores: el bot en cada publicación y
Santi cada vez que corre los tests o un preview localmente. Los dos agregan
artículos al mismo JSON, así que `git pull --rebase` choca:

    CONFLICT (content): Merge conflict in data/ada_archive.json

Resolverlo a mano es absurdo y elegir un lado pierde datos: quedarse con la
versión del bot borra lo que vio el crawl local, y al revés se pierde la marca
de lo que se publicó. Las dos versiones son correctas y el resultado que se
quiere es la suma.

No sirve el `merge=union` de git, que une línea por línea y deja un JSON
inválido. Este driver une por clave:

    articles      unión; si un artículo está en los dos, se conservan las
                  claves de ambos y `used` gana si está en cualquiera
    weeks         unión de las listas de cada semana
    runs          el mayor
    deepest_page  el mayor

Se instala una sola vez por clon:

    git config merge.ada-archive.driver \\
        "python3 tools/merge_archive.py %O %A %B"

`.gitattributes` ya asocia el archivo a este driver, pero git exige que el
comando esté en la config local: un repo no puede traer un driver ejecutable
consigo, por razones obvias de seguridad.

Uso directo (%O base, %A nuestro, %B el otro; el resultado va a %A):

    python3 tools/merge_archive.py base.json nuestro.json otro.json
"""
from __future__ import annotations

import json
import sys


def unir(a: dict, b: dict) -> dict:
    """
    Une por clave, sin saber qué archivo es.

    Sirve para el archivo de ADA (`articles`, `weeks`, `runs`,
    `deepest_page`) y para el de PubMed (`estudios`, `weeks`, `runs`), que
    tienen la misma forma con otros nombres. Escribir un driver por archivo
    garantizaba que el tercero se olvidara.

    Las reglas, por tipo de valor:

        dict de dicts   unión; en los repetidos se conservan las claves de
                        los dos y `used` gana si está en cualquiera
        dict de listas  unión por clave (así se unen las semanas)
        entero          el mayor (contadores y profundidad de crawl)
        lo demás        gana el lado no vacío
    """
    fusion: dict = {}
    for clave in set(a) | set(b):
        va, vb = a.get(clave), b.get(clave)

        if isinstance(va, int) and isinstance(vb, int):
            fusion[clave] = max(va, vb)
            continue

        if isinstance(va, dict) and isinstance(vb, dict):
            juntos: dict = {}
            for fuente in (va, vb):
                for k, datos in fuente.items():
                    if isinstance(datos, list):
                        juntos[k] = sorted(set(juntos.get(k, [])) | set(datos))
                        continue
                    if not isinstance(datos, dict):
                        juntos[k] = datos if datos not in (None, "", [], {}) \
                            else juntos.get(k, datos)
                        continue
                    actual = juntos.setdefault(k, {})
                    # Lo que ya está no se pisa con vacío: un lado puede tener
                    # el registro a medio hacer (solo `skipped`, por ejemplo).
                    for kk, vv in datos.items():
                        if vv not in (None, "", [], {}) or kk not in actual:
                            actual[kk] = vv
                    # Publicado en cualquiera de los dos lados es publicado.
                    # Es el dato que no se puede perder: es el único filtro
                    # que evita republicar lo mismo.
                    if datos.get("used") or actual.get("used"):
                        actual["used"] = True
            fusion[clave] = juntos
            continue

        fusion[clave] = va if va not in (None, "", [], {}) else vb
    return fusion


def _cuantos(d: dict) -> int:
    """Registros en la colección principal, se llame como se llame."""
    for clave in ("articles", "estudios"):
        if isinstance(d.get(clave), dict):
            return len(d[clave])
    return 0


def _usados(d: dict) -> int:
    for clave in ("articles", "estudios"):
        if isinstance(d.get(clave), dict):
            return sum(1 for x in d[clave].values()
                       if isinstance(x, dict) and x.get("used"))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__)
        return 2
    _base, nuestro, otro = argv[1], argv[2], argv[3]
    try:
        a = json.loads(open(nuestro).read())
        b = json.loads(open(otro).read())
    except (OSError, ValueError) as exc:
        # Devolver != 0 deja el conflicto en manos de git, que es lo correcto:
        # es mejor un conflicto que un archivo de estado inventado.
        print(f"[merge-archive] no se pudo leer un lado ({exc}); "
              f"queda el conflicto", file=sys.stderr)
        return 1

    fusion = unir(a, b)
    with open(nuestro, "w") as fh:
        json.dump(fusion, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    print(f"[merge-archive] {_cuantos(fusion)} registros "
          f"({_cuantos(a)} + {_cuantos(b)}), {_usados(fusion)} publicados")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
