#!/usr/bin/env python3
"""
Test offline del archivo acumulativo de ADA News.

Simula corridas semanales contra un listado falso, sin tocar la red. Prueba
la propiedad que importa: la cobertura crece corrida a corrida y nada se
propone dos veces.

    python -m tests.test_archive
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from pipeline import ada_news as an

TITLES = [
    "ADA urges CMS interoperability and prior authorization proposal",
    "New HPI survey data on dental care utilization trends",
    "Historic plaque returns to ADA founding site",          # debe puntuar 0
    "ADA opposes insurance companies charging for paper checks",
]


def build_fixture(n: int = 60) -> list[dict]:
    return [{
        "url": f"https://adanews.ada.org/ada-news/2026/m/art-{i:02d}/",
        "title": TITLES[i % len(TITLES)],
        "pub": (date.today() - timedelta(days=i)).isoformat(),
    } for i in range(n)]


def run(runs: int = 5) -> dict:
    items = build_fixture()
    an.discover = lambda pages: [a["url"] for a in items[: pages * 5]]
    an.fetch_article = lambda url: (lambda a: an.Article(
        url=url, title=a["title"], summary="", category="Practice",
        published=a["pub"], author="x"))(next(x for x in items if x["url"] == url))

    sizes, depths, used = [], [], []
    for _ in range(runs):
        cands = an.latest_relevant(limit=3)
        arch = an.load_archive()
        sizes.append(len(arch["articles"]))
        depths.append(arch["deepest_page"])
        if cands:
            an.mark_published(cands[0].url)
            used.append(cands[0].url)
    return {"sizes": sizes, "depths": depths, "used": used,
            "archive": an.load_archive()}


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    original = an.ARCHIVE
    an.ARCHIVE = tmp / "ada_archive.json"
    try:
        r = run()
    finally:
        an.ARCHIVE = original

    failures = []

    if r["sizes"] != sorted(r["sizes"]) or r["sizes"][0] >= r["sizes"][-1]:
        failures.append(f"el archivo no crece: {r['sizes']}")
    if r["depths"] != sorted(r["depths"]) or r["depths"][0] >= r["depths"][-1]:
        failures.append(f"la profundidad no aumenta: {r['depths']}")
    if len(set(r["used"])) != len(r["used"]):
        failures.append("se propuso dos veces el mismo artículo")

    arts = r["archive"]["articles"]
    noise = [a for a in arts.values()
             if a.get("title", "").startswith("Historic plaque")]
    if any(a.get("score", 0) >= an.MIN_SCORE for a in noise):
        failures.append("un titular institucional superó el piso de relevancia")
    if not all("score" in a or a.get("skipped") for a in arts.values()):
        failures.append("hay artículos archivados sin score")

    print(f"artículos por corrida : {r['sizes']}")
    print(f"profundidad por corrida: {r['depths']}")
    print(f"publicados únicos      : {len(set(r['used']))}/{len(r['used'])}")
    print(f"archivo final          : {len(arts)} artículos")

    if failures:
        print("\nFALLA")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("\nOK — la cobertura crece y nada se repite")
    return 0


if __name__ == "__main__":
    sys.exit(main())
