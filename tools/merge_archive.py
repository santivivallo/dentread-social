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
    arts: dict[str, dict] = {}
    for fuente in (a.get("articles", {}), b.get("articles", {})):
        for url, datos in fuente.items():
            actual = arts.setdefault(url, {})
            # Lo que ya está no se pisa con vacío: un lado puede tener el
            # artículo a medio registrar (solo `skipped`, por ejemplo).
            for k, v in datos.items():
                if v not in (None, "", [], {}) or k not in actual:
                    actual[k] = v
            # Publicado en cualquiera de los dos lados es publicado. Este es
            # el dato que no se puede perder: es el único filtro que evita
            # republicar una nota.
            if datos.get("used") or actual.get("used"):
                actual["used"] = True

    semanas: dict[str, list[str]] = {}
    for fuente in (a.get("weeks", {}), b.get("weeks", {})):
        for semana, urls in fuente.items():
            semanas[semana] = sorted(set(semanas.get(semana, [])) | set(urls))

    return {
        "articles": arts,
        "weeks": semanas,
        "runs": max(a.get("runs", 0), b.get("runs", 0)),
        "deepest_page": max(a.get("deepest_page", 0), b.get("deepest_page", 0)),
    }


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
    print(f"[merge-archive] {len(fusion['articles'])} artículos "
          f"({len(a.get('articles', {}))} + {len(b.get('articles', {}))}), "
          f"{sum(1 for x in fusion['articles'].values() if x.get('used'))} "
          f"publicados")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
