#!/usr/bin/env python3
"""
Auditoría del sistema. Corre los tres controles que sostienen la promesa:

  1. VERIFICABILIDAD  cada hecho de facts.json tiene su cifra localizable en
                      la fuente citada, o una fuente externa declarada.
  2. BREVEDAD         el copy entra en los límites de lectura de cada red y
                      el gancho invita a abrir.
  3. COBERTURA        el archivo de ADA News crece semana a semana.

    python -m pipeline.verify
    python -m pipeline.verify --strict     # sale con error si algo falla

Está pensado para correr en CI antes de publicar y como chequeo manual.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

FACTS = Path("data/facts.json")
KB_PATH = Path("data/kb.jsonl")   # opcional: solo si se usó tools/kb_build
DOCS = Path("docs")

# Fuentes citadas que no están en el corpus indexado, con su respaldo.
EXTERNAL_SOURCES = {
    "ADA News, New CDT codes you should know for 2026 (2025-09-29)":
        "data/corpus_notes/cdt-2026-sin-codigos-ia.md",
}

# Límites de lectura. No son de la API — son de atención.
IG_FIRST_LINE = 125       # lo que muestra el feed antes de "más"
LI_FIRST_LINE = 210       # lo que muestra LinkedIn antes de "ver más"
IG_TARGET = 700           # por encima de esto el carrusel compite consigo mismo
LI_TARGET = 900


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    # una cifra es la misma escrita 9,5 o 9.5
    return re.sub(r"(?<=\d)[.,](?=\d)", ".", s)


# --------------------------------------------------------------------------

def check_facts() -> tuple[int, int, list[str]]:
    facts = json.loads(FACTS.read_text())["facts"]
    docs = [json.loads(l) for l in KB_PATH.open()]
    problems: list[str] = []

    corpus_by_title: dict[str, str] = {}
    for d in docs:
        corpus_by_title.setdefault(norm(d["title"]), "")
        corpus_by_title[norm(d["title"])] += " " + norm(d["text"])

    external_text = {
        cite: norm(Path(path).read_text())
        for cite, path in EXTERNAL_SOURCES.items() if Path(path).exists()
    }

    ok = 0
    for f in facts:
        numbers = re.findall(r"\d[\d.,]*", norm(f["number"]))
        blob = ""

        if f["cite"] in external_text:
            blob = external_text[f["cite"]]
        else:
            title = f["cite"].split("(")[0]
            title = title.split(",", 1)[1] if "," in title else title
            key = norm(title.strip())[:26]
            for k, v in corpus_by_title.items():
                if key and key in k:
                    blob += v

        if not blob:
            problems.append(f"{f['id']}: no se encuentra la fuente citada")
            continue

        missing = [n for n in numbers if n not in blob]
        if missing:
            problems.append(f"{f['id']}: {missing} no aparece(n) en la fuente")
            continue

        for field in ("statement", "statement_en", "cite", "tier"):
            if not f.get(field):
                problems.append(f"{f['id']}: falta el campo '{field}'")
                break
        else:
            ok += 1

    return ok, len(facts), problems


def check_brevity(folder: Path | None = None) -> tuple[int, int, list[str]]:
    posts = sorted(Path("out").glob("*/post.json")) if folder is None else \
        [folder / "post.json"]
    if not posts:
        return 0, 0, ["no hay posts generados en out/ para medir"]

    problems, ok = [], 0
    for p in posts:
        d = json.loads(p.read_text())
        name = p.parent.name
        es, en = d["caption_es"], d["commentary_en"]
        bad = False

        for label, text, first_max, target in (
            ("ES", es, IG_FIRST_LINE, IG_TARGET),
            ("EN", en, LI_FIRST_LINE, LI_TARGET),
        ):
            first = text.split("\n", 1)[0]
            if len(first) > first_max:
                problems.append(
                    f"{name} [{label}] gancho de {len(first)} chars "
                    f"(máx {first_max}): se corta antes de enganchar")
                bad = True
            if len(text) > target:
                problems.append(
                    f"{name} [{label}] {len(text)} chars (objetivo <{target}): "
                    "el carrusel ya cuenta la historia, el texto la repite")
                bad = True
            if not re.search(r"[?¿]", text):
                problems.append(f"{name} [{label}] sin pregunta: no invita a responder")
                bad = True
        if not bad:
            ok += 1
    return ok, len(posts), problems


def check_inventory() -> tuple[bool, list[str]]:
    """
    ¿Cuánto contenido queda? El sistema anterior se secaba en la semana 8 sin
    avisar. Ahora la falta de inventario es un fallo visible, no una sorpresa.
    """
    from pipeline.plan import inventory
    inv = inventory()
    notes = [
        f"{inv['temas_publicables']} temas publicables · "
        f"{inv['hechos_disponibles']}/{inv['hechos_totales']} hechos disponibles · "
        f"{inv['evergreen_disponibles']} evergreen",
        f"runway: ~{inv['semanas_de_runway']} semanas a 2 posts/semana",
    ]
    ok = inv["semanas_de_runway"] >= 4
    if not ok:
        notes.append("menos de 4 semanas de contenido: curar más hechos antes "
                     "de dejarlo automático")
    return ok, notes


def check_site() -> tuple[bool, list[str]]:
    """Sin activo indexable, el esfuerzo no compone."""
    if not DOCS.exists():
        return False, ["no existe docs/: el sistema no produce activos indexables"]
    pages = [p for p in DOCS.glob("*/index.html")]
    problems, notes = [], []
    notes.append(f"{len(pages)} páginas · índice de datos: "
                 f"{'sí' if (DOCS / 'datos/index.html').exists() else 'NO'} · "
                 f"sitemap: {'sí' if (DOCS / 'sitemap.xml').exists() else 'NO'}")
    for p in pages:
        html = p.read_text()
        if "application/ld+json" not in html:
            problems.append(f"{p.parent.name}: sin schema.org")
        if '<link rel="canonical"' not in html:
            problems.append(f"{p.parent.name}: sin canonical")
    if not (DOCS / "sitemap.xml").exists():
        problems.append("falta sitemap.xml")
    return (not problems), notes + [f"✗ {x}" for x in problems]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    failed = False

    print("═══ 1. VERIFICABILIDAD")
    ok, total, problems = check_facts()
    print(f"    {ok}/{total} hechos con cifra localizable en su fuente")
    for p in problems:
        print(f"    ✗ {p}")
    failed |= bool(problems)

    print("\n═══ 2. BREVEDAD")
    ok, total, problems = check_brevity()
    print(f"    {ok}/{total} posts dentro de los límites de lectura")
    for p in problems:
        print(f"    ✗ {p}")
    failed |= bool(problems)

    print("\n═══ 3. INVENTARIO DE CONTENIDO")
    oki, notes = check_inventory()
    for n in notes:
        print(f"    {'·' if oki else '✗'} {n}")
    failed |= not oki

    print("\n═══ 4. ACTIVO INDEXABLE")
    oks, notes = check_site()
    for n in notes:
        print(f"    {'·' if oks else '✗'} {n}")
    failed |= not oks

    print("\n" + ("FALLA" if failed else "TODO OK"))
    if failed and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
