#!/usr/bin/env python3
"""
Avisa a los buscadores que el sitio cambió (IndexNow).

Sin esto Bing descubre una página nueva cuando vuelve a pasar por el sitemap,
que en un sitio chico y nuevo puede ser semanas. Bing importa más de lo que
parece: el buscador de ChatGPT y Copilot se apoyan en su índice. Un aviso por
IndexNow le llega a Bing, Yandex, Seznam y Naver a la vez.

La clave NO es un secreto: el protocolo exige publicarla como archivo en la
raíz del sitio (docs/<clave>.txt), y así el buscador comprueba que el aviso
viene de quien controla el dominio.

    python -m tools.indexnow            # todas las URLs del sitemap
    python -m tools.indexnow --dry-run  # qué mandaría

Lo llama el workflow después de desplegar en Cloudflare Pages. Nunca frena
una publicación: si el aviso falla, el sitemap sigue ahí.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

CLAVE = "5f8389a54eb5542d18d328e285c23db6"
ENDPOINT = "https://api.indexnow.org/indexnow"


def urls() -> list[str]:
    return re.findall(r"<loc>([^<]+)</loc>", Path("docs/sitemap.xml").read_text())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not Path(f"docs/{CLAVE}.txt").exists():
        print(f"✗ falta docs/{CLAVE}.txt: sin el archivo, el buscador rechaza el aviso")
        return 1
    lista = urls()
    # La base sale del propio sitemap y no de `pipeline.site`: así esto corre
    # en el workflow `site`, que solo instala requests.
    base = lista[0].rstrip("/")
    cuerpo = {"host": urlparse(base).netloc, "key": CLAVE,
              "keyLocation": f"{base}/{CLAVE}.txt", "urlList": lista}
    if args.dry_run:
        print(f"[dry-run] {len(lista)} URL(s) a {ENDPOINT}")
        return 0
    try:
        r = requests.post(ENDPOINT, json=cuerpo, timeout=30)
    except requests.RequestException as exc:
        print(f"[indexnow] no se pudo avisar ({exc.__class__.__name__}); el sitemap sigue")
        return 0
    # 200 = recibido; 202 = recibido, la clave se valida después.
    if r.status_code in (200, 202):
        print(f"[indexnow] ✓ {len(lista)} URL(s) avisadas ({r.status_code})")
        return 0
    print(f"[indexnow] respondió {r.status_code}: {r.text[:200]}")
    return 0 if r.status_code == 429 else 1


if __name__ == "__main__":
    sys.exit(main())
