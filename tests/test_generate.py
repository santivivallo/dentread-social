#!/usr/bin/env python3
"""
Genera TODOS los tipos de post y valida su forma.

Existe por un fallo concreto: al pasar de 6 frames a 3 quedó un
`slides[:MAX_SLIDES]` en el camino de evergreen apuntando a una constante
renombrada. Las pruebas manuales usaron siempre `--theme <tema de datos>`,
así que el `NameError` apareció recién en CI, en la primera corrida real.

La lección no es "faltaba un test" sino "probé un camino y asumí el otro".
Esto recorre los dos.

    python -m tests.test_generate
"""
from __future__ import annotations

import sys

from pipeline import plan
from pipeline.generate import N_SLIDES, generate
from pipeline.render_html import frames_for

# Roles esperados por posición. El brand guide fija el orden: gancho, datos,
# cierre. Si alguien reordena, esto falla antes que el renderer.
EXPECTED_ROLES = ("hook", "data", "close")


def _check(spec, kind: str) -> list[str]:
    errs = []
    if len(spec.slides) != N_SLIDES:
        errs.append(f"{kind}: {len(spec.slides)} frames, se esperaban {N_SLIDES}")
    for i, s in enumerate(spec.slides):
        if s.role not in EXPECTED_ROLES:
            errs.append(f"{kind}: frame {i+1} tiene rol '{s.role}'")
        if not s.headline.strip():
            errs.append(f"{kind}: frame {i+1} sin titular")

    # El cierre no puede ser el mismo en todos los posts: durante un tiempo
    # los doce de datos terminaron con la misma frase genérica.
    cierre = spec.slides[-1]
    if len(f"{cierre.headline} {cierre.accent}".strip()) < 12:
        errs.append(f"{kind}: cierre demasiado corto o vacío")
    if not spec.caption_es.strip():
        errs.append(f"{kind}: caption vacío")

    # Los titulares del frame de datos eran etiquetas de sección repetidas en
    # los 27 posts ("Lo que dicen las cifras", "Lo que hacemos"). El frame del
    # medio es el que sostiene el post: si su titular no dice nada, el lector
    # ve dos números sin marco.
    medio_titulo = spec.slides[1].headline.strip()
    if medio_titulo in ("Lo que dicen las cifras", "Lo que hacemos"):
        errs.append(f"{kind}: el frame 2 usa el titular genérico de reserva")
    # Reglas del brand guide que se pueden verificar sin renderizar.
    n_tags = spec.caption_es.count("#")
    if not 4 <= n_tags <= 6:
        errs.append(f"{kind}: {n_tags} hashtags, el brand guide pide 4-6")
    if "🦷" not in spec.caption_es:
        errs.append(f"{kind}: falta el emoji dental en el caption")
    if "—" in spec.caption_es:
        errs.append(f"{kind}: em dash en el caption")

    # Alternancia y densidad, sobre los frames ya compuestos.
    #
    # Los dos fallos que esto atrapa aparecieron publicados: los tres frames
    # de un evergreen salieron oscuros porque el del medio caía en el rol
    # `close` al no haber cifras, y ese mismo frame quedó con un título y
    # nada más. Ninguna de las dos cosas rompe nada, por eso hay que medirlas.
    # Una tarjeta de cifra cortada al medio ("…y del…") pasa todos los guards
    # y se ve en el feed. Salió publicado así en medicaid-adultos: el enunciado
    # tenía 155 chars y la tarjeta corta en 120.
    for s in spec.slides:
        for st in (s.stats or []):
            if st.label.rstrip().endswith("…"):
                errs.append(f"{kind}: tarjeta '{st.number}' cortada al medio: "
                            f"...{st.label[-40:]}")

    # Ninguna cifra queda huérfana: si el frame 1 muestra un número grande,
    # ese mismo frame tiene que decir qué mide.
    #
    # Salió publicado un "5%" gigante bajo el titular "Cubrir no es lo mismo
    # que pagar". El 5% mide cuántos beneficiarios de Medicaid tienen además
    # seguro privado; el titular habla de reembolsos. El lector veía una cifra
    # sin referente. No se arregla escribiendo mejor el titular: el titular es
    # del tema y los hechos rotan, así que ninguna frase fija puede explicar
    # una cifra que cambia.
    portada = spec.slides[0]
    if portada.stat and not (portada.body or "").strip():
        errs.append(f"{kind}: el frame 1 muestra '{portada.stat}' y no dice "
                    f"de qué es")

    # La cifra del gancho no se repite como tarjeta en el frame 2. Con dos
    # hechos por post, mostrar los dos en el frame de datos garantizaba que el
    # número gigante del 01 volviera a aparecer en el 02.
    gancho = (spec.slides[0].stat or "").strip()
    if gancho:
        repes = [st.number for s in spec.slides[1:]
                 for st in (s.stats or []) if st.number.strip() == gancho]
        if repes:
            errs.append(f"{kind}: '{gancho}' es el número del gancho y vuelve "
                        f"como tarjeta en el frame de datos")

    frames = frames_for(spec)
    patron = [f.dark for f in frames]
    if patron != [True, False, True]:
        errs.append(f"{kind}: alternancia {patron}, se esperaba oscuro/claro/oscuro")
    medio = frames[1].body_html
    if 'class="stats"' not in medio and 'class="points"' not in medio:
        errs.append(f"{kind}: el frame 2 no tiene ni cifras ni puntos")
    return errs


