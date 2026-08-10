#!/usr/bin/env python3
"""
Verifica que cada credencial funcione, antes de publicar.

Sin esto, un token mal copiado se descubre el martes a las 9 de la mañana
cuando el post no sale. Cada chequeo hace una llamada real de solo lectura
a la API correspondiente.

    python -m tools.check_credentials
    python -m tools.check_credentials --only meta

No modifica nada. No publica nada.
"""
from __future__ import annotations

import argparse
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

GRAPH = "https://graph.facebook.com/v21.0"
LINKEDIN = "https://api.linkedin.com/rest"
LINKEDIN_VERSION = "202605"

OK, FAIL, SKIP = "✓", "✗", "·"


def _print(mark: str, label: str, detail: str = "") -> None:
    print(f"  {mark} {label:<34} {detail}")


# --------------------------------------------------------------------------

def check_meta() -> bool:
    print("\n═══ META / INSTAGRAM")
    token = os.environ.get("META_ACCESS_TOKEN")
    ig_id = os.environ.get("IG_USER_ID")
    app_id = os.environ.get("META_APP_ID")
    app_secret = os.environ.get("META_APP_SECRET")

    if not token:
        _print(FAIL, "META_ACCESS_TOKEN", "sin configurar")
        return False

    ok = True

    # 1. ¿el token sirve y cuánto le queda?
    try:
        r = requests.get(f"{GRAPH}/debug_token",
                         params={"input_token": token,
                                 "access_token": f"{app_id}|{app_secret}"
                                 if app_id and app_secret else token},
                         timeout=20)
        data = r.json().get("data", {})
        if data.get("is_valid"):
            exp = data.get("expires_at")
            if exp:
                from datetime import datetime
                days = (datetime.fromtimestamp(exp) - datetime.now()).days
                _print(OK, "token válido", f"expira en {days} días")
                if days < 15:
                    _print(FAIL, "  ⚠ vence pronto", "refrescalo antes de encender el cron")
            else:
                _print(OK, "token válido", "sin fecha de expiración")
        else:
            _print(FAIL, "token inválido", str(data.get("error", {}))[:70])
            ok = False
    except Exception as exc:
        _print(FAIL, "debug_token falló", str(exc)[:70])
        ok = False

    # 2. ¿los permisos que hacen falta están concedidos?
    try:
        r = requests.get(f"{GRAPH}/me/permissions",
                         params={"access_token": token}, timeout=20)
        granted = {p["permission"] for p in r.json().get("data", [])
                   if p.get("status") == "granted"}
        needed = {"instagram_basic", "pages_show_list"}
        publish = {"instagram_content_publish"}
        missing = needed - granted
        if missing:
            _print(FAIL, "permisos básicos", f"faltan {missing}")
            ok = False
        else:
            _print(OK, "permisos básicos", "instagram_basic, pages_show_list")
        if publish & granted:
            _print(OK, "permiso de publicación", "instagram_content_publish")
        else:
            _print(FAIL, "permiso de publicación",
                   "falta instagram_content_publish — en dev mode alcanza "
                   "si sos tester de la app")
    except Exception as exc:
        _print(SKIP, "permisos", f"no se pudieron leer ({exc.__class__.__name__})")

    # 3. ¿el IG_USER_ID es el correcto y responde?
    if ig_id:
        try:
            r = requests.get(f"{GRAPH}/{ig_id}",
                             params={"fields": "username,name,followers_count",
                                     "access_token": token}, timeout=20)
            d = r.json()
            if "username" in d:
                _print(OK, "IG_USER_ID",
                       f"@{d['username']} · {d.get('followers_count', '?')} seguidores")
                if d["username"] != "dentread_":
                    _print(FAIL, "  ⚠ cuenta inesperada",
                           f"se esperaba dentread_, es {d['username']}")
                    ok = False
            else:
                _print(FAIL, "IG_USER_ID", str(d.get("error", {}).get("message"))[:70])
                ok = False
        except Exception as exc:
            _print(FAIL, "IG_USER_ID", str(exc)[:70])
            ok = False
    else:
        _print(FAIL, "IG_USER_ID", "sin configurar")
        ok = False

    # 4. cuota de publicación
    #
    # Esta rama tenía un verde falso: hacía .get("data", [{}])[0] sobre la
    # respuesta, así que un 400 —que devuelve {"error": ...} y ningún "data"—
    # caía en el default y se imprimía "100/100 disponibles". El chequeo
    # nunca miró la respuesta. Se descubrió el 2026-08-10, cuando publish.py
    # falló contra el mismo endpoint que acá figuraba en verde.
    #
    # Regla: un chequeo solo informa OK si leyó el dato. Si no lo leyó, dice
    # que no lo leyó.
    if ig_id:
        try:
            r = requests.get(f"{GRAPH}/{ig_id}/content_publishing_limit",
                             params={"fields": "quota_usage,config",
                                     "access_token": token}, timeout=20)
            body = r.json()
            data = body.get("data") or []
            if not r.ok or not data:
                msg = body.get("error", {}).get("message", "")[:60]
                _print(SKIP, "cuota de publicación",
                       f"no legible ({r.status_code}{': ' + msg if msg else ''}) "
                       "— no bloquea, se publica igual")
            else:
                d = data[0]
                used = d.get("quota_usage", 0)
                total = d.get("config", {}).get("quota_total", 100)
                _print(OK, "cuota de publicación",
                       f"{total - used}/{total} disponibles en 24h")
        except Exception as exc:
            _print(SKIP, "cuota de publicación",
                   f"no legible ({exc.__class__.__name__}) — no bloquea")

    return ok


