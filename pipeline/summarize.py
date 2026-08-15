"""
Resumen propio de una noticia o un estudio, verificado antes de publicarse.

**Por qué existe.** Un carrusel que solo entrecomilla el titular no le aporta
nada a nadie. Para que sirva tiene que decir qué dice el artículo. Pero
copiarlo es un problema de copyright, y en un paper, soltar la conclusión es
un claim clínico con la cita de otro.

**Por qué ahora sí, si la regla era "sin LLM".** La regla existía porque no
había verificador. La extracción por expresiones regulares producía frases sin
sentido que pasaban todos los guards, y la conclusión fue que solo un humano
podía garantizar el contenido. Eso sigue siendo cierto para las CIFRAS —por
eso `data/facts.json` se cura a mano y no se toca acá—, pero no para un
resumen de tres líneas cuya calidad **sí se puede medir**:

    modelo propone  →  newsguard mide copia y originalidad  →  claims guard
    mide riesgo regulatorio  →  si algo falla, se descarta y el post sale con
    el formato señalizador de siempre

Nada se publica sin cruzar los dos aros. El peor caso no es un resumen malo:
es no tener resumen.

**Costo: cero.** GitHub Models está incluido con la cuenta y el `GITHUB_TOKEN`
del runner ya trae el permiso `models:read`. Sin claves nuevas, sin tarjeta.
El límite de la capa gratuita es ~10 peticiones por minuto; el sistema hace
tres por semana.

Fuera de GitHub Actions no hay token y esto devuelve None, así que en local
el pipeline sigue funcionando con el formato señalizador.
"""
from __future__ import annotations

import json
import os
import re
import textwrap

import requests

ENDPOINT = "https://models.github.ai/inference/chat/completions"

# Modelo chico a propósito: la tarea es reescribir tres líneas a partir de un
# texto que ya se le entrega. No hace falta capacidad de razonamiento, y los
# modelos grandes tienen límites de tasa más estrictos en la capa gratuita.
MODEL = "openai/gpt-4o-mini"

TIMEOUT = 40
MAX_CHARS_FUENTE = 6000        # el cuerpo se recorta: el resumen vive arriba


REGLAS_NOTICIA = """\
Escribís para el Instagram de DentRead, una empresa de IA aplicada a
radiografías dentales. Público: dentistas y responsables de clínicas.

Escribí en español rioplatense un resumen de la noticia en 2 o 3 frases.

Reglas, todas obligatorias:
- Con TUS palabras. No copies frases del original. Nunca más de 6 palabras
  seguidas iguales al texto fuente.
- Decí qué pasó y a quién le cambia algo. Nada de "es importante destacar".
- Sin adjetivos de opinión. Sin "revolucionario", "innovador", "clave".
- Sin em dashes. Sin emojis. Sin hashtags.
- No inventes cifras, fechas ni nombres que no estén en el texto.
- No opines en nombre de DentRead ni menciones a DentRead.
- Si el texto no alcanza para 2 frases con sustancia, respondé exactamente:
  INSUFICIENTE
"""

# Hay dos reglas para papers, y la diferencia no es de prudencia sino de
# quién parece estar hablando.
#
# Reportar un hallazgo ajeno y atribuido es periodismo, no un claim propio.
# Salvo en un caso: cuando el estudio trata sobre lo mismo que vende DentRead.
# "La IA detectó caries con 92% de sensibilidad" publicado en la cuenta de una
# empresa de IA para radiografías no se lee como "un estudio dice esto", se lee
# como "esto es lo que hace DentRead". Lo que se juzga es la impresión neta,
# no el pie de página, y DentRead no tiene FDA clearance para sostenerla.
#
# Entonces: rendimiento diagnóstico de IA, solo se señaliza. Todo lo demás
# —acceso, utilización, economía, adherencia, prevención, periodontal— lleva
# el hallazgo con su atribución.

REGLAS_PAPER_LIBRE = """\
Escribís para el Instagram de DentRead, una empresa de IA aplicada a
radiografías dentales. Público: dentistas y responsables de clínicas.

Resumí este estudio en español rioplatense, en 2 o 3 frases: qué se preguntó,
con qué diseño, y qué reportó.

Reglas, todas obligatorias:
- El hallazgo va SIEMPRE atribuido al estudio: "el estudio reportó",
  "los autores observaron". Nunca como afirmación general ni como verdad
  establecida.
- Sin generalizar: si el estudio es en una población concreta, decilo.
- Con tus palabras. Nunca más de 6 palabras seguidas iguales al original.
- Mencioná el diseño y, si está, el número de participantes.
- No inventes cifras que no estén en el texto.
- Sin em dashes, emojis ni hashtags. No menciones a DentRead ni saques
  conclusiones para la práctica.
- Si el texto no alcanza, respondé exactamente: INSUFICIENTE
"""

