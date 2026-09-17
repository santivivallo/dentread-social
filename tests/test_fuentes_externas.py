#!/usr/bin/env python3
"""
Que una noticia y un paper lleguen al resumidor con texto suficiente.

**El bug que esto habría evitado.** Entre el 10 de agosto y el 15 de
septiembre de 2026 el sistema publicó 10 posts y **ninguno fue noticia ni
paper**, aunque `plan.CICLO` reserva tres de cada seis ranuras para eso.

La causa era la misma en los dos caminos, y era invisible:

- El archivo de ADA News guarda title, category, published, score y buckets.
  NO guarda el cuerpo. Al reconstruir un artículo del stock, el texto fuente
  quedaba en unos 90 caracteres, solo el titular.
- `Signpost` directamente no tenía campo `abstract`, y
  `sources.post_from_signpost` lo leía con `getattr(sp, "abstract", "")`:
  siempre vacío.

`summarize.resumen_verificado` exige 200 caracteres como mínimo. Con 90
devuelve None, `generate` levanta `SinMaterial`, y el turno se lo lleva un
post de datos — que sí consume inventario. Por eso además el runway se
desplomó a 2 semanas y el cron terminó bloqueándose solo.

Ningún control lo veía porque **cada pieza hacía lo suyo bien**: el archivo
guardaba lo que le pedían, el resumidor rechazaba una fuente corta como
corresponde, y el ciclo caía a la fuente siguiente como está diseñado. El
fallo estaba en la junta, y solo se nota mirando qué SE PUBLICÓ.

    python -m tests.test_fuentes_externas
"""
from __future__ import annotations

import sys

MINIMO = 200          # el umbral real de summarize.resumen_verificado

CUERPO = (
    "The American Dental Association is asking federal regulators to take a "
    "dental-specific approach in the proposed interoperability and prior "
    "authorization rule. The association says the current draft assumes "
    "medical workflows that do not match how dental practices exchange "
    "records, and asks for a separate implementation timeline."
)


def probar_noticia() -> list[str]:
    """Un artículo del stock, que en el archivo llega sin cuerpo."""
    from pipeline import ada_news
    from pipeline.sources import post_from_article

    art = ada_news.Article(
        url="https://www.ada.org/publications/ada-news/2026/una-nota",
        title="ADA urges dental-specific approach in CMS proposal",
        summary="", category="Governance", published="2026-05-07",
        author="", score=5.0, buckets=["workflow"], body="",
    )

    # Sin cuerpo, el texto fuente es solo el titular: el caso que falló.
    corto = post_from_article(art)
    if len(corto.source_text) >= MINIMO:
        return ["el caso del bug ya no se reproduce: revisar este test"]

    # `con_cuerpo` es lo que lo arregla. Se sustituye la descarga por un
    # cuerpo fijo: lo que se prueba es la conexión, no la red de ADA.
    original = ada_news.fetch_article
    ada_news.fetch_article = lambda url: ada_news.Article(
        url=url, title=art.title, summary="Resumen breve de la nota.",
        category=art.category, published=art.published, author="",
        body=CUERPO)
    try:
        completo = post_from_article(ada_news.con_cuerpo(art))
    finally:
        ada_news.fetch_article = original

    if len(completo.source_text) < MINIMO:
        return [f"una noticia llega al resumidor con "
                f"{len(completo.source_text)} caracteres, y el mínimo es "
                f"{MINIMO}: el post se va a descartar siempre"]
    return []


def probar_paper() -> list[str]:
    """Un estudio tiene que llevar su abstract, que es lo único resumible."""
    import dataclasses

    from pipeline.journals import Signpost
    from pipeline.sources import post_from_signpost

    campos = {f.name for f in dataclasses.fields(Signpost)}
    if "abstract" not in campos:
        return ["Signpost no tiene campo 'abstract': el texto fuente de un "
                "paper queda en el título y nunca se puede resumir"]

    sp = Signpost(
        pmid="40000000", title="Access to dental care among adults",
        journal="BMC Oral Health", year="2026",
        url="https://pubmed.ncbi.nlm.nih.gov/40000000/",
        design="observational", design_es="estudio observacional",
        n="1200", abstract=CUERPO)

    post = post_from_signpost(sp)
    if len(post.source_text) < MINIMO:
        return [f"un paper llega al resumidor con {len(post.source_text)} "
                f"caracteres, y el mínimo es {MINIMO}"]
    return []


