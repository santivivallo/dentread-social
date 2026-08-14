"""
Catálogo de temas para contenido dirigido por datos.

Por qué existe: atar todo el contenido a ADA News limita la cadencia a lo
que publique la ADA esa semana (3-4 items útiles) y hace que cada post
arrastre riesgo de copyright y atribución. El corpus de estudio de mercado
soporta contenido por sí solo, sin disparador externo.

El catálogo es la lista de ángulos posibles. Un tema se vuelve publicable
cuando tiene 2 hechos verificados disponibles en data/facts.json — la
rotación y la disponibilidad viven en pipeline/plan.py.

    python -m pipeline.themes            # catálogo y disponibilidad
"""
from __future__ import annotations

from dataclasses import dataclass


# Audiencias:
#   es  → Instagram, español. Clínicas y profesionales de LatAm/Chile.
#   en  → LinkedIn, inglés. Mini-DSOs y operadores en EE.UU.
#   both
ES, EN, BOTH = "es", "en", "both"


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    query: str
    audience: str
    angle: str          # qué tesis sostiene DentRead sobre este dato (ES)
    family: str
    angle_en: str = ""  # el mismo ángulo para LinkedIn; si falta, cae al ES

    # Cierre del carrusel, en dos partes: una afirmación y el giro que va en
    # cian. Es por tema y no una frase global. Antes los doce posts de datos
    # cerraban con "El dato describe el contexto. La decisión está en el
    # flujo.", que no dice nada de ninguno en particular y se lee como relleno.
    close: str = ""
    close_accent: str = ""

    def angle_for(self, lang: str) -> str:
        return (self.angle_en or self.angle) if lang == "en" else self.angle


