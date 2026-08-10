#!/usr/bin/env python3
"""
Asistente para ampliar data/facts.json.

Muestra candidatos a hecho extraídos del corpus para un tema, con su cita.
**No** los agrega solo: los tenés que leer en la fuente y copiarlos a mano.
Esa lectura es el único control real de calidad que tiene el sistema.

    python -m pipeline.suggest_facts --theme higienistas
    python -m pipeline.suggest_facts --pending
"""
from __future__ import annotations

import argparse
import json

from pipeline.plan import _state, facts_for
from pipeline.generate import curated_for, extract_stats
from tools.kb import KB
from pipeline.themes import CATALOG


def pending() -> list:
    return [t for t in CATALOG if len(curated_for(t.id, 2)) < 2]


def suggest(kb: KB, theme_id: str, k: int = 8) -> None:
    match = [t for t in CATALOG if t.id == theme_id]
    if not match:
        print(f"tema desconocido: {theme_id}")
        return
    theme = match[0]
    have = len(curated_for(theme_id, 2))
    print(f"\n═══ {theme.name}  ({theme_id})")
    print(f"    hechos curados: {have}/2   ángulo: {theme.angle[:80]}")

    brief = build_brief_from_theme(theme, kb, k=k)
    cands = extract_stats(brief.evidence["facts"], limit=k)
    if not cands:
        print("    sin candidatos automáticos: buscá a mano en las fuentes")
        for c in brief.evidence["citations"]:
            print(f"      · {c}")
        return

    print("    candidatos (VERIFICAR EN LA FUENTE antes de usar):")
    for c in cands:
        print(f"      {c['number']:>12}  {c['context'][:88]}")
        print(f"                    ↳ {c['cite']}")

    print("\n    plantilla para data/facts.json:")
    print(json.dumps({
        "id": f"{theme_id}-XXX",
        "themes": [theme_id],
        "number": "…", "number_en": "…",
        "statement": "…", "statement_en": "…",
        "cite": cands[0]["cite"], "tier": "primary",
    }, indent=2, ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme")
    ap.add_argument("--pending", action="store_true")
    args = ap.parse_args()

    if args.pending or not args.theme:
        rows = pending()
        print(f"{len(CATALOG) - len(rows)}/{len(CATALOG)} temas listos para publicar\n")
        if rows:
            print("Pendientes de hechos verificados:")
            for t in rows:
                print(f"  · {t.id:<24} {t.name}")
            print("\n  python -m pipeline.suggest_facts --theme <id>")
        return

    suggest(KB(), args.theme)


if __name__ == "__main__":
    main()
