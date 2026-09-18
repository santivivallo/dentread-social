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
import time

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

# Reintentos ante fallas de capacidad, no de programación.
#
# **Medido el 17 de septiembre de 2026.** Tres candidatos de noticia murieron
# en la misma corrida y dos con el mismo motivo:
#
#   [info] el modelo respondió 503: "This model is currently experiencing
#   high demand. Spikes in demand are usually temporary. Please try again…"
#
# El propio mensaje dice que es temporal y el código se daba por vencido al
# primer intento. Resultado: 0/1 posts, `pipeline.run` termina en rojo y el
# día se pierde. Nada estaba roto: el proveedor estaba ocupado quince
# segundos.
#
# Solo se reintenta lo que tiene sentido reintentar. Un 401 o un 404 de modelo
# inexistente no mejora esperando, y reintentarlos solo retrasa el
# diagnóstico. 429 y 5xx sí: son cola, no error.
REINTENTABLES = {429, 500, 502, 503, 504}
ESPERAS = (2, 6, 15)          # segundos; el sistema hace ~3 llamadas/semana

# Si el modelo sigue saturado, se prueba otro.
#
# Un 503 es capacidad DE ESE modelo, así que cambiarlo suele alcanzar donde
# esperar no alcanza. Se dejan en orden de preferencia y se saltan los que
# repitan el modelo configurado.
MODELOS_DE_RESERVA = ("gemini-2.5-flash", "gemini-2.0-flash",
                      "gemini-flash-lite-latest")


# Motivo del último fallo, para que quien diagnostica no tenga que ir a
# buscarlo entre la salida del pipeline. Se guarda acá, en el único lugar que
# sabe qué pasó de verdad.
ultimo_error: str = ""

# Si el proveedor ya se dio por muerto en esta corrida, no se insiste.
#
# El techo de tiempo importa: `redaccion` pide hasta 4 candidatos por post y
# el ciclo prueba hasta 3 posts. Reintentar cada llamada contra 4 modelos son
# ~90 s de espera, y multiplicado por una docena de llamadas se pasa de los 15
# minutos del workflow. Reintentar sirve contra un pico de demanda; contra un
# proveedor caído solo consume el presupuesto de la corrida.
#
# Así el costo de un proveedor caído es una espera de 90 s por corrida, no por
# llamada, y todo lo demás sale con el texto curado.
_agotado: bool = False


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
    global ultimo_error, _agotado
    ultimo_error = ""

    clave = os.environ.get("LLM_API_KEY")
    if not clave:
        ultimo_error = "falta LLM_API_KEY"
        return None

    if _agotado:
        ultimo_error = "el proveedor ya se dio por caído en esta corrida"
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

    # Modelos a probar: el configurado primero, las reservas después. Solo se
    # baja de modelo si el primero devuelve fallas de capacidad.
    candidatos = [modelo()] + [m for m in MODELOS_DE_RESERVA if m != modelo()]

    for n_modelo, nombre in enumerate(candidatos):
        cuerpo["model"] = nombre
        if n_modelo:
            print(f"   [info] se prueba con {nombre}")

        for intento in range(len(ESPERAS) + 1):
            r, exc = _llamar(cuerpo, clave)

            if exc is not None:
                # Timeout o corte de conexión: también es transitorio.
                ultimo_error = f"{exc.__class__.__name__}: {exc}"
                if intento < len(ESPERAS):
                    espera = ESPERAS[intento]
                    print(f"   [info] falló la llamada "
                          f"({exc.__class__.__name__}); se reintenta en "
                          f"{espera} s")
                    time.sleep(espera)
                    continue
                print(f"   [info] falló la llamada al modelo "
                      f"({exc.__class__.__name__}); se usa el texto curado")
                break

            if r.ok:
                try:
                    datos = r.json()
                except ValueError as err:
                    ultimo_error = f"respuesta no es JSON: {err}"
                    print(f"   [info] {ultimo_error}; se usa el texto curado")
                    return None
                texto, motivo = _texto_de(datos)
                if texto is None:
                    ultimo_error = motivo
                    print(f"   [info] {motivo}; se usa el texto curado")
                return texto

            # El cuerpo del error dice mucho más que el código: modelo
            # inexistente, cuota agotada, clave sin permisos. Se recorta y se
            # imprime, porque diagnosticar esto a ciegas costó una semana.
            detalle = (r.text or "")[:300].replace("\n", " ")
            ultimo_error = f"HTTP {r.status_code}: {detalle}"

            # `reasoning_effort` es reciente; si el proveedor lo rechaza, se
            # reintenta sin él antes de darse por vencido.
            if r.status_code == 400 and "reasoning_effort" in cuerpo:
                print(f"   [info] el proveedor rechaza reasoning_effort; "
                      f"se reintenta sin eso")
                del cuerpo["reasoning_effort"]
                continue

            if r.status_code in REINTENTABLES and intento < len(ESPERAS):
                # Si el proveedor dice cuánto esperar, se le cree.
                espera = _retry_after(r) or ESPERAS[intento]
                print(f"   [info] el modelo respondió {r.status_code} "
                      f"(saturado); se reintenta en {espera} s")
                time.sleep(espera)
                continue

            print(f"   [info] el modelo respondió {r.status_code}: "
                  f"{detalle[:160]}")
            if r.status_code in REINTENTABLES:
                break            # se agotaron los intentos: probar otro modelo
            return None          # 401, 404: esperar no lo arregla

    # Todos los modelos saturados o inalcanzables: el resto de la corrida sale
    # con el texto curado, sin volver a pagar la espera.
    _agotado = True
    print("   [info] el proveedor no responde con ningún modelo; el resto de "
          "la corrida usa el texto curado")
    return None


def _llamar(cuerpo: dict, clave: str):
    """Una sola llamada. Devuelve (respuesta, None) o (None, excepción)."""
    try:
        return requests.post(endpoint(),
                             headers={"Authorization": f"Bearer {clave}",
                                      "Content-Type": "application/json"},
                             json=cuerpo, timeout=TIMEOUT), None
    except requests.RequestException as exc:
        return None, exc


def _retry_after(r) -> int | None:
    """Los segundos que pide el proveedor, si los pide y son razonables."""
    try:
        segundos = int(float(r.headers.get("Retry-After", "")))
    except (TypeError, ValueError):
        return None
    # Un Retry-After de media hora no sirve: la corrida tiene 15 minutos de
    # techo. En ese caso conviene bajar de modelo.
    return segundos if 0 < segundos <= 30 else None


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
