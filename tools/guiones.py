"""
Agente de contenido: 3 guiones de reel por día para @dentread_.

Junta lo que pasó (noticias ADA ya archivadas, papers de IA dental en PubMed y
novedades de competidores vía Google News RSS) y le pide al modelo 3 guiones
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
Devuelve SOLO JSON: {"guiones":[{"titulo":"","formato":"","gancho":"","escenas":["",""],"cierre":"","fuente_url":"","hechos":["id"]}]} con exactamente 3 guiones de formatos distintos."""


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "dentread-social/guiones"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def competidores(dias: int = 7) -> list[dict]:
    q = "(" + " OR ".join(f'"{c}"' for c in COMPETIDORES) + f") dental AI when:{dias}d"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})
    try:
        root = ET.fromstring(_get(url))
    except Exception as e:  # sin red o RSS caído: el guion sale con lo demás
        print(f"[guiones] competidores no disponibles: {e}", file=sys.stderr)
        return []
    out = []
    for it in root.iter("item"):
        try:
            fecha = parsedate_to_datetime(it.findtext("pubDate") or "").date().isoformat()
        except (TypeError, ValueError):
            fecha = ""
        out.append({"tipo": "competidor", "titulo": it.findtext("title") or "", "url": it.findtext("link") or "", "fecha": fecha})
    return out[:8]


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
    fuentes = noticias() + (competidores() if con_red else [])
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
            "guiones": ok[:3], "descartados": descartes, "fuentes": len(fuentes)}


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
