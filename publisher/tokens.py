"""
Token store con refresh automático.

Meta:     token de larga duración (~60 días). Se refresca intercambiándolo
          por otro de larga duración antes de expirar.
LinkedIn: access token 60 días + refresh token 365 días. El refresh token
          solo se emite si tu app tiene habilitado "Refresh Tokens"; si no,
          hay que rehacer OAuth manualmente cada 60 días.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken

STORE = Path(os.environ.get("TOKEN_STORE", ".tokens.enc"))
GRAPH = "https://graph.facebook.com/v21.0"
REFRESH_MARGIN = 7 * 24 * 3600  # refrescar 7 días antes de expirar


def _cipher() -> Fernet:
    """
    El token store se cifra en reposo. Motivo concreto: en CI se persiste
    entre corridas (cache o artifact), y el caché de GitHub Actions es
    legible por cualquier workflow del repo. Un refresh token de LinkedIn
    dura 365 días — en claro ahí es un pasivo de un año.

    Generar la clave una vez:
        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    y guardarla como secret TOKEN_STORE_KEY.
    """
    key = os.environ.get("TOKEN_STORE_KEY")
    if not key:
        raise RuntimeError(
            "Falta TOKEN_STORE_KEY. Generala con:\n"
            "  python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def _load() -> dict:
    if not STORE.exists():
        return {}
    try:
        return json.loads(_cipher().decrypt(STORE.read_bytes()))
    except InvalidToken:
        raise RuntimeError(
            f"No se pudo descifrar {STORE}: TOKEN_STORE_KEY no coincide. "
            "Si rotaste la clave, borrá el store y rehacé OAuth."
        )


def _save(data: dict) -> None:
    STORE.write_bytes(_cipher().encrypt(json.dumps(data).encode()))
    STORE.chmod(0o600)


# --------------------------------------------------------------------------

def meta_token() -> str:
    data = _load().get("meta", {})
    token = data.get("access_token") or os.environ["META_ACCESS_TOKEN"]
    expires_at = data.get("expires_at", 0)

    if expires_at and expires_at - time.time() > REFRESH_MARGIN:
        return token

    r = requests.get(
        f"{GRAPH}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": os.environ["META_APP_ID"],
            "client_secret": os.environ["META_APP_SECRET"],
            "fb_exchange_token": token,
        },
        timeout=30,
    )
    # No usar raise_for_status(): mete la URL en el mensaje, y acá el token
    # y el app secret viajan como query params. Ver publisher/instagram.py.
    if not r.ok:
        try:
            msg = r.json().get("error", {}).get("message", "")[:200]
        except ValueError:
            msg = r.text[:200]
        raise RuntimeError(f"Meta rechazó el refresh del token ({r.status_code}): {msg}")
    payload = r.json()
    new = payload["access_token"]
    store = _load()
    store["meta"] = {
        "access_token": new,
        "expires_at": time.time() + payload.get("expires_in", 60 * 24 * 3600),
    }
    _save(store)
    return new


def linkedin_token() -> str:
    data = _load().get("linkedin", {})
    token = data.get("access_token") or os.environ.get("LINKEDIN_ACCESS_TOKEN")
    refresh = data.get("refresh_token") or os.environ.get("LINKEDIN_REFRESH_TOKEN")
    expires_at = data.get("expires_at", 0)

    if token and (not expires_at or expires_at - time.time() > REFRESH_MARGIN):
        return token

    if not refresh:
        raise RuntimeError(
            "Access token de LinkedIn vencido y no hay refresh token. "
            "Rehacé el flujo OAuth manualmente."
        )

    r = requests.post(
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": os.environ["LINKEDIN_CLIENT_ID"],
            "client_secret": os.environ["LINKEDIN_CLIENT_SECRET"],
        },
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    store = _load()
    store["linkedin"] = {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", refresh),
        "expires_at": time.time() + payload.get("expires_in", 60 * 24 * 3600),
    }
    _save(store)
    return payload["access_token"]


def days_left() -> dict[str, float]:
    """Para alertar antes de que se caiga la automatización en silencio."""
    store = _load()
    out = {}
    for k in ("meta", "linkedin"):
        exp = store.get(k, {}).get("expires_at")
        out[k] = round((exp - time.time()) / 86400, 1) if exp else -1
    return out
