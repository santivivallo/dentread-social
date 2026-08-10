"""
Modelo de oferta: cuánto contenido produce cada fuente y cuánto hay que
tener guardado para que la cadencia no se caiga.

La distinción que importa
-------------------------
Hay dos tipos de fuente y se dimensionan distinto:

  GARANTIZADA   hechos curados y evergreen. Están en disco. Si el
                enfriamiento lo permite, salen sí o sí.

  VARIABLE      ADA News y journals. Dependen de que alguien publique algo
                relevante esa semana. Medido sobre datos reales de ADA News:
                1,5 utilizables por semana en promedio, pero **el 18% de las
                semanas hay cero**.

El error sería sumar promedios: 1,5 de noticias + 0,75 de evergreen + lo que
den los hechos = 3, listo. No funciona, porque el promedio no publica los
martes. Una semana sin noticias deja un hueco o fuerza un post malo.

La regla: la fuente garantizada se dimensiona para absorber la varianza de
la variable. En concreto, se asume que la fuente variable rinde su p25, no
su media.
"""
from __future__ import annotations

from dataclasses import dataclass

WEEK_DAYS = 7

# FLUJO — lo que llega cada semana.
# Medido: 50 artículos de ADA News en 91 días = 3,8/semana; tasa de
# relevancia 38% sobre 16 titulares reales → 1,5 utilizables/semana.
# Distribución de Poisson: p25 ≈ 1, p10 = 0, 18% de semanas en cero.
ADA_MEAN = 1.5
ADA_P25 = 1.0

# STOCK — el backlog del año, que el modelo de flujo ignoraba.
# Todo 2026 (ene-ago) cabe en ~3 páginas del listado ≈ 150 artículos.
# Medido sobre 20 titulares reales de ene-mar: el 50% supera el piso.
# → ~75 artículos publicables en stock, disponibles de inmediato.
#
# Esto cambia el problema: el stock es un colchón que absorbe las semanas
# malas de flujo. A un post por semana, 75 artículos son año y medio de
# contenido aunque ADA News no publicara nada nuevo.
#
# Condición: el stock se enmarca con su fecha, no como novedad.
# `publisher.newsguard` bloquea el vocabulario de novedad si is_fresh=False.
ADA_BACKLOG_2026 = 75
ADA_BACKLOG_RATE = 0.50

# Journals en modo señalizador: PubMed tiene volumen alto, pero el filtro por
# revista + diseño + ausencia de conclusión deja pocos. Conservador hasta
# medirlo en vivo.
JOURNAL_MEAN = 1.0
JOURNAL_P25 = 0.5


@dataclass
class Sources:
    facts: bool = True
    evergreen: bool = True
    ada_news: bool = False
    journals: bool = False


def variable_supply(src: Sources, optimistic: bool = False) -> float:
    """Posts por semana que aportan las fuentes que no controlamos."""
    total = 0.0
    if src.ada_news:
        total += ADA_MEAN if optimistic else ADA_P25
    if src.journals:
        total += JOURNAL_MEAN if optimistic else JOURNAL_P25
    return total


def requirements(slots: int, src: Sources, *,
                 cooldown_fact: int = 90, cooldown_theme: int = 60,
                 cooldown_evergreen: int = 120,
                 evergreen_every: int = 4) -> dict:
    """
    Inventario garantizado necesario para sostener `slots` por semana.

    Se calcula contra el p25 de la fuente variable: si ADA News rinde su
    promedio, sobra; si rinde poco, el banco de hechos cubre el hueco.
    """
    from_variable = variable_supply(src, optimistic=False)
    evergreen_rate = slots / evergreen_every if src.evergreen else 0.0
    from_facts = max(0.0, slots - from_variable - evergreen_rate)

    return {
        "slots": slots,
        "de_fuentes_variables": round(from_variable, 2),
        "de_evergreen": round(evergreen_rate, 2),
        "de_hechos": round(from_facts, 2),
        "facts": round(from_facts * 2 * cooldown_fact / WEEK_DAYS),
        "themes": round(from_facts * cooldown_theme / WEEK_DAYS),
        "evergreen": round(evergreen_rate * cooldown_evergreen / WEEK_DAYS),
    }


def ceiling(n_themes: int, n_evergreen: int, *,
            cooldown_theme: int = 60, cooldown_evergreen: int = 120) -> dict:
    """
    Techo estructural de las fuentes garantizadas.

    Esto es lo que se me pasó al principio: hay DOS restricciones, no una.

      · los HECHOS limitan qué temas están disponibles hoy
      · los TEMAS limitan cuántos posts de datos caben por semana, y ese
        techo no se mueve agregando hechos

    Con 22 temas y enfriamiento de 60 días el máximo es 2,57 posts de datos
    por semana, tenga uno 21 hechos o 200. Para subir el techo hay que
    agregar ángulos, no cifras — y un ángulo nuevo sobre hechos que ya
    existen es mucho más barato que curar un hecho nuevo.
    """
    data = n_themes / (cooldown_theme / WEEK_DAYS)
    ever = n_evergreen / (cooldown_evergreen / WEEK_DAYS)
    return {
        "posts_datos_semana": round(data, 2),
        "posts_evergreen_semana": round(ever, 2),
        "techo_garantizado": round(data + ever, 2),
    }


def runway_with_backlog(slots: int, n_themes: int, n_evergreen: int,
                        backlog: int = ADA_BACKLOG_2026) -> dict:
    """
    Semanas de contenido contando el stock, no solo el flujo.

    El modelo de flujo puro decía que el sistema se secaba. Ignoraba que hay
    un backlog de año completo disponible desde el primer día.
    """
    cap = ceiling(n_themes, n_evergreen)
    garantizado = cap["techo_garantizado"]
    # el stock cubre el hueco entre lo garantizado y el objetivo
    deficit = max(0.0, slots - garantizado - ADA_P25)
    semanas_stock = backlog / max(0.25, deficit + ADA_P25)
    return {
        "techo_garantizado": garantizado,
        "flujo_p25": ADA_P25,
        "stock_disponible": backlog,
        "cubre_objetivo": garantizado + ADA_P25 >= slots,
        "semanas_de_stock": round(semanas_stock),
    }


def compare(slots: int = 3) -> str:
    """Tabla de escenarios: qué cambia según qué fuentes estén encendidas."""
    scenarios = [
        ("solo hechos + evergreen", Sources()),
        ("+ ADA News", Sources(ada_news=True)),
        ("+ ADA News + journals", Sources(ada_news=True, journals=True)),
    ]
    lines = [f"Para sostener {slots} posts/semana:\n",
             f"  {'escenario':<26}{'hechos':>8}{'temas':>8}{'evergreen':>11}"]
    lines.append("  " + "─" * 53)
    for name, src in scenarios:
        r = requirements(slots, src)
        lines.append(f"  {name:<26}{r['facts']:>8}{r['themes']:>8}{r['evergreen']:>11}")
    lines.append("")
    lines.append("  Calculado con las fuentes variables en su p25, no en su media:")
    lines.append(f"  ADA News rinde {ADA_MEAN}/semana en promedio pero 0 el 18% de")
    lines.append("  las semanas. El banco de hechos es lo que absorbe esos huecos.")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--slots", type=int, default=3)
    print(compare(ap.parse_args().slots))
