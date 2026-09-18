#!/usr/bin/env python3
"""
Revisión quincenal: qué hizo el sistema, qué se degradó y qué conviene cambiar.

    python -m tools.revision                 # últimos 14 días
    python -m tools.revision --dias 30
    python -m tools.revision --escribir      # además deja el informe en informes/

**Por qué existe.** Este sistema se rompió cuatro veces de la misma forma:
cada pieza hacía lo suyo bien y la falla estaba en la junta, así que ningún
control la veía. Los tres casos medidos:

- Un mes entero sin publicar noticias ni papers, teniendo la mitad de las
  ranuras reservadas. Cada corrida lo avisaba; para verlo había que abrir 15
  corridas y compararlas.
- El banco de cifras agotado reportado como "0 semanas de contenido", que no
  era cierto y mandó a curar hechos como si fuera una urgencia.
- Una columna de opinión publicada como si fuera noticia de la ADA, elegida
  por el scorer con el puntaje más alto del stock.

Los tres se ven en una sola tabla si alguien la arma. Ninguno se ve leyendo
una corrida suelta. Eso es lo que hace esto.

**Lo que NO hace.** No decide. Mide y ordena hallazgos por umbral; la decisión
editorial es de Santiago. Y no llama a ningún modelo: todo lo de acá es
aritmética sobre archivos del repo, así que correrlo es gratis. La propuesta
de mejoras se hace después, sobre este informe.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from pipeline import bitacora, plan

INFORMES = Path("informes")
SERIE = INFORMES / "serie.json"

# Cadencia objetivo: el cron corre lunes, miércoles y viernes.
POSTS_POR_SEMANA = 3

# Umbrales. Están acá arriba y no repartidos en el código porque son la parte
# discutible del archivo: cada uno es un juicio sobre cuándo algo dejó de ser
# ruido. Cambiarlos es una decisión, no un detalle.
UMBRALES = {
    # Más descartes que publicaciones significa que el generador produce
    # candidatos que sus propios controles rechazan. Uno o dos son sanos: el
    # ciclo está diseñado para probar la fuente siguiente.
    "descartes_por_publicado": 2.0,
    # Si el modelo falla más de un tercio de las veces, los posts salen con
    # texto curado y el sistema se degrada sin avisar.
    "tasa_fallo_modelo": 0.34,
    # Una caída de 3 puntos en el promedio de auditoría es una regresión real:
    # el promedio histórico viene en 91.
    "caida_auditoria": 3.0,
    # Menos de 10 artículos publicables en stock y la fuente de noticias
    # empieza a repetirse o a quedarse sin turno.
    "stock_noticias": 10,
}


def _modo_de(carpeta: str) -> str:
    """De qué fuente salió un post publicado, por su carpeta."""
    p = Path(carpeta)
    datos = p / "post.json"
    if datos.exists():
        try:
            return json.loads(datos.read_text()).get("mode", "?")
        except ValueError:
            pass
    # Las carpetas viejas vuelven del repo con solo su published.json, así que
    # el modo se infiere del slug. No es adivinar: el slug lo compone
    # `sources` con ese prefijo.
    nombre = p.name
    for marca, modo in (("-news-", "news"), ("-paper-", "paper")):
        if marca in nombre:
            return modo
    return "data/evergreen"


def publicaciones(desde: date) -> list[dict]:
    """Lo que llegó al feed en la ventana, desde los published.json."""
    fuera = []
    for reg in sorted(Path("out").glob("*/published.json")):
        try:
            d = json.loads(reg.read_text())
        except ValueError:
            continue
        if d.get("dry_run"):
            continue
        try:
            cuando = datetime.fromisoformat(str(d.get("date"))[:10]).date()
        except (ValueError, TypeError):
            continue
        if cuando < desde:
            continue
        fuera.append({"fecha": cuando.isoformat(), "carpeta": str(reg.parent),
                      "modo": _modo_de(str(reg.parent)),
                      "instagram": d.get("instagram", "")})
    return fuera


def _auditoria() -> tuple[float, int]:
    """
    Promedio de calidad del catálogo y cuántos posts caen bajo el piso.

    Se mide **con el modelo apagado**, a propósito y por dos razones:

    1. Esta herramienta tiene que poder correr gratis y rápido. `auditar_todo`
       genera los 26 posts, y generar llama al modelo por cada uno: la primera
       versión de esto disparó 26 llamadas y cuatro rondas de reintentos.
    2. Más importante: el modelo escribe distinto cada vez. Si el promedio se
       midiera con su texto, la serie de revisiones mezclaría el estado del
       sistema con la varianza del modelo, y una caída de 3 puntos podría ser
       simplemente otra tirada. Con el texto curado la comparación entre
       quincenas mide lo que cambió en el código y en el catálogo.

    O sea que el número no es "qué tan buenos son los posts que salen", es
    "qué tan bueno es el piso garantizado". Es la comparación que sirve para
    detectar una regresión.
    """
    from pipeline import llm
    try:
        with llm.sin_modelo():
            from pipeline import auditoria
            filas = auditoria.auditar_todo()
    except Exception:
        return 0.0, 0
    if not filas:
        return 0.0, 0
    puntajes = [f.puntaje for f in filas]
    piso = getattr(auditoria, "PISO", 70.0)
    return round(sum(puntajes) / len(puntajes), 1), sum(1 for p in puntajes if p < piso)


def _stock_noticias() -> int:
    """Cuántos artículos de ADA quedan publicables, sin salir a la red."""
    try:
        from pipeline import ada_news
        arch = ada_news.load_archive()
        return sum(
            1 for url, a in arch["articles"].items()
            if not a.get("used") and not a.get("skipped")
            and a.get("score", 0) >= ada_news.MIN_SCORE
            and not ada_news.es_opinion(url, a.get("title", ""))
        )
    except Exception:
        return -1


def medir(dias: int) -> dict:
    desde = date.today() - timedelta(days=dias)
    eventos = bitacora.leer(desde=desde.isoformat())
    pubs = publicaciones(desde)

    descartes = [e for e in eventos if e["evento"] == "candidato_descartado"]
    llamadas = [e for e in eventos if e["evento"] == "llamada_modelo"]
    corridas = [e for e in eventos if e["evento"] == "corrida"]
    promedio, bajo_piso = _auditoria()
    inv = plan.inventory()

    esperados = round(POSTS_POR_SEMANA * dias / 7)
    return {
        "generado": date.today().isoformat(),
        "dias": dias,
        "publicados": len(pubs),
        "esperados": esperados,
        "por_fuente": dict(Counter(p["modo"] for p in pubs)),
        "descartes": len(descartes),
        "descartes_por_motivo": dict(Counter(e.get("motivo", "?") for e in descartes)),
        "descartes_por_fuente": dict(Counter(e.get("kind", "?") for e in descartes)),
        "llamadas_modelo": len(llamadas),
        "llamadas_fallidas": sum(1 for e in llamadas if not e.get("ok")),
        "corridas": len(corridas),
        "corridas_a_mano": sum(1 for e in corridas
                               if e.get("origen") == "workflow_dispatch"),
        "corridas_por_cron": sum(1 for e in corridas
                                 if e.get("origen") == "schedule"),
        "auditoria_promedio": promedio,
        "auditoria_bajo_piso": bajo_piso,
        "stock_noticias": _stock_noticias(),
        "semanas_con_posts_de_datos": inv["semanas_con_posts_de_datos"],
        "mezcla_esperada": inv["mezcla_esperada"],
        "temas_publicables": inv["temas_publicables"],
        "hechos_disponibles": inv["hechos_disponibles"],
        "hechos_totales": inv["hechos_totales"],
        "bitacora_vacia": not eventos,
    }


def hallazgos(m: dict, previo: dict | None) -> list[tuple[str, str, str]]:
    """
    Lista de (severidad, qué pasó, qué hacer). Ordenada por severidad.

    Cada hallazgo nombra la acción concreta. Un informe que dice "la calidad
    bajó" sin decir qué revisar obliga a rehacer el análisis para poder actuar.
    """
    h: list[tuple[str, str, str]] = []

    if m["bitacora_vacia"]:
        h.append(("info",
                  "La bitácora no tiene eventos en la ventana: se instaló el "
                  f"{date.today().isoformat()} y se llena publicando.",
                  "Esta primera revisión mide solo lo reconstruible del repo. "
                  "La próxima ya tiene descartes y llamadas al modelo."))

    faltan = m["esperados"] - m["publicados"]
    if faltan >= 2:
        h.append(("alto",
                  f"Salieron {m['publicados']} posts de {m['esperados']} "
                  f"esperados en {m['dias']} días: faltaron {faltan}.",
                  "Revisar las corridas fallidas del período: "
                  "gh run list --workflow=publish.yml --status failure"))

    ratio = m["descartes"] / max(m["publicados"], 1)
    if ratio > UMBRALES["descartes_por_publicado"]:
        motivo = max(m["descartes_por_motivo"].items(),
                     key=lambda x: x[1], default=("?", 0))
        h.append(("alto",
                  f"{m['descartes']} candidatos descartados para "
                  f"{m['publicados']} publicados ({ratio:.1f} por post). "
                  f"Motivo dominante: {motivo[0]} ({motivo[1]}).",
                  "Si el motivo es sin_material, el cuello está en el "
                  "resumidor o en el proveedor del modelo, no en las fuentes."))

    if m["llamadas_modelo"]:
        tasa = m["llamadas_fallidas"] / m["llamadas_modelo"]
        if tasa > UMBRALES["tasa_fallo_modelo"]:
            h.append(("alto",
                      f"El modelo falló en {m['llamadas_fallidas']} de "
                      f"{m['llamadas_modelo']} llamadas ({tasa:.0%}).",
                      "Los posts salen con texto curado y nadie se enteraría. "
                      "Probar python -m pipeline.redaccion y, si el proveedor "
                      "está saturado de forma sostenida, cambiar LLM_MODEL."))

    # Fuentes que tenían ranura y no publicaron nada. Es el fallo que costó un
    # mes: CICLO reserva 3 de 6 para noticias y papers, y salieron 0.
    for fuente in ("news", "paper"):
        ranuras = plan.CICLO.count(fuente)
        if ranuras and not m["por_fuente"].get(fuente):
            h.append(("alto",
                      f"La fuente '{fuente}' tiene {ranuras} de "
                      f"{len(plan.CICLO)} ranuras del ciclo y publicó 0 veces "
                      f"en {m['dias']} días.",
                      "Es el fallo que dejó el feed un mes sin noticias ni "
                      "papers. Correr python -m pipeline.run --slots 1 y leer "
                      "por qué se descarta el candidato."))

    if previo and previo.get("auditoria_promedio"):
        delta = m["auditoria_promedio"] - previo["auditoria_promedio"]
        if delta <= -UMBRALES["caida_auditoria"]:
            h.append(("alto",
                      f"El promedio de auditoría cayó {abs(delta):.1f} puntos "
                      f"({previo['auditoria_promedio']} → "
                      f"{m['auditoria_promedio']}).",
                      "python -m pipeline.auditoria --peores 8 para ver qué "
                      "posts la empujaron abajo."))

    if m["auditoria_bajo_piso"]:
        h.append(("medio",
                  f"{m['auditoria_bajo_piso']} posts del catálogo están bajo "
                  f"el piso de calidad.",
                  "python -m pipeline.auditoria --peores 8"))

    if 0 <= m["stock_noticias"] < UMBRALES["stock_noticias"]:
        h.append(("medio",
                  f"Quedan {m['stock_noticias']} artículos de ADA "
                  f"publicables en stock.",
                  "El crawl entra una página más por corrida; si no crece, "
                  "revisar MAX_PAGES y el piso MIN_SCORE."))

    if m["corridas_a_mano"] > m["corridas_por_cron"] and m["corridas"]:
        h.append(("medio",
                  f"{m['corridas_a_mano']} corridas disparadas a mano contra "
                  f"{m['corridas_por_cron']} por cron.",
                  "Es la métrica de costo real: un sistema que hay que "
                  "empujar no es automático. Cada corrida a mano tuvo una "
                  "causa; están en los hallazgos de arriba."))

    if m["semanas_con_posts_de_datos"] < 4:
        h.append(("medio",
                  f"Quedan {m['semanas_con_posts_de_datos']} semanas de posts "
                  f"de datos ({m['temas_publicables']} temas, "
                  f"{m['hechos_disponibles']}/{m['hechos_totales']} hechos). "
                  f"El feed no se detiene: sale con la mezcla "
                  f"{m['mezcla_esperada']}.",
                  "Decisión editorial, no urgencia: curar hechos en "
                  "data/facts.json recupera el balance de fuentes."))

    orden = {"alto": 0, "medio": 1, "info": 2}
    return sorted(h, key=lambda x: orden.get(x[0], 9))


def informe(m: dict, h: list, previo: dict | None) -> str:
    l = [f"# Revisión del {m['generado']} · últimos {m['dias']} días", ""]
    l.append(f"**{m['publicados']}/{m['esperados']} publicaciones** · "
             f"auditoría {m['auditoria_promedio']}"
             + (f" (antes {previo['auditoria_promedio']})" if previo else "")
             + f" · {len(h)} hallazgo(s)")
    l += ["", "## Hallazgos", ""]
    if not h:
        l.append("Ninguno sobre los umbrales. El sistema hizo lo que debía.")
    for sev, que, hacer in h:
        l += [f"### [{sev}] {que}", "", f"→ {hacer}", ""]

    l += ["## Medido", "", "| | |", "|---|---|"]
    for k in ("publicados", "esperados", "por_fuente", "descartes",
              "descartes_por_motivo", "descartes_por_fuente",
              "llamadas_modelo", "llamadas_fallidas", "corridas",
              "corridas_a_mano", "corridas_por_cron", "auditoria_promedio",
              "auditoria_bajo_piso", "stock_noticias",
              "semanas_con_posts_de_datos", "mezcla_esperada",
              "temas_publicables"):
        l.append(f"| {k.replace('_', ' ')} | {m[k]} |")
    l += ["",
          "_Generado por `python -m tools.revision`. Sin llamadas a modelos: "
          "todo es aritmética sobre archivos del repo._"]
    return "\n".join(l) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=14)
    ap.add_argument("--escribir", action="store_true",
                    help="deja el informe en informes/ y agrega la serie")
    args = ap.parse_args()

    serie = []
    if SERIE.exists():
        try:
            serie = json.loads(SERIE.read_text())
        except ValueError:
            serie = []
    previo = serie[-1] if serie else None

    m = medir(args.dias)
    h = hallazgos(m, previo)
    texto = informe(m, h, previo)
    print(texto)

    if args.escribir:
        # Van a informes/ y NO a docs/: docs/ es el sitio público en Pages, y
        # un diagnóstico interno con los fallos del sistema no tiene por qué
        # quedar indexado.
        INFORMES.mkdir(parents=True, exist_ok=True)
        destino = INFORMES / f"revision-{m['generado']}.md"
        destino.write_text(texto, encoding="utf-8")
        serie.append(m)
        SERIE.write_text(json.dumps(serie[-26:], indent=1, ensure_ascii=False),
                         encoding="utf-8")
        print(f"[ok] {destino}")

    # Los hallazgos altos salen por código de retorno para que el workflow los
    # marque, sin frenar nada: esto no publica.
    return 1 if any(s == "alto" for s, _, _ in h) else 0


if __name__ == "__main__":
    raise SystemExit(main())
