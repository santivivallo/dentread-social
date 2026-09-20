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

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

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

    # El abstract, que es lo ÚNICO que el resumidor puede resumir.
    #
    # Faltaba, y `sources.post_from_signpost` lo leía con
    # `getattr(sp, "abstract", "")`: siempre vacío. Así el texto fuente de un
    # paper era solo el título, unos 90 caracteres, y `resumen_verificado`
    # exige 200. Cada turno de paper moría con SinMaterial y se lo llevaba un
    # post de datos. Entre el 10 de agosto y el 15 de septiembre de 2026 no
    # se publicó ni un paper, teniendo una ranura de cada seis reservada.
    #
    # No se publica el abstract: se resume, y ese resumen pasa por newsguard,
    # el claims guard y el control de magnitudes como cualquier otro texto.
    abstract: str = ""

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


ARCHIVO = Path("data/pubmed_archive.json")


def _archivo_vacio() -> dict:
    return {"estudios": {}, "weeks": {}, "runs": 0}


def cargar() -> dict:
    if ARCHIVO.exists():
        try:
            return {**_archivo_vacio(), **json.loads(ARCHIVO.read_text())}
        except ValueError:
            pass
    return _archivo_vacio()


def guardar(arch: dict) -> None:
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(json.dumps(arch, indent=1, ensure_ascii=False))


def marcar_publicado(pmid: str) -> None:
    """Un estudio que salió al feed no se vuelve a proponer."""
    if not pmid:
        return
    arch = cargar()
    arch["estudios"].setdefault(str(pmid), {})["used"] = True
    guardar(arch)


def find(preset: str = "ia", years: int = 1, n: int = 10) -> list[Signpost]:
    """
    Candidatos a señalizar. Filtra por revista, diseño y fecha, y **archiva
    todo lo que ve con el motivo por el que lo descartó**.

    **Por qué archiva.** Los papers tienen 1 de las 6 ranuras del ciclo y
    llevan 0 publicaciones. Ese es el mismo síntoma exacto que tuvieron las
    noticias entre el 10 de agosto y el 15 de septiembre de 2026, cuando la
    causa resultó ser que el archivo de ADA no guardaba el cuerpo del artículo
    —algo que nadie podía ver porque cada pieza hacía lo suyo bien.

    La diferencia es que las noticias sí tenían archivo, así que la causa se
    pudo reconstruir. Acá no había nada: cada corrida consultaba PubMed en
    vivo, descartaba en silencio por revista, por diseño o por título
    concluyente, y no dejaba rastro. Diagnosticar el 0 era imposible sin
    adivinar, y adivinar ya costó una semana con el 410 de GitHub Models.

    Así que ahora cada candidato queda con su motivo. Después de una corrida
    real, `python -m pipeline.journals --archivo` dice si el cuello está en la
    allowlist de revistas, en los diseños aceptados o en el detector de
    conclusiones.

    Y además el archivo es la base de datos que Santiago pidió que creciera:
    PubMed no recuerda nada entre consultas, así que sin esto la literatura
    vista se perdía en cada corrida.
    """
    arch = cargar()
    semana = date.today().strftime("%G-W%V")
    ya_usados = {p for p, e in arch["estudios"].items() if e.get("used")}
    nuevos: list[str] = []

    out: list[Signpost] = []
    for a in summarize(search(PRESETS.get(preset, preset), years, n * 2)):
        pmid = str(a["pmid"])
        journal = (a["journal"] or "").lower().rstrip(".")
        design, design_es = _design(a["type"])

        # El motivo se decide una sola vez y se guarda. Sin esto, un turno de
        # paper que no publica nada no deja forma de saber por qué.
        motivo = ""
        if not any(j in journal for j in JOURNAL_ALLOWLIST):
            motivo = "revista_fuera_de_allowlist"
        elif not design:
            motivo = f"diseno_no_señalizable:{a['type']}"[:60]

        sp = None
        if not motivo:
            sp = Signpost(
                pmid=pmid, title=a["title"], journal=a["journal"],
                year=a["year"], url=a["url"], design=design,
                design_es=design_es, n=_extract_n(a["abstract"]),
                abstract=a.get("abstract", ""),
            )
            # El propio título puede traer la conclusión: si la trae, publicar
            # el señalizador seria publicar un claim.
            hallado = FORBIDDEN.search(sp.question_es())
            if hallado:
                motivo = f"titulo_concluyente:{hallado.group(0)}"[:60]

        registro = arch["estudios"].get(pmid, {})
        if pmid not in arch["estudios"]:
            nuevos.append(pmid)
        registro.update({
            "title": a["title"][:180], "journal": a["journal"],
            "year": a["year"], "design": design or "",
            "preset": preset, "first_seen": registro.get("first_seen", semana),
            "descartado": motivo,
        })
        arch["estudios"][pmid] = registro

        if motivo or pmid in ya_usados:
            continue
        out.append(sp)
        if len(out) >= n:
            break

    arch["runs"] = arch.get("runs", 0) + 1
    arch["weeks"][semana] = sorted(set(arch["weeks"].get(semana, [])) | set(nuevos))
    try:
        guardar(arch)
    except OSError:
        pass          # un archivo de diagnóstico no frena una publicación
    return out


def cobertura() -> str:
    """Qué vio el archivo y por qué descartó, para diagnosticar el 0."""
    arch = cargar()
    est = arch["estudios"]
    motivos: dict[str, int] = {}
    for e in est.values():
        clave = (e.get("descartado") or "PUBLICABLE").split(":")[0]
        motivos[clave] = motivos.get(clave, 0) + 1
    lineas = [f"archivo de PubMed: {len(est)} estudios · "
              f"{len(arch['weeks'])} semanas · {arch.get('runs', 0)} consultas",
              f"publicados por DentRead: "
              f"{sum(1 for e in est.values() if e.get('used'))}", "",
              "por qué se descartó cada uno:"]
    for k, v in sorted(motivos.items(), key=lambda x: -x[1]):
        lineas.append(f"  {v:5}  {k}")
    revistas: dict[str, int] = {}
    for e in est.values():
        if (e.get("descartado") or "").startswith("revista"):
            revistas[(e.get("journal") or "?")[:40]] = \
                revistas.get((e.get("journal") or "?")[:40], 0) + 1
    if revistas:
        lineas += ["", "revistas rechazadas más frecuentes "
                       "(candidatas a entrar en la allowlist):"]
        for k, v in sorted(revistas.items(), key=lambda x: -x[1])[:10]:
            lineas.append(f"  {v:5}  {k}")
    return "\n".join(lineas)


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
    ap.add_argument("--archivo", action="store_true",
                    help="qué vio el archivo y por qué descartó cada estudio")
    args = ap.parse_args()

    if args.archivo:
        print(cobertura())
        return

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