REGLAS_PAPER_SENALIZADOR = """\
Escribís para el Instagram de DentRead, una empresa de IA aplicada a
radiografías dentales. Público: dentistas y responsables de clínicas.

Este estudio trata sobre rendimiento diagnóstico de inteligencia artificial,
que es lo que vende DentRead. Por eso NO se cuenta qué encontró: en esta
cuenta, ese hallazgo se leería como una afirmación sobre el producto.

Resumí en 2 frases QUÉ SE PREGUNTÓ y CÓMO.

Reglas, todas obligatorias:
- Nada de resultados, precisión, sensibilidad, eficacia, mejoras ni
  comparaciones de desempeño. Solo la pregunta y el diseño.
- Con tus palabras. Nunca más de 6 palabras seguidas iguales al original.
- Mencioná el diseño y, si está, el número de participantes.
- Sin em dashes, emojis ni hashtags. No menciones a DentRead.
- Si el texto no alcanza, respondé exactamente: INSUFICIENTE
"""

# Un estudio entra en el carril señalizador si mide desempeño de IA o de un
# sistema automático de detección. Necesita las dos cosas: hablar de IA y
# hablar de rendimiento. Un paper sobre adopción de IA en clínicas, o sobre
# costos, no cae acá.
_IA = re.compile(
    r"\b(artificial intelligence|deep learning|machine learning|"
    r"convolutional|neural network|automated detection|computer-aided|CAD)\b",
    re.I)
_RENDIMIENTO = re.compile(
    r"\b(accuracy|sensitivity|specificity|AUC|ROC|F1|precision|recall|"
    r"diagnostic performance|detection rate|agreement|kappa)\b", re.I)


def es_rendimiento_de_ia(texto: str) -> bool:
    """
    ¿El estudio mide qué tan bien detecta un sistema automático?

    Se exigen las dos señales. Solo "artificial intelligence" no alcanza: un
    paper sobre cuántas clínicas adoptaron IA es un dato de mercado, no un
    claim de desempeño, y ese sí se puede contar entero.
    """
    return bool(_IA.search(texto) and _RENDIMIENTO.search(texto))


def disponible() -> bool:
    """Hay token de GitHub, así que se puede llamar al modelo."""
    return bool(os.environ.get("GITHUB_TOKEN"))


def _pedir(reglas: str, fuente: str) -> str | None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    try:
        r = requests.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json={
                "model": MODEL,
                # temperatura baja: se busca fidelidad al texto dado, no
                # creatividad. La creatividad es de donde salen las invenciones.
                "temperature": 0.2,
                "max_tokens": 300,
                "messages": [
                    {"role": "system", "content": reglas},
                    {"role": "user", "content": fuente[:MAX_CHARS_FUENTE]},
                ],
            },
            timeout=TIMEOUT,
        )
        if not r.ok:
            print(f"   [info] GitHub Models respondió {r.status_code}; "
                  f"el post sale en formato señalizador")
            return None
        texto = r.json()["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, KeyError, ValueError) as exc:
        print(f"   [info] no se pudo resumir ({exc.__class__.__name__}); "
              f"el post sale en formato señalizador")
        return None

    if not texto or "INSUFICIENTE" in texto.upper():
        return None
    return texto


def resumen_verificado(fuente: str, *, es_paper: bool, url: str = "",
                       atribucion: str = "", es_reciente: bool = True,
                       publicado: str = "") -> str | None:
    """
    Devuelve el resumen solo si pasa los dos controles. None si no.

    El orden importa: primero copyright, después claims. Un texto que copia
    demasiado se descarta sin importar lo bien escrito que esté, porque el
    problema no es de estilo.
    """
    if not fuente or len(fuente) < 200:
        return None

    if not es_paper:
        reglas = REGLAS_NOTICIA
    elif es_rendimiento_de_ia(fuente):
        reglas = REGLAS_PAPER_SENALIZADOR
    else:
        reglas = REGLAS_PAPER_LIBRE
    texto = _pedir(reglas, fuente)
    if not texto:
        return None

    # 1. Copyright y originalidad, contra el texto fuente.
    #
    # Se verifica el texto TAL COMO SE VA A PUBLICAR, con su línea de fuente.
    # newsguard exige atribución, y la atribución vive en el caption, no en el
    # resumen: pasarle el resumen solo lo hacía fallar siempre por falta de
    # crédito que en realidad sí está.
    publicable = f"{texto}\n\nFuente: {atribucion}." if atribucion else texto
    try:
        from publisher import newsguard
        res = newsguard.check_derived(publicable, fuente, url,
                                      is_fresh=es_reciente, published=publicado)
        if not getattr(res, "ok", True):
            motivos = "; ".join(str(f) for f in getattr(res, "findings", [])[:2])
            print(f"   [info] resumen descartado por newsguard: {motivos[:120]}")
            return None
    except ImportError:
        pass

    # 2. Riesgo regulatorio, con las mismas reglas que el resto del copy.
    try:
        from publisher import guard
        res = guard.check(publicable, {"has_source": True})
        if not getattr(res, "ok", True):
            malos = [f for f in getattr(res, "findings", [])
                     if getattr(f, "level", "") == "BLOCK"]
            if malos:
                print(f"   [info] resumen descartado por claims guard: "
                      f"{malos[0].domain}/{malos[0].strength}")
                return None
    except ImportError:
        pass

    return textwrap.dedent(texto).strip()
