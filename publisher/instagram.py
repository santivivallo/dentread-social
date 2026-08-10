"""
Instagram carousel publishing (Instagram Graph API / Instagram Platform).

Flujo obligatorio:
  1. POST /{ig_user_id}/media  por cada slide con is_carousel_item=true
  2. esperar a que cada container quede FINISHED
  3. POST /{ig_user_id}/media  con media_type=CAROUSEL y children=[...]
  4. POST /{ig_user_id}/media_publish  con creation_id

Límites: 2-10 slides, 100 posts publicados por API en 24h (el carrusel
cuenta como 1), caption <=2200 chars, <=30 hashtags.
"""
from __future__ import annotations

import time

import requests

GRAPH = "https://graph.facebook.com/v21.0"
MAX_CAPTION = 2200
POLL_INTERVAL = 3
POLL_TIMEOUT = 180


class InstagramError(RuntimeError):
    pass


def _check(r: requests.Response, what: str) -> dict:
    """
    Nunca dejar que `requests` levante la excepción por su cuenta.

    `raise_for_status()` mete la URL completa en el mensaje, y en el Graph de
    Meta el token viaja como query param. Un traceback pegado en un chat, un
    issue o un log de CI publica el token entero. Pasó una vez: 2026-08-10,
    en el chequeo de cuota. Acá se levanta un error propio que solo contiene
    el código, el endpoint y el mensaje que devolvió Meta.
    """
    if r.ok:
        return r.json()
    try:
        msg = r.json().get("error", {}).get("message", r.text[:200])
    except ValueError:
        msg = r.text[:200]
    raise InstagramError(f"{r.status_code} en {what}: {msg}")


def _post(path: str, token: str, **params) -> dict:
    r = requests.post(f"{GRAPH}/{path}", data={**params, "access_token": token}, timeout=60)
    return _check(r, path)


def _wait_ready(container_id: str, token: str) -> None:
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        r = requests.get(
            f"{GRAPH}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=30,
        )
        _check(r, f"estado del container {container_id}")
        status = r.json().get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise InstagramError(f"Container {container_id} falló: {r.json()}")
        time.sleep(POLL_INTERVAL)
    raise InstagramError(f"Timeout esperando container {container_id}")


def publish_carousel(
    ig_user_id: str,
    token: str,
    image_urls: list[str],
    caption: str,
    *,
    dry_run: bool = False,
) -> str:
    if not 2 <= len(image_urls) <= 10:
        raise ValueError(f"Instagram admite 2-10 slides, recibí {len(image_urls)}")
    if len(caption) > MAX_CAPTION:
        raise ValueError(f"Caption de {len(caption)} chars excede {MAX_CAPTION}")
    if caption.count("#") > 30:
        raise ValueError("Más de 30 hashtags")

    if dry_run:
        print(f"[dry-run][IG] {len(image_urls)} slides, caption {len(caption)} chars")
        for u in image_urls:
            print(f"           - {u}")
        return "dry-run"

    children = []
    for url in image_urls:
        res = _post(
            f"{ig_user_id}/media", token,
            image_url=url, is_carousel_item="true",
        )
        _wait_ready(res["id"], token)
        children.append(res["id"])

    parent = _post(
        f"{ig_user_id}/media", token,
        media_type="CAROUSEL",
        children=",".join(children),
        caption=caption,
    )
    _wait_ready(parent["id"], token)

    published = _post(f"{ig_user_id}/media_publish", token, creation_id=parent["id"])
    return published["id"]


def quota_remaining(ig_user_id: str, token: str) -> int | None:
    """
    Cuántas publicaciones quedan en la ventana de 24 h, o None si no se pudo
    averiguar.

    Devuelve None en vez de romper: la cuota es una cortesía —evita gastar
    una llamada que Meta va a rechazar—, no una condición para publicar. Si
    el endpoint falla, el peor caso es que el intento de publicar devuelva el
    error de cuota, que es exactamente lo que este chequeo quería anticipar.
    Antes levantaba una excepción y frenaba la publicación por no poder
    consultar un dato opcional.
    """
    try:
        r = requests.get(
            f"{GRAPH}/{ig_user_id}/content_publishing_limit",
            params={"fields": "quota_usage,config", "access_token": token},
            timeout=30,
        )
        data = _check(r, "content_publishing_limit").get("data") or []
        if not data:
            return None
        d = data[0]
        return d.get("config", {}).get("quota_total", 100) - d.get("quota_usage", 0)
    except (InstagramError, requests.RequestException, KeyError, ValueError):
        return None
