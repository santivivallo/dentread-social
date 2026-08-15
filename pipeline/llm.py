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

# El .env se lee acá, en el único módulo que mira la clave.
#
# Sin esto, `LLM_API_KEY` en el .env no llegaba a `os.environ` y el sistema
# informaba "falta la clave" con la clave puesta. Ya había pasado igual en
# `readiness.py`, que reportaba las 14 variables sin configurar por el mismo
# motivo: un diagnóstico que miente es peor que uno que falta, porque manda a
# buscar el problema al lado equivocado.
#
# `load_dotenv()` no pisa lo que ya está en el entorno, así que en GitHub
# Actions siguen mandando los secrets del workflow.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:      # el .env es una comodidad local, no un requisito
    pass

# Gemini expone una capa compatible con OpenAI, así que el mismo código sirve
# para casi cualquier proveedor con solo cambiar la variable.
ENDPOINT_POR_DEFECTO = ("https://generativelanguage.googleapis.com"
                        "/v1beta/openai/chat/completions")

# Los nombres de modelo cambian seguido, y fijar uno ya falló: el primer
# intento apuntaba a `gemini-2.5-flash-lite`, que devolvía
# "no longer available to new users".
#
# Por eso el valor por defecto es un alias. Google desaconseja los alias
# `-latest` en producción porque cambian de versión sin aviso, y para un
# sistema que le pide precisión a un modelo eso importaría. Acá no: la tarea
# es escribir tres frases y TODO lo que escribe pasa por un verificador antes
# de publicarse. Entre un alias que puede cambiar de versión y un nombre fijo
# que caduca en silencio, el alias falla mejor. Igual se puede fijar una
# versión exacta con LLM_MODEL.
MODELO_POR_DEFECTO = "gemini-flash-latest"

TIMEOUT = 40


def endpoint() -> str:
    return os.environ.get("LLM_ENDPOINT") or ENDPOINT_POR_DEFECTO


def modelo() -> str:
    return os.environ.get("LLM_MODEL") or MODELO_POR_DEFECTO


def disponible() -> bool:
    return bool(os.environ.get("LLM_API_KEY"))


def _texto_de(datos: dict) -> tuple[str | None, str]:
    """
    Saca el texto de la respuesta sin asumir su forma. Devuelve (texto, motivo).

    Antes esto era `datos["choices"][0]["message"]["content"]` y un KeyError
    pelado, que no dice nada. Los modelos Flash actuales razonan antes de
    responder y los tokens de razonamiento salen del mismo presupuesto: con un
    tope bajo, la respuesta llega SIN campo `content` y con
    `finish_reason: length`. La llamada "falla" habiendo funcionado, y el
    mensaje de error manda a mirar la clave o el nombre del modelo.
    """
    opciones = datos.get("choices") or []
    if not opciones:
        return None, f"la respuesta no trae 'choices' (claves: {list(datos)})"

    primera = opciones[0]
    mensaje = primera.get("message") or {}
    texto = (mensaje.get("content") or "").strip()
    if texto:
        return texto, ""

    razon = primera.get("finish_reason", "?")
    if razon == "length":
        return None, ("se acabó el presupuesto de tokens antes de la "
                      "respuesta: subir max_tokens o bajar el razonamiento")
    if mensaje.get("reasoning_content"):
        return None, "el modelo razonó pero no escribió respuesta"
    return None, f"respuesta vacía (finish_reason={razon})"


def pedir(reglas: str, contenido: str, *, json_mode: bool = False,
          temperatura: float = 0.3, max_tokens: int = 1500) -> str | None:
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
        # Escribir tres frases a partir de un texto dado no necesita cadena de
        # razonamiento, y en los Flash actuales el razonamiento se descuenta
        # del mismo presupuesto que la respuesta. Los proveedores que no
        # conocen este campo lo ignoran.
        "reasoning_effort": "none",
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
            # `reasoning_effort` es reciente; si el proveedor lo rechaza, se
            # reintenta sin él antes de darse por vencido.
            if r.status_code == 400 and "reasoning_effort" in cuerpo:
                del cuerpo["reasoning_effort"]
                r = requests.post(endpoint(),
                                  headers={"Authorization": f"Bearer {clave}",
                                           "Content-Type": "application/json"},
                                  json=cuerpo, timeout=TIMEOUT)
                if not r.ok:
                    return None
            else:
                return None

        texto, motivo = _texto_de(r.json())
        if texto is None:
            print(f"   [info] {motivo}; se usa el texto curado")
        return texto
    except (requests.RequestException, ValueError) as exc:
        print(f"   [info] falló la llamada al modelo "
              f"({exc.__class__.__name__}); se usa el texto curado")
        return None


def modelos_disponibles(limite: int = 12) -> list[str]:
    """
    Qué modelos acepta esta clave, preguntándoselo al proveedor.

    Existe porque un nombre de modelo caduca sin aviso y el error que devuelve
    la API no dice cuál usar en su lugar. Sin esto, la única salida era buscar
    la documentación a mano y adivinar de nuevo.

    Usa el `/models` de la API compatible con OpenAI, que es el mismo camino
    en Gemini, Groq, OpenRouter y Cerebras.
    """
    clave = os.environ.get("LLM_API_KEY")
    if not clave:
        return []
    url = endpoint().replace("/chat/completions", "/models")
    try:
        r = requests.get(url, headers={"Authorization": f"Bearer {clave}"},
                         timeout=TIMEOUT)
        if not r.ok:
            return []
        ids = [m.get("id", "") for m in r.json().get("data", [])]
    except (requests.RequestException, KeyError, ValueError):
        return []

    # Los "flash" y similares primero: son los chicos y rápidos, que es lo que
    # pide esta tarea. Se le saca el prefijo "models/" que agrega Gemini.
    ids = [i.split("/")[-1] for i in ids if i]
    livianos = [i for i in ids if any(p in i for p in ("flash", "lite", "mini",
                                                       "8b", "instant"))]
    return (livianos or ids)[:limite]


def diagnostico() -> tuple[bool, str]:
    """¿Está configurado y responde? Para `tools/check_credentials`."""
    if not disponible():
        return False, "falta LLM_API_KEY"
    r = pedir("Respondé exactamente: ok", "ok", max_tokens=10)
    if r is None:
        return False, f"no responde ({modelo()} en {endpoint()})"
    return True, f"{modelo()} responde"
