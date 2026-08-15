"""
Puntúa TODOS los posts que el sistema puede publicar y muestra los peores.

**Por qué existe.** Cada control de este repo nació de una captura de pantalla:
Santiago veía un post malo, lo mandaba, y se agregaba un test para esa falla.
Eso arregla lo que ya salió mal. No encuentra lo próximo.

Esto invierte la dirección. En vez de esperar a que un post malo llegue al
feed, se generan los 26 posibles, se puntúan en todas las dimensiones que sí
se pueden medir, y se ordenan de peor a mejor. Lo que aparece arriba es lo
próximo que va a molestar.

    python -m pipeline.auditoria            # tabla completa
    python -m pipeline.auditoria --peores 5 # solo los que hay que mirar
    python -m pipeline.auditoria --strict   # falla si alguno baja del piso

**Qué mide y qué no.** Mide lo que tiene forma: cifras sin explicar, siglas
sin glosa, frames que se parafrasean, ganchos sin registro, densidad, largo,
desvío de magnitud. NO mide si un post es interesante — eso no tiene forma y
ya se intentó dos veces con resultados malos.

Por eso el puntaje no dice "este post es bueno". Dice "a este post no le
encontré nada", que es distinto y más honesto. Un 100 con un titular aburrido
sigue siendo un titular aburrido; lo que garantiza es que no vas a encontrar
un `&#x2019;` crudo ni un "5%" sin referente.

**Cómo se usa de verdad.** Antes de una tanda: mirar los tres peores. Después
de agregar un tema o un hecho: correrlo otra vez y ver si algo empeoró. Es la
diferencia entre revisar un post por semana y revisar los 26 de una sentada.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from pipeline import glosario, plan, redaccion, referentes
from pipeline.generate import SinMaterial, generate
from pipeline.render_html import frames_for
from pipeline.spec import PostSpec

# Piso por debajo del cual un post no debería llegar al feed. No es 100: hay
# dimensiones que penalizan de a poco y un post correcto puede quedar en 85.
PISO = 70.0


@dataclass
class Hallazgo:
    dimension: str
    penaliza: float
    detalle: str


@dataclass
class Auditoria:
    post_id: str
    kind: str
    hallazgos: list[Hallazgo] = field(default_factory=list)

    @property
    def puntaje(self) -> float:
        return max(0.0, 100.0 - sum(h.penaliza for h in self.hallazgos))

    @property
    def peor(self) -> Hallazgo | None:
        return max(self.hallazgos, key=lambda h: h.penaliza, default=None)


def _texto_visible(spec: PostSpec) -> str:
    partes: list[str] = []
    for s in spec.slides:
        partes += [s.headline, s.accent, s.body, s.source]
        partes += [st.label for st in (s.stats or [])]
        partes += list(s.bullets or [])
    return " ".join(p for p in partes if p)


def auditar_post(spec: PostSpec, post) -> Auditoria:
    """
    Un post contra todas las dimensiones medibles.

    Las penalizaciones están calibradas por consecuencia, no por frecuencia:
    lo que hace que el lector no entienda pesa más que lo que lo aburre.
    """
    a = Auditoria(post_id=post.id, kind=post.kind)
    visible = _texto_visible(spec)

    # 1. Cifra sin referente. Es lo que más rompe la lectura: el frame 1
    #    muestra un número grande y no dice de qué.
    portada = spec.slides[0]
    if portada.stat and not (portada.body or "").strip():
        a.hallazgos.append(Hallazgo(
            "cifra huérfana", 40,
            f"el frame 1 muestra '{portada.stat}' sin decir qué mide"))

    # 2. Sigla sin glosa. El lector que no está en el rubro se cae acá.
    faltan = glosario.sin_explicar(visible)
    if faltan:
        a.hallazgos.append(Hallazgo(
            "sigla sin explicar", 25, f"usa {faltan} sin definirlas"))

    # 3. Paráfrasis entre frames: el carrusel gira en vez de avanzar.
    g = spec.slides[0].headline
    t = spec.slides[1].headline
    c = f"{spec.slides[2].headline} {spec.slides[2].accent}"
    peor_solape = max(redaccion.solape(g, t), redaccion.solape(g, c),
                      redaccion.solape(t, c))
    if peor_solape >= redaccion.UMBRAL_SOLAPE:
        a.hallazgos.append(Hallazgo(
            "frames que se repiten", 30,
            f"dos de los tres frames comparten {peor_solape:.0%} del texto"))
    elif peor_solape >= 0.28:
        a.hallazgos.append(Hallazgo(
            "frames parecidos", 8,
            f"solape de {peor_solape:.0%}, por debajo del umbral pero alto"))

    # 4. Desvío de magnitud, SOLO sobre texto que escribió el modelo.
    #
    # El texto curado —el ángulo del tema, los mensajes evergreen— lo aprobó
    # una persona y puede apuntar legítimamente a algo que los dos hechos del
    # día no miden. Medirlo con esta vara marcaba 11 posts, casi todos por
    # frases que Santi escribió. Un auditor que grita sobre contenido aprobado
    # entrena a ignorarlo.
    fuente = " ".join(f.get("statement", "") for f in (post.facts or []))
    if fuente and spec.redaccion == "modelo":
        cuerpo = " ".join(s.body or "" for s in spec.slides)
        d = referentes.desvios(cuerpo, fuente)
        if d:
            a.hallazgos.append(Hallazgo(
                "cambia qué se mide", 35,
                f"el texto habla de {d} y los hechos no miden eso"))

    # 5 y 6. Registro y largo del gancho, SOLO en posts de datos.
    #
    # Un evergreen abre con un mensaje aprobado de la empresa, que es otra
    # cosa que un gancho de 52 caracteres: dice qué hace DentRead, y eso no
    # entra en una frase con contraste. Medirlos con la misma vara marcaba 15
    # posts por un largo que es correcto para su tipo.
    if post.kind == "data":
        if not (redaccion._CONTRASTE.search(g) or redaccion._TENSION.search(g)):
            a.hallazgos.append(Hallazgo(
                "gancho sin registro", 10,
                f"'{g}' no marca contraste ni tensión: puede estar enunciando"))
        if len(g) > 52:
            a.hallazgos.append(Hallazgo(
                "gancho largo", 15, f"{len(g)} caracteres, el máximo es 52"))
        elif len(g) < 18:
            a.hallazgos.append(Hallazgo(
                "gancho corto", 8, f"{len(g)} caracteres: puede no decir nada"))

    # 7. Densidad del frame 2. Un frame con título y nada más es un hueco.
    frames = frames_for(spec)
    medio = frames[1].body_html
    if 'class="stats"' not in medio and 'class="points"' not in medio:
        a.hallazgos.append(Hallazgo(
            "frame 2 vacío", 30, "ni cifras ni puntos en el frame del medio"))

    # 8. Alternancia de fondos, del brand guide.
    if [f.dark for f in frames] != [True, False, True]:
        a.hallazgos.append(Hallazgo(
            "alternancia rota", 20, "no es oscuro / claro / oscuro"))

    # 9. Entidades HTML crudas. Salió publicado un "&#x2019;".
    if "&#" in visible or "&amp;" in visible:
        a.hallazgos.append(Hallazgo(
            "entidad HTML cruda", 25, "hay texto sin desescapar en un slide"))

    # 10. Caption: el brand guide pide pregunta, emoji y 4-6 hashtags.
    cap = spec.caption_es
    if "?" not in cap and "¿" not in cap:
        a.hallazgos.append(Hallazgo("caption sin pregunta", 10,
                                    "no invita a responder"))
    if not 4 <= cap.count("#") <= 6:
        a.hallazgos.append(Hallazgo("hashtags fuera de rango", 5,
                                    f"{cap.count('#')}, el brand guide pide 4-6"))
    return a


def auditar_todo() -> list[Auditoria]:
    """Todos los posts que el sistema puede producir hoy, sin consumir nada."""
    estado = {"themes": {}, "facts": {}, "evergreen": {}, "count": 0}
    salida: list[Auditoria] = []

    for tema, _ in plan.available_themes(estado):
        hechos = plan.facts_for(tema.id, estado, limit=2)
        if len(hechos) < 2:
            continue
        post = plan.post_from_theme(tema, hechos)
        try:
            salida.append(auditar_post(generate(post), post))
        except (SinMaterial, ValueError):
            continue

    for bloque in plan.available_evergreen(estado):
        post = plan.post_from_block(bloque, seed=0)
        try:
            salida.append(auditar_post(generate(post), post))
        except (SinMaterial, ValueError):
            continue

    salida.sort(key=lambda a: a.puntaje)
    return salida


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--peores", type=int, default=0,
                    help="mostrar solo los N peores")
    ap.add_argument("--strict", action="store_true",
                    help="salir con error si algún post baja del piso")
    args = ap.parse_args()

    todo = auditar_todo()
    if not todo:
        print("no hay posts disponibles para auditar")
        return 1

    mostrar = todo[:args.peores] if args.peores else todo

    print(f"\n{'puntaje':>7}  {'tipo':10} {'post':28} qué le falta")
    print("-" * 92)
    for a in mostrar:
        peor = a.peor
        detalle = f"{peor.dimension}: {peor.detalle}" if peor else "nada"
        print(f"{a.puntaje:7.0f}  {a.kind:10} {a.post_id:28} {detalle[:44]}")

    limpios = sum(1 for a in todo if not a.hallazgos)
    bajo = [a for a in todo if a.puntaje < PISO]
    print()
    print(f"{len(todo)} posts · {limpios} sin hallazgos · "
          f"promedio {sum(a.puntaje for a in todo) / len(todo):.0f}")

    # Las dimensiones que más aparecen: es lo que conviene atacar primero,
    # porque arreglar una arregla muchos posts a la vez.
    conteo: dict[str, int] = {}
    for a in todo:
        for h in a.hallazgos:
            conteo[h.dimension] = conteo.get(h.dimension, 0) + 1
    if conteo:
        print("\nlo que más se repite:")
        for dim, n in sorted(conteo.items(), key=lambda x: -x[1])[:5]:
            print(f"   {n:3} posts · {dim}")

    if bajo:
        print(f"\n⚠ {len(bajo)} post(s) por debajo del piso de {PISO:.0f}:")
        for a in bajo:
            for h in a.hallazgos:
                print(f"   {a.post_id}: {h.dimension} — {h.detalle}")
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
