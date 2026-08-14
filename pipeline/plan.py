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

# Ventana editorial: noticias y literatura, solo de 2026. Un artículo de 2025
# se lee como archivo y contradice que la cobertura crezca semana a semana.
ANIO_MINIMO = 2026

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
    source_url: str = ""             # noticia o paper: de dónde salió
    source_label: str = ""

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
             familias: set[str]) -> Post | None:
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
        # hay, el stock de 2026, que son ~75 artículos publicables. Tratar a
        # ADA News como un goteo semanal desperdiciaba el año entero: la
        # ventana de 21 días descartaba enero a julio.
        try:
            from pipeline import ada_news
            from pipeline.sources import post_from_article
            for art in ada_news.latest_relevant(limit=5):
                return post_from_article(art)
            for art in ada_news.backlog(year=2026, limit=40):
                return post_from_article(art)
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
            for preset in orden:
                for sp in journals.find(preset=preset, years=1, n=10):
                    if sp.year and int(sp.year) < ANIO_MINIMO:
                        continue          # solo 2026, como el resto del flujo
                    return post_from_signpost(sp)
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
    inicio = state.get("count", 0)

    for i in range(n):
        turno = (inicio + i) % len(CICLO)
        # se prueba el tipo que toca y, si no hay, los siguientes del ciclo
        for salto in range(len(CICLO)):
            kind = CICLO[(turno + salto) % len(CICLO)]
            post = _un_post(kind, state, usados, familias)
            if post:
                posts.append(post)
                familias.add("dentread" if post.kind == "evergreen"
                             else post.family)
                break

    return posts[:n]


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
    """Cuánto contenido queda antes de secarse. La métrica que faltaba."""
    s = _state()
    facts = load_facts()
    fresh = [f for f in facts if _age(s["facts"].get(f["id"])) >= COOLDOWN_FACT]
    themes = available_themes(s)
    return {
        "hechos_totales": len(facts),
        "hechos_disponibles": len(fresh),
        "temas_publicables": len(themes),
        "evergreen_disponibles": len(available_evergreen(s)),
        "posts_publicados": s.get("count", 0),
        "semanas_de_runway": round(len(themes) / 2, 1),
    }
