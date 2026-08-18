#!/usr/bin/env python3
"""
DentRead — publicador de carruseles.

Entrada: una carpeta con los slides que ya genera tu automatización
         + un post.json con el copy en ES (Instagram) e EN (LinkedIn).

Uso:
    python publish.py ./out/2026-08-09 --dry-run
    python publish.py ./out/2026-08-09
    python publish.py ./out/2026-08-09 --only linkedin

Orden de validación (falla temprano y barato):
    1. specs de plataforma  -> dimensiones, ratio, pesos, longitudes
    2. claims guard         -> riesgo regulatorio y de credibilidad
    3. cuota y tokens
    4. publicación
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from publisher import guard, instagram, linkedin, media, specs, tokens

load_dotenv()

REQUIRED_FIELDS = ("slug", "caption_es", "commentary_en", "title_en")


def ping_healthcheck(dry_run: bool) -> None:
    """
    Aviso de vida. El modo de falla más probable de este sistema no es
    publicar algo malo: es dejar de publicar sin que nadie se entere.
    Tres causas reales: token vencido, GitHub desactiva el cron tras 60 días
    sin actividad en el repo, y el fetcher devuelve vacío sin error.

    Healthchecks.io es gratis: si el ping no llega a horario, manda mail.
    """
    url = os.environ.get("HEALTHCHECK_URL")
    if not url or dry_run:
        return
    try:
        import requests
        requests.get(url, timeout=10)
    except Exception as exc:                 # nunca romper por el monitoreo
        print(f"[warn] no se pudo enviar el ping de salud: {exc}")


def load_post(folder: Path) -> dict:
    path = folder / "post.json"
    if not path.exists():
        sys.exit(f"[error] falta {path}")
    meta = json.loads(path.read_text())
    missing = [k for k in REQUIRED_FIELDS if not meta.get(k)]
    if missing:
        sys.exit(f"[error] post.json: faltan campos {missing}")
    return meta


def run_specs(meta: dict, slides: list[Path], folder: Path,
              want_ig: bool, want_li: bool) -> tuple[list[Path], Path | None]:
    issues: list[specs.SpecIssue] = []
    ig_slides: list[Path] = []
    pdf: Path | None = None

    if want_ig:
        ig_slides, ig_issues = specs.prepare_instagram_slides(
            slides, folder / ".ig"
        )
        issues += ig_issues
        issues += specs.validate_instagram_caption(meta["caption_es"])

    if want_li:
        pdf = media.build_pdf(slides, folder / f"{meta['slug']}.pdf")
        issues += specs.validate_linkedin(
            pdf, meta["commentary_en"], meta["title_en"]
        )

    ok, body = specs.summarize(issues)
    print("[specs]")
    print(body)
    if not ok:
        sys.exit("\n[specs] BLOQUEADO: corregí los ERROR antes de publicar.")
    return ig_slides, pdf


def run_guard(meta: dict, force: bool) -> None:
    failed = False
    for label, res in guard.check_post(meta).items():
        print(f"[guard] {label}: {'OK' if res.ok else 'BLOQUEADO'}")
        print(res.report())
        failed |= not res.ok

    if failed:
        if force:
            print("\n[guard] --force: publicando bajo revisión humana explícita.")
            return
        sys.exit(
            "\n[guard] BLOQUEADO. El copy contiene claims que DentRead no puede\n"
            "        sostener sin FDA clearance o sin evidencia declarada.\n"
            "        Corregí el copy, declará la evidencia en post.json,\n"
            "        o pasá --force si lo revisaste vos mismo.\n"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="ignora el claims guard (revisión humana explícita)")
    ap.add_argument("--only", choices=["instagram", "linkedin"])
    ap.add_argument("--keep-media", action="store_true")
    args = ap.parse_args()

    want_ig = args.only in (None, "instagram")
    want_li = args.only in (None, "linkedin")

    folder = args.folder
    meta = load_post(folder)
    slides = media.collect_slides(folder)
    print(f"[info] {len(slides)} slides · slug={meta['slug']}")

    ig_slides, pdf = run_specs(meta, slides, folder, want_ig, want_li)
    run_guard(meta, args.force)

    if not args.dry_run:
        for svc, d in tokens.days_left().items():
            if 0 <= d < 10:
                print(f"[warn] token de {svc} expira en {d} días")

    # El registro se escribe apenas cada plataforma confirma, no al final.
    # Antes se escribía después de las dos: si Instagram publicaba y LinkedIn
    # tiraba excepción, no quedaba rastro y la corrida siguiente republicaba
    # en Instagram. Duplicado público e irreversible.
    ledger = folder / "published.json"
    results: dict[str, str] = {}
    if ledger.exists():
        prev = json.loads(ledger.read_text())
        results = {k: v for k, v in prev.items()
                   if k in ("instagram", "linkedin") and not prev.get("dry_run")}
        if results:
            print(f"[info] ya publicado antes: {list(results)} — se saltea")

    def record() -> None:
        ledger.write_text(json.dumps(
            {"date": str(date.today()), "dry_run": args.dry_run, **results},
            indent=2))

    want_ig = want_ig and "instagram" not in results
    want_li = want_li and "linkedin" not in results
    if not (want_ig or want_li):
        print("[ok] nada pendiente de publicar")
        return

    prefix = f"carousels/{date.today():%Y-%m}/{meta['slug']}"

    # ---- Instagram (español) -----------------------------------------
    if want_ig:
        if args.dry_run:
            urls = [f"https://example.invalid/{prefix}/{p.name}" for p in ig_slides]
            token = ""
        else:
            urls = media.upload_public(ig_slides, prefix)
            token = tokens.meta_token()
            left = instagram.quota_remaining(os.environ["IG_USER_ID"], token)
            if left is None:
                print("[warn] no se pudo leer la cuota de IG; se publica igual")
            else:
                print(f"[info] cuota IG restante en 24h: {left}")
                if left < 1:
                    sys.exit("[error] cuota de publicación de Instagram agotada")
        try:
            results["instagram"] = instagram.publish_carousel(
                os.environ["IG_USER_ID"], token, urls,
                meta["caption_es"], dry_run=args.dry_run,
            )
            record()                      # ← antes de tocar LinkedIn
        finally:
            if not args.dry_run and not args.keep_media:
                media.cleanup(prefix)

    # ---- LinkedIn (inglés, PDF) ---------------------------------------
    if want_li and pdf is not None:
        print(f"[info] PDF: {pdf.name} ({pdf.stat().st_size/1e6:.2f}MB)")
        results["linkedin"] = linkedin.publish_document(
            os.environ["LINKEDIN_ORG_URN"],
            "" if args.dry_run else tokens.linkedin_token(),
            pdf, meta["commentary_en"], meta["title_en"],
            dry_run=args.dry_run,
        )
        record()

    record()
    # El consumo se marca acá, no al generar.
    #
    # Antes lo hacia `pipeline.run`: generar un post quemaba tema, hechos y
    # bloque aunque nunca saliera. Probando el sistema un solo dia se
    # consumieron 5 temas, 12 hechos y 4 evergreen, el runway cayo a cero y el
    # control de inventario bloqueo la publicacion real. El sistema se quedo
    # sin material testeandose a si mismo.
    #
    # En dry-run no se marca: un ensayo no gasta contenido.
    if not args.dry_run and results:
        from pipeline import plan
        plan.mark_used_from_folder(folder)
        print("[ok] inventario actualizado")

    ping_healthcheck(args.dry_run)
    print(f"[ok] {results}")


if __name__ == "__main__":
    main()
