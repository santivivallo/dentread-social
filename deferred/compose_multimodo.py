"""
Compone el brief que se le entrega al generador de carruseles.

TRES MODOS DE CONTENIDO
-----------------------
`data`     El modo principal. El disparador es un tema del catálogo y la
           sustancia son los estudios del corpus. No depende del ciclo de
           noticias ni arrastra riesgo de copyright. Es odontología,
           mercado, tendencias y cifras.

`news`     ADA News como disparador + corpus como sustancia + tesis propia.
           Cuando hay una noticia que realmente lo amerita. Exige
           atribución y pasa por `newsguard`.

`dentread` Lo que solo DentRead puede contar: producto, avance, aprendizaje.
           Sin fuente externa, pero el claims guard sigue aplicando entero.

En los tres, la estructura es la misma:

    DISPARADOR  →  qué motiva el post
    SUSTANCIA   →  el dato con cita verificable
    TESIS       →  qué significa para una clínica

Mezcla sugerida por semana: 2 `data` + 1 `news` si la hay + 1 `dentread`
cada dos semanas. El modo `data` es el que sostiene la cadencia.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.ada_news import Article
from pipeline.kb import KB
from pipeline.themes import Theme

# Lo que DentRead sí puede afirmar hoy. El generador solo puede apoyarse en
# esto; cualquier cosa fuera de la lista la frena el claims guard.
DENTREAD_GROUND_TRUTH = """
- DentRead es early-stage, con MVP funcional. NO tiene FDA clearance.
- NO hay pilotos corriendo en EE.UU. Se están buscando los primeros.
- Evidencia propia: 57 profesionales dentales entrevistados vía Global Hub
  for Future Dentistry. El hallazgo más sólido es la brecha de seguimiento.
- Participación en C10 Labs (Nueva York) y en Global Hub for Future Dentistry.
- Segmento primario: mini-DSO emergente (20-100 empleados).
- Posicionamiento no regulado: workflow, explicación visual al paciente,
  seguimiento, QA y soporte de ingresos. NO claims diagnósticos.
"""

# Mapa de industria. Sin esto el generador escribe sobre odontología en
# general; con esto escribe desde una posición. Es la diferencia entre un
# post correcto y uno que un operador de DSO reconoce como propio.
INDUSTRY_CONTEXT = """
CÓMO SE ORGANIZA EL SECTOR
La industria se ordena por control del flujo de trabajo, no por producto.
Gana quien controla el punto donde el hallazgo clínico se convierte en dinero
cobrado. Cinco capas: (1) captura de imagen y equipamiento, (2) sistema de
gestión PMS — el peaje de distribución, nada llega al cliente sin pasar por
ahí, (3) capa de aplicación/IA — la más expuesta: sin canal propio, sin
relación con el paciente, sin código de facturación, (4) comprador agregado
(DSOs, presupuesto centralizado), (5) pagador, que ahora también compra
software.

LOS CUATRO HECHOS ESTRUCTURALES
1. La IA dental no tiene código de facturación. El CDT 2026 sumó 31 códigos
   y ninguno es de IA, mientras el CPT médico sí incorporó categorías de
   inteligencia aumentada. Consecuencia: la IA dental es un GASTO, no un
   ingreso. Solo se vende como eficiencia operativa, embebida en el precio
   de otra cosa, o directo al paciente fuera del seguro. Esto explica toda
   la narrativa de "aceptación de tratamiento" del sector — incluida la de
   DentRead. Es el ángulo más fuerte y el menos usado en contenido.
2. El PMS decidió no bundlear IA nativa. El mercado va a integración
   best-of-breed, pero por decisión del dueño de la plataforma, no por
   derecho del desarrollador. Dinámica de app store.
3. La jugada de dos lados del pagador: vender el mismo motor al proveedor y
   a la aseguradora crea un estándar de facto. Es el moat más fuerte del
   sector y no depende de la calidad del modelo.
4. La IA está reemplazando al laboratorio, no al dentista. Cada
   procedimiento internalizado es facturación que sale del laboratorio:
   transferencia de valor entre capas, no crecimiento neto.

DEMANDA DESATENDIDA
El software se construye sobre el ~46% de la población que ya va al dentista.
El 54% restante es un problema de acceso y cobertura, no de diagnóstico.

LA BRECHA PROFESIÓN vs. MERCADO
La FDI exige evaluación crítica por el profesional, mitigación del sesgo de
automatización y evaluación de generalizabilidad. El mercado promete
detección. Esa brecha es en sí misma un tema de contenido, y DentRead está
del lado prudente por diseño.

CÓMO HABLAR DE COMPETIDORES
Overjet, Pearl, VideaHealth y Diagnocat existen y están bien financiados.
Nunca compararse en calidad ni nombrarlos para decir que DentRead es mejor:
el newsguard lo bloquea. Se puede describir la dinámica de la categoría en
tercera persona, sin adjetivos.
"""

# Cómo citar. El generador tiende a tratar toda cifra como equivalente.
CITATION_RULES = """
- Cada cifra publicada lleva su fuente visible en el slide.
- Nivel de evidencia: "dato primario" se puede afirmar; "consultora" se cita
  como orden de magnitud; "material de proveedor" se cita como señal de
  mercado y con el nombre del proveedor a la vista. Nunca presentar material
  de un competidor como evidencia neutral.
