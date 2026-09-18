#!/usr/bin/env python3
"""
Que una saturación temporal del proveedor no se lleve el post del día.

**El fallo que esto habría evitado.** El 17 de septiembre de 2026 la corrida
terminó en 0/1 posts. Tres candidatos de noticia murieron y dos con el mismo
motivo, textual en el log:

    [info] el modelo respondió 503: "This model is currently experiencing
    high demand. Spikes in demand are usually temporary. Please try again…"

El mensaje del proveedor dice que es temporal. El código se daba por vencido
al primer intento, `generate` levantaba `SinMaterial` por falta de resumen, el
ciclo bajaba de fuente, y con los tres candidatos caídos `pipeline.run` salía
con código 1. Nada estaba roto: el modelo estuvo ocupado unos segundos.

Es el peor tipo de falla para diagnosticar porque el sistema se comporta
exactamente como cuando NO hay material: mismo mensaje, mismo resultado. La
diferencia entre "no hay nada que publicar" y "el proveedor estaba ocupado"
tiene que estar en el código, no en el ojo de quien lee el log.

Se prueba sin red: se sustituye `requests.post` y se mide QUÉ decide el
cliente ante cada código.

    python -m tests.test_llm
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from pipeline import bitacora, llm

# Un test no escribe en la bitácora real: sus 8 llamadas falsas ensuciarían
# la revisión quincenal, que cuenta exactamente eso para saber si el
# proveedor está rindiendo.
bitacora.RUTA = Path(tempfile.gettempdir()) / "bitacora-de-prueba.jsonl"


class Respuesta:
    """Lo mínimo de `requests.Response` que usa el cliente."""

    def __init__(self, status: int, texto: str = "", headers: dict | None = None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self.text = texto or ("{}" if self.ok else f'{{"error": {status}}}')
        self.headers = headers or {}

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "texto del modelo"},
                             "finish_reason": "stop"}]}


def _con_respuestas(secuencia: list[Respuesta]):
    """
    Reemplaza la red por una lista de respuestas y registra qué se pidió.

    Devuelve (llamar, registro): el registro guarda el modelo de cada intento,
    que es como se verifica que se bajó de modelo y no que se repitió el mismo.
    """
    registro: list[str] = []
    pendientes = list(secuencia)

    def falso_post(url, headers=None, json=None, timeout=None):
        registro.append(json["model"])
        return pendientes.pop(0) if pendientes else Respuesta(503)

    return falso_post, registro


def _correr(secuencia: list[Respuesta]) -> tuple[str | None, list[str], list[int]]:
    """Corre `pedir` contra esas respuestas. Devuelve (texto, modelos, esperas)."""
    esperas: list[int] = []
    post_real, sleep_real = llm.requests.post, llm.time.sleep
    clave_real = llm.os.environ.get("LLM_API_KEY")

    falso_post, registro = _con_respuestas(secuencia)
    llm.requests.post = falso_post
    llm._agotado = False       # cada caso arranca con el proveedor vivo
    llm.time.sleep = lambda s: esperas.append(s)
    llm.os.environ["LLM_API_KEY"] = "clave-de-prueba"
    try:
        texto = llm.pedir("reglas", "contenido")
    finally:
        llm.requests.post, llm.time.sleep = post_real, sleep_real
        if clave_real is None:
            llm.os.environ.pop("LLM_API_KEY", None)
        else:
            llm.os.environ["LLM_API_KEY"] = clave_real
    return texto, registro, esperas


def probar_503_transitorio() -> list[str]:
    """Dos 503 y después un 200: tiene que devolver el texto, no None."""
    texto, modelos, esperas = _correr(
        [Respuesta(503), Respuesta(503), Respuesta(200)])
    errs = []
    if texto != "texto del modelo":
        errs.append(f"un 503 transitorio pierde el post: devolvió {texto!r} "
                    f"después de {len(modelos)} intento(s)")
    if len(modelos) != 3:
        errs.append(f"se esperaban 3 intentos y hubo {len(modelos)}")
    if esperas != [llm.ESPERAS[0], llm.ESPERAS[1]]:
        errs.append(f"las esperas no escalan: {esperas}")
    if len(set(modelos)) != 1:
        errs.append(f"cambió de modelo antes de agotar los reintentos: "
                    f"{modelos}")
    return errs


def probar_baja_de_modelo() -> list[str]:
    """
    Si el modelo sigue saturado, se prueba otro.

    Un 503 es capacidad de ESE modelo: cambiarlo alcanza donde esperar no.
    """
    # Cuatro 503 agotan los reintentos del primer modelo; el quinto responde.
    texto, modelos, _ = _correr(
        [Respuesta(503)] * 4 + [Respuesta(200)])
    errs = []
    if texto != "texto del modelo":
        errs.append("con el modelo principal saturado no se prueba otro: "
                    f"devolvió {texto!r}")
    if len(set(modelos)) < 2:
        errs.append(f"no bajó de modelo: {modelos}")
    return errs


def probar_error_permanente() -> list[str]:
    """
    Un 401 o un 404 no se reintenta: esperar no lo arregla.

    Reintentar un error de configuración solo retrasa el diagnóstico, que es
    justo lo que hizo perder una semana con el 410 de GitHub Models.
    """
    errs = []
    for codigo in (401, 404):
        texto, modelos, esperas = _correr([Respuesta(codigo)])
        if texto is not None:
            errs.append(f"un {codigo} devolvió texto")
        if len(modelos) != 1:
            errs.append(f"un {codigo} se reintentó {len(modelos)} veces")
        if esperas:
            errs.append(f"un {codigo} durmió {esperas}")
    return errs


def probar_reasoning_effort() -> list[str]:
    """
    Un 400 por `reasoning_effort` se reintenta sin ese campo, sin esperar.

    El campo es reciente y no todos los proveedores lo conocen. Esto ya
    existía; se mide para que el reintento nuevo no lo haya tapado.
    """
    texto, modelos, esperas = _correr([Respuesta(400), Respuesta(200)])
    errs = []
    if texto != "texto del modelo":
        errs.append("un 400 por reasoning_effort ya no se reintenta sin el "
                    "campo")
    if esperas:
        errs.append(f"esperó de gusto ante un 400: {esperas}")
    if len(modelos) != 2 or len(set(modelos)) != 1:
        errs.append(f"el reintento sin reasoning_effort cambió de modelo: "
                    f"{modelos}")
    return errs


def probar_corte_tras_agotarse() -> list[str]:
    """
    Con el proveedor caído, la segunda llamada no vuelve a pagar la espera.

    `redaccion` pide hasta 4 candidatos por post y el ciclo prueba hasta 3
    posts: reintentar cada llamada contra cuatro modelos son ~90 s, y por una
    docena de llamadas se pasa de los 15 minutos del workflow. El reintento
    sirve contra un pico de demanda; contra un proveedor caído solo consume el
    presupuesto de la corrida.
    """
    esperas: list[int] = []
    post_real, sleep_real = llm.requests.post, llm.time.sleep
    clave_real = llm.os.environ.get("LLM_API_KEY")
    llamadas: list[str] = []

    def siempre_503(url, headers=None, json=None, timeout=None):
        llamadas.append(json["model"])
        return Respuesta(503)

    llm.requests.post = siempre_503
    llm.time.sleep = lambda s: esperas.append(s)
    llm.os.environ["LLM_API_KEY"] = "clave-de-prueba"
    llm._agotado = False
    try:
        llm.pedir("reglas", "contenido")          # paga la espera completa
        n_primera = len(llamadas)
        llm.pedir("reglas", "contenido")          # esta ya no debería llamar
        n_segunda = len(llamadas) - n_primera
    finally:
        llm.requests.post, llm.time.sleep = post_real, sleep_real
        llm._agotado = False
        if clave_real is None:
            llm.os.environ.pop("LLM_API_KEY", None)
        else:
            llm.os.environ["LLM_API_KEY"] = clave_real

    errs = []
    if n_segunda:
        errs.append(f"con el proveedor caído la segunda llamada igual hizo "
                    f"{n_segunda} intento(s): la corrida se come el reloj")
    if sum(esperas) > 120:
        errs.append(f"la espera total de una llamada es {sum(esperas)} s: "
                    f"demasiado para un techo de 15 minutos")
    return errs


def probar_sin_clave() -> list[str]:
    """Sin clave no se llama a nadie: se usa el texto curado."""
    clave_real = llm.os.environ.pop("LLM_API_KEY", None)
    llamadas: list[str] = []
    post_real = llm.requests.post
    llm.requests.post = lambda *a, **k: llamadas.append("red") or Respuesta(200)
    try:
        texto = llm.pedir("reglas", "contenido")
    finally:
        llm.requests.post = post_real
        if clave_real is not None:
            llm.os.environ["LLM_API_KEY"] = clave_real
    if texto is not None:
        return ["sin clave devolvió texto"]
    if llamadas:
        return ["sin clave igual salió a la red"]
    return []


def main() -> int:
    errores = (probar_503_transitorio() + probar_baja_de_modelo()
               + probar_error_permanente() + probar_reasoning_effort()
               + probar_corte_tras_agotarse() + probar_sin_clave())
    if errores:
        print("✗ el cliente del modelo no aguanta una saturación:\n")
        print("\n".join(f"  {e}" for e in errores))
        return 1
    print("✓ 503 y timeouts se reintentan con espera creciente, se baja de "
          "modelo si persiste, y 401/404 cortan de una")
    return 0


if __name__ == "__main__":
    sys.exit(main())
