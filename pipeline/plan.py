"""
Planificación: qué se publica y cuándo.

Reemplaza a `compose.py`. No usa recuperación ni modelos: elige entre hechos
curados con enfriamiento a tres niveles.

    tema      60 días   no repetir el mismo ángulo
    hecho     90 días   no repetir la misma cifra   ← el que faltaba
    evergreen 120 días  los posts sobre DentRead sí pueden volver

El enfriamiento por HECHO es la corrección central. Antes solo se enfriaban
temas, y como cada hecho pertenece a 2-4 temas, la misma cifra reaparecía a
la semana siguiente bajo otro título.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pipeline.themes import CATALOG, Theme

STATE = Path("data/rotation.json")
FACTS = Path("data/facts.json")
EVERGREEN = Path("data/evergreen.json")

COOLDOWN_THEME = 60
COOLDOWN_FACT = 90
COOLDOWN_EVERGREEN = 120

# Cada cuántos posts entra uno sobre DentRead. 1 de cada 4 = ~1 cada dos
# semanas a dos posts semanales. Más que eso y el canal se vuelve publicidad.
EVERGREEN_EVERY = 4

# Orden en que se intercalan las fuentes. No es "usar una hasta agotarla":
# esperar a que un pozo se seque para abrir otro deja huecos justo cuando el
# inventario está bajo, y hace que el feed se lea por tandas del mismo tipo.
# Con seis ranuras y tres posts por semana, el ciclo dura dos semanas.
CICLO = ("data", "news", "evergreen", "paper", "data", "news")

# Cuántas noticias o papers de repuesto se ofrecen cuando el turno es de una
# fuente externa. Existe porque esas dos pueden caerse DESPUÉS de elegidas
# —sin resumen, o con un resumen que no cruza los controles— y una sola
# alternativa no alcanza cuando hay cientos de artículos disponibles.
ALTERNATIVAS_EXTERNAS = 3

# Ventana editorial: noticias y literatura, solo del año en curso. Un artículo
# del año pasado se lee como archivo y contradice que la cobertura crezca
# semana a semana.
#
# **Era una constante con 2026 escrito a mano, y eso es una bomba de tiempo
# con fecha conocida.** El 1 de enero de 2027 el sistema habría seguido
# sirviendo stock de 2026 como si fuera del año en curso, y no habría mirado
# un solo artículo de 2027: contenido cada vez más viejo, sin un error, sin un
# aviso, exactamente el modo de falla que dejó el feed un mes sin noticias.
#
# Ahora se calcula. La política no cambia —sigue siendo solo el año en curso—
# pero el cambio de año deja de depender de que alguien se acuerde.
#
# El costo de esto es visible y hay que decirlo: al 1 de enero el stock
# publicable cae de golpe a los artículos del año nuevo, que el 1 de enero son
# casi cero. Por eso `tools.revision` avisa en noviembre y diciembre cuántos
# artículos hay para el año siguiente: la decisión de ensanchar la ventana o
# de aceptar menos noticias en enero es editorial, y conviene tomarla en
# diciembre con el número delante, no descubrirla en enero.
def anio_minimo() -> int:
    return date.today().year

# Los papers rotan de tema entre corridas. Con un solo preset el sistema
# volvía siempre sobre IA y dejaba fuera el resto de la tesis de mercado.
PRESETS_PAPER = ("ia", "aceptacion", "acceso", "economia", "medicaid", "workforce")


@dataclass
class Post:
    kind: str                    # "data" | "evergreen"
    id: str
    title: str
    audience: str
    angle: str
    angle_en: str
    family: str
    facts: list[dict] = field(default_factory=list)
    body: str = ""               # solo evergreen
    body_en: str = ""
    # Mensajes extra del bloque, para que un post de posicionamiento pueda
    # construirse sin depender de cifras.
    messages: list[str] = field(default_factory=list)
    messages_en: list[str] = field(default_factory=list)
    close: str = ""                  # cierre propio del post
    close_accent: str = ""
    data_title: str = ""             # titular del frame de datos
    kicker: str = ""                 # etiqueta de tema del frame 1
    hook: str = ""                   # titular del frame 1
    source_url: str = ""             # noticia o paper: de dónde salió
    source_label: str = ""
    # Texto fuente, solo en memoria: es lo que se resume y contra lo que
    # newsguard mide copia. Nunca se publica ni se guarda en post.json.
    source_text: str = ""
    es_reciente: bool = True         # False = viene del stock del año
    publicado: str = ""

    def fact_ids(self) -> list[str]:
        return [f["id"] for f in self.facts]


# --------------------------------------------------------------------------

def load_facts() -> list[dict]:
    return json.loads(FACTS.read_text())["facts"] if FACTS.exists() else []


def load_evergreen() -> list[dict]:
    return json.loads(EVERGREEN.read_text())["posts"] if EVERGREEN.exists() else []


def _state() -> dict:
    base = {"themes": {}, "facts": {}, "evergreen": {}, "count": 0}
    if STATE.exists():
        return {**base, **json.loads(STATE.read_text())}
    return base


def _save(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1))


def _age(stamp: str | None) -> int:
    if not stamp:
        return 10_000
    return date.today().toordinal() - date.fromisoformat(stamp).toordinal()


def facts_for(theme_id: str, state: dict, limit: int = 2) -> list[dict]:
    """Hechos del tema que además superaron su propio enfriamiento."""
    out = []
    for f in load_facts():
        if theme_id not in f.get("themes", []):
            continue
        if _age(state["facts"].get(f["id"])) < COOLDOWN_FACT:
            continue
        out.append(f)
        if len(out) >= limit:
            break
    return out


def available_themes(state: dict | None = None) -> list[tuple[Theme, list[dict]]]:
    state = state or _state()
    out = []
    for t in CATALOG:
        if _age(state["themes"].get(t.id)) < COOLDOWN_THEME:
            continue
        fs = facts_for(t.id, state)
        if len(fs) >= 2:
            out.append((t, fs))
    # el tema con más hechos disponibles primero: gasta el inventario parejo
    out.sort(key=lambda x: -len(facts_for(x[0].id, state, limit=99)))
    return out


def post_from_block(block: dict, seed: int = 0) -> Post:
    """
    Arma un post a partir de un bloque de mensajes.

    El bloque ofrece varios mensajes aprobados y matizados; se elige uno de
    cada uno rotando por `seed`, de modo que el mismo bloque no produzca dos
    veces el mismo texto. Así el posicionamiento se edita cambiando mensajes,
    sin tocar el código.
    """
    def pick(key: str, fallback: str = "") -> str:
        opts = block.get(key) or []
        return opts[seed % len(opts)] if opts else fallback

    approved = pick("approved_messages")
    approved_en = pick("approved_messages_en", approved)
    qualified = pick("qualified_messages")
    qualified_en = pick("qualified_messages_en", qualified)

    # el resto de los mensajes queda disponible para armar los slides
    rest = [m for m in (block.get("approved_messages") or []) if m != approved]
    rest_en = [m for m in (block.get("approved_messages_en") or []) if m != approved_en]

    return Post(
        kind="evergreen",
        id=block["id"],
        title=block.get("title", block["id"]),
        audience=block.get("audience", "both"),
        angle=approved,
        angle_en=approved_en,
        family=block.get("category", "dentread"),
        body=qualified,
        body_en=qualified_en,
        facts=[f for f in load_facts()
               if f["id"] in block.get("context_facts", [])][:2],
        messages=rest,
        messages_en=rest_en,
        close=block.get("close", ""),
        close_accent=block.get("close_accent", ""),
        data_title=block.get("data_title", ""),
    )


def post_from_theme(theme: Theme, facts: list[dict]) -> Post:
    """
    Único lugar donde un tema se convierte en Post.

    Antes esto estaba escrito dos veces —acá y en los tests— y al agregarle
    el cierre propio al tema, la segunda copia quedó sin él. Un campo nuevo
    no debería poder olvidarse en la mitad de los casos.
    """
    return Post(
        kind="data", id=theme.id, title=theme.name, audience=theme.audience,
        angle=theme.angle, angle_en=theme.angle_for("en"),
        family=theme.family, facts=facts,
        close=theme.close, close_accent=theme.close_accent,
        data_title=theme.data_title,
        kicker=theme.kicker, hook=theme.hook,
    )


def available_evergreen(state: dict | None = None) -> list[dict]:
    state = state or _state()
    out = []
    for e in load_evergreen():
        # cada bloque puede definir su propio ciclo de revisión
        cooldown = e.get("review_cycle_days", COOLDOWN_EVERGREEN)
        if _age(state["evergreen"].get(e["id"])) >= cooldown:
            out.append(e)
    return out


def _un_post(kind: str, state: dict, usados: set[str],
             familias: set[str], saltar: set[str] | None = None) -> Post | None:
    """
    Devuelve un post de ese tipo, o None si esa fuente no tiene nada hoy.

    Las fuentes externas se importan acá adentro a propósito: ADA News y
    PubMed salen a la red, y no queremos que `import plan` la toque. Si una
    falla —la red, un cambio de HTML, la API caída— devuelve None y el ciclo
    sigue con la fuente siguiente. Una fuente caída no puede frenar la tanda.
    """
    if kind == "evergreen":
        for bloque in available_evergreen(state):
            if "dentread" not in familias:
                return post_from_block(bloque, state.get("count", 0))
        return None

    if kind == "data":
        for theme, _ in available_themes(state):
            if theme.family in familias:
                continue
            fs = [f for f in facts_for(theme.id, state, limit=4)
                  if f["id"] not in usados][:2]
            if len(fs) >= 2:
                usados |= {f["id"] for f in fs}
                return post_from_theme(theme, fs)
        return None

    if kind == "news":
        # Dos pasadas. Primero lo reciente, que es lo que da actualidad; si no
        # hay, el stock del año en curso. Tratar a
        # ADA News como un goteo semanal desperdiciaba el año entero: la
        # ventana de 21 días descartaba enero a julio.
        try:
            from pipeline import ada_news
            from pipeline.sources import post_from_article
            # `con_cuerpo` trae el texto del artículo. Sin esto, los del
            # stock llegan solo con el titular y el resumidor los rechaza por
            # corto, así que la ranura de noticias NUNCA publicaba.
            # `saltar` trae los que ya se ofrecieron en esta tanda. Sin esto
            # la fuente devolvía siempre el primer artículo y pedir una
            # alternativa daba el mismo.
            omitir = (saltar or set()) | set(state.get("externos", {}))
            for art in list(ada_news.latest_relevant(limit=5)) + \
                    list(ada_news.backlog(year=anio_minimo(), limit=40)):
                p = post_from_article(art)
                if p.id in omitir:
                    continue
                return post_from_article(ada_news.con_cuerpo(art))
        except Exception as exc:                 # red, parseo, API
            print(f"   [info] ADA News no disponible ahora: "
                  f"{exc.__class__.__name__}")
        return None

    if kind == "paper":
        # Se rota el preset por posición en el ciclo: buscar siempre "ia"
        # devolvía los mismos estudios y dejaba fuera acceso, economía,
        # aceptación de tratamiento y Medicaid, que son el resto de la tesis.
        try:
            from pipeline import journals
            from pipeline.sources import post_from_signpost
            n_prev = len(state.get("externos", {}))
            orden = PRESETS_PAPER[n_prev % len(PRESETS_PAPER):] + \
                    PRESETS_PAPER[:n_prev % len(PRESETS_PAPER)]
            # `externos` es el registro de lo que ya salió. Para los papers es
            # el único filtro que hay: PubMed no sabe qué publicó DentRead, y
            # el mismo preset devuelve el mismo ranking cada semana.
            omitir = (saltar or set()) | set(state.get("externos", {}))
            for preset in orden:
                for sp in journals.find(preset=preset, years=1, n=10):
                    if sp.year and int(sp.year) < anio_minimo():
                        continue          # solo el año en curso, como las noticias
                    p = post_from_signpost(sp)
                    if p.id in omitir:
                        continue
                    return p
        except Exception as exc:
            print(f"   [info] PubMed no disponible ahora: "
                  f"{exc.__class__.__name__}")
        return None

    return None


def next_posts(n: int = 2) -> list[Post]:
    """
    Arma la tanda intercalando fuentes según CICLO.

    La posición en el ciclo la marca `count`, así que el orden se sostiene
    entre corridas: si el lunes salió una noticia, el miércoles no sale otra.
    Cuando la fuente que toca no tiene material, se prueba la siguiente del
    ciclo en vez de abortar — pero se conserva el turno, para que una semana
    sin noticias no desplace la rotación para siempre.
    """
    state = _state()
    posts: list[Post] = []
    familias: set[str] = set()
    usados: set[str] = set()
    emitidos: set[str] = set()
    inicio = state.get("count", 0)

    for i in range(n):
        turno = (inicio + i) % len(CICLO)
        # se prueba el tipo que toca y, si no hay, los siguientes del ciclo
        for salto in range(len(CICLO)):
            kind = CICLO[(turno + salto) % len(CICLO)]
            post = _un_post(kind, state, usados, familias, emitidos)
            # Sin este filtro la tanda repetía el mismo post.
            #
            # Para noticias y papers, `_un_post` devuelve siempre el mejor
            # candidato disponible: nada dentro de la corrida recordaba que ya
            # lo había ofrecido. Con los reemplazos de `run.py` eso se volvió
            # visible —el mismo artículo tres veces seguidas— y los reemplazos
            # se gastaban en el candidato que acababa de fallar.
            if post and post.id in emitidos:
                post = None
            if post:
                emitidos.add(post.id)
                posts.append(post)
                familias.add("dentread" if post.kind == "evergreen"
                             else post.family)

                # Una noticia o un paper rechazado no pierde el turno.
                #
                # `generate` puede descartarlos después: sin resumen
                # verificado, o porque el resumen no cruza el control de
                # magnitudes. Antes eso alcanzaba para que el turno se lo
                # llevara un post de datos, aunque el archivo tenga 604
                # artículos y PubMed miles. Pasó el 16 de septiembre de 2026:
                # una columna de opinión no pasó el control y la ranura de
                # noticias se perdió con el primer intento.
                #
                # Acá se agregan alternativas de la MISMA fuente, que
                # `run.py` prueba antes de bajar al tipo siguiente del ciclo.
                if kind in ("news", "paper"):
                    for _ in range(ALTERNATIVAS_EXTERNAS):
                        otro = _un_post(kind, state, usados, familias,
                                        emitidos)
                        if not otro or otro.id in emitidos:
                            break
                        emitidos.add(otro.id)
                        posts.append(otro)
                break

    return posts[:n]


def mark_used_from_folder(folder) -> None:
    """
    Marca el consumo a partir de una carpeta ya publicada.

    Existe porque el consumo estaba atado a GENERAR, no a publicar. Cada
    corrida local de `pipeline.run` quemaba tema, hechos y bloque aunque el
    post nunca saliera: probando el sistema un solo día se consumieron 5
    temas, 12 hechos y 4 evergreen, el inventario cayó a cero y el control de
    runway bloqueó la publicación real. El sistema se quedó sin material
    testeándose a sí mismo.

    Un post que no se publicó no gastó nada. Lo que gasta es el feed.
    """
    from pathlib import Path

    datos = json.loads((Path(folder) / "post.json").read_text())
    s = _state()
    hoy = date.today().isoformat()
    slug = datos.get("slug", "")

    if datos.get("mode") == "evergreen":
        s["evergreen"][slug] = hoy
    elif datos.get("mode") in ("news", "paper"):
        # Una fuente externa no gasta inventario editorial, pero SÍ hay que
        # anotar que ya salió.
        #
        # Acá había un `pass` con el comentario "su material es externo y no se
        # repite por definición". Era falso de las dos formas posibles:
        #
        # - Quien marca el artículo en el archivo de ADA es `mark_used`, y
        #   `publish.py` no llama a `mark_used` sino a esta función. O sea que
        #   `ada_news.mark_published` nunca corrió en producción y el flag
        #   `used` —el único filtro que tiene `latest_relevant`— quedó siempre
        #   en falso.
        # - Los papers no tenían registro de ningún tipo: `journals.find` con
        #   el mismo preset devuelve el mismo ranking, así que el estudio de
        #   esta semana es el candidato número uno de la próxima.
        #
        # El resultado es que el siguiente turno de noticia podía republicar
        # exactamente lo mismo, y no se habría notado hasta verlo en el feed.
        externos = s.setdefault("externos", {})
        externos[datos.get("post_id") or slug] = hoy
        url = datos.get("source_url") or ""
        if datos.get("mode") == "news" and url:
            try:
                from pipeline import ada_news
                ada_news.mark_published(url)
            except Exception as exc:
                # No frena la publicación: el post ya salió. Pero se ve.
                print(f"   [aviso] no se pudo marcar la nota en el archivo "
                      f"({exc.__class__.__name__}): puede volver a salir")
        if datos.get("mode") == "paper":
            # El pmid viaja en el id del post (`paper-41204923`). PubMed no
            # sabe qué publicó DentRead y el mismo preset devuelve el mismo
            # ranking cada semana, así que sin esto el estudio de hoy es el
            # candidato número uno del turno siguiente.
            pmid = (datos.get("post_id") or "").split("-")[-1]
            try:
                from pipeline import journals
                journals.marcar_publicado(pmid)
            except Exception as exc:
                print(f"   [aviso] no se pudo marcar el estudio {pmid} "
                      f"({exc.__class__.__name__}): puede volver a salir")
    else:
        s["themes"][slug] = hoy
        for fid in datos.get("fact_ids", []):
            s["facts"][fid] = hoy

    s["count"] = s.get("count", 0) + 1
    _save(s)


def mark_used(post: Post) -> None:
    s = _state()
    today = date.today().isoformat()
    if post.kind == "evergreen":
        # Los evergreen NO consumen el banco de hechos: la cifra ahí es
        # contexto de un post sobre DentRead, no el contenido. Si gastaran
        # hechos, hablar de la empresa reduciría el inventario editorial.
        s["evergreen"][post.id] = today
    elif post.kind in ("news", "paper"):
        # Tampoco consumen inventario editorial: su material es externo y no
        # se repite por definición. Lo único que hay que registrar es que ese
        # artículo o ese estudio ya salió, y de eso se encargan el archivo de
        # ADA News y el pmid.
        if post.kind == "news" and post.source_url:
            try:
                from pipeline import ada_news
                ada_news.mark_published(post.source_url)
            except Exception:
                pass
        s.setdefault("externos", {})[post.id] = today
    else:
        s["themes"][post.id] = today
        for fid in post.fact_ids():
            s["facts"][fid] = today
    s["count"] = s.get("count", 0) + 1
    _save(s)


def inventory() -> dict:
    """
    Qué queda de cada fuente, y qué mezcla va a salir al feed.

    **Ojo con el nombre que tenía.** Esto devolvía `semanas_de_runway`
    descrito como "semanas hasta quedarse sin contenido", y lo calculaba solo
    sobre los hechos curados y los evergreen. Con el banco de cifras agotado
    marcaba 0,0 semanas, que se lee como "el sistema se seca el lunes".

    No es cierto, y está medido: con 0 temas publicables, `next_posts(6)`
    devuelve 6 posts. De las cuatro fuentes del CICLO, tres se reponen solas
    —ADA News tiene 96 artículos publicables en stock, PubMed es ilimitado— y
    la ranura de datos que no encuentra tema cae a la siguiente del ciclo. El
    sistema se diseñó así justamente para que no pudiera quedarse sin qué
    publicar.

    Lo que el número medía de verdad era otra cosa: cuántas semanas quedan de
    posts DE DATOS antes de que esas ranuras empiecen a caerse. Eso no para el
    feed, le cambia la mezcla, y la consecuencia real es que 5 de cada 6 posts
    salen de noticias.

    Un nombre que exagera lo que mide manda a arreglar el problema equivocado:
    con esto en cero se propuso curar cifras a mano como si fuera urgencia de
    supervivencia, cuando era una decisión editorial sobre el balance del feed.
    Así que ahora la clave dice qué mide, y además se informa la mezcla.
    """
    s = _state()
    facts = load_facts()
    fresh = [f for f in facts if _age(s["facts"].get(f["id"])) >= COOLDOWN_FACT]
    themes = available_themes(s)
    evergreen = available_evergreen(s)
    return {
        "hechos_totales": len(facts),
        "hechos_disponibles": len(fresh),
        "temas_publicables": len(themes),
        "evergreen_disponibles": len(evergreen),
        "posts_publicados": s.get("count", 0),
        "semanas_con_posts_de_datos": _runway(len(themes), len(evergreen)),
        "mezcla_esperada": _mezcla(len(themes), len(evergreen)),
    }


def _mezcla(temas: int, evergreen: int) -> str:
    """
    Con qué proporción de cada fuente va a salir el feed esta semana.

    Es la métrica que importa cuando una fuente se agota, porque el ciclo no
    deja de publicar: redistribuye. Un feed que pasa a ser 5/6 noticias no
    está roto, pero dejó de ser el que se diseñó, y eso hay que verlo en el
    `--inventory` y no descubrirlo mirando el perfil.
    """
    reparto: dict[str, int] = {}
    for kind in CICLO:
        # Una ranura sin material cae a la fuente siguiente del ciclo, que en
        # la práctica es casi siempre noticias: es la única sin tope.
        if kind == "data" and temas <= 0:
            kind = "news"
        elif kind == "evergreen" and evergreen <= 0:
            kind = "news"
        reparto[kind] = reparto.get(kind, 0) + 1
    total = len(CICLO)
    return " · ".join(f"{k} {n}/{total}"
                      for k, n in sorted(reparto.items(), key=lambda x: -x[1]))


# Publicaciones por semana. El cron corre lunes, miércoles y viernes.
POSTS_POR_SEMANA = 3


def _ritmo(kind: str) -> float:
    """Cuántos posts de este tipo salen por semana, según CICLO."""
    veces = CICLO.count(kind)
    return POSTS_POR_SEMANA * veces / len(CICLO)


def _runway(temas: int, evergreen: int) -> float:
    """
    Semanas de posts de datos y evergreen, por la fuente que apriete antes.

    NO es "semanas hasta quedarse sin contenido": las noticias y los papers se
    reponen solos y una ranura sin material cae a la siguiente del ciclo. Con
    esto en cero el sistema sigue publicando tres veces por semana; lo que
    cambia es la mezcla, y eso lo informa `_mezcla`.

    Antes era `temas / 2`, un divisor escrito cuando todos los posts salían de
    hechos curados. Desde que CICLO intercala cuatro fuentes, los de datos son
    2 de cada 6 ranuras: a tres por semana, uno por semana y no dos. El número
    salía a la mitad de lo real y bloqueaba la publicación por un runway que
    no existía.

    Las noticias y los papers no entran en la cuenta a propósito: no consumen
    inventario editorial, se reponen solos.
    """
    limites = []
    for kind, disponible in (("data", temas), ("evergreen", evergreen)):
        ritmo = _ritmo(kind)
        if ritmo:
            limites.append(disponible / ritmo)
    return round(min(limites), 1) if limites else 0.0
