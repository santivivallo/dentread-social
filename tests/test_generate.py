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
    frames = frames_for(spec)
    patron = [f.dark for f in frames]
    if patron != [True, False, True]:
        errs.append(f"{kind}: alternancia {patron}, se esperaba oscuro/claro/oscuro")
    medio = frames[1].body_html
    if 'class="stats"' not in medio and 'class="points"' not in medio:
        errs.append(f"{kind}: el frame 2 no tiene ni cifras ni puntos")
    return errs


def main() -> int:
    state = {"themes": {}, "facts": {}, "evergreen": {}, "count": 0}
    errors: list[str] = []
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
