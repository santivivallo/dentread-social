"""
Registro de lo que el sistema decidió, para poder revisarlo después.

**Por qué existe.** Todo lo que este pipeline descarta se imprime y se pierde.
Los logs de una corrida de GitHub Actions se borran, así que la única memoria
de por qué NO se publicó algo era el archivo de ADA —y solo para noticias.

Eso tuvo un costo medido. Entre el 10 de agosto y el 15 de septiembre de 2026
se publicaron 10 posts y ninguno fue noticia ni paper, teniendo la mitad de
las ranuras reservadas para eso. El sistema avisaba en cada corrida
("SIN MATERIAL · sin resumen verificado") y nadie lo vio, porque para verlo
había que abrir 15 corridas viejas y compararlas. Un mes de feed
desbalanceado por falta de un archivo de 40 líneas.

Lo que se anota acá es lo que una revisión necesita y no puede reconstruir:

    candidato_descartado   qué fuente, qué id, por qué motivo
    post_generado          qué salió del generador
    publicado             qué llegó al feed, con su id de Instagram
    llamada_modelo        si respondió, con qué modelo y cuántos reintentos
    corrida               si la disparó el cron o una persona

Esa última es la que mide costo de verdad. Un sistema automático que necesita
que alguien lo empuje tres veces por semana no es automático, y esa
intervención no aparece en ninguna métrica técnica.

**No puede tirar abajo una publicación.** Es un archivo de auditoría: si falla
al escribirse, se ignora. Nunca al revés.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

RUTA = Path("data/bitacora.jsonl")

# JSONL y no JSON a propósito: se agrega una línea por evento sin leer ni
# reescribir el archivo. Dos escritores concurrentes (el bot y una corrida
# local) no pueden corromperse entre sí, y el merge en git es una unión de
# líneas —que acá sí es la semántica correcta, al revés que en el archivo de
# ADA, donde une por clave.


def anotar(evento: str, **datos) -> None:
    """Agrega un evento. Nunca levanta."""
    try:
        RUTA.parent.mkdir(parents=True, exist_ok=True)
        linea = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "evento": evento,
            # De dónde vino la corrida. En local no hay nada de esto y queda
            # como "local", que también es información: distingue lo que pasó
            # en producción de lo que pasó probando.
            "origen": os.environ.get("GITHUB_EVENT_NAME", "local"),
            "corrida": os.environ.get("GITHUB_RUN_ID", ""),
            **datos,
        }
        with RUTA.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(linea, ensure_ascii=False) + "\n")
    except Exception:
        pass          # un registro de auditoría no frena una publicación


def leer(desde: str | None = None) -> list[dict]:
    """
    Los eventos, opcionalmente desde una fecha ISO (YYYY-MM-DD).

    Las líneas ilegibles se saltan en silencio: el archivo lo escriben dos
    procesos y una línea a medio escribir no puede invalidar la revisión
    entera.
    """
    if not RUTA.exists():
        return []
    fuera = []
    for linea in RUTA.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            ev = json.loads(linea)
        except ValueError:
            continue
        if desde and str(ev.get("ts", ""))[:10] < desde:
            continue
        fuera.append(ev)
    return fuera
