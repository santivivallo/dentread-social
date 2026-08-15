"""
Que el texto no cambie QUÉ MIDE una cifra.

**El caso.** Los hechos dicen que el reembolso de Medicaid queda por debajo
del 50% de *lo que cobra el dentista*. El modelo escribió "los aranceles de
Medicaid siguen cubriendo solo una fracción del **costo operativo real**". El
número está bien, la cita está bien, y la frase es falsa: lo que un dentista
cobra no es lo que le cuesta operar. Un lector que decide con eso decide con
un dato que nadie midió.

Es el modo de falla más peligroso del sistema, porque no se parece a un error:
se lee mejor que el original.

**Por qué esto sí se puede medir, si "titular vacío" no se pudo.** Un titular
flojo es una cuestión de criterio y no tiene forma. Esto sí la tiene: el texto
nombra una magnitud que la fuente no nombra. No hace falta entender la frase,
alcanza con comparar de qué familia semántica son los sustantivos de cada
lado.

**La asimetría se invierte acá, y por eso es un rechazo y no un puntaje.** En
estilo, rechazar de más cuesta contenido bueno. En exactitud, aceptar de más
cuesta publicar algo falso con la cita de la ADA al pie. Ante la duda, se
descarta el candidato: hay tres más y, si todos fallan, el texto curado.

Las familias son deliberadamente pocas. Cubren las confusiones que ya
aparecieron o que son plausibles en este dominio, no todo el español.
"""
from __future__ import annotations

import re
import unicodedata

# Familias de magnitudes que se confunden entre sí. Si el texto generado usa
# una palabra de una familia, la fuente tiene que usar alguna de esa misma
# familia; si no, está hablando de otra cosa.
#
# **Cada familia es bilingüe, y no es un detalle.** El texto se genera en
# español pero ADA News y PubMed publican en inglés. Con las familias solo en
# español, una fuente inglesa no activaba ninguna y CUALQUIER resumen parecía
# un desvío: el control habría rechazado todos los resúmenes de noticias, que
# es justo el camino que más lo necesita.
FAMILIAS: dict[str, set[str]] = {
    # Lo que el profesional cobra ≠ lo que le cuesta operar. Esta es la que
    # falló.
    "pago_al_profesional": {"honorario", "honorarios", "arancel", "aranceles",
                            "reembolso", "reembolsos", "tarifa", "tarifas",
                            "pago", "pagos", "remuneracion",
                            "fee", "fees", "reimbursement", "reimbursements",
                            "payment", "payments", "rate", "rates"},
    "costo_de_operar": {"costo", "costos", "coste", "gasto", "gastos",
                        "estructura", "operativo", "operativos", "overhead",
                        "rentabilidad", "margen", "margenes",
                        "cost", "costs", "expense", "expenses", "margin",
                        "profitability"},

    # Estar cubierto ≠ ir al dentista. Medio catálogo trata de esta brecha,
    # así que confundirlas borra justo el punto.
    "cobertura": {"cobertura", "coberturas", "beneficio", "beneficios",
                  "asegurado", "asegurados", "elegible", "elegibles",
                  "seguro", "seguros", "plan", "planes",
                  "coverage", "benefit", "benefits", "insured", "insurance",
                  "eligible", "eligibility", "payer", "network"},
    "uso": {"utilizacion", "uso", "visita", "visitas", "consulta", "consultas",
            "asistencia", "acceso", "atencion",
            "utilization", "visit", "visits", "attendance", "access"},

    # Detectar ≠ tratar. Acá además hay riesgo regulatorio, no solo de
    # exactitud.
    "diagnostico": {"diagnostico", "diagnosticos", "deteccion", "hallazgo",
                    "hallazgos", "lectura", "radiografia", "radiografias",
                    "diagnosis", "diagnostic", "detection", "finding",
                    "findings", "radiograph", "radiographs", "imaging"},
    "tratamiento": {"tratamiento", "tratamientos", "procedimiento",
                    "procedimientos", "terapia", "cirugia", "restauracion",
                    "treatment", "treatments", "procedure", "procedures",
                    "therapy", "surgery", "restoration"},

    # Cuántos profesionales hay ≠ cuánto trabajan.
    "fuerza_laboral": {"dentista", "dentistas", "higienista", "higienistas",
                       "profesional", "profesionales", "personal", "dotacion",
                       "dentist", "dentists", "hygienist", "hygienists",
                       "workforce", "staff", "staffing", "provider",
                       "providers"},
    "capacidad": {"agenda", "agendas", "turno", "turnos", "hora", "horas",
                  "capacidad", "sillon", "sillones",
                  "schedule", "appointment", "appointments", "chair",
                  "chairs", "capacity", "hours"},
}


# La fuente nombra una magnitud de más formas que el texto generado: donde el
# resumen dice "visita", el enunciado curado dice "fue al dentista". Sin esto,
# "no pisó una consulta en el año" se marcaba como desvío sobre una fuente que
# habla exactamente de eso.
#
# Son frases, no palabras, y valen SOLO del lado de la fuente: sirven para
# reconocer que la magnitud está presente, nunca para autorizar una nueva.
FRASES_FUENTE: dict[str, tuple[str, ...]] = {
    "uso": ("al dentista", "a la consulta", "al odontologo", "se atendio",
            "volvio a la clinica", "no volvio"),
    "pago_al_profesional": ("lo que cobra", "lo que paga el seguro",
                            "lo que se paga"),
    "cobertura": ("tiene seguro", "sin seguro", "esta cubierto"),
    "capacidad": ("horas de agenda", "por hora"),
}


def _norm(texto: str) -> set[str]:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return set(re.findall(r"[a-z]+", t))


def familias_de(texto: str, *, es_fuente: bool = False) -> set[str]:
    """
    Qué magnitudes nombra este texto.

    `es_fuente` amplía el reconocimiento con las frases de `FRASES_FUENTE`.
    Solo del lado de la fuente: reconocer de más ahí hace el control más
    permisivo, que es el lado seguro para equivocarse en un reconocedor.
    """
    palabras = _norm(texto)
    presentes = {nombre for nombre, terminos in FAMILIAS.items()
                 if palabras & terminos}
    if es_fuente:
        plano = " ".join(sorted(palabras)) if False else _plano(texto)
        for nombre, frases in FRASES_FUENTE.items():
            if any(f in plano for f in frases):
                presentes.add(nombre)
    return presentes


def _plano(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def desvios(generado: str, fuente: str) -> list[str]:
    """
    Familias que el texto generado nombra y la fuente no. Vacío está bien.

    Lo que se compara son magnitudes, no palabras: parafrasear "reembolso"
    como "arancel" no es un desvío porque las dos están en la misma familia.
    Cambiar "honorario" por "costo operativo" sí lo es.
    """
    de_la_fuente = familias_de(fuente, es_fuente=True)
    return sorted(familias_de(generado) - de_la_fuente)
