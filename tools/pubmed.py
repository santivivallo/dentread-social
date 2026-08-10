#!/usr/bin/env python3
"""
Buscador de literatura para CURAR hechos, no para publicar.

Usa PubMed E-utilities, que es una **API oficial y gratuita** del NCBI: no
hay que scrapear nada. Devuelve metadatos estructurados y el resumen, con
DOI y revista.

    python -m tools.pubmed --query "dental care utilization United States"
    python -m tools.pubmed --preset acceso --years 2

POR QUÉ ESTO NO AUTOPUBLICA
---------------------------
Resumir estudios clínicos es la categoría de contenido de mayor riesgo que
DentRead podría publicar. Un paper que dice "la IA detectó caries con 92% de
sensibilidad" republicado por una empresa de IA dental sin FDA clearance se
lee como claim propio, por más atribución que lleve. Y el abstract tiene
copyright del editor.

El uso correcto es el de esta herramienta: encontrar el paper, leerlo,
y curar de ahí un hecho a `data/facts.json` con su cita. El humano en el
medio es el control.

Cortesía con el NCBI: máximo 3 consultas por segundo sin API key. Si vas a
usarlo seguido, pedí una key gratis y ponela en NCBI_API_KEY.
"""
from __future__ import annotations

import argparse
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "DentReadCuration"
EMAIL = "contact@dentread.com"

# Búsquedas alineadas con el catálogo de temas. Filtradas a revisiones y
# estudios poblacionales: es donde están las cifras citables, no en los
# reportes de caso.
PRESETS = {
    "acceso": '("dental care"[Title/Abstract] AND (access OR utilization OR '
              'coverage OR "unmet need") AND (United States OR national))',
    "economia": '("dental practice"[Title/Abstract] AND (economics OR cost OR '
                '"health expenditures" OR productivity))',
    "workforce": '(dentist[Title/Abstract] AND (workforce OR supply OR '
                 'shortage OR "dental hygienist"))',
    "ia": '((artificial intelligence OR "deep learning" OR "machine learning") '
          'AND (dentistry OR dental OR radiograph))',
    "aceptacion": '(("treatment acceptance" OR "treatment adherence" OR '
                  '"appointment adherence" OR recall) AND dental)',
    "medicaid": '(dental AND (Medicaid OR CHIP OR "public insurance") AND '
                '(United States OR state))',
}

FILTERS = ('AND (humans[MeSH] AND (systematic[sb] OR review[pt] OR '
           'meta-analysis[pt] OR "cross-sectional studies"[MeSH]))')


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"{TOOL} ({EMAIL})"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _params(**kw) -> str:
    kw.update(tool=TOOL, email=EMAIL)
    if os.environ.get("NCBI_API_KEY"):
        kw["api_key"] = os.environ["NCBI_API_KEY"]
    return urllib.parse.urlencode(kw)


def search(term: str, years: int = 3, retmax: int = 15) -> list[str]:
    q = f"({term}) {FILTERS} AND (\"last {years} years\"[PDat])"
    url = f"{EUTILS}/esearch.fcgi?{_params(db='pubmed', term=q, retmax=retmax, sort='relevance')}"
    root = ET.fromstring(_fetch(url))
    time.sleep(0.4)
    return [e.text for e in root.findall(".//Id")]


def summarize(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []
    url = f"{EUTILS}/efetch.fcgi?{_params(db='pubmed', id=','.join(pmids), retmode='xml')}"
    root = ET.fromstring(_fetch(url))
    time.sleep(0.4)

    out = []
    for art in root.findall(".//PubmedArticle"):
        def txt(path: str) -> str:
            el = art.find(path)
            return "".join(el.itertext()).strip() if el is not None else ""

        pmid = txt(".//PMID")
        doi = ""
        for aid in art.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text or ""
        abstract = " ".join(
            "".join(a.itertext()).strip()
            for a in art.findall(".//Abstract/AbstractText")
        )
        out.append({
            "pmid": pmid,
            "title": txt(".//ArticleTitle"),
            "journal": txt(".//Journal/ISOAbbreviation") or txt(".//Journal/Title"),
            "year": txt(".//PubDate/Year") or txt(".//PubDate/MedlineDate")[:4],
            "doi": doi,
            "type": ", ".join(t.text or "" for t in art.findall(".//PublicationType"))[:60],
            "abstract": abstract,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        })
    return out


def report(items: list[dict], show_abstract: bool = False) -> None:
    if not items:
        print("  sin resultados")
        return
    for i, a in enumerate(items, 1):
        print(f"\n{i}. {a['title']}")
        print(f"   {a['journal']} {a['year']} · {a['type']}")
        print(f"   {a['url']}" + (f" · doi:{a['doi']}" if a['doi'] else ""))
        if show_abstract and a["abstract"]:
            print(f"   {a['abstract'][:400]}…")

    print("\n" + "─" * 70)
    print("SIGUIENTE PASO: abrir el paper, leer la cifra en contexto, y curarla")
    print("a data/facts.json. No copiar el abstract — tiene copyright del editor")
    print("y un resumen de estudio clínico publicado por DentRead se lee como")
    print("claim propio. La lectura humana es el control de calidad.")
    print("\nPlantilla:")
    print('  { "id": "...", "themes": ["..."], "number": "...", "number_en": "...",')
    print('    "statement": "...", "statement_en": "...",')
    print(f'    "cite": "{items[0]["journal"]} {items[0]["year"]}, ... (doi:{items[0]["doi"] or "..."})",')
    print('    "tier": "primary" }')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query")
    ap.add_argument("--preset", choices=sorted(PRESETS))
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--abstract", action="store_true")
    args = ap.parse_args()

    term = args.query or PRESETS.get(args.preset or "")
    if not term:
        print("Presets disponibles:")
        for k, v in PRESETS.items():
            print(f"  {k:<12} {v[:70]}…")
        return

    print(f"PubMed · últimos {args.years} años · revisiones y estudios poblacionales")
    report(summarize(search(term, args.years, args.n)), args.abstract)


if __name__ == "__main__":
    main()
