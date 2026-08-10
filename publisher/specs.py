"""
Validación y normalización de specs de plataforma.

Instagram rechaza containers sin decir por qué. Este módulo falla antes,
en local, con un mensaje útil — y arregla lo que se puede arreglar solo.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# ---- Instagram -----------------------------------------------------------
# Meta acepta oficialmente JPEG para image_url. PNG funciona a veces y falla
# otras sin error claro: convertimos siempre.
IG_MIN_WIDTH = 320
IG_MAX_WIDTH = 1440
IG_MAX_BYTES = 8 * 1024 * 1024
IG_MIN_RATIO = 0.8      # 4:5 vertical
IG_MAX_RATIO = 1.91     # 1.91:1 horizontal
IG_MIN_SLIDES = 2
IG_MAX_SLIDES = 10
IG_MAX_CAPTION = 2200
IG_MAX_HASHTAGS = 30
IG_RATIO_TOLERANCE = 0.01

# ---- LinkedIn ------------------------------------------------------------
LI_MAX_PAGES = 300
LI_MAX_BYTES = 100 * 1024 * 1024
LI_MAX_COMMENTARY = 3000
LI_MAX_TITLE = 100      # se trunca en el feed mucho antes


@dataclass
class SpecIssue:
    level: str          # "error" | "warn"
    where: str
    message: str

    def __str__(self) -> str:
        tag = "ERROR" if self.level == "error" else "warn "
        return f"  {tag} [{self.where}] {self.message}"


# --------------------------------------------------------------------------
# Instagram
# --------------------------------------------------------------------------

def prepare_instagram_slides(
    slides: list[Path], workdir: Path, quality: int = 92
) -> tuple[list[Path], list[SpecIssue]]:
    """
    Convierte a JPEG, reescala si excede el ancho máximo y valida.
    Devuelve (rutas normalizadas, issues).
    """
    issues: list[SpecIssue] = []
    workdir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    ratios: list[float] = []

    if not IG_MIN_SLIDES <= len(slides) <= IG_MAX_SLIDES:
        issues.append(SpecIssue(
            "error", "instagram",
            f"{len(slides)} slides; el carrusel admite {IG_MIN_SLIDES}-{IG_MAX_SLIDES}",
        ))

    for i, src in enumerate(slides[:IG_MAX_SLIDES], start=1):
        img = Image.open(src)
        w, h = img.size
        ratios.append(round(w / h, 3))

        if w < IG_MIN_WIDTH:
            issues.append(SpecIssue(
                "error", f"instagram/{src.name}",
                f"ancho {w}px < mínimo {IG_MIN_WIDTH}px",
            ))

        ratio = w / h
        if not (IG_MIN_RATIO - 0.01) <= ratio <= (IG_MAX_RATIO + 0.01):
            issues.append(SpecIssue(
                "error", f"instagram/{src.name}",
                f"aspect ratio {ratio:.3f} fuera de {IG_MIN_RATIO}–{IG_MAX_RATIO} "
                f"(usá 1080x1350 o 1080x1080)",
            ))

        # aplanar transparencia y forzar RGB/JPEG
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, "white")
            bg.paste(img, mask=img.convert("RGBA").split()[-1])
            img = bg
        else:
            img = img.convert("RGB")

        if w > IG_MAX_WIDTH:
            new_h = round(h * IG_MAX_WIDTH / w)
            img = img.resize((IG_MAX_WIDTH, new_h), Image.LANCZOS)
            issues.append(SpecIssue(
                "warn", f"instagram/{src.name}",
                f"reescalado {w}x{h} -> {IG_MAX_WIDTH}x{new_h}",
            ))

        dst = workdir / f"{i:02d}.jpg"
        img.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)

        if dst.stat().st_size > IG_MAX_BYTES:
            img.save(dst, "JPEG", quality=80, optimize=True, progressive=True)
        if dst.stat().st_size > IG_MAX_BYTES:
            issues.append(SpecIssue(
                "error", f"instagram/{src.name}",
                f"{dst.stat().st_size/1e6:.1f}MB excede el límite de 8MB",
            ))
        out.append(dst)

    # Instagram recorta todo el carrusel al ratio del primer slide.
    if ratios and max(ratios) - min(ratios) > IG_RATIO_TOLERANCE:
        issues.append(SpecIssue(
            "error", "instagram",
            f"los slides tienen ratios distintos {sorted(set(ratios))}; "
            "Instagram recorta todo al ratio del primero",
        ))

    return out, issues


def validate_instagram_caption(caption: str) -> list[SpecIssue]:
    issues = []
    n = len(caption)
    if n > IG_MAX_CAPTION:
        issues.append(SpecIssue("error", "instagram/caption",
                                f"{n} chars excede {IG_MAX_CAPTION}"))
    tags = caption.count("#")
    if tags > IG_MAX_HASHTAGS:
        issues.append(SpecIssue("error", "instagram/caption",
                                f"{tags} hashtags excede {IG_MAX_HASHTAGS}"))
    if tags > 12:
        issues.append(SpecIssue("warn", "instagram/caption",
                                f"{tags} hashtags; >12 se lee como spam"))

    first = caption.split("\n", 1)[0]
    if len(first) > 125:
        issues.append(SpecIssue(
            "warn", "instagram/caption",
            f"primera línea de {len(first)} chars; el feed corta en ~125 "
            "y ahí se decide si abren el post",
        ))
    if caption.count("@") > 5:
        issues.append(SpecIssue("warn", "instagram/caption",
                                "más de 5 menciones"))
    return issues


# --------------------------------------------------------------------------
# LinkedIn
# --------------------------------------------------------------------------

def validate_linkedin(pdf: Path, commentary: str, title: str) -> list[SpecIssue]:
    issues = []
    size = pdf.stat().st_size
    if size > LI_MAX_BYTES:
        issues.append(SpecIssue("error", "linkedin/pdf",
                                f"{size/1e6:.1f}MB excede 100MB"))

    n = len(commentary)
    if n > LI_MAX_COMMENTARY:
        issues.append(SpecIssue("error", "linkedin/commentary",
                                f"{n} chars excede {LI_MAX_COMMENTARY}"))

    first = commentary.split("\n", 1)[0]
    if len(first) > 210:
        issues.append(SpecIssue(
            "warn", "linkedin/commentary",
            f"primera línea de {len(first)} chars; LinkedIn corta en ~210 "
            "con 'ver más'",
        ))
    if not title.strip():
        issues.append(SpecIssue("error", "linkedin/title", "título vacío"))
    if len(title) > LI_MAX_TITLE:
        issues.append(SpecIssue("warn", "linkedin/title",
                                f"{len(title)} chars; se trunca en el feed"))
    if "http" in commentary:
        issues.append(SpecIssue(
            "warn", "linkedin/commentary",
            "link externo en el cuerpo: LinkedIn penaliza el alcance. "
            "Ponelo en el primer comentario",
        ))
    if commentary.count("#") > 5:
        issues.append(SpecIssue("warn", "linkedin/commentary",
                                "más de 5 hashtags en LinkedIn resta"))
    return issues


def summarize(issues: list[SpecIssue]) -> tuple[bool, str]:
    errors = [i for i in issues if i.level == "error"]
    body = "\n".join(str(i) for i in issues) or "  sin hallazgos"
    return (not errors), body
