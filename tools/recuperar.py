#!/usr/bin/env python3
"""
Relee hacia atrás lo que se descartó, con las reglas de hoy.

    python -m tools.recuperar --ada        # reevalúa el archivo de ADA
    python -m tools.recuperar --papers     # barre PubMed a fondo
    python -m tools.recuperar --ada --papers

**Por qué existe.** Los dos archivos guardan el veredicto, no solo el
artículo. Eso es deliberado y sirve para diagnosticar, pero tiene un costo
que se pagó dos veces:

- El archivo de ADA guarda el `score` calculado en su momento y lo reusa
  para siempre (`latest_relevant` solo recalcula si hay `needs_refetch`).
  Una regla nueva no toca los 612 artículos ya archivados. Cuando se agregó
  el filtro de columnas de opinión, la que ya estaba guardada con 10,0 seguía
  siendo candidata número uno.
- El archivo de PubMed guarda el motivo del descarte. Al ensanchar la
  allowlist de revistas, los 77 estudios rechazados por "revista fuera de
  allowlist" siguen marcados así hasta que la consulta los devuelva otra vez
  — y cada corrida pide apenas 20 por preset.

O sea que **ensanchar un criterio no recupera nada por sí solo.** Hay que
volver a pasar por lo viejo, y eso es lo que hace esto.

No inventa nada: reevalúa con las mismas funciones que usa el pipeline
(`ada_news.score`, `journals.find`) y solo informa lo que cambia de estado.
"""
from __future__ import annotations

import argparse

from pipeline import ada_news, journals, plan


def recuperar_ada(refetch: bool = False) -> None:
    """
    Reevalúa el archivo de ADA en dos etapas.

    **Etapa 1, gratis y sin red.** Se repuntúa con el título y la categoría,
    que es lo que el archivo guarda. El `haystack` original incluía además el
    `summary`, que no se guardó, así que esta puntuación es **más
    conservadora** que la primera: puede ascender un artículo, nunca puede
    ser la razón para bajarlo. Por eso solo se escriben los ascensos —
    descartar algo por tener menos información sería peor que dejarlo como
    está.

    **Etapa 2, con red y opcional (`--refetch`).** A los que siguen bajo el
    piso se les pone `needs_refetch`, que es el mecanismo que ya existe en
    `latest_relevant` para volver a bajar el artículo completo y puntuarlo
    con todo el texto. No se descargan acá: se marcan, y las corridas
    normales los van resolviendo.
    """
    arch = ada_news.load_archive()
    arts = arch["articles"]
    anio = plan.anio_minimo()

    subieron: list[tuple[str, float, float]] = []
    bajaron = 0
    opinion_nueva = 0
    marcados = 0

    for url, reg in arts.items():
        if reg.get("skipped") or reg.get("used"):
            continue
        viejo = float(reg.get("score", 0) or 0)

        # El filtro de opinión es de lectura, no de puntaje: si ahora cae
        # ahí, se anota para que se vea en el conteo.
        if ada_news.es_opinion(url, reg.get("title", "")):
            opinion_nueva += 1
            continue

        art = ada_news.score(ada_news.Article(
            url=url, title=reg.get("title", ""), summary="",
            category=reg.get("category", ""),
            published=reg.get("published", ""), author=""))
        nuevo = art.score

        if nuevo > viejo:
            reg["score"] = nuevo
            reg["buckets"] = art.buckets
            reg["repuntuado"] = True
            subieron.append((reg.get("title", "")[:60], viejo, nuevo))
        elif nuevo < viejo:
            bajaron += 1        # se deja el viejo: tenía más información

        # Marcar para volver a bajar, pero SOLO los del año editorial.
        #
        # Cada marca es un GET en la próxima corrida. Marcar los 550 que
        # están bajo el piso sería ~9 minutos de descargas en una corrida con
        # techo de 15, y sin ganancia posible: `backlog` solo sirve artículos
        # del año en curso, así que reevaluar los de 2025 y 2024 no puede
        # producir un post. Acotado al año, son unos 130.
        if (refetch and viejo < ada_news.MIN_SCORE
                and str(reg.get("published", "")).startswith(str(anio))):
            reg["needs_refetch"] = True
            marcados += 1

    ada_news.save_archive(arch)

    publicables = [
        u for u, x in arts.items()
        if not x.get("used") and not x.get("skipped")
        and x.get("score", 0) >= ada_news.MIN_SCORE
        and not ada_news.es_opinion(u, x.get("title", ""))
        and str(x.get("published", "")).startswith(str(anio))
    ]

    print(f"\n=== ADA News: {len(arts)} artículos archivados ===")
    print(f"ascendieron con las reglas de hoy: {len(subieron)}")
    for t, v, n in subieron[:12]:
        print(f"   {v:5.2f} → {n:5.2f}  {t}")
    print(f"puntuaron más bajo sin el summary: {bajaron} "
          f"(se conserva el puntaje viejo, que tenía más texto)")
    print(f"ahora caen en el filtro de opinión: {opinion_nueva}")
    if refetch:
        print(f"marcados para volver a bajar con texto completo: {marcados}")
        print("   las corridas normales los van a reevaluar solos")
    print(f"publicables de {anio}: {len(publicables)}")


def recuperar_papers(anios: int = 2, por_preset: int = 60) -> None:
    """
    Barre PubMed con todos los presets y una ventana más ancha.

    Las corridas normales piden 20 por preset porque solo necesitan un
    candidato. Para recuperar lo que la allowlist vieja rechazó hace falta
    volver a verlo, y para eso hay que pedir mucho más de una sola vez.

    `journals.find` archiva todo lo que ve con el motivo del descarte, y
    **recalcula el motivo cada vez**, así que este barrido actualiza de paso
    los 77 que estaban marcados como "revista fuera de allowlist" con la
    lista vieja.
    """
    print(f"\n=== PubMed: barrido de {anios} año(s), "
          f"{por_preset} por preset ===")
    total = 0
    for preset in plan.PRESETS_PAPER:
        try:
            hallados = journals.find(preset=preset, years=anios, n=por_preset)
        except Exception as exc:
            print(f"   {preset:12} falló ({exc.__class__.__name__})")
            continue
        total += len(hallados)
        print(f"   {preset:12} {len(hallados):3} publicables")
    print(f"\npublicables en total: {total}")
    print(journals.cobertura())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ada", action="store_true")
    ap.add_argument("--papers", action="store_true")
    ap.add_argument("--refetch", action="store_true",
                    help="marca los de ADA bajo el piso para volver a "
                         "bajarlos con texto completo")
    ap.add_argument("--anios", type=int, default=2)
    args = ap.parse_args()

    if not (args.ada or args.papers):
        print(__doc__)
        return 2
    if args.ada:
        recuperar_ada(refetch=args.refetch)
    if args.papers:
        recuperar_papers(anios=args.anios)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
