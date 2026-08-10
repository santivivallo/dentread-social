"""
Literatura científica como contenido: modo SEÑALIZADOR.

El problema con publicar estudios
---------------------------------
Resumir un hallazgo clínico es la categoría de mayor riesgo que DentRead
puede publicar. Un paper que concluye "la IA detectó caries con 92% de
sensibilidad", republicado por una empresa de IA dental sin FDA clearance,
se lee como claim propio por más atribución que lleve. Y el abstract tiene
copyright del editor.

La solución: no contar la conclusión
------------------------------------
Un post señalizador dice **qué se preguntó y cómo**, y enlaza. No dice qué
se encontró.

    "Nuevo en JADA: ¿los omega-3 modifican la inflamación periodontal?
     Análisis secundario de un ensayo aleatorizado con 240 pacientes.
     Link al estudio."

Eso es periodismo de agenda, no claim clínico. Es útil para un dentista que
quiere estar al día, es honesto sobre lo que DentRead sabe y no sabe, y no
reproduce obra ajena: título, revista, diseño del estudio y N son hechos
descriptivos, no la expresión creativa del autor.

Lo que este módulo NO deja pasar está en FORBIDDEN: efectos, conclusiones,
significancia, superioridad. Si el texto generado los contiene, se descarta.

Fuente: PubMed E-utilities, API oficial y gratuita del NCBI. Sin scraping.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from tools.pubmed import PRESETS, search, summarize

# Revistas cuyo alcance es relevante para la audiencia de DentRead.
JOURNAL_ALLOWLIST = {
    "j am dent assoc", "jada", "j dent res", "j dent", "int dent j",
    "community dent oral epidemiol", "bmc oral health", "jdr clin trans res",
    "clin oral investig", "j public health dent", "health aff",
}

# Vocabulario de conclusión. Si aparece en el texto que se va a publicar,
# el post deja de ser señalizador y pasa a ser claim.
FORBIDDEN = re.compile(
    r"\b(significant|significativ|improved|mejor[óo]|reduced|redujo|increase[d]?|"
    r"aument[óo]|effective|eficaz|superior|outperform|accuracy|sensitivity|"
    r"specificity|precisi[óo]n|sensibilidad|especificidad|proven|demostr[óo]|"
    r"conclude[ds]?|concluy[óe]|associated with|asociad[oa] (a|con)|"
    r"\d+(\.\d+)?\s?%|p\s?[<=]\s?0?\.\d+|odds ratio|hazard ratio|\bOR\b|\bCI\b)",
    re.I,
)

# Diseños que vale la pena señalizar. Un reporte de caso no es noticia.
DESIGNS = {
    "Randomized Controlled Trial": "ensayo aleatorizado",
    "Systematic Review": "revisión sistemática",
    "Meta-Analysis": "metaanálisis",
    "Multicenter Study": "estudio multicéntrico",
    "Observational Study": "estudio observacional",
    "Comparative Study": "estudio comparativo",
}


@dataclass
class Signpost:
    pmid: str
    title: str
    journal: str
    year: str
    url: str
    design: str
    design_es: str
    n: str = ""

    def question_es(self) -> str:
        """El título como pregunta, sin conclusión."""
        t = self.title.rstrip(".")
        # Muchos títulos ya vienen como "X: a randomized trial"
        return t.split(":")[0].strip()

    def line_es(self) -> str:
        bits = [f"Nuevo en {self.journal}"]
        detail = self.design_es or "estudio"
        if self.n:
            detail += f", {self.n} participantes"
        return f"{bits[0]}: {self.question_es()}. {detail.capitalize()}."

    def line_en(self) -> str:
        detail = self.design or "study"
        if self.n:
            detail += f", {self.n} participants"
        return f"New in {self.journal}: {self.question_es()}. {detail}."


def _extract_n(abstract: str) -> str:
    """N del estudio: es un hecho descriptivo, no una conclusión."""
    for pat in (r"\b(\d{2,6})\s+(?:patients|participants|subjects|adults|children)",
                r"\bn\s?=\s?(\d{2,6})\b"):
        m = re.search(pat, abstract, re.I)
        if m:
            return m.group(1)
    return ""


def _design(pub_types: str) -> tuple[str, str]:
    for en, es in DESIGNS.items():
        if en.lower() in pub_types.lower():
            return en, es
    return "", ""


def find(preset: str = "ia", years: int = 1, n: int = 10) -> list[Signpost]:
    """Candidatos a señalizar. Filtra por revista, diseño y fecha."""
    out: list[Signpost] = []
    for a in summarize(search(PRESETS.get(preset, preset), years, n * 2)):
        journal = (a["journal"] or "").lower().rstrip(".")
        if not any(j in journal for j in JOURNAL_ALLOWLIST):
            continue
        design, design_es = _design(a["type"])
        if not design:
            continue
        sp = Signpost(
            pmid=a["pmid"], title=a["title"], journal=a["journal"],
            year=a["year"], url=a["url"], design=design, design_es=design_es,
            n=_extract_n(a["abstract"]),
        )
        # el propio título puede traer la conclusión: si la trae, se descarta
        if FORBIDDEN.search(sp.question_es()):
            continue
        out.append(sp)
        if len(out) >= n:
            break
    return out


def validate(text: str) -> list[str]:
    """
    Último control antes de publicar. Un señalizador no puede contener
    vocabulario de conclusión ni cifras de resultado.
    """
    return [m.group(0) for m in FORBIDDEN.finditer(text)]


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="ia", choices=sorted(PRESETS))
    ap.add_argument("--years", type=int, default=1)
    args = ap.parse_args()

    found = find(args.preset, args.years)
    print(f"{len(found)} candidatos a señalizar\n")
    for s in found:
        print(f"· {s.line_es()}")
        print(f"  {s.url}")
        bad = validate(s.line_es())
        if bad:
            print(f"  ✗ contiene vocabulario de conclusión: {bad}")
        print()
    if found:
        print("Un señalizador dice qué se preguntó y cómo. Nunca qué se encontró.")


if __name__ == "__main__":
    _cli()