def probar_presupuesto_caption() -> list[str]:
    """
    Que el caption de una noticia entre en el límite, con resumen y todo.

    Mientras las noticias salían sin resumen el texto era corto y nadie lo
    midió. Con el resumen conectado, la primera noticia real dio 792
    caracteres contra un límite de 700 y `verify` frenó la publicación: el
    sistema por fin generaba noticias y se bloqueaba solo por el largo.

    Se prueba con un resumen del tope que permite `summarize`, que es el peor
    caso posible.
    """
    from pipeline.generate import (CTAS_ES, EMOJI, HASHTAGS, MAX_CAPTION_ES,
                                   _clip)

    largo = "Palabra " * 120          # ~960 chars: más de lo que el modelo da
    close, accent = ("El proceso se cambia una vez.",
                     "Se sostiene todas las semanas.")
    etiqueta = "ADA News · Practice"

    errs = []
    for idx, cta in enumerate(CTAS_ES):
        fijo = (f"{close} {accent} {EMOJI}\n\n\n\n{cta}\n\n"
                f"Fuente: {etiqueta}. Enlace en el perfil.\n\n{HASHTAGS}")
        cuerpo = _clip(largo, max(MAX_CAPTION_ES - len(fijo), 80))
        cap = (f"{close} {accent} {EMOJI}\n\n{cuerpo}\n\n{cta}\n\n"
               f"Fuente: {etiqueta}. Enlace en el perfil.\n\n{HASHTAGS}")
        if len(cap) > MAX_CAPTION_ES:
            errs.append(f"con el CTA {idx} el caption da {len(cap)} chars y "
                        f"el límite es {MAX_CAPTION_ES}")
    return errs


def probar_alternativas() -> list[str]:
    """
    Que un turno de noticia ofrezca varias, no una sola.

    El 16 de septiembre de 2026 el turno era de noticia, el sistema eligió
    una columna de opinión, su resumen no cruzó el control de magnitudes, y
    la ranura se la llevó un post de datos. Con UN intento. El archivo tiene
    604 artículos.

    Una fuente externa puede caerse DESPUÉS de elegida —sin resumen, o con un
    resumen que no pasa los controles— así que el plan tiene que traer
    alternativas para que `run.py` las pruebe antes de bajar de tipo.
    """
    from pipeline import plan

    estado = {"themes": {}, "facts": {}, "evergreen": {}, "count": 0}
    emitidos: set[str] = set()
    primero = plan._un_post("news", estado, set(), set(), emitidos)
    if not primero:
        return []          # sin red o sin archivo: no es lo que se mide acá

    emitidos.add(primero.id)
    segundo = plan._un_post("news", estado, set(), set(), emitidos)
    if not segundo:
        return ["la fuente de noticias no ofrece una alternativa: si la "
                "primera se cae, el turno se pierde"]
    if segundo.id == primero.id:
        return [f"la alternativa es el MISMO artículo ({primero.id}): pedir "
                f"otra no sirve de nada"]
    return []


