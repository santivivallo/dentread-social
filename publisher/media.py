"""
Media helpers: publicar los slides a un bucket S3-compatible (Instagram exige
URLs HTTPS públicas) y compilar los mismos slides en un PDF para LinkedIn.
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path

import boto3
from botocore.config import Config
from PIL import Image

IG_MAX_SLIDES = 10
LI_MAX_PAGES = 300
LI_MAX_BYTES = 100 * 1024 * 1024


SLIDE_GLOB = "slide-*.png"


def collect_slides(folder: str | Path) -> list[Path]:
    """
    Slides ordenados por nombre: `slide-01.png`, `slide-02.png`...

    El patrón es explícito y no "toda imagen de la carpeta". La carpeta también
    contiene `logo-cyan.png` y `logo-ink.png` —el HTML los referencia por ruta
    relativa, así que tienen que estar al lado— y tomarlos como slides mandaba
    5 imágenes a Instagram, dos de ellas cuadradas. El chequeo de ratios lo
    atajó, pero la causa era esta.
    """
    folder = Path(folder)
    slides = sorted(folder.glob(SLIDE_GLOB))
    if not slides:
        raise FileNotFoundError(
            f"No hay {SLIDE_GLOB} en {folder}. "
            f"¿Corriste `python -m pipeline.render_html {folder}`?"
        )
    return slides


# --------------------------------------------------------------------------
# S3 / Cloudflare R2
# --------------------------------------------------------------------------

def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],          # R2: https://<acct>.r2.cloudflarestorage.com
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.environ.get("S3_REGION", "auto"),
        config=Config(signature_version="s3v4"),
    )


def upload_public(paths: list[Path], prefix: str) -> list[str]:
    """
    Sube los archivos y devuelve URLs HTTPS públicas.
    Requiere S3_PUBLIC_BASE apuntando a un dominio público del bucket
    (en R2: un custom domain o el r2.dev público).
    """
    client = _s3_client()
    bucket = os.environ["S3_BUCKET"]
    base = os.environ["S3_PUBLIC_BASE"].rstrip("/")
    urls = []
    for p in paths:
        key = f"{prefix}/{p.name}"
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        client.upload_file(str(p), bucket, key, ExtraArgs={"ContentType": ctype})
        urls.append(f"{base}/{key}")
    return urls


def cleanup(prefix: str) -> None:
    client = _s3_client()
    bucket = os.environ["S3_BUCKET"]
    resp = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    objs = [{"Key": o["Key"]} for o in resp.get("Contents", [])]
    if objs:
        client.delete_objects(Bucket=bucket, Delete={"Objects": objs})


# --------------------------------------------------------------------------
# PDF para LinkedIn
# --------------------------------------------------------------------------

def build_pdf(slides: list[Path], out_path: str | Path, dpi: int = 150) -> Path:
    """
    Compila los slides en un PDF. LinkedIn renderiza el documento en 1:1 o 4:5;
    slides cuadrados (1080x1080) o verticales (1080x1350) funcionan bien.
    """
    if len(slides) > LI_MAX_PAGES:
        raise ValueError(f"LinkedIn admite hasta {LI_MAX_PAGES} páginas")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pages = []
    for p in slides:
        img = Image.open(p)
        if img.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", img.size, "white")
            bg.paste(img, mask=img.convert("RGBA").split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
        pages.append(img)

    pages[0].save(
        out_path, "PDF", save_all=True, append_images=pages[1:], resolution=dpi
    )

    size = out_path.stat().st_size
    if size > LI_MAX_BYTES:
        raise ValueError(f"PDF de {size/1e6:.1f}MB excede el límite de 100MB")
    return out_path