CATALOG: list[Theme] = [
    # ---- Acceso, cobertura y demanda -----------------------------------
    Theme("medicaid-adultos", "Beneficio dental adulto en Medicaid",
          "Medicaid adult dental benefit enhanced limited emergency states",
          EN,
          "La cobertura define el volumen. Donde el beneficio es amplio la "
          "utilización sube: el cuello de botella es de cobertura, no clínico.",
          "acceso",
          "Coverage sets volume. Where the benefit is broad, utilization rises: the bottleneck is coverage, not clinical capacity.",
          close="Ampliar cobertura llena la agenda.",
          close_accent="Terminar el tratamiento es otro problema."),

    Theme("medicaid-participacion", "Participación de dentistas en Medicaid",
          "dentist participation Medicaid CHIP reimbursement rates",
          EN,
          "Una red que no crece hace años. Quien atiende Medicaid necesita "
          "eficiencia administrativa, no más capacidad clínica.",
          "acceso",
          "A network that has not grown in a decade. Practices that serve Medicaid need administrative efficiency, not more clinical capacity.",
          close="Más clínicas no arreglan la red.",
          close_accent="El cuello está en la administración."),

    Theme("sin-seguro", "Adultos sin seguro dental",
          "uninsured adults dental coverage lack insurance",
          BOTH,
          "Muchísimos más adultos sin seguro dental que médico. El paciente "
          "que paga de su bolsillo decide distinto, y eso cambia cómo hay "
          "que explicarle el tratamiento.",
          "acceso",
          "Far more adults lack dental coverage than medical coverage. A patient paying out of pocket decides differently, and that changes how treatment has to be explained.",
          close="Sin seguro, cada plan se discute.",
          close_accent="Explicar bien vale más que descontar."),

    Theme("costo-barrera", "El costo como barrera de acceso",
          "cost barrier delayed dental care afford out-of-pocket",
          BOTH,
          "El costo es la razón número uno para postergar. La conversación "
          "económica es parte del acto clínico, no un anexo.",
          "acceso",
          "Cost is the number one reason people delay care. The money conversation is part of the clinical encounter, not an afterthought.",
          close="El precio no se objeta: se posterga.",
          close_accent="Lo que no se entiende, no se paga."),

    Theme("utilizacion", "Quién va al dentista y quién no",
          "dental visit utilization adults children past year",
          BOTH,
          "El software del sector se construye sobre los que ya van. La otra "
          "mitad es un problema de acceso que ninguna categoría aborda.",
          "acceso",
          "Dental software is built on the people who already come in. The other half is an access and coverage problem no category addresses.",
          close="El que no vuelve ya estuvo sentado en tu sillón.",
          close_accent="Recuperarlo cuesta menos que conseguir uno nuevo."),

    Theme("ninos-chip", "Cobertura dental infantil y CHIP",
          "children pediatric dental CHIP coverage utilization",
          EN,
          "La cobertura pediátrica es la más sólida del sistema y aun así la "
          "utilización no la sigue. El problema es la conversión, no el beneficio.",
          "acceso",
          "Pediatric coverage is the most robust in the system and utilization still does not follow. The problem is conversion, not the benefit.",
          close="La cobertura está. La visita no.",
          close_accent="El problema es la conversión."),

    Theme("adultos-mayores", "Adultos mayores y el vacío de Medicare",
          "older adults seniors Medicare dental elderly",
          BOTH,
          "El segmento con más necesidad acumulada es el que peor cobertura "
          "tiene.",
          "acceso",
          "The segment with the most accumulated need has the weakest coverage.",
          close="La necesidad acumulada llega en planes largos.",
          close_accent="Los planes largos son los que más se abandonan."),

    Theme("urgencias", "Urgencias hospitalarias por dolor dental",
          "emergency department visits dental conditions avoidable",
          BOTH,
          "Casi dos millones de visitas a urgencias por algo que se resuelve "
          "en un sillón. Es el costo de no tener seguimiento.",
          "acceso",
          "Nearly two million emergency department visits for something a dental chair resolves. That is the cost of no follow-up.",
          close="A urgencias se llega tarde.",
          close_accent="Casi siempre por algo que ya se había visto."),

    # ---- Economía y estructura del sector -------------------------------
    Theme("economia-practica", "La economía de la clínica",
          "practice revenue collections busyness economic confidence",
          BOTH,
          "Ingresos y ocupación se mueven distinto. La brecha entre agenda "
          "llena y cobranza es donde vive el problema operativo.",
          "mercado",
          "Revenue and chair occupancy move differently. The gap between a full schedule and actual collections is where the operational problem lives.",
          close="Agenda llena no es caja llena.",
          close_accent="Entre una cosa y la otra vive el margen."),

    Theme("gasto-nacional", "Cuánto gasta EE.UU. en odontología",
          "national dental expenditures spending billion health",
          EN,
          "Un sector enorme y fragmentado, con una porción estable del gasto "
          "sanitario. El crecimiento viene de eficiencia, no de volumen.",
          "mercado",
          "A large, fragmented sector holding a stable share of health spending. Growth comes from efficiency, not volume.",
          close="El sector no crece atendiendo más rápido.",
          close_accent="Crece terminando lo que ya diagnosticó."),

    Theme("consolidacion-dso", "Consolidación y DSOs",
          "DSO affiliation group practice consolidation trend",
          EN,
          "La decisión de compra se centraliza. Vender a una clínica y "
          "vender a un grupo son dos negocios distintos.",
          "mercado",
          "Purchasing decisions are centralizing. Selling to a practice and selling to a group are two different businesses.",
          close="Quien decide ya no está en el sillón.",
          close_accent="Vender a un grupo es otro negocio."),

    Theme("higienistas", "Escasez de higienistas y dotación",
          "hygienist shortage recruiting staffing difficult practices",
          BOTH,
          "No se puede contratar la salida del problema. Lo que queda es "
          "sacarle horas al trabajo administrativo.",
          "mercado",
          "You cannot hire your way out of this. What is left is taking hours out of administrative work.",
          close="No hay a quién contratar.",
          close_accent="Solo queda devolver horas."),

    Theme("demografia-dentista", "La fuerza laboral odontológica",
          "dentist age gender workforce supply per capita",
          BOTH,
          "Quién ejerce y dónde. La distribución explica más del acceso que "
          "la cantidad total.",
          "mercado",
          "Who practices and where. Distribution explains access better than headcount does.",
          close="Sumar un dentista lleva meses.",
          close_accent="Recuperar una hora de agenda, no."),

    # ---- Clínica, tecnología y tendencias -------------------------------
    Theme("tecnologia-clinica", "Adopción de tecnología en la clínica",
          "technology adoption software digital practice investment",
          BOTH,
          "La tecnología entra por operación, no por clínica. Es un gasto "
          "que se justifica por tiempo recuperado.",
          "tecnologia",
          "Technology enters through operations, not through the clinic. It is an expense justified by time recovered.",
          close="La tecnología entra por la operación.",
          close_accent="Se justifica en tiempo, no en diagnóstico."),

    Theme("imagen-radiologia", "Imagenología y lectura radiográfica",
          "radiographic imaging interpretation caries detection",
          BOTH,
          "La variabilidad entre lectores es un hecho documentado. "
          "Estandarizar la lectura es un problema de proceso.",
          "tecnologia",
          "Variability between readers is documented. Standardizing the read is a process problem.",
          close="El desacuerdo entre lectores ya está documentado.",
          close_accent="Lo que no se registra es qué pasó después."),

    Theme("cbct-3d", "CBCT y volumen 3D",
          "CBCT cone beam three dimensional imaging",
          BOTH,
          "Más datos por paciente no es lo mismo que más claridad para el "
          "paciente.",
          "tecnologia",
          "More data per patient is not the same as more clarity for the patient.",
          close="Más datos no es más claridad.",
          close_accent="El paciente sigue viendo manchas grises."),

    Theme("cdt-sin-codigo-ia", "La IA dental no tiene código de facturación",
          "dental AI billing code CDT reimbursement expense revenue claim",
          BOTH,
          "CDT 2026 sumó 31 códigos y ninguno de los destacados es de IA. "
          "Por eso toda la categoría vende aceptación de tratamiento y no "
          "desempeño de modelo: la IA dental es un gasto, no un ingreso.",
          "mercado",
          "CDT 2026 added 31 codes and none of the highlighted ones covers AI. That is why the whole category sells treatment acceptance instead of model performance: dental AI is an expense, not a revenue line.",
          close="Ningún código paga por usar IA.",
          close_accent="Se paga el tratamiento que sí se termina."),

    Theme("codigos-documentan", "Los códigos nuevos documentan lo que ya se hacía",
          "CDT 2026 new codes point-of-care saliva cracked tooth occlusal guard documentation",
          BOTH,
          "Cinco de las adiciones destacadas de CDT 2026 registran servicios "
          "que ya se prestaban. El código no crea la prestación: la hace "
          "cobrable. Ese es el problema que el software todavía no se resolvió.",
          "mercado",
          "Five of the highlighted CDT 2026 additions record services practices already delivered. The code does not create the procedure, it makes it billable. That is the problem dental software has not solved for itself.",
          close="El código no crea la prestación.",
          close_accent="La vuelve cobrable."),

    Theme("ia-odontologia", "IA en odontología: qué dice la profesión",
          "artificial intelligence dentistry applications clinical",
          BOTH,
          "La postura de la profesión es más cauta que la del mercado. Esa "
          "brecha es el tema, y DentRead está del lado prudente por diseño.",
          "tecnologia",
          "The profession's stance is more cautious than the market's. That gap is the story, and DentRead sits on the prudent side by design.",
          close="La cautela de la profesión no es resistencia.",
          close_accent="Es pedir evidencia antes de cambiar un flujo."),

    # ---- Clínica y prevención -------------------------------------------
    Theme("prevencion", "Prevención y utilización preventiva",
          "preventive care prophylaxis sealant fluoride utilization",
          BOTH,
          "Lo preventivo es lo más cubierto y lo menos completado. El "
          "problema es que el paciente vuelva.",
          "clinica",
          "Preventive care is the most covered and the least completed. The problem is getting the patient back.",
          close="Lo preventivo se cubre y no se completa.",
          close_accent="El problema es que el paciente vuelva."),

    Theme("salud-sistemica", "Salud oral y salud general",
          "oral health systemic disease overall wellbeing quality life",
          BOTH,
          "La boca como parte del cuadro general. Sirve para hablarle al "
          "paciente sin tecnicismos.",
          "clinica",
          "The mouth as part of the whole picture. Useful for talking to patients without jargon.",
          close="El paciente entiende su boca cuando la ve.",
          close_accent="No cuando se la nombran."),

    Theme("periodontal", "Enfermedad periodontal",
          "periodontal disease prevalence treatment gum",
          BOTH,
          "Alta prevalencia, baja completitud de tratamiento. El caso típico "
          "de plan aceptado que no se termina.",
          "clinica",
          "High prevalence, low treatment completion. The textbook case of an accepted plan that never finishes.",
          close="Se diagnostica mucho y se termina poco.",
          close_accent="El plan aceptado que nadie completa."),
]

# Medidos y por debajo del piso — no están en el catálogo porque el corpus
# no los sostiene. Son la lista de compras del KB:
#   - teledentistry              (0.88, solo material de proveedor)
#   - sesgo y validación de IA   (1.27)
#   - downcoding y denegaciones  (0.96, solo proveedores)
#   - códigos CDT para IA        (sin fuente en el corpus)
MISSING_FROM_CORPUS = [
    "teleodontología", "sesgo y validación de modelos",
    "downcoding y denegaciones", "ausencia de códigos CDT para IA",
]




def _cli() -> None:
    from pipeline.plan import available_themes, facts_for, _state
    state = _state()
    avail = {t.id for t, _ in available_themes(state)}
    print(f"Catálogo: {len(CATALOG)} temas · publicables hoy: {len(avail)}\n")
    for t in CATALOG:
        n = len(facts_for(t.id, state, limit=99))
        flag = "OK " if t.id in avail else "-- "
        print(f"{flag} [{t.audience:<4}] {t.family:<11} {t.name}")
        print(f"      hechos disponibles: {n}")
        if t.id not in avail:
            print("      falta: hechos curados o enfriamiento activo")


if __name__ == "__main__":
    _cli()
