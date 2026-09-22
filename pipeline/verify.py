#!/usr/bin/env python3
"""
Auditoría del sistema. Corre los tres controles que sostienen la promesa:

  1. VERIFICABILIDAD  cada hecho de facts.json tiene su cifra localizable en
                      la fuente citada, o una fuente externa declarada.
  2. BREVEDAD         el copy entra en los límites de lectura de cada red y
                      el gancho invita a abrir.
  3. COBERTURA        el archivo de ADA News crece semana a semana.

    python -m pipeline.verify
    python -m pipeline.verify --strict     # sale con error si algo falla

Está pensado para correr en CI antes de publicar y como chequeo manual.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

FACTS = Path("data/facts.json")
KB_PATH = Path("data/kb.jsonl")   # opcional: solo si se usó tools/kb_build
DOCS = Path("docs")

# Fuentes cuyo texto vive en una nota de corpus y no en kb.jsonl.
#
# Varias claves pueden apuntar al mismo archivo, y es correcto: FastStats es un
# índice donde cada cifra remite a su encuesta y su tabla. El hecho cita la
# encuesta, que es la fuente real de la cifra; la verificación lee la nota que
# transcribe la página donde se leyeron todas.
_CDC = "CDC/NCHS, FastStats Oral and Dental Health (revisado 2026-01-16)"
_NOTA_CDC = "data/corpus_notes/cdc-nchs-faststats-dental.md"

EXTERNAL_SOURCES = {
    "ADA News, New CDT codes you should know for 2026 (2025-09-29)":
        "data/corpus_notes/cdt-2026-sin-codigos-ia.md",
    "OMS, hoja informativa Salud bucodental (17-03-2025), a partir de "
    "GBD 2021":
        "data/corpus_notes/oms-salud-bucodental-2025.md",
    _CDC: _NOTA_CDC,
    f"{_CDC}, NHANES 2017-marzo 2020, NHSR 158 tablas 4 y 9": _NOTA_CDC,
    f"{_CDC}, Health, United States 2019, tabla 28 "
    f"(NHANES 2015-2018)": _NOTA_CDC,
    f"{_CDC}, NHIS 2023 Early Release": _NOTA_CDC,
    f"{_CDC}, Health, United States 2019, tabla DentCh (niños, 2019) y "
    f"NHIS 2023 (adultos)": _NOTA_CDC,
}

# Límites de lectura. No son de la API — son de atención.
IG_FIRST_LINE = 125       # lo que muestra el feed antes de "más"
LI_FIRST_LINE = 210       # lo que muestra LinkedIn antes de "ver más"
IG_TARGET = 700           # por encima de esto el carrusel compite consigo mismo
LI_TARGET = 900


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    # una cifra es la misma escrita 9,5 o 9.5
    return re.sub(r"(?<=\d)[.,](?=\d)", ".", s)


# --------------------------------------------------------------------------

# Marcas de población en el enunciado de un hecho. Se usan para detectar
# hechos asignados a un tema de la población equivocada.
_NINOS = re.compile(r"niñ|infantil|pediátric|CHIP", re.I)
_ADULTOS = re.compile(r"\badulto", re.I)


def check_facts() -> tuple[int, int, list[str]]:
    facts = json.loads(FACTS.read_text())["facts"]
    docs = [json.loads(l) for l in KB_PATH.open()]
    problems: list[str] = []

    corpus_by_title: dict[str, str] = {}
    for d in docs:
        corpus_by_title.setdefault(norm(d["title"]), "")
        corpus_by_title[norm(d["title"])] += " " + norm(d["text"])

    external_text = {
        cite: norm(Path(path).read_text())
        for cite, path in EXTERNAL_SOURCES.items() if Path(path).exists()
    }

    ok = 0
    for f in facts:
        numbers = re.findall(r"\d[\d.,]*", norm(f["number"]))
        blob = ""

        if f["cite"] in external_text:
            blob = external_text[f["cite"]]
        else:
            title = f["cite"].split("(")[0]
            title = title.split(",", 1)[1] if "," in title else title
            key = norm(title.strip())[:26]
            for k, v in corpus_by_title.items():
                if key and key in k:
                    blob += v

        if not blob:
            problems.append(f"{f['id']}: no se encuentra la fuente citada")
            continue

        missing = [n for n in numbers if n not in blob]
        if missing:
            problems.append(f"{f['id']}: {missing} no aparece(n) en la fuente")
            continue

        for field in ("statement", "statement_en", "cite", "tier"):
            if not f.get(field):
                problems.append(f"{f['id']}: falta el campo '{field}'")
                break
        else:
            # Un hecho sobre niños no puede publicarse bajo un tema de
            # adultos, ni al revés. Salió así: el frame 1 decía "MEDICAID
            # ADULTO" y la tarjeta del frame 2 hablaba de niños beneficiarios.
            # La cifra era correcta y estaba bien citada, así que ningún
            # control la tocó; lo que fallaba era a qué tema estaba asignada.
            #
            # Los hechos que COMPARAN las dos poblaciones quedan fuera: "53%
            # de los niños contra 41% de los adultos" pertenece a los dos
            # temas con todo derecho, y marcarlo seria un falso positivo.
            texto_hecho = f["statement"]
            habla_ninos = bool(_NINOS.search(texto_hecho))
            habla_adultos = bool(_ADULTOS.search(texto_hecho))
            if habla_ninos != habla_adultos:
                for tema in f.get("themes", []):
                    if habla_ninos and re.search(r"adulto|mayores", tema):
                        problems.append(f"{f['id']}: habla de niños y está en "
                                        f"el tema '{tema}'")
                    if habla_adultos and re.search(r"ninos|chip", tema):
                        problems.append(f"{f['id']}: habla de adultos y está "
                                        f"en el tema '{tema}'")

            # `card` es la versión corta que va en la tarjeta del frame 2.
            # Es texto escrito a mano, así que se controla lo mismo que en el
            # enunciado: que entre en la tarjeta y que no traiga ninguna cifra
            # que no esté ya verificada contra la fuente.
            card = f.get("card")
            if card:
                if len(card) > 120:
                    problems.append(f"{f['id']}: card de {len(card)} chars, "
                                    f"el máximo de la tarjeta es 120")
                    continue
                del_enunciado = set(re.findall(r"\d[\d.,]*",
                                               norm(f["statement"] + " " + f["number"])))
                inventadas = [n for n in re.findall(r"\d[\d.,]*", norm(card))
                              if n not in del_enunciado]
                if inventadas:
                    problems.append(f"{f['id']}: la card trae cifras que no "
                                    f"están en el enunciado: {inventadas}")
                    continue
            ok += 1

    return ok, len(facts), problems


def check_brevity(folder: Path | None = None) -> tuple[int, int, list[str]]:
    posts = sorted(Path("out").glob("*/post.json")) if folder is None else \
        [folder / "post.json"]
    if not posts:
        return 0, 0, ["no hay posts generados en out/ para medir"]

    problems, ok = [], 0
    for p in posts:
        d = json.loads(p.read_text())
        name = p.parent.name
        es, en = d["caption_es"], d["commentary_en"]
        bad = False

        for label, text, first_max, target in (
            ("ES", es, IG_FIRST_LINE, IG_TARGET),
            ("EN", en, LI_FIRST_LINE, LI_TARGET),
        ):
            first = text.split("\n", 1)[0]
            if len(first) > first_max:
                problems.append(
                    f"{name} [{label}] gancho de {len(first)} chars "
                    f"(máx {first_max}): se corta antes de enganchar")
                bad = True
            if len(text) > target:
                problems.append(
                    f"{name} [{label}] {len(text)} chars (objetivo <{target}): "
                    "el carrusel ya cuenta la historia, el texto la repite")
                bad = True
            if not re.search(r"[?¿]", text):
                problems.append(f"{name} [{label}] sin pregunta: no invita a responder")
                bad = True
        if not bad:
            ok += 1
    return ok, len(posts), problems


def check_inventory() -> tuple[bool, list[str]]:
    """
    ¿Cuánto contenido queda? El sistema anterior se secaba en la semana 8 sin
    avisar. Esto lo hace visible.

    OJO: devuelve False cuando el runway está bajo, pero el que llama NO debe
    bloquear la publicación con eso. Es un aviso sobre el futuro; frenar un
    post que ya existe no agrega ni un hecho al banco. Ver el comentario en
    `main`.
    """
    from pipeline.plan import inventory
    inv = inventory()
    notes = [
        f"{inv['temas_publicables']} temas publicables · "
        f"{inv['hechos_disponibles']}/{inv['hechos_totales']} hechos disponibles · "
        f"{inv['evergreen_disponibles']} evergreen",
        f"posts de datos: ~{inv['semanas_con_posts_de_datos']} semanas al "
        f"ritmo del ciclo",
        f"mezcla esperada: {inv['mezcla_esperada']}",
    ]
    ok = inv["semanas_con_posts_de_datos"] >= 4
    if not ok:
        # Se nombra la consecuencia real. "Menos de 4 semanas de contenido"
        # decía que el feed se apaga, y el feed no se apaga: tres de las
        # cuatro fuentes del ciclo se reponen solas y la ranura sin tema cae
        # a la siguiente. Lo que se degrada es el balance.
        notes.append(f"quedan pocas semanas de posts de datos; el feed sigue "
                     f"publicando con la mezcla {inv['mezcla_esperada']}. "
                     f"Curar hechos es lo que recupera el balance, no lo que "
                     f"evita que se detenga")
    return ok, notes


def check_site() -> tuple[bool, list[str]]:
    """Sin activo indexable, el esfuerzo no compone."""
    if not DOCS.exists():
        return False, ["no existe docs/: el sistema no produce activos indexables"]
    pages = [p for p in DOCS.glob("*/index.html")]
    problems, notes = [], []
    notes.append(f"{len(pages)} páginas · índice de datos: "
                 f"{'sí' if (DOCS / 'datos/index.html').exists() else 'NO'} · "
                 f"sitemap: {'sí' if (DOCS / 'sitemap.xml').exists() else 'NO'}")
    for p in pages:
        html = p.read_text()
        if "application/ld+json" not in html:
            problems.append(f"{p.parent.name}: sin schema.org")
        if '<link rel="canonical"' not in html:
            problems.append(f"{p.parent.name}: sin canonical")
    if not (DOCS / "sitemap.xml").exists():
        problems.append("falta sitemap.xml")
    return (not problems), notes + [f"✗ {x}" for x in problems]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    failed = False

    print("═══ 1. VERIFICABILIDAD")
    ok, total, problems = check_facts()
    print(f"    {ok}/{total} hechos con cifra localizable en su fuente")
    for p in problems:
        print(f"    ✗ {p}")
    failed |= bool(problems)

    print("\n═══ 2. BREVEDAD")
    ok, total, problems = check_brevity()
    print(f"    {ok}/{total} posts dentro de los límites de lectura")
    for p in problems:
        print(f"    ✗ {p}")
    failed |= bool(problems)

    print("\n═══ 3. INVENTARIO DE CONTENIDO")
    oki, notes = check_inventory()
    for n in notes:
        print(f"    {'·' if oki else '⚠'} {n}")

    # El inventario bajo AVISA, no bloquea. Y es una corrección, no un
    # descuido.
    #
    # Este control tiraba a la basura un post ya generado, ya verificado y ya
    # renderizado, por un problema que es del FUTURO: quedarse sin material la
    # semana que viene. El 14 de septiembre de 2026 el cron generó el post
    # ("1/1 listos") y después se negó a publicarlo porque el runway estaba en
    # 2 semanas. Resultado: cero publicaciones y el inventario intacto, que no
    # le sirve a nadie.
    #
    # La repetición ya la impiden los enfriamientos por tema, hecho y bloque.
    # Y si el inventario llega de verdad a cero, `pipeline.run` no produce
    # ningún post y la corrida falla ahí sola, que es el freno correcto y en
    # el momento correcto.
    if not oki:
        print("::warning::Inventario bajo: se publica igual, pero hay que "
              "curar más hechos en data/facts.json")

    print("\n═══ 4. ACTIVO INDEXABLE")
    oks, notes = check_site()
    for n in notes:
        print(f"    {'·' if oks else '✗'} {n}")
    failed |= not oks

    print("\n" + ("FALLA" if failed else "TODO OK"))
    if failed and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
