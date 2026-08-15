"""
Un solo cliente de modelo, con el proveedor en variables de entorno.

**Por qué existe.** El endpoint estaba escrito a mano en `summarize.py` y otra
vez en `redaccion.py`, apuntando a GitHub Models. GitHub Models se retiró por
completo el 30 de julio de 2026 y empezó a devolver 410. Las dos features
—resúmenes de noticias y titulares de datos— dejaron de funcionar en silencio:
las dos están escritas para caer al formato de reserva cuando la llamada
falla, así que nada se rompió y nada avisó.

La lección no es "elegí mal el proveedor". Los proveedores gratuitos abren y
cierran; el que hoy anda va a cerrar también. La lección es que el endpoint no
puede vivir en el código, porque entonces cambiar de proveedor es un commit en
dos archivos en vez de un secreto.

    LLM_API_KEY     la clave (único dato obligatorio)
    LLM_ENDPOINT    por defecto, la capa compatible con OpenAI de Gemini
    LLM_MODEL       por defecto, un Flash

Cualquier proveedor con API compatible con OpenAI sirve cambiando esas tres:
Gemini, Groq, Cerebras, OpenRouter, Mistral. El sistema hace unas tres
llamadas por semana, así que entra de sobra en cualquier capa gratuita.

**Si no hay clave, esto devuelve None** y el pipeline sigue con los textos
curados. Nunca se cae una publicación por esto.
"""
from __future__ import annotations

import os

import requests

# Gemini expone una capa compatible con OpenAI, así que el mismo código sirve
# para casi cualquier proveedor con solo cambiar la variable.
ENDPOINT_POR_DEFECTO = ("https://generativelanguage.googleapis.com"
                        "/v1beta/openai/chat/completions")

# Los nombres de modelo cambian seguido y no conviene fijarlos en el código:
# este es solo el valor por defecto y se pisa con LLM_MODEL.
MODELO_POR_DEFECTO = "gemini-2.5-flash-lite"

TIMEOUT = 40


def endpoint() -> str:
    return os.environ.get("LLM_ENDPOINT") or ENDPOINT_POR_DEFECTO


def modelo() -> str:
    return os.environ.get("LLM_MODEL") or MODELO_POR_DEFECTO


def disponible() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


def pedir(reglas: str, contenido: str, *, json_mode: bool = False,
          temperatura: float = 0.3, max_tokens: int = 300) -> str | None:
    """
    Una llamada. Devuelve el texto o None, nunca levanta.

    None significa "seguí con el texto curado". Que esto no pueda tirar abajo
    una corrida es deliberado: el contenido de reserva siempre existe, así que
    un proveedor caído tiene que degradar la calidad, no la publicación.
    """
    clave = os.environ.get("LLM_API_KEY")
    if not clave:
        return None

    cuerpo = {
        "model": modelo(),
        "temperature": temperatura,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": reglas},
                     {"role": "user", "content": contenido}],
    }
    if json_mode:
        cuerpo["response_format"] = {"type": "json_object"}

    try:
        r = requests.post(endpoint(),
                          headers={"Authorization": f"Bearer {clave}",
                                   "Content-Type": "application/json"},
                          json=cuerpo, timeout=TIMEOUT)
        if not r.ok:
            # El cuerpo del error dice mucho más que el código: modelo
            # inexistente, cuota agotada, clave sin permisos. Se recorta y se
            # imprime, porque diagnosticar esto a ciegas costó una semana.
            detalle = (r.text or "")[:200].replace("\n", " ")
            print(f"   [info] el modelo respondió {r.status_code}: {detalle}")
            return None
        texto = r.json()["choices"][0]["message"]["content"].strip()
        return texto or None
    except (requests.RequestException, KeyError, ValueError, IndexError) as exc:
        print(f"   [info] falló la llamada al modelo "
              f"({exc.__class__.__name__}); se usa el texto curado")
        return None


def diagnostico() -> tuple[bool, str]:
    """¿Está configurado y responde? Para `tools/check_credentials`."""
    if not disponible():
        return False, "falta LLM_API_KEY"
    r = pedir("Respondé exactamente: ok", "ok", max_tokens=10)
    if r is None:
        return False, f"no responde ({modelo()} en {endpoint()})"
    return True, f"{modelo()} responde"
