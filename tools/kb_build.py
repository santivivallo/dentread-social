#!/usr/bin/env python3
"""
Construye el índice de conocimiento de DentRead a partir del corpus de
estudio de mercado (PDFs).

Se corre UNA VEZ (y de nuevo cuando agregues documentos). El resultado es
un JSONL versionado en el repo: sin base de datos vectorial, sin API de
embeddings, sin costo recurrente. La recuperación es BM25 puro en
`pipeline/kb.py`.

    python -m pipeline.kb_build "/ruta/US Market Research" -o data/kb.jsonl

Cada chunk guarda su procedencia. Sin procedencia no hay cita, y sin cita
el claims guard bloquea cualquier métrica.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

CHUNK_WORDS = 220
CHUNK_OVERLAP = 40
MIN_CHUNK_WORDS = 40

# Nivel de evidencia. La distinción importa más que la cifra: un número de
# ADA HPI y uno de un proveedor no se citan igual, aunque digan lo mismo.
#
#   primary      dato primario: organismos, encuestas oficiales, revisión
#                por pares, cuerpos de estándares.
#   consultancy  consultora. Metodología no pública, varía hasta 3x entre
#                firmas. Orden de magnitud, nunca cifra exacta.
#   vendor       material de quien vende la solución. Señal de mercado,
#                jamás evidencia validada.
#   reference    material de referencia / definiciones.
TIER_WEIGHT = {"primary": 1.0, "reference": 0.7, "consultancy": 0.7, "vendor": 0.4}

# (publisher, título, tier, as_of, caution)
SOURCES: dict[str, tuple[str, str, str, str, str]] = {
    "US_Dentist_Workforce_2025": (
        "ADA Health Policy Institute", "US Dentist Workforce 2025",
        "primary", "2025-08", ""),
    "State_US_Dental_Economy_Q42025": (
        "ADA Health Policy Institute", "State of the US Dental Economy Q4 2025",
        "primary", "2025-12", ""),
    "US-Oral-Health-Well-Being": (
        "ADA Health Policy Institute", "US Oral Health and Well-Being",
        "primary", "2024-01", "Datos autorreportados de percepción, no clínicos."),
    "Dental_Care_in_Medicaid_Programs": (
        "ADA Health Policy Institute", "Dental Care in Medicaid Programs",
        "primary", "2025-12", ""),
    "National_Trends_Dental_Use_Benefits_Barriers_2026": (
        "ADA Health Policy Institute",
        "National Trends in Dental Care Use, Coverage and Cost Barriers",
        "primary", "2026-04", "Basado en MEPS y NHIS."),
    "CareQuest_Institute_Out-of-Pocket_11.13.25": (
        "CareQuest Institute", "Out-of-Pocket Costs for Dental Care",
        "primary", "2025-11", ""),
    "Dentistry — Overview of Artificial and Augmented Intelligence Uses in Dentistry": (
        "ADA Standards Committee on Dental Informatics", "SCDI White Paper No. 1106",
        "primary", "2022-12",
        "Aprobado en dic-2022. En IA eso es antiguo: útil para marcos y "
        "definiciones, no para el estado del arte."),
    "FDI ARTIFICIAL INTELLIGENCE WORKING GROUP WHITE PAPER_0": (
        "FDI World Dental Federation", "AI Working Group White Paper",
        "primary", "2024-01",
        "Postura de la profesión, deliberadamente más cauta que el mercado."),
    "Article - Billing and Coding_ Dental Services (A59449)": (
        "CMS", "Billing and Coding: Dental Services (A59449)",
        "primary", "2025-01", ""),
    "us-dental-outlook": (
        "L.E.K. Consulting", "Outlook for the US Dental Industry",
        "consultancy", "2023-01",
        "Consultora: metodología no pública. Cifras base de 2022. Usar como "
        "orden de magnitud."),
    "CDT codes vs CPT codes_ What’s the difference_": (
        "Referencia", "CDT vs CPT codes",
        "reference", "2025-01", ""),
    "2025-Dental-Industry-Outlook-Planet-DDS": (
        "Planet DDS (proveedor de PMS)", "2025 Dental Industry Outlook",
        "vendor", "2025-01",
        "Publicado por un proveedor de PMS. Señal de mercado, no evidencia."),
    "The growth of AI in dental radiology _ Pearl AI": (
        "Pearl AI (competidor)", "The growth of AI in dental radiology",
        "vendor", "2025-01",
        "Material de un competidor directo. Nunca citar como evidencia a "
        "favor de DentRead."),
    "AI in Dentistry_ Faster, More Accurate Diagnoses, Fewer Claim Denials": (
        "Forbes (contributor)", "How AI Is Transforming Dentistry",
        "vendor", "2026-05",
        "Nota de contributor construida alrededor del CEO de Overjet. "
        "Tratar como material de proveedor."),
}

# Cifras que solo se pueden usar por dirección del efecto, nunca por magnitud.
FUNDED_STUDY_MARKERS = (
    "united concordia", "cigna", "delta dental", "guardian", "metlife",
)


def extract(pdf: Path) -> list[tuple[int, str]]:
    """Devuelve [(página, texto)] usando pdftotext (rápido y sin dependencias Python)."""
    out = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
        capture_output=True, text=True, timeout=180,
    )
    if out.returncode != 0:
        return []
    return [(i, p) for i, p in enumerate(out.stdout.split("\f"), start=1) if p.strip()]


def clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # cortes de guion al final de línea
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"(?<![.\n])\n(?![\n•\-\d])", " ", text)
    return text.strip()


def chunk(text: str) -> list[str]:
    words = text.split()
    step = CHUNK_WORDS - CHUNK_OVERLAP
    out = []
    for i in range(0, max(1, len(words)), step):
        piece = words[i:i + CHUNK_WORDS]
        if len(piece) >= MIN_CHUNK_WORDS:
            out.append(" ".join(piece))
        if i + CHUNK_WORDS >= len(words):
            break
    return out


def has_number(text: str) -> bool:
    """
    Los chunks con cifras son los que sirven para sostener un claim.

    Cuenta porcentajes, montos, magnitudes y también conteos simples de dos
    dígitos o más ("60 cambios", "31 adiciones"): son datos igual de citables
    y quedaban afuera.
    """
    patterns = (
        r"\d[\d,.]*\s?%",                                    # 45%
        r"[$€]\s?\d",                                        # $1,200
        r"\b\d[\d,.]*\s?(percent|million|billion|thousand)",  # 3 million
        r"\b\d{2,}\b",                                       # 60, 240, 1944
        r"\b\d+\s?(in|of|de)\s?\d+\b",                       # 1 in 4
    )
    return any(re.search(p, text, re.I) for p in patterns)


def funded_study(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in FUNDED_STUDY_MARKERS) and bool(
        re.search(r"(saving|savings|cost|ahorro|\$)", low)
    )


# Notas de corpus propias: investigación verificada que no viene en PDF.
# Van como `primary` porque cada una cita su fuente primaria y declara sus
# limitaciones en el propio texto.
NOTES_DIR = Path("data/corpus_notes")
NOTE_SOURCES: dict[str, tuple[str, str, str, str, str]] = {
    "cdt-2026-sin-codigos-ia": (
        "ADA News / ADA.org (verificado por DentRead)",
        "CDT 2026: cambios de código y ausencia de códigos de IA",
        "primary", "2026-01",
        "La ADA destacó algunas de las 31 adiciones, no las publicó todas en "
        "abierto. Afirmar 'no se ha reportado un código de IA', nunca "
        "'ninguna de las 31 es de IA'."),
}


def build_notes(records: list, stats: dict) -> None:
    """Indexa las notas markdown de data/corpus_notes/."""
    if not NOTES_DIR.exists():
        return
    for md in sorted(NOTES_DIR.glob("*.md")):
        stem = md.stem
        publisher, title, tier, as_of, caution = NOTE_SOURCES.get(
            stem, ("DentRead (nota interna)", stem, "primary", "", "")
        )
        body = clean(md.read_text())
        n = 0
        for j, piece in enumerate(chunk(body)):
            records.append({
                "id": f"{stem}::note::c{j}",
                "text": piece,
                "publisher": publisher,
                "title": title,
                "tier": tier,
                "as_of": as_of,
                "caution": caution,
                "page": j + 1,
                "file": md.name,
                "vendor_source": False,
                "quantitative": has_number(piece),
                "funded_study": False,
            })
            n += 1
        stats[title] = n
        print(f"  [{tier:<11}] {title[:52]:<52} {n:>5} chunks  (nota)")


def build(folder: Path, out_path: Path) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    records, stats = [], {}
    unmapped = []

    for pdf in sorted(folder.rglob("*.pdf")):
        stem = pdf.stem
        if stem not in SOURCES:
            unmapped.append(stem)
        publisher, title, tier, as_of, caution = SOURCES.get(
            stem, ("Sin clasificar", stem, "vendor", "",
                   "Fuente no clasificada: tratada como material de proveedor "
                   "hasta que se le asigne un nivel de evidencia.")
        )
        pages = extract(pdf)
        n = 0
        for page_no, raw in pages:
            body = clean(raw)
            if len(body.split()) < MIN_CHUNK_WORDS:
                continue
            for j, piece in enumerate(chunk(body)):
                records.append({
                    "id": f"{stem}::p{page_no}::c{j}",
                    "text": piece,
                    "publisher": publisher,
                    "title": title,
                    "tier": tier,
                    "as_of": as_of,
                    "caution": caution,
                    "page": page_no,
                    "file": pdf.name,
                    "vendor_source": tier == "vendor",
                    "quantitative": has_number(piece),
                    "funded_study": funded_study(piece),
                })
                n += 1
        stats[title] = n
        print(f"  [{tier:<11}] {title[:52]:<52} {n:>5} chunks")

    build_notes(records, stats)

    if unmapped:
        print("\n[warn] documentos sin clasificar (van como 'vendor' por defecto):")
        for s in unmapped:
            print(f"       - {s}")
        print("       Agregalos a SOURCES en pipeline/kb_build.py")

    with out_path.open("w") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n[ok] {len(records)} chunks -> {out_path} "
          f"({out_path.stat().st_size/1e6:.1f}MB)")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("data/kb.jsonl"))
    args = ap.parse_args()
    build(args.folder, args.out)


if __name__ == "__main__":
    main()
