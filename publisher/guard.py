"""
Claims guard v3 — clasifica por TIPO y FUERZA de afirmación, no por palabra.

Qué cambió respecto de v2
-------------------------
La versión anterior bloqueaba términos. Cualquier aparición de "diagnóstico"
frenaba el post, así que el sistema empujaba a DentRead a describirse solo
por sus restricciones: "no diagnostica", "no es un dispositivo", "no hace
lectura". Eso protege de un claim falso y a la vez impide decir lo que la
empresa efectivamente es — una empresa de IA aplicada a radiografías
dentales y al flujo clínico.

El problema nunca fue la palabra. Es la estructura de la afirmación:

    "IA para radiografías dentales"                    describe capacidad
    "detecta caries con 92% de sensibilidad"           afirma desempeño
    "mejora la aceptación de tratamientos"             promete resultado
    "garantiza menos errores diagnósticos"             promesa absoluta
    "FDA-cleared"                                      estado regulatorio
    "más preciso que Pearl"                            comparación

Las seis contienen vocabulario clínico. Solo dos son un problema en
cualquier contexto.

El modelo
---------
Cada afirmación se clasifica en dos ejes:

  DOMINIO    capability · performance · outcome · regulatory ·
             comparative · traction · guarantee
  FUERZA     hedged ("busca", "puede", "está orientado a")
             assertive ("mejora", "reduce", "aumenta")
             absolute ("garantiza", "elimina", "siempre", "100%")

Y la decisión sale de la combinación, no del término suelto. La política
completa, con la separación entre posicionamiento corporativo, claims
comerciales, clínicos, regulatorios y descripción técnica, está en
`claims_policy.md`.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BLOCK, REVIEW, INFO = "BLOCK", "REVIEW", "INFO"

# --------------------------------------------------------------------------
# Fuerza de la afirmación
# --------------------------------------------------------------------------

HEDGED = re.compile(
    r"\b(busca|buscamos|puede|pueden|podría|podrían|apunta a|orientad[oa] a|"
    r"est[áa] diseñad[oa] para|diseñad[oa] para|con el objetivo de|"
    r"contribuir a|apoyar|apoya|acompañar|facilitar|explora|"
    r"aims? to|seeks? to|can|could|may|is designed to|intended to|"
    r"helps?|supports?|contributes? to|is exploring)\b", re.I)

ABSOLUTE = re.compile(
    r"\b(garantiza|garantizamos|garantizad[oa]|asegura|elimina|erradica|"
    r"siempre|nunca falla|todos los casos|sin excepci[óo]n|100\s?%|"
    r"cero errores|infalible|definitiv[oa]|"
    r"guarantee[sd]?|ensures?|eliminates?|always|never fails|"
    r"every case|foolproof|risk[\s-]free|sin riesgo)\b", re.I)

# --------------------------------------------------------------------------
# Dominios
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Domain:
    id: str
    pattern: str
    # decisión según fuerza: hedged / assertive / absolute
    hedged: str
    assertive: str
    absolute: str
    satisfied_by: str | None = None
    why: str = ""
    fix: str = ""


DOMAINS: list[Domain] = [
    # --- Garantía: promesa absoluta, sin importar sobre qué. --------------
    # Va primero y sin dominio asociado: "garantiza menos errores" no toca
    # ninguna otra categoría y aun así es el claim menos defendible que
    # DentRead puede hacer. Una garantía es una obligación creada en un post.
    Domain(
        "guarantee",
        ABSOLUTE.pattern,
        hedged=BLOCK, assertive=BLOCK, absolute=BLOCK,
        why="Una garantía o un absoluto crean una obligación que el producto "
            "no puede sostener, y basta un contraejemplo para desmentirla.",
        fix="'Está diseñado para' / 'busca' / 'puede contribuir a'.",
    ),

    # --- Capacidad: qué hace el producto. Es descripción, no promesa. ------
    Domain(
        "capability",
        r"\b(inteligencia artificial|artificial intelligence|\bIA\b|\bAI\b|"
        r"an[áa]lisis radiogr[áa]fico|radiographic analysis|"
        r"radiograf[íi]as?|radiographs?|im[áa]genes dentales|dental imaging|"
        r"flujo cl[íi]nico|clinical workflow|herramienta|tool|plataforma|platform)\b",
        hedged="", assertive="", absolute=ABSOLUTE.pattern and BLOCK,
        why="Describir capacidad es legítimo; prometerla en absoluto no.",
        fix="Quitá el absoluto: 'garantiza' → 'está diseñado para'.",
    ),

    # --- Desempeño: qué tan bien lo hace. Exige evidencia. -----------------
    Domain(
        "performance",
        r"\b(sensibilidad|especificidad|precisi[óo]n|exactitud|concordancia|"
        r"\bAUC\b|\bF1\b|sensitivity|specificity|accuracy|precision|"
        r"detection rate|tasa de detecci[óo]n)\b"
        r"|(\d{1,3}(?:[.,]\d+)?\s?%\s*(?:de\s+)?(?:precisi[óo]n|sensibilidad|"
        r"especificidad|accuracy|sensitivity|specificity))",
        hedged=REVIEW, assertive=REVIEW, absolute=BLOCK,
        satisfied_by="model_metrics_documented",
        why="Una métrica de desempeño exige dataset, N, población y método.",
        fix="Publicá el estudio o declarálo en post.json; si no, sacá la cifra.",
    ),

    # --- Resultado: qué consigue el usuario. Matizado, se puede. ----------
    Domain(
        "outcome",
        r"\b(mejora|mejoran|aumenta|aumentan|reduce|reducen|incrementa|"
        r"acelera|optimiza|ahorra|recupera|"
        r"improves?|increases?|reduces?|boosts?|accelerates?|saves?|recovers?)\s+"
        r"\w*\s?(aceptaci[óo]n|acceptance|ingresos|revenue|tiempo|time|"
        r"eficiencia|efficiency|resultados|outcomes|productividad|productivity|"
        r"confianza|trust|comprensi[óo]n|understanding|desempe[ñn]o|performance|"
        r"consistencia|consistency|seguimiento|follow[\s-]up)",
        hedged="", assertive=REVIEW, absolute=BLOCK,
        satisfied_by="has_source",
        why="Afirmar una mejora sin matiz ni fuente es una promesa de resultado.",
        fix="Matizá ('puede contribuir a', 'busca mejorar') o citá la evidencia.",
    ),

    # --- Cifras de resultado en dinero o porcentaje ------------------------
    Domain(
        "quantified_outcome",
        r"(\d{1,3}\s?%\s*(m[áa]s|menos|de\s+(aumento|mejora|reducci[óo]n))|"
        r"(aumento|mejora|reducci[óo]n|increase|improvement|reduction)\s+(de|del|of)\s+\d{1,3}\s?%|"
        r"[$€]\s?\d[\d.,]*\s*(por|per|al|a[ñn]o|month|mes)|"
        r"\d+(\.\d+)?x\s+(m[áa]s|faster|more|better))",
        hedged=REVIEW, assertive=REVIEW, absolute=BLOCK,
        satisfied_by="has_source",
        why="Una cifra de resultado atribuida al producto exige medición propia.",
        fix="Citá la fuente o convertilo en escenario explícito.",
    ),

    # --- Estado regulatorio: verificable en un registro público -----------
    Domain(
        "regulatory",
        r"\b(FDA[\s-]?(cleared|approved|aprobad[oa]|autorizad[oa])|510\s?\(?k\)?|"
        r"CE[\s-]?mark(ed)?|marcado\s?CE|HIPAA[\s-]?(compliant|certified|certificad)|"
        r"SOC\s?2\s?(certified|compliant|type\s?II)|ISO\s?(13485|27001)\s?certified|"
        r"ANMAT|COFEPRIS|ISP)\b",
        hedged=REVIEW, assertive=REVIEW, absolute=BLOCK,
        satisfied_by="regulatory_status_verified",
        why="El estado regulatorio se verifica en un registro público en un clic.",
        fix="Declaralo solo si está emitido, con número y fecha. Si no, omitilo.",
    ),

    # --- Comparación con competidores nombrados ---------------------------
    Domain(
        "comparative",
        r"\b(mejor|superior|m[áa]s\s+\w+|better|superior|more\s+\w+|outperform\w*)"
        r"\s+(que|than)\s+(Pearl|Overjet|VideaHealth|Videa|Diagnocat|Denti\.?AI|"
        r"la competencia|the competition|los dem[áa]s|others)",
        hedged=REVIEW, assertive=BLOCK, absolute=BLOCK,
        satisfied_by="head_to_head_study",
        why="Publicidad comparativa sin estudio head-to-head es riesgo legal.",
        fix="Diferenciá por lo que hacés distinto, no por ser mejor.",
    ),

    # --- Tracción: clientes, pilotos, volumen -----------------------------
    Domain(
        "traction",
        r"\b((trusted by|used (in|by)|usado (en|por)|conf[íi]an en|"
        r"m[áa]s de|more than|over)\s+\d+\s*\+?\s*"
        r"(cl[íi]nicas?|clinics?|practices?|DSOs?|dentistas?|dentists?|"
        r"organizaciones|organizations|pacientes|patients)|"
        r"\d+\s+(pilotos?|pilots?)\s+(activos?|running|live|en curso)|"
        r"nuestros\s+clientes\s+(reportan|logran|obtienen)|"
        r"our\s+(customers|clients)\s+(report|see|achieve))",
        hedged=REVIEW, assertive=REVIEW, absolute=BLOCK,
        satisfied_by="traction_verified",
        why="Volumen de clientes o pilotos se verifica en una llamada.",
        fix="Declarálo solo si el número es exacto y actual.",
    ),

    # --- Sustitución del profesional --------------------------------------
    Domain(
        "replacement",
        r"\b(reemplaza|sustituye|replaces?|substitutes?)\s+(al?\s+|the\s+)?"
        r"(dentista|profesional|cl[íi]nico|radi[óo]logo|criterio|juicio|"
        r"dentist|clinician|radiologist|professional|judgment)",
        hedged=REVIEW, assertive=BLOCK, absolute=BLOCK,
        why="Posicionarse como sustituto del profesional agrava el perfil "
            "regulatorio en cualquier jurisdicción.",
        fix="'Apoya al profesional' / 'supports the clinician'.",
    ),

    # --- Identificadores de paciente --------------------------------------
    Domain(
        "phi",
        r"\b(patient\s+(name|DOB|record\s?#|chart\s?#)|"
        r"nombre\s+del\s+paciente|RUT\s+del\s+paciente|ficha\s+cl[íi]nica\s+n)",
        hedged=BLOCK, assertive=BLOCK, absolute=BLOCK,
        why="Posible identificador de paciente en material público.",
        fix="Eliminalo. No hay versión aceptable.",
    ),

    # --- Reglas propias del brand guide de DentRead ------------------------
    # Salen de brand/references/brand-and-compliance.md. No son riesgo
    # regulatorio sino consistencia de marca, pero el brand guide las marca
    # como no negociables y un sistema que publica solo no tiene a nadie que
    # las mire.
    Domain(
        "competitor_figures",
        r"\b(Pearl|Overjet|VideaHealth|Diagnocat)\b",
        hedged=REVIEW, assertive=REVIEW, absolute=REVIEW,
        why="El brand guide prohíbe citar cifras de competidores salvo "
            "pedido explícito; prefiere fuentes neutrales.",
        fix="Usar CareQuest, ADA Health Policy Institute, FDI, Planet DDS "
            "o ADA.",
    ),
    Domain(
        "em_dash",
        r"—",
        hedged=REVIEW, assertive=REVIEW, absolute=REVIEW,
        why="El brand guide prohíbe em dashes en material de marca.",
        fix="Reemplazar por dos puntos, punto seguido o paréntesis.",
    ),
]

# Frases que neutralizan un match por negación o aclaración explícita.
NEGATABLE = (r"(diagnos\w*|diagn[óo]stic\w*|dispositivo\s+m[ée]dico|"
             r"medical\s+device|reemplaza\w*|replaces?)")
NEGATION = (
    r"\b(no|not|never|nunca|sin|without|"
    r"does\s+not|doesn'?t|do\s+not|don'?t|is\s+not|isn'?t|are\s+not|"
    r"n[io]\s+es|n[io]\s+hace|n[io]\s+entrega|n[io]\s+reemplaza|"
    r"rather\s+than|instead\s+of|en\s+lugar\s+de)\b"
    r"[^.;!?]{0,45}?" + NEGATABLE
)


@dataclass
class Finding:
    level: str
    domain: str
    strength: str
    match: str
    why: str
    fix: str

    def __str__(self) -> str:
        return (f"  {self.level:<6} {self.domain}/{self.strength:<9} “{self.match}”\n"
                f"         por qué: {self.why}\n"
                f"         arreglo: {self.fix}")


@dataclass
class GuardResult:
    ok: bool
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def report(self) -> str:
        parts = [str(f) for f in self.findings] + [f"  INFO   {n}" for n in self.notes]
        return "\n".join(parts) if parts else "  sin hallazgos"


def strength_of(text: str, around: int, window: int = 90) -> str:
    """Fuerza de la afirmación, mirando la oración que rodea al match."""
    lo = max(0, around - window)
    chunk = text[lo: around + window]
    if ABSOLUTE.search(chunk):
        return "absolute"
    if HEDGED.search(chunk):
        return "hedged"
    return "assertive"


def _strip_negated(text: str) -> str:
    """
    Un término regulado negado dice lo contrario del claim.

    "no reemplaza al profesional" es exactamente lo que se quiere poder decir.
    Se detecta por contexto y no con una lista de frases, porque las variantes
    son infinitas y cada una que falte bloquea contenido legítimo.
    """
    return re.sub(NEGATION, " ", text, flags=re.I)


def check(text: str, declarations: dict | None = None) -> GuardResult:
    decl = declarations or {}
    cleaned = _strip_negated(text)
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()

    for dom in DOMAINS:
        for m in re.finditer(dom.pattern, cleaned, flags=re.I):
            hit = m.group(0).strip()[:70]
            key = (dom.id, hit.lower())
            if key in seen:
                continue
            seen.add(key)

            strength = strength_of(cleaned, m.start())
            level = {"hedged": dom.hedged, "assertive": dom.assertive,
                     "absolute": dom.absolute}[strength]
            if not level:
                continue
            if dom.satisfied_by and decl.get(dom.satisfied_by):
                continue
            findings.append(Finding(level, dom.id, strength, hit, dom.why, dom.fix))

    notes = []
    if not re.search(r"[?¿]", text):
        notes.append("sin pregunta: el post no invita a responder")

    ok = not any(f.level in (BLOCK, REVIEW) for f in findings)
    return GuardResult(ok=ok, findings=findings, notes=notes)


def check_post(meta: dict) -> dict[str, GuardResult]:
    return {
        "ES/Instagram": check(meta.get("caption_es", ""), meta),
        "EN/LinkedIn": check(
            f"{meta.get('commentary_en','')}\n{meta.get('title_en','')}", meta),
    }


def _cli() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    meta = json.loads(Path(sys.argv[1]).read_text())
    failed = False
    for label, res in check_post(meta).items():
        print(f"[guard] {label}: {'OK' if res.ok else 'BLOQUEADO'}")
        print(res.report())
        print()
        failed |= not res.ok
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_cli())
