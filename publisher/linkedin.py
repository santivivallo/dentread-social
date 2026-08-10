"""
LinkedIn document post ("carrusel") en la página de empresa.

Flujo:
  1. POST /rest/documents?action=initializeUpload  -> uploadUrl + document URN
  2. PUT del PDF a uploadUrl
  3. poll GET /rest/documents/{urn} hasta status=AVAILABLE
  4. POST /rest/posts con content.media = {title, id: <document urn>}

Requisitos duros:
  - Community Management API aprobada (scope w_organization_social)
  - el usuario del token debe ser ADMIN o DSC de la página
  - PDF <=100MB, <=300 páginas
Ref: learn.microsoft.com/linkedin/marketing/community-management/shares/documents-api
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

API = "https://api.linkedin.com/rest"
# Versión de la Marketing API en YYYYMM. Revisar el calendario de sunset de
# LinkedIn cada trimestre: las versiones caducan a los ~12 meses.
LINKEDIN_VERSION = "202605"
MAX_COMMENTARY = 3000
POLL_INTERVAL = 3
POLL_TIMEOUT = 180


class LinkedInError(RuntimeError):
    pass


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "LinkedIn-Version": LINKEDIN_VERSION,
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json",
    }


def _init_upload(org_urn: str, token: str) -> tuple[str, str]:
    r = requests.post(
        f"{API}/documents?action=initializeUpload",
        headers=_headers(token),
        json={"initializeUploadRequest": {"owner": org_urn}},
        timeout=60,
    )
    if not r.ok:
        raise LinkedInError(f"initializeUpload {r.status_code}: {r.text}")
    v = r.json()["value"]
    return v["uploadUrl"], v["document"]


def _upload(upload_url: str, pdf_path: Path, token: str) -> None:
    with open(pdf_path, "rb") as fh:
        r = requests.put(
            upload_url,
            data=fh,
            headers={"Authorization": f"Bearer {token}"},
            timeout=300,
        )
    if r.status_code not in (200, 201):
        raise LinkedInError(f"upload {r.status_code}: {r.text}")


def _wait_available(doc_urn: str, token: str) -> None:
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        r = requests.get(f"{API}/documents/{doc_urn}", headers=_headers(token), timeout=30)
        if r.ok:
            status = r.json().get("status")
            if status == "AVAILABLE":
                return
            if status == "PROCESSING_FAILED":
                raise LinkedInError(f"LinkedIn falló al procesar {doc_urn}")
        time.sleep(POLL_INTERVAL)
    raise LinkedInError(f"Timeout esperando documento {doc_urn}")


def publish_document(
    org_urn: str,
    token: str,
    pdf_path: str | Path,
    commentary: str,
    title: str,
    *,
    dry_run: bool = False,
) -> str:
    """org_urn con formato urn:li:organization:1234567"""
    pdf_path = Path(pdf_path)
    if len(commentary) > MAX_COMMENTARY:
        raise ValueError(f"Commentary de {len(commentary)} chars excede {MAX_COMMENTARY}")
    if not org_urn.startswith("urn:li:organization:"):
        raise ValueError(f"org_urn inválido: {org_urn}")

    if dry_run:
        print(
            f"[dry-run][LI] {pdf_path.name} "
            f"({pdf_path.stat().st_size/1e6:.2f}MB) -> {org_urn}"
        )
        print(f"           title: {title}")
        print(f"           commentary: {len(commentary)} chars")
        return "dry-run"

    upload_url, doc_urn = _init_upload(org_urn, token)
    _upload(upload_url, pdf_path, token)
    _wait_available(doc_urn, token)

    body = {
        "author": org_urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "content": {"media": {"title": title, "id": doc_urn}},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    r = requests.post(f"{API}/posts", headers=_headers(token), json=body, timeout=60)
    if r.status_code != 201:
        raise LinkedInError(f"posts {r.status_code}: {r.text}")
    return r.headers.get("x-restli-id", "")