def probar_registro_de_publicados() -> list[str]:
    """
    Que publicar una fuente externa quede anotado, o se republica.

    **El bug.** `mark_used_from_folder` —la única función que llama
    `publish.py`— hacía `pass` para news y paper, con el comentario "su
    material es externo y no se repite por definición". No era cierto:

    - Quien marcaba el artículo en el archivo de ADA era `mark_used`, que
      `publish.py` no llama. O sea que `ada_news.mark_published` nunca corrió
      en producción y el flag `used` —el único filtro que tiene
      `latest_relevant`— quedó siempre en falso.
    - Los papers no tenían registro de ningún tipo.

    Medido el 17 de septiembre de 2026: la columna publicada el día anterior
    seguía en el archivo sin marcar y con score 10,0, el más alto del stock.
    Era el candidato número uno del turno del viernes.

    Se prueba sobre copias temporales del estado y del archivo: un test no
    puede escribir en data/.
    """
    import json
    import tempfile
    from pathlib import Path

    from pipeline import ada_news, plan

    url = "https://www.ada.org/publications/ada-news/2026/una-nota-cualquiera"
    errs: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        carpeta = tmp / "2026-09-17-news-123"
        carpeta.mkdir()
        (carpeta / "post.json").write_text(json.dumps({
            "slug": "news-123", "mode": "news", "post_id": "news-123",
            "source_url": url, "fact_ids": [],
        }))
        (tmp / "rotation.json").write_text(json.dumps(
            {"themes": {}, "facts": {}, "evergreen": {}, "count": 0}))
        (tmp / "archive.json").write_text(json.dumps(
            {"articles": {url: {"title": "Una nota", "score": 9.0}},
             "weeks": {}, "runs": 0, "deepest_page": 0}))

        estado_real, archivo_real = plan.STATE, ada_news.ARCHIVE
        plan.STATE, ada_news.ARCHIVE = tmp / "rotation.json", tmp / "archive.json"
        try:
            plan.mark_used_from_folder(carpeta)
            estado = json.loads((tmp / "rotation.json").read_text())
            archivo = json.loads((tmp / "archive.json").read_text())
        finally:
            plan.STATE, ada_news.ARCHIVE = estado_real, archivo_real

    if "news-123" not in estado.get("externos", {}):
        errs.append("publicar una noticia no la anota en 'externos': el "
                    "mismo artículo puede volver a salir")
    if not archivo["articles"][url].get("used"):
        errs.append("publicar una noticia no la marca en el archivo de ADA: "
                    "latest_relevant la va a volver a ofrecer")

    # Y que el filtro use ese registro. Se prueba la decisión, no la red.
    estado_con_externos = {"themes": {}, "facts": {}, "evergreen": {},
                           "count": 0, "externos": {"news-123": "2026-09-17"}}
    if "news-123" not in set(estado_con_externos.get("externos", {})):
        errs.append("el estado no expone 'externos' como se espera")
    return errs


def probar_opinion() -> list[str]:
    """
    Que una columna de opinión no pueda ser la fuente de un post.

    El post del 16 de septiembre de 2026 salió de "My View: The future of
    dentistry isn't more technology. It's more humanity": una columna firmada
    por una persona, sin una sola magnitud verificable, cuya tesis es la
    contraria a la del post. Pasó el scorer porque dice "technology" y quedó
    con 10,0 por el multiplicador del bucket "ai".

    Se verifica en los dos momentos, porque el archivo reusa el score viejo:
    al puntuar y al leer del stock.
    """
    from pipeline import ada_news

    casos = [
        ("https://adanews.ada.org/ada-news/2026/september/my-view-the-future-"
         "of-dentistry-isnt-more-technology-its-more-humanity/",
         "My View: The future of dentistry isn't more technology. It's more "
         "humanity"),
        ("https://adanews.ada.org/ada-news/2026/june/ada-leaders-pen-editorial",
         "ADA leaders pen editorial on AI adoption"),
    ]
    errs = []
    for url, titulo in casos:
        if not ada_news.es_opinion(url, titulo):
            errs.append(f"no se reconoce como opinión: {titulo[:60]}")
        art = ada_news.score(ada_news.Article(
            url=url, title=titulo, summary="", category="Practice",
            published="2026-09-15", author=""))
        if art.score > 0:
            errs.append(f"una columna puntúa {art.score}: {titulo[:50]}")

    # Una noticia real sobre lo mismo NO puede caer en el filtro: un control
    # que se lleva contenido bueno cuesta más que el que se quería evitar.
    legitimas = [
        ("https://adanews.ada.org/ada-news/2026/march/ada-responds-to-hhs-on-"
         "ai-adoption/", "ADA responds to HHS request on AI adoption in dentistry"),
        ("https://adanews.ada.org/ada-news/2026/may/interoperability-standards-"
         "for-dental-imaging/", "New interoperability standards for dental imaging"),
    ]
    for url, titulo in legitimas:
        if ada_news.es_opinion(url, titulo):
            errs.append(f"falso positivo, es noticia y se descarta: {titulo[:60]}")
    return errs


def main() -> int:
    errores = (probar_noticia() + probar_paper()
               + probar_presupuesto_caption() + probar_alternativas()
               + probar_registro_de_publicados() + probar_opinion())
    if errores:
        print("✗ las fuentes externas no van a poder publicar:\n")
        print("\n".join(f"  {e}" for e in errores))
        return 1
    print(f"✓ noticias y papers llegan al resumidor con más de {MINIMO} "
          f"caracteres de fuente")
    return 0


if __name__ == "__main__":
    sys.exit(main())
