#!/usr/bin/env python3
"""
¿Está listo para publicar solo? Chequeo de puesta en marcha.

    python -m pipeline.readiness              # a 2 posts/semana
    python -m pipeline.readiness --slots 3    # a 3 posts/semana

Separa lo que bloquea de lo que solo conviene. Un bloqueante significa que
encender el cron produce un fallo o una publicación mala; el resto se puede
arreglar con el sistema andando.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pipeline.plan import (COOLDOWN_EVERGREEN, COOLDOWN_FACT, COOLDOWN_THEME,
                           EVERGREEN_EVERY, available_themes, load_evergreen,
                           load_facts, _state)
from pipeline.supply import Sources, requirements as supply_requirements
from pipeline.themes import CATALOG

WEEK = 7


def requirements(slots: int, sources: Sources | None = None) -> dict:
    """
    Inventario garantizado necesario, contando las fuentes variables en su
    p25. Ver pipeline/supply.py: sumar promedios sobreestima, porque el
    promedio no publica los martes.
    """
    return supply_requirements(slots, sources or Sources())


def check(slots: int, sources: Sources | None = None) -> tuple[list[str], list[str], dict]:
    blockers: list[str] = []
    warnings: list[str] = []

    need = requirements(slots, sources)
    facts = load_facts()
    evergreen = load_evergreen()
    themes_with_facts = [
        t for t in CATALOG
        if len([f for f in facts if t.id in f.get("themes", [])]) >= 2
    ]

    have = {"facts": len(facts), "themes": len(themes_with_facts),
            "evergreen": len(evergreen)}

    # Techo estructural: los temas limitan cuántos posts de datos caben por
    # semana, y ese techo no se mueve agregando hechos.
    from pipeline.supply import ceiling
    cap = ceiling(len(CATALOG), len(evergreen))
    variable = need["de_fuentes_variables"]
    if cap["techo_garantizado"] + variable < slots:
        blockers.append(
            f"techo estructural: {len(CATALOG)} temas y {len(evergreen)} evergreen "
            f"dan {cap['techo_garantizado']}/semana garantizados + {variable} "
            f"variables = {cap['techo_garantizado'] + variable:.2f} < {slots}. "
            f"Agregar ángulos al catálogo, no hechos")
    elif cap["techo_garantizado"] + variable < slots * 1.25:
        warnings.append(
            f"techo estructural justo: {cap['techo_garantizado'] + variable:.2f} "
            f"contra {slots} objetivo. Sin margen para una mala semana de "
            f"noticias — sumar ~8 temas al catálogo da holgura")

    # ---- contenido -------------------------------------------------------
    for k, label in (("facts", "hechos curados"),
                     ("themes", "temas con 2+ hechos"),
                     ("evergreen", "posts evergreen")):
        if have[k] < need[k]:
            gap = need[k] - have[k]
            msg = (f"{label}: {have[k]}/{need[k]} · faltan {gap} para sostener "
                   f"{slots}/semana sin repetir")
            (blockers if have[k] < need[k] * 0.5 else warnings).append(msg)

    # ---- credenciales ----------------------------------------------------
    required_env = {
        "IG_USER_ID": "ID numérico de la cuenta Instagram Professional",
        "META_APP_ID": "app de Meta",
        "META_APP_SECRET": "app de Meta",
        "META_ACCESS_TOKEN": "token de larga duración inicial",
        "LINKEDIN_ORG_URN": "urn:li:organization:102793096",
        "LINKEDIN_CLIENT_ID": "app de LinkedIn",
        "LINKEDIN_CLIENT_SECRET": "app de LinkedIn",
        "LINKEDIN_ACCESS_TOKEN": "OAuth de LinkedIn",
        "S3_ENDPOINT": "bucket R2/S3 para staging de imágenes",
        "S3_ACCESS_KEY_ID": "bucket",
        "S3_SECRET_ACCESS_KEY": "bucket",
        "S3_BUCKET": "bucket",
        "S3_PUBLIC_BASE": "dominio público del bucket",
        "TOKEN_STORE_KEY": "clave Fernet para cifrar el token store",
    }
    missing_env = [k for k in required_env if not os.environ.get(k)]
    if missing_env:
        blockers.append(f"variables sin configurar: {', '.join(missing_env)}")

    optional_env = {
        "HEALTHCHECK_URL": "ping de salud — sin esto el fallo es silencioso",
        "LINKEDIN_REFRESH_TOKEN": "sin esto hay que rehacer OAuth cada 60 días",
        "NCBI_API_KEY": "solo si usás tools/pubmed intensivamente",
    }
    for k, why in optional_env.items():
        if not os.environ.get(k):
            warnings.append(f"{k} sin configurar: {why}")

    # ---- sitio -----------------------------------------------------------
    site_src = Path("pipeline/site.py").read_text()
    if "dentread.github.io" in site_src or "example.com" in site_src:
        warnings.append(
            "BASE_URL en pipeline/site.py sigue apuntando al placeholder: "
            "cambiar al dominio real antes de que Google indexe la URL vieja")
    if not Path("docs/index.html").exists():
        warnings.append("docs/ vacío: correr `python -m pipeline.site --rebuild`")

    # ---- workflow --------------------------------------------------------
    wf = Path(".github/workflows/publish.yml")
    if wf.exists():
        text = wf.read_text()
        if "TODO: pinear por SHA" in text:
            warnings.append("actions sin pinear por SHA en el workflow")
        if "environment: production" not in text:
            warnings.append("falta el environment `production` en el workflow")

    # ---- hechos sin fecha de revisión ------------------------------------
    stale = [f["id"] for f in facts if not f.get("review_by")]
    if stale:
        warnings.append(
            f"{len(stale)} hechos sin `review_by`: nada avisa cuándo caducan")

    return blockers, warnings, {"have": have, "need": need}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slots", type=int, default=2,
                    help="posts por semana que se quieren sostener")
    ap.add_argument("--no-news", action="store_true",
                    help="calcular sin ADA News")
    ap.add_argument("--no-journals", action="store_true",
                    help="calcular sin señalizadores de journals")
    args = ap.parse_args()

    sources = Sources(ada_news=not args.no_news, journals=not args.no_journals)
    blockers, warnings, inv = check(args.slots, sources)

    on = [n for n, v in (("hechos", True), ("evergreen", True),
                         ("ADA News", sources.ada_news),
                         ("journals", sources.journals)) if v]
    print(f"═══ PUESTA EN MARCHA · objetivo {args.slots} posts/semana")
    print(f"    fuentes: {', '.join(on)}")
    print(f"    mix esperado: {inv['need']['de_fuentes_variables']} variables + "
          f"{inv['need']['de_evergreen']} evergreen + "
          f"{inv['need']['de_hechos']} de hechos\n")
    print("   inventario        tenés   necesitás")
    for k, label in (("facts", "hechos"), ("themes", "temas"),
                     ("evergreen", "evergreen")):
        h, n = inv["have"][k], inv["need"][k]
        mark = "OK" if h >= n else f"faltan {n - h}"
        print(f"   {label:<16} {h:>5}   {n:>9}   {mark}")

    print(f"\n═══ BLOQUEANTES ({len(blockers)})")
    for b in blockers:
        print(f"   ✗ {b}")
    if not blockers:
        print("   ninguno")

    print(f"\n═══ CONVIENE ARREGLAR ({len(warnings)})")
    for w in warnings:
        print(f"   · {w}")
    if not warnings:
        print("   nada")

    print()
    if blockers:
        print(f"NO ENCENDER EL CRON todavía. {len(blockers)} bloqueante(s).")
        sys.exit(1)
    print("Listo para publicar automáticamente.")


if __name__ == "__main__":
    main()
