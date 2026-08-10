#!/usr/bin/env python3
"""
Canjea el token corto de Meta por uno de larga duración y lo escribe en .env.

El token que devuelve el Explorador de la API Graph dura una o dos horas.
Para publicar sin intervención hace falta uno de ~60 días, que se obtiene
intercambiando el corto contra el par app_id/app_secret.

Se hace acá y no a mano con curl por una razón concreta: un token pegado en
una terminal queda en el historial del shell, y el historial no se cifra.
Este script lee el corto de .env, lo canjea, escribe el largo de vuelta en
.env y borra la línea del corto. Nada se imprime en pantalla.

    # en .env:
    #   META_APP_ID=...
    #   META_APP_SECRET=...
    #   META_SHORT_TOKEN=<pegar el del Explorador>
    python -m tools.exchange_meta_token

Después: python -m tools.check_credentials --only meta
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

GRAPH = "https://graph.facebook.com/v21.0"
ENV = Path(".env")


def _fail(msg: str) -> None:
    print(f"✗ {msg}")
    sys.exit(1)


def _upsert(text: str, key: str, value: str) -> str:
    """Reemplaza KEY=... si existe; si no, lo agrega al final."""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    if pattern.search(text):
        return pattern.sub(f"{key}={value}", text)
    return text.rstrip("\n") + f"\n{key}={value}\n"


def main() -> None:
    load_dotenv()

    if not ENV.exists():
        _fail("No hay .env en este directorio. Copiá .env.example primero.")

    app_id = os.environ.get("META_APP_ID")
    secret = os.environ.get("META_APP_SECRET")
    short = os.environ.get("META_SHORT_TOKEN")

    missing = [k for k, v in
               [("META_APP_ID", app_id), ("META_APP_SECRET", secret),
                ("META_SHORT_TOKEN", short)] if not v]
    if missing:
        _fail(f"Faltan en .env: {', '.join(missing)}")

    r = requests.get(
        f"{GRAPH}/oauth/access_token",
        params={"grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": secret,
                "fb_exchange_token": short},
        timeout=30,
    )
    data = r.json()

    if "access_token" not in data:
        err = data.get("error", {})
        _fail(f"Meta rechazó el canje: {err.get('message', r.text[:200])}")

    long_token = data["access_token"]
    expires = int(data.get("expires_in", 0))

    # Verificar contra la cuenta correcta ANTES de guardar: un token válido
    # de la cuenta equivocada pasa cualquier chequeo de sintaxis.
    ig_id = os.environ.get("IG_USER_ID")
    if ig_id:
        v = requests.get(f"{GRAPH}/{ig_id}",
                         params={"fields": "username",
                                 "access_token": long_token}, timeout=30).json()
        user = v.get("username")
        if user != "dentread_":
            _fail(f"El token no da acceso a @dentread_ (devolvió {user!r}). "
                  "No se guardó nada.")
        print(f"  ✓ el token resuelve @{user}")

    text = ENV.read_text()
    text = _upsert(text, "META_ACCESS_TOKEN", long_token)
    # el corto ya no sirve para nada y es un secreto de menos que cuidar
    text = re.sub(r"^META_SHORT_TOKEN=.*$\n?", "", text, flags=re.M)
    ENV.write_text(text)
    ENV.chmod(0o600)

    if expires:
        until = datetime.now() + timedelta(seconds=expires)
        print(f"  ✓ META_ACCESS_TOKEN guardado · vence {until:%d %b %Y} "
              f"({expires // 86400} días)")
    else:
        print("  ✓ META_ACCESS_TOKEN guardado · sin fecha de expiración")
    print("  ✓ META_SHORT_TOKEN borrado de .env")
    print("\nVerificá con: python -m tools.check_credentials --only meta")


if __name__ == "__main__":
    main()
