#!/usr/bin/env python3
"""
Que renovar el secreto del token alcance para que el sistema lo use.

El token de Meta dura ~60 días. Una copia refrescada vive cifrada en el caché
del workflow, y esa copia tenía prioridad absoluta sobre el secreto: con el
token de agosto vencido (8-oct-2026), cargar uno nuevo con `gh secret set` no
cambiaba nada, porque el workflow seguía leyendo el viejo.

Sin red: se sustituyen el almacén y el canje.

    python -m tests.test_tokens
"""
from __future__ import annotations

import sys
import time

from publisher import tokens


class _Canje:
    ok = True

    def __init__(self, registro):
        self.registro = registro

    def __call__(self, url, params=None, timeout=None):
        self.registro.append(params["fb_exchange_token"])
        return self

    def json(self):
        return {"access_token": "refrescado", "expires_in": 60 * 24 * 3600}


def _correr(almacen: dict, secreto: str) -> tuple[str, list[str], dict]:
    canjeados: list[str] = []
    reales = tokens._load, tokens._save, tokens.requests.get
    antes = {k: tokens.os.environ.get(k)
             for k in ("META_ACCESS_TOKEN", "META_APP_ID", "META_APP_SECRET")}
    tokens._load = lambda: dict(almacen)
    tokens._save = lambda data: almacen.update(data)
    tokens.requests.get = _Canje(canjeados)
    tokens.os.environ.update(META_ACCESS_TOKEN=secreto, META_APP_ID="1",
                             META_APP_SECRET="2")
    try:
        return tokens.meta_token(), canjeados, almacen
    finally:
        tokens._load, tokens._save, tokens.requests.get = reales
        for k, v in antes.items():
            if v is None:
                tokens.os.environ.pop(k, None)
            else:
                tokens.os.environ[k] = v


def main() -> int:
    errs = []
    lejos = time.time() + 50 * 24 * 3600

    # Copia vieja (sin huella, o de otro secreto) + secreto nuevo.
    for copia in ({"access_token": "viejo", "expires_at": lejos},
                  {"access_token": "viejo", "expires_at": lejos,
                   "semilla": tokens._huella("secreto-de-agosto")}):
        token, canjeados, almacen = _correr({"meta": dict(copia)}, "secreto-nuevo")
        if token == "viejo" or canjeados != ["secreto-nuevo"]:
            errs.append("con el secreto renovado se sigue usando la copia vieja")
        if almacen["meta"].get("semilla") != tokens._huella("secreto-nuevo"):
            errs.append("la copia nueva no recuerda de qué secreto salió")

    # Mismo secreto y copia vigente: se usa la copia, sin salir a la red.
    token, canjeados, _ = _correr(
        {"meta": {"access_token": "copia", "expires_at": lejos,
                  "semilla": tokens._huella("secreto")}}, "secreto")
    if token != "copia" or canjeados:
        errs.append("con el mismo secreto se descarta una copia vigente")

    if errs:
        print("✗ el token de Meta no se renueva bien:\n")
        print("\n".join(f"  {e}" for e in errs))
        return 1
    print("✓ un secreto nuevo reemplaza la copia guardada, y una copia vigente se respeta")
    return 0


if __name__ == "__main__":
    sys.exit(main())