- Cifras de ahorro o de aceptación reportadas por empresas: siempre
  "reportado por [empresa]", nunca como resultado esperable de DentRead.
- Estudios de ahorro financiados por aseguradoras dentales: usar la
  dirección del efecto, jamás la magnitud.
- Cifras agregadas de productividad perdida: contexto narrativo, no base de
  cálculo de ROI.
- Si un dato tiene más de 18 meses en un tema de IA, decir la fecha o no
  usarlo.
"""

SLIDE_PLANS: dict[str, list[tuple[str, str]]] = {
    "data": [
        ("hook",     "La tensión en una frase. Sin marca, sin logo."),
        ("evidence", "El dato principal, grande y legible. Fuente al pie del slide."),
        ("evidence", "El segundo dato o la contracara del primero, con fuente."),
        ("reading",  "Qué se lee entre esos dos números. Acá va el criterio, "
                     "no otro dato."),
        ("thesis",   "Qué implica para una clínica el lunes a la mañana. "
                     "Concreto y accionable."),
        ("cta",      "Una pregunta real que un dentista quiera contestar. "
                     "No 'contáctanos'."),
    ],
    "news": [
        ("hook",     "La tensión en una frase. Sin marca, sin logo."),
        ("context",  "Qué pasó, atribuido a ADA News. Máximo 2 frases."),
        ("evidence", "Un dato del corpus, con la fuente visible en el slide."),
        ("evidence", "Segundo dato o la contracara del primero, con fuente."),
        ("thesis",   "Qué significa para una clínica el lunes a la mañana."),
        ("cta",      "Una pregunta real. No 'contáctanos'."),
    ],
    "dentread": [
        ("hook",     "Qué cambió. Sin superlativos."),
        ("context",  "Por qué importa, anclado en un dato del sector con fuente."),
        ("detail",   "Lo concreto: qué hace, para quién, en qué etapa."),
        ("honesty",  "Qué todavía no está resuelto. Este slide no es opcional: "
                     "es lo que hace creíbles a los otros cinco."),
        ("thesis",   "Hacia dónde va y por qué esa dirección."),
        ("cta",      "Invitación específica a quien corresponda."),
    ],
}


@dataclass
class Brief:
    mode: str
    trigger: dict
    evidence: dict
    ground_truth: str
    industry_context: str
    citation_rules: str
    slide_plan: list
    constraints: dict
    audience: str = "both"

    def to_json(self, path: Path | None = None) -> str:
        payload = {
            "mode": self.mode,
            "audience": self.audience,
            "trigger": self.trigger,
            "evidence": self.evidence,
            "ground_truth": self.ground_truth,
            "industry_context": self.industry_context,
            "citation_rules": self.citation_rules,
            "slide_plan": [{"role": r, "instruction": i} for r, i in self.slide_plan],
            "constraints": self.constraints,
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return text


# BM25 siempre devuelve algo. Sin un piso, un artículo irrelevante produce un
# brief con evidencia inconexa y el generador escribe un post que no une nada.
MIN_RETRIEVAL_SCORE = 1.6   # sobre el score normalizado, no el BM25 crudo
MIN_ARTICLE_SCORE = 3.5


def _base_constraints(evidence: dict, *, must_attribute: bool) -> dict:
    return {
        "max_words_from_source": 7,
        "min_original_ratio": 0.60,
        "max_quotes": 1,
        "max_quote_words": 15,
        "must_attribute": must_attribute,
        "must_cite_evidence": True,
        "forbidden": [
            "cualquier claim diagnóstico o de detección de patología",
            "FDA, HIPAA, SOC 2, CE, ADA Seal, ADA-approved",
            "tracción, clientes o pilotos que no existen",
            "comparaciones con Pearl, Overjet, VideaHealth, Diagnocat",
            "garantías o promesas monetarias",
            "imágenes alojadas por la ADA",
        ],
        "languages": {
            "caption_es": "español neutro, para clínicas y profesionales de LatAm",
            "commentary_en": "inglés de operador, para mini-DSOs en EE.UU.",
        },
        "declarations_to_set": {
            "has_source": bool(evidence["citations"]),
            "model_metrics_documented": False,
            "imagery_cleared": False,
            "pilots_verified": False,
        },
    }


def build_brief_from_theme(theme: Theme, kb: KB, *, k: int = 5) -> Brief:
    """Modo `data`: el disparador es un tema del catálogo, no una noticia."""
    evidence = kb.evidence_pack(theme.query, k=k)
    return Brief(
        mode="data",
        audience=theme.audience,
        trigger={
            "theme_id": theme.id,
            "theme": theme.name,
            "family": theme.family,
            "angle": theme.angle,
            "angle_en": theme.angle_for("en"),
            "relevance_score": 99.0,     # el tema ya fue curado a mano
        },
        evidence=evidence,
        ground_truth=DENTREAD_GROUND_TRUTH.strip(),
        industry_context=INDUSTRY_CONTEXT.strip(),
        citation_rules=CITATION_RULES.strip(),
        slide_plan=SLIDE_PLANS["data"],
        constraints=_base_constraints(evidence, must_attribute=False),
    )


def build_brief_from_news(article: Article, kb: KB, *, k: int = 5) -> Brief:
    """Modo `news`: ADA News como disparador. Exige atribución."""
    query = f"{article.title} {article.summary} {' '.join(article.buckets)}"
    evidence = kb.evidence_pack(query, k=k)
    return Brief(
        mode="news",
        audience="both",
        trigger={
            "headline": article.title,
            "summary": article.summary,
            "url": article.url,
            "published": article.published,
            "category": article.category,
            "relevance_score": article.score,
            "attribution_required": f"Source: ADA News — {article.url}",
        },
        evidence=evidence,
        ground_truth=DENTREAD_GROUND_TRUTH.strip(),
        industry_context=INDUSTRY_CONTEXT.strip(),
        citation_rules=CITATION_RULES.strip(),
        slide_plan=SLIDE_PLANS["news"],
        constraints=_base_constraints(evidence, must_attribute=True),
    )


def build_brief_dentread(headline: str, detail: str, kb: KB,
                         *, context_query: str = "", audience: str = "both",
                         k: int = 4) -> Brief:
    """
    Modo `dentread`: novedad propia, anclada en un dato del sector para que
    no sea un anuncio flotando en el vacío.
    """
    evidence = kb.evidence_pack(context_query or headline, k=k)
    return Brief(
        mode="dentread",
        audience=audience,
        trigger={
            "headline": headline,
            "detail": detail,
            "relevance_score": 99.0,
        },
        evidence=evidence,
        ground_truth=DENTREAD_GROUND_TRUTH.strip(),
        industry_context=INDUSTRY_CONTEXT.strip(),
        citation_rules=CITATION_RULES.strip(),
        slide_plan=SLIDE_PLANS["dentread"],
        constraints=_base_constraints(evidence, must_attribute=False),
    )


# Compatibilidad con la versión anterior.
build_brief = build_brief_from_news


def brief_is_publishable(brief: Brief) -> tuple[bool, list[str]]:
    """Chequeos previos a gastar una llamada al generador."""
    ev = brief.evidence
    problems = []

    if brief.mode == "news" and brief.trigger.get("relevance_score", 0) < MIN_ARTICLE_SCORE:
        problems.append(
            f"la noticia puntúa {brief.trigger.get('relevance_score', 0)} "
            f"(mínimo {MIN_ARTICLE_SCORE}): no hay ángulo de DentRead"
        )
    if brief.mode in ("data", "news") and ev.get("top_score_norm", 0) < MIN_RETRIEVAL_SCORE:
        problems.append(
            f"la mejor evidencia recuperada puntúa {ev.get('top_score_norm', 0)} "
            f"(mínimo {MIN_RETRIEVAL_SCORE}): el corpus no sostiene este tema"
        )
    if not ev["citations"]:
        problems.append(
            "sin evidencia recuperada: el post no tendría nada verificable "
            "que mostrar"
        )
    if len(ev["facts"]) < 2:
        problems.append("menos de 2 hechos citables")
    if not ev["has_quantitative"]:
        problems.append(
            "la evidencia recuperada no tiene cifras: el post carecería de "
            "sustancia verificable"
        )
    if not ev["has_primary"]:
        problems.append(
            "ningún dato primario recuperado: el post se apoyaría solo en "
            "consultoras y proveedores"
        )
    if ev["vendor_only_quantitative"]:
        problems.append(
            "las únicas cifras disponibles son de proveedores (posiblemente "
            "competidores): sostener un claim de DentRead con material de "
            "quien vende lo mismo no es defendible"
        )
    return (not problems), problems


# --------------------------------------------------------------------------
# Plan semanal
# --------------------------------------------------------------------------

def plan_week(kb: KB, *, news: list[Article] | None = None,
              slots: int = 2) -> list[Brief]:
    """
    Arma la tanda de la semana.

    Prioridad: si hay una noticia que realmente lo amerita, ocupa un slot.
    El resto lo llenan temas del catálogo. El modo `data` es el que sostiene
    la cadencia — la oferta de noticias no alcanza y no debería forzarse.
    """
    from pipeline.themes import next_themes

    briefs: list[Brief] = []

    for art in sorted(news or [], key=lambda a: -a.score):
        if len(briefs) >= 1:            # como mucho una noticia por tanda
            break
        b = build_brief_from_news(art, kb)
        if brief_is_publishable(b)[0]:
            briefs.append(b)

    for theme, _ in next_themes(kb, n=slots - len(briefs)):
        b = build_brief_from_theme(theme, kb)
        if brief_is_publishable(b)[0]:
            briefs.append(b)
        if len(briefs) >= slots:
            break

    return briefs
