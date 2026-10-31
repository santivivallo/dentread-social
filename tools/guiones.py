"""
Agente de contenido: 4 guiones de reel por día (3 dentales + 1 tendencia o herramienta de IA) para @dentread_.

Junta lo que pasó (noticias ADA ya archivadas, papers de IA dental en PubMed y
novedades de competidores, tendencias y herramientas nuevas de IA vía Google News, Hacker News y Product Hunt) y le pide al modelo 3 guiones
con los formatos de anuncio aprobados. Regla 1 del repo: las cifras no las
inventa el modelo. Un guion con un número que no esté en un hecho verificado
(data/facts.json) ni en el titular de su fuente se descarta.

Salida: data/guiones/AAAA-MM-DD.md (para leer) y data/guiones/ultimo.json
(lo lee wa-agent para avisar por WhatsApp). Nada se publica solo.

    python -m tools.guiones            # genera el del día
    python -m tools.guiones --sin-red  # solo con lo archivado (pruebas)
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

from pipeline import llm

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "data" / "guiones"
COMPETIDORES = ["Pearl", "Overjet", "VideaHealth", "Diagnocat"]
FORMATOS = [
    "Última hora (noticia real con fuente)", "Reseña cero estrellas (ironía)",
    "Pedimos disculpas (falso comunicado)", "No compres esto (anti-venta)",
    "Efectos secundarios (prospecto con beneficios)", "Búsqueda en Google (duda real del paciente)",
    "En caso de emergencia (guía rápida)", "Antiguo vs nuevo", "Problema → solución",
    "No vayas de listo (corrige un mito)", "Titular con dato (cifra verificada + fuente)",
    "X razones por las que…",
]
REGLAS = """Eres guionista de reels de DentRead (IA que ayuda a dentistas a leer radiografías).
Escribe en español de Chile, tono cercano y profesional. Reglas que no se negocian:
- La IA apoya, el odontólogo decide. Nunca prometas diagnóstico ni compitas en precisión diagnóstica.
- NO inventes cifras: usa solo números que aparezcan en HECHOS (cita su id) o en el titular de la FUENTE elegida.
- Sin testimonios, clientes ni sellos inventados. Si hablas de un competidor, solo lo que dice su titular, sin atacarlo.
- fuente_url debe ser la fuente del tema del guion; si la cifra viene de HECHOS, cita su id en "hechos".
- Cada guion: gancho de máximo 8 palabras (primeros 2 segundos), 3 a 5 escenas cortas, cierre con llamada a la acción.
Devuelve SOLO JSON: {"guiones":[{"titulo":"","formato":"","gancho":"","escenas":["",""],"cierre":"","fuente_url":"","hechos":["id"]}]} con exactamente 4 guiones de formatos distintos: 3 sobre odontología/IA dental y competidores, y el 4.º SIEMPRE sobre una tendencia o herramienta nueva de IA (fuentes «tendencia IA», «IA en salud» o «herramienta»), explicando qué significa para un dentista o una clínica. Si la herramienta no tiene relación posible con salud o clínicas, elige otra."""


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "dentread-social/guiones"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _gnews(q: str, dias: int) -> str:
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": f"{q} when:{dias}d", "hl": "en-US", "gl": "US", "ceid": "US:en"})


# (tipo, url, máximo). Todas gratis y sin clave. Si una cae, las demás siguen.
FEEDS = [
    ("competidor", _gnews("(" + " OR ".join(f'"{c}"' for c in COMPETIDORES) + ") dental AI", 7), 6),
    ("tendencia IA", _gnews('("AI" OR "artificial intelligence") (launch OR "new model" OR "new tool" OR agent)', 3), 6),
    ("IA en salud", _gnews('("AI" healthcare OR "AI" dentistry OR "AI" radiology) (study OR launch OR FDA)', 7), 5),
    ("herramienta", "https://hnrss.org/newest?points=100&q=AI", 5),
    ("herramienta", "https://www.producthunt.com/feed?category=artificial-intelligence", 5),
]
ATOM = "{http://www.w3.org/2005/Atom}"


def feed(tipo: str, url: str, maximo: int) -> list[dict]:
    try:
        root = ET.fromstring(_get(url))
    except Exception as e:  # sin red o feed caído: el guion sale con lo demás
        print(f"[guiones] {tipo} no disponible: {str(e)[:80]}", file=sys.stderr)
        return []
    out = []
    for it in list(root.iter("item")) + list(root.iter(ATOM + "entry")):
        titulo = it.findtext("title") or it.findtext(ATOM + "title") or ""
        link = it.findtext("link") or (it.find(ATOM + "link").get("href") if it.find(ATOM + "link") is not None else "")
        bruto = it.findtext("pubDate") or it.findtext(ATOM + "published") or it.findtext(ATOM + "updated") or ""
        try:
            fecha = parsedate_to_datetime(bruto).date().isoformat()
        except (TypeError, ValueError):
            fecha = bruto[:10]
        out.append({"tipo": tipo, "titulo": titulo.strip(), "url": link, "fecha": fecha})
    return out[:maximo]


def externas() -> list[dict]:
    vistos, out = set(), []
    for tipo, url, maximo in FEEDS:
        for f in feed(tipo, url, maximo):
            if f["url"] and f["url"] not in vistos:
                vistos.add(f["url"]); out.append(f)
    return out


def noticias(dias: int = 21) -> list[dict]:
    desde = (date.today() - timedelta(days=dias)).isoformat()
    out = []
    try:
        arts = json.loads((RAIZ / "data" / "ada_archive.json").read_text()).get("articles", {})
        for url, a in arts.items():
            if (a.get("published") or "")[:10] >= desde and float(a.get("score") or 0) > 0:
                out.append({"tipo": "noticia ADA", "titulo": a.get("title", ""), "url": url, "fecha": a.get("published", "")[:10]})
    except (OSError, ValueError):
        pass
    try:
        estudios = json.loads((RAIZ / "data" / "pubmed_archive.json").read_text()).get("estudios", {})
        for pmid, e in estudios.items():
            # Solo los que pasaron la allowlist y el filtro de diseño
            if not e.get("descartado") and str(e.get("year", "")) >= str(date.today().year - 1):
                out.append({"tipo": "paper", "titulo": e.get("title", ""), "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", "fecha": str(e.get("year", ""))})
    except (OSError, ValueError, AttributeError):
        pass
    return sorted(out, key=lambda x: x["fecha"], reverse=True)[:12]


def hechos() -> list[dict]:
    return [{k: f[k] for k in ("id", "number", "statement", "cite")} for f in json.loads((RAIZ / "data" / "facts.json").read_text())["facts"]]


NUM = re.compile(r"\d[\d.,]*")


def numeros(texto: str) -> set[str]:
    return {re.sub(r"[.,]", "", n) for n in NUM.findall(texto)}


def valido(g: dict, fuentes: list[dict], hs: list[dict]) -> tuple[bool, str]:
    """Todo número del guion debe estar en un hecho citado o en el titular de su fuente."""
    texto = " ".join([g.get("gancho", ""), *g.get("escenas", []), g.get("cierre", ""), g.get("titulo", "")])
    permitidos = set()
    for h in hs:
        if h["id"] in g.get("hechos", []):
            permitidos |= numeros(h["number"] + " " + h["statement"])
    for f in fuentes:
        if f["url"] and f["url"] == g.get("fuente_url"):
            permitidos |= numeros(f["titulo"])
    sueltos = numeros(texto) - permitidos
    if sueltos:
        return False, f"cifras sin respaldo: {', '.join(sorted(sueltos))}"
    if not g.get("gancho") or not 3 <= len(g.get("escenas", [])) <= 5:
        return False, "estructura incompleta"
    return True, ""


def generar(con_red: bool = True) -> dict:
    fuentes = noticias() + (externas() if con_red else [])
    hs = hechos()
    contenido = json.dumps({"FORMATOS": FORMATOS, "FUENTES": fuentes, "HECHOS": hs}, ensure_ascii=False)
    texto = llm.pedir(REGLAS, contenido) or ""
    m = re.search(r"\{.*\}", texto, re.S)
    try:
        cands = json.loads(m.group(0)).get("guiones", []) if m else []
    except ValueError:
        cands = []
    ok, descartes = [], []
    for g in cands:
        bien, motivo = valido(g, fuentes, hs)
        (ok if bien else descartes).append(g if bien else {"titulo": g.get("titulo", ""), "motivo": motivo})
    return {"fecha": date.today().isoformat(), "generado": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "guiones": ok[:4], "descartados": descartes, "fuentes": len(fuentes)}


def markdown(r: dict) -> str:
    L = [f"# Guiones de reel · {r['fecha']}", "", f"{len(r['guiones'])} guiones · {r['fuentes']} fuentes revisadas. Revisar antes de grabar.", ""]
    for i, g in enumerate(r["guiones"], 1):
        L += [f"## {i}. {g.get('titulo', '')}", f"**Formato:** {g.get('formato', '')}", f"**Gancho (0-2 s):** {g.get('gancho', '')}", ""]
        L += [f"{j}. {e}" for j, e in enumerate(g.get("escenas", []), 1)]
        citas = [f"{h['number']} — {h['cite']}" for h in r.get("_hechos", []) if h["id"] in g.get("hechos", [])]
        L += ["", f"**Cierre:** {g.get('cierre', '')}", f"**Fuente:** {g.get('fuente_url') or '—'}"]
        L += [f"**Cifra verificada:** {c}" for c in citas] + [""]
    if r["descartados"]:
        L += ["### Descartados por verificación", *[f"- {d['titulo']}: {d['motivo']}" for d in r["descartados"]]]
    return "\n".join(L) + "\n"


def main() -> int:
    r = generar(con_red="--sin-red" not in sys.argv)
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / f"{r['fecha']}.md").write_text(markdown({**r, "_hechos": hechos()}))
    (SALIDA / "ultimo.json").write_text(json.dumps(r, ensure_ascii=False, indent=2))
    print(f"[guiones] {len(r['guiones'])} guiones, {len(r['descartados'])} descartados, {r['fuentes']} fuentes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