def probar_caminos_de_construccion() -> list[str]:
    """
    Que todo camino que arme un Post desde un tema pase por `post_from_theme`.

    Había tres copias de esa construcción, no dos. La tercera vivía en
    `run.py --theme` y le faltaban close, close_accent, data_title, kicker y
    hook, o sea todo lo que se le agregó al tema con el tiempo. El resultado
    fue que `--theme` abortaba con "no trae cierre" mientras la corrida normal
    andaba bien: el camino roto era justamente el que se usa para revisar un
    post antes de publicarlo.

    Un campo nuevo en Theme no debería poder olvidarse en un camino y no en
    otro, así que esto compara los dos Posts campo por campo.
    """
    import dataclasses

    from pipeline.themes import CATALOG

    errs = []
    state = {"themes": {}, "facts": {}, "evergreen": {}, "count": 0}
    for theme in CATALOG:
        facts = plan.facts_for(theme.id, state, limit=2)
        if len(facts) < 2:
            continue
        canonico = plan.post_from_theme(theme, facts)
        for campo in ("close", "close_accent", "data_title", "kicker", "hook"):
            if not getattr(canonico, campo, None):
                errs.append(f"{theme.id}: post_from_theme no propaga "
                            f"'{campo}' del tema")
        # Y que el dataclass no tenga campos que el tema define y el Post no
        # reciba: si alguien agrega un campo a Theme y se olvida acá, esto lo
        # muestra antes que una corrida en produccion.
        faltantes = [f.name for f in dataclasses.fields(theme)
                     if getattr(theme, f.name, None)
                     and f.name in {f2.name for f2 in dataclasses.fields(canonico)}
                     and not getattr(canonico, f.name, None)]
        if faltantes:
            errs.append(f"{theme.id}: el tema define {faltantes} y el Post "
                        f"queda sin eso")
        break  # con un tema alcanza: la construcción es la misma para todos
    return errs


def main() -> int:
    state = {"themes": {}, "facts": {}, "evergreen": {}, "count": 0}
    errors: list[str] = probar_caminos_de_construccion()
    tested = 0
    # El cierre es lo único que hace distinto a un post del siguiente cuando
    # el lector ya deslizó dos frames. Si se repite, el carrusel se vuelve
    # plantilla. Se verifica que sean únicos, no sólo que existan.
    cierres: dict[str, list[str]] = {}

    # Todos los temas con hechos suficientes, no solo el primero.
    for theme, facts in plan.available_themes(state):
        facts = plan.facts_for(theme.id, state, limit=2)
        if len(facts) < 2:
            continue
        post = plan.post_from_theme(theme, facts)
        spec = generate(post)
        errors += _check(spec, f"data/{theme.id}")
        c = spec.slides[-1]
        cierres.setdefault(f"{c.headline} / {c.accent}", []).append(theme.id)
        tested += 1

    # Y todos los bloques evergreen: el camino que se rompió.
    for block in plan.available_evergreen(state):
        post = plan.post_from_block(block, seed=0)
        spec = generate(post)
        errors += _check(spec, f"evergreen/{block['id']}")
        c = spec.slides[-1]
        cierres.setdefault(f"{c.headline} / {c.accent}", []).append(block["id"])
        tested += 1

    for texto, quienes in cierres.items():
        if len(quienes) > 1:
            errors.append(f"cierre repetido en {len(quienes)} posts "
                          f"({', '.join(quienes[:3])}…): \"{texto}\"")

    if errors:
        print(f"✗ {len(errors)} problema(s) en {tested} posts:\n")
        print("\n".join(f"  {e}" for e in errors))
        return 1
    print(f"✓ {tested} posts generados, {N_SLIDES} frames cada uno, "
          f"{len(cierres)} cierres únicos, captions dentro del brand guide")
    return 0


if __name__ == "__main__":
    sys.exit(main())