def check_linkedin() -> bool:
    print("\n═══ LINKEDIN")
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
    org = os.environ.get("LINKEDIN_ORG_URN", "")

    if not token:
        _print(FAIL, "LINKEDIN_ACCESS_TOKEN", "sin configurar")
        return False

    headers = {"Authorization": f"Bearer {token}",
               "LinkedIn-Version": LINKEDIN_VERSION,
               "X-Restli-Protocol-Version": "2.0.0"}
    ok = True

    # ¿el token vive?
    try:
        r = requests.get("https://api.linkedin.com/v2/userinfo",
                         headers={"Authorization": f"Bearer {token}"}, timeout=20)
        if r.ok:
            _print(OK, "token válido", r.json().get("name", ""))
        else:
            _print(FAIL, "token inválido", f"{r.status_code} {r.text[:60]}")
            ok = False
    except Exception as exc:
        _print(FAIL, "userinfo falló", str(exc)[:70])
        ok = False

    # ¿tenemos permiso de administrador sobre la organización?
    if org.startswith("urn:li:organization:"):
        org_id = org.rsplit(":", 1)[-1]
        try:
            r = requests.get(
                f"{LINKEDIN}/organizationAcls",
                params={"q": "roleAssignee", "role": "ADMINISTRATOR",
                        "projection": "(elements*(organization~(localizedName)))"},
                headers=headers, timeout=20)
            if r.ok:
                names = [e.get("organization~", {}).get("localizedName", "?")
                         for e in r.json().get("elements", [])]
                if any(org_id in str(e) for e in r.json().get("elements", [])) or names:
                    _print(OK, "acceso a la organización", ", ".join(names)[:60])
                else:
                    _print(FAIL, "acceso a la organización",
                           f"el token no administra {org_id}")
                    ok = False
            elif r.status_code == 403:
                _print(FAIL, "organizationAcls", "403 — falta Community Management API")
                ok = False
            else:
                _print(FAIL, "organizationAcls", f"{r.status_code} {r.text[:60]}")
                ok = False
        except Exception as exc:
            _print(FAIL, "organizationAcls", str(exc)[:70])
            ok = False
    else:
        _print(FAIL, "LINKEDIN_ORG_URN", f"formato inválido: {org!r}")
        ok = False

    if not os.environ.get("LINKEDIN_REFRESH_TOKEN"):
        _print(SKIP, "refresh token",
               "sin configurar — habrá que rehacer OAuth cada 60 días")

    return ok


def check_bucket() -> bool:
    print("\n═══ BUCKET (staging de imágenes para Instagram)")
    needed = ["S3_ENDPOINT", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY",
              "S3_BUCKET", "S3_PUBLIC_BASE"]
    missing = [k for k in needed if not os.environ.get(k)]
    if missing:
        _print(FAIL, "configuración", f"faltan {', '.join(missing)}")
        return False

    import io
    import uuid
    try:
        from publisher.media import _s3_client
        client = _s3_client()
        bucket = os.environ["S3_BUCKET"]
        key = f"_healthcheck/{uuid.uuid4().hex}.txt"

        client.upload_fileobj(io.BytesIO(b"dentread ok"), bucket, key,
                              ExtraArgs={"ContentType": "text/plain"})
        _print(OK, "escritura en el bucket", bucket)

        # lo importante: que la URL pública funcione, no solo que el objeto exista
        url = f"{os.environ['S3_PUBLIC_BASE'].rstrip('/')}/{key}"
        r = requests.get(url, timeout=20)
        if r.ok and b"dentread ok" in r.content:
            _print(OK, "URL pública accesible", url[:58])
            good = True
        else:
            _print(FAIL, "URL pública", f"{r.status_code} — Instagram va a rechazar el post")
            good = False

        client.delete_object(Bucket=bucket, Key=key)
        return good
    except Exception as exc:
        _print(FAIL, "bucket", f"{exc.__class__.__name__}: {str(exc)[:60]}")
        return False


def check_local() -> bool:
    print("\n═══ LOCAL")
    ok = True
    key = os.environ.get("TOKEN_STORE_KEY")
    if key:
        try:
            from cryptography.fernet import Fernet
            Fernet(key.encode())
            _print(OK, "TOKEN_STORE_KEY", "válida")
        except Exception:
            _print(FAIL, "TOKEN_STORE_KEY", "no es una clave Fernet válida")
            ok = False
    else:
        _print(FAIL, "TOKEN_STORE_KEY", "sin configurar")
        ok = False

    if os.environ.get("HEALTHCHECK_URL"):
        _print(OK, "HEALTHCHECK_URL", "configurada")
    else:
        _print(SKIP, "HEALTHCHECK_URL", "sin configurar — el fallo sería silencioso")

    from pathlib import Path
    fonts = os.environ.get("BRAND_FONTS")
    if fonts and Path(fonts).exists():
        _print(OK, "fuentes de marca", fonts)
    else:
        _print(SKIP, "BRAND_FONTS", "se usará la fuente de sistema")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["meta", "linkedin", "bucket", "local"])
    args = ap.parse_args()

    checks = {"local": check_local, "meta": check_meta,
              "linkedin": check_linkedin, "bucket": check_bucket}
    if args.only:
        checks = {args.only: checks[args.only]}

    results = {name: fn() for name, fn in checks.items()}

    print("\n" + "─" * 62)
    bad = [n for n, v in results.items() if not v]
    if bad:
        print(f"FALLA en: {', '.join(bad)}")
        print("Corregí eso antes de publicar. Detalle arriba.")
        sys.exit(1)
    print("Todas las credenciales responden. Listo para --dry-run.")


if __name__ == "__main__":
    main()
