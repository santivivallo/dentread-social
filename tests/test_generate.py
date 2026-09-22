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
import tempfile
from pathlib import Path

from pipeline import bitacora, plan

# Este test genera los 26 posts posibles, y generar llama al modelo. Son
# llamadas legítimas —se está probando el camino real— pero no son producción:
# si se anotaran en la bitácora real, la revisión quincenal contaría los
# intentos de los tests como intentos del sistema e inflaría la tasa de fallo
# del proveedor, que es justo el número que decide si hay que cambiar de
# modelo.
bitacora.RUTA = Path(tempfile.gettempdir()) / "bitacora-de-prueba.jsonl"
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
    # El em dash se mide en los TRES textos que revisa el guard, no solo en
    # el caption español.
    #
    # Acá estaba el agujero. Este test verificaba `caption_es` y nada más,
    # así que pasaba en verde mientras el guard —que mira también
    # `commentary_en` y `title_en`— frenaba la publicación. El 21 de
    # septiembre de 2026 la corrida del lunes murió con
    # "BLOQUEADO · EN/LinkedIn: em_dash/assertive → —" con los ocho tests en
    # verde: el control existía, pero medía un campo de los tres.
    for campo in ("caption_es", "commentary_en", "title_en"):
        texto = getattr(spec, campo, "") or ""
        if "—" in texto or "–" in texto:
            errs.append(f"{kind}: em dash en {campo} (el guard lo bloquea)")

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

    # Ninguna sigla sale sin explicar.
    #
    # Salió publicado un frame 1 que decía "CDT 2026 trae 60 cambios de
    # código" sin decir en ningún lado qué es CDT. Un dentista en EE.UU. lo
    # sabe; la cuenta la lee también gente que administra clínicas o mira
    # desde otro país, y una sigla sin explicar es el punto donde el lector
    # deja de entender y se va. Son 6 siglas en 23 lugares del catálogo, así
    # que explicarlas a mano es olvidarse una.
    from pipeline import glosario
    partes: list[str] = []
    for s in spec.slides:
        partes += [s.headline, s.accent, s.body, s.source]
        partes += [st.label for st in (s.stats or [])]
        partes += list(s.bullets or [])
    texto_visible = " ".join(p for p in partes if p)
    faltan = glosario.sin_explicar(texto_visible)
    if faltan:
        errs.append(f"{kind}: usa {faltan} sin explicar qué significan")

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
    # Lo que el brand guide exige es ALTERNAR, no empezar oscuro.
    #
    # Este test pedía exactamente [oscuro, claro, oscuro], así que le puso
    # candado a la monotonía: en la grilla del perfil solo se ve el frame 1 y
    # todos los posts daban la misma baldosa oscura. La polaridad de arranque
    # es una decisión por carrusel según el propio brand guide.
    if patron[0] == patron[1] or patron[1] == patron[2]:
        errs.append(f"{kind}: los fondos no alternan: {patron}")
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


def probar_camino_bloqueado() -> list[str]:
    """
    Que `run_guard` sepa leer un hallazgo del guard.

    **El bug que esto habría evitado**, arreglado por Santi el 18 de
    septiembre de 2026 en 190e702: `run_guard` armaba el mensaje con
    `f.rule.id` y `f.rule.level`, y `Finding` no tiene `.rule` — tiene
    `level`, `domain`, `strength`, `match`. O sea que el camino de bloqueo
    levantaba AttributeError en vez de bloquear.

    Nunca se notó porque **solo se recorre cuando un post tiene un hallazgo**,
    y los posts del catálogo están limpios. El control que existe para frenar
    contenido riesgoso se rompía justo en el momento de frenarlo, y la corrida
    habría muerto con un error que no dice nada del claim.

    Es el mismo patrón que el `NameError` de evergreen: un camino que nadie
    probó a mano. Así que acá se fuerza un hallazgo con texto que el guard
    tiene que marcar, y se verifica que devuelva el problema como string.
    """
    from pipeline.run import run_guard

    class Falso:
        # Un claim diagnóstico sin FDA clearance es exactamente lo que el
        # guard existe para atajar.
        caption_es = ("DentRead diagnostica caries con 99% de precisión y "
                      "reemplaza al dentista. 🦷 #DentRead")
        commentary_en = ("DentRead diagnoses caries with 99% accuracy and "
                         "replaces the dentist.")
        title_en = "DentRead diagnoses caries"
        declarations: dict = {}

    try:
        ok, problemas = run_guard(Falso())
    except AttributeError as exc:
        return [f"run_guard no sabe leer un hallazgo del guard: {exc}"]
    if ok:
        return ["un claim diagnóstico con cifra de precisión no fue "
                "bloqueado: revisar publisher/guard"]
    if not all(isinstance(p, str) and p.strip() for p in problemas):
        return [f"run_guard devolvió problemas no imprimibles: {problemas}"]
    return []


def main() -> int:
    state = {"themes": {}, "facts": {}, "evergreen": {}, "count": 0}
    errors: list[str] = (probar_caminos_de_construccion()
                         + probar_camino_bloqueado())
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
