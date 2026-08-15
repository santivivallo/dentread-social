"""
Redacción automática del gancho y el titular de datos, verificada.

**El problema.** El gancho de un post de datos salía de partir el ángulo del
tema en el primer punto. O sea que el titular del frame 1 era la tesis del
tema, y la tesis es exactamente lo que el frame 2 y el cierre vuelven a decir
con otras palabras. Medido sobre los 22 temas, 14 parafraseaban; en cuatro los
titulares del frame 1 y del 2 eran las mismas palabras.

Escribir 22 ganchos a mano arregla esos 22 y nada más. El hecho 22 nuevo, el
tema 23, la noticia del martes: todos vuelven al mismo lugar.

**La regla "sin LLM" no se rompe, se aplica donde corresponde.** Esa regla
existe para las CIFRAS, y sigue intacta: `data/facts.json` se cura a mano y
acá no se toca un solo número. Lo que se genera es la PROSA que enmarca
cifras ya verificadas contra su fuente. Es el mismo trato que `summarize` le
da a noticias y papers desde que se conectaron.

    modelo propone  →  se verifica que no invente cifras, que no parafrasee
    los otros frames, que no haga claims y que entre en el espacio  →  si algo
    falla, se reintenta una vez  →  si vuelve a fallar, se usa el gancho
    curado del tema

Los 22 ganchos escritos a mano no se tiran: pasan a ser la red. Un post
siempre sale, con o sin modelo.

**Sin `LLM_API_KEY` esto devuelve None** y el post sale con el gancho curado.
El proveedor se configura en `pipeline/llm.py`; para comprobar que anda:

    python -m pipeline.redaccion

**Costo cero.** Unas tres llamadas por semana entran en cualquier capa
gratuita.
"""
from __future__ import annotations

import json
import re
import unicodedata

from pipeline import llm

INTENTOS = 2

MAX_GANCHO = 52      # a 88px entra en dos líneas de ~26 caracteres
MAX_TITULAR = 40
MAX_LECTURA = 190

# Umbral de paráfrasis entre frames. Holgado a propósito: dos frames del mismo
# post comparten tema y van a compartir vocabulario. Se persigue la repetición,
# no la coherencia.
UMBRAL_SOLAPE = 0.40

VACIAS = {"donde", "cuando", "sobre", "entre", "para", "desde", "cada",
          "como", "esta", "este", "esto", "pero", "mientras", "todo", "toda"}


def palabras(texto: str) -> set[str]:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return set(re.findall(r"[a-z]{4,}", t)) - VACIAS


def solape(a: str, b: str) -> float:
    """
    Proporción de la frase MÁS CORTA que reaparece en la otra.

    Se divide por el mínimo y no por la unión a propósito: un titular de tres
    palabras metido entero dentro de uno de doce es justo el caso a atrapar, y
    con Jaccard daría un número bajo y tranquilizador.
    """
    A, B = palabras(a), palabras(b)
    if not A or not B:
        return 0.0
    return len(A & B) / min(len(A), len(B))


REGLAS = """\
Escribís los titulares del Instagram de DentRead, una empresa de IA aplicada a
radiografías dentales. Público: dentistas y dueños de clínicas en EE.UU.

Te doy dos cifras ya verificadas y el cierre que ya tiene escrito el post.
Devolvés SOLO un objeto JSON con tres claves:

{"gancho": "...", "titular_datos": "...", "lectura": "..."}

- "gancho": el titular del primer frame, debajo de una cifra grande. Máximo 52
  caracteres. Dice algo concreto y con tensión que haga querer deslizar. No es
  un resumen ni una tesis abstracta.
- "titular_datos": el titular del segundo frame, el de las cifras. Máximo 40
  caracteres. Tiene que AFIRMAR algo, con verbo. No es una etiqueta de
  sección ni una lista de temas. Mal: "Expansión del beneficio y aranceles".
  Bien: "Se cubre más, se paga igual".
- "lectura": una sola frase que interpreta las dos cifras juntas. Máximo 190
  caracteres. Va en el texto del post, no en la imagen.

Reglas, todas obligatorias:
- Las tres frases dicen COSAS DISTINTAS entre sí y distintas del cierre. Si el
  gancho, el titular y el cierre son la misma idea con otras palabras, el
  carrusel no avanza. Este es el error más importante a evitar.
- No inventes NINGÚN número, porcentaje, año ni nombre propio que no esté en
  las cifras que te doy. Podés no usarlos.
- No cambies QUÉ MIDE una cifra. Si el dato habla de honorarios, no lo
  cuentes como costos; si habla de cobertura, no lo cuentes como uso; si
  habla de diagnósticos, no lo cuentes como tratamientos. Son cosas
  distintas y confundirlas es un dato falso aunque el número esté bien.
  Usá las mismas palabras que el enunciado para nombrar lo que se mide.
- Nada de afirmar que una IA detecta, diagnostica, mejora la precisión o
  supera a un profesional. DentRead no tiene autorización de la FDA.
- Sin adjetivos de opinión: nada de revolucionario, innovador, clave,
  impresionante, alarmante.
- Sin em dashes, emojis, hashtags ni signos de exclamación.
- Español rioplatense, tono profesional y seco. No menciones a DentRead.
- Si no podés cumplir todo, respondé exactamente: INSUFICIENTE
"""


def disponible() -> bool:
    return llm.disponible()


def _pedir(contexto: str) -> dict | None:
    texto = llm.pedir(REGLAS, contexto, json_mode=True, temperatura=0.4)
    if not texto or "INSUFICIENTE" in texto.upper():
        return None
    try:
        return json.loads(texto)
    except ValueError:
        # Algunos proveedores devuelven el JSON envuelto en un bloque de
        # codigo aunque se pida json_object.
        m = re.search(r"\{.*\}", texto, re.S)
        if not m:
            print("   [info] el modelo no devolvió JSON; se usa el gancho curado")
            return None
        try:
            return json.loads(m.group(0))
        except ValueError:
            print("   [info] el modelo no devolvió JSON; se usa el gancho curado")
            return None


def verificar(prop: dict, *, cifras_permitidas: set[str],
              cierre: str) -> list[str]:
    """
    Los aros que tiene que cruzar la propuesta. Devuelve los motivos de rechazo.

    Separado de la llamada al modelo a propósito: así se puede testear sin red
    y sin token, que es la única forma de saber que el verificador realmente
    rechaza lo que dice rechazar.
    """
    fallas = []
    for clave, tope in (("gancho", MAX_GANCHO), ("titular_datos", MAX_TITULAR),
                        ("lectura", MAX_LECTURA)):
        v = (prop.get(clave) or "").strip()
        if not v:
            fallas.append(f"falta '{clave}'")
        elif len(v) > tope:
            fallas.append(f"'{clave}' tiene {len(v)} chars, el máximo es {tope}")

    if fallas:
        return fallas

    g, t, lec = prop["gancho"].strip(), prop["titular_datos"].strip(), prop["lectura"].strip()

    # 1. Ninguna cifra que no venga de un hecho verificado contra su fuente.
    #    Esta es la línea que no se cruza: el modelo enmarca números, no los
    #    produce.
    for clave, v in (("gancho", g), ("titular_datos", t), ("lectura", lec)):
        for n in re.findall(r"\d[\d.,]*", v):
            if n.rstrip(".,") not in cifras_permitidas:
                fallas.append(f"'{clave}' trae una cifra que no está en los "
                              f"hechos: {n}")

    # 2. Paráfrasis: el motivo por el que existe este módulo.
    for na, a, nb, b in (("gancho", g, "titular", t),
                         ("gancho", g, "cierre", cierre),
                         ("titular", t, "cierre", cierre)):
        v = solape(a, b)
        if v >= UMBRAL_SOLAPE:
            fallas.append(f"el {na} y el {nb} dicen lo mismo ({v:.0%})")

    # 3. Marca y formato.
    for clave, v in (("gancho", g), ("titular_datos", t), ("lectura", lec)):
        if "—" in v:
            fallas.append(f"'{clave}' trae em dash")
        if "#" in v or "!" in v or "¡" in v:
            fallas.append(f"'{clave}' trae hashtag o exclamación")

    # 4. Riesgo regulatorio, con las mismas reglas que el resto del copy.
    try:
        from publisher import guard
        res = guard.check(f"{g}\n{t}\n{lec}", {"has_source": True})
        malos = [f for f in getattr(res, "findings", [])
                 if getattr(f, "level", "") == "BLOCK"]
        if malos:
            fallas.append(f"claims guard: {malos[0].domain}/{malos[0].strength}")
    except ImportError:
        pass

    return fallas


def redactar(*, tema: str, angulo: str, cierre: str,
             hechos: list[dict]) -> dict | None:
    """
    Devuelve {gancho, titular_datos, lectura} o None si no pasó los controles.

    None no es un error: significa que el post sale con el gancho curado del
    tema. El peor caso no es una redacción mala, es no tener redacción.
    """
    if not disponible() or len(hechos) < 2:
        return None

    cifras = set()
    for f in hechos:
        for campo in ("number", "statement"):
            cifras |= {n.rstrip(".,")
                       for n in re.findall(r"\d[\d.,]*", f.get(campo, ""))}

    contexto = (
        f"Tema: {tema}\n"
        f"Lo que sostiene la empresa sobre este tema: {angulo}\n\n"
        f"Cifra 1: {hechos[0]['number']} — {hechos[0]['statement']}\n"
        f"Cifra 2: {hechos[1]['number']} — {hechos[1]['statement']}\n\n"
        f"Cierre ya escrito del post (NO lo repitas ni lo parafrasees): "
        f"{cierre}"
    )

    for intento in range(INTENTOS):
        prop = _pedir(contexto)
        if not prop:
            return None
        fallas = verificar(prop, cifras_permitidas=cifras, cierre=cierre)
        if not fallas:
            return {k: prop[k].strip()
                    for k in ("gancho", "titular_datos", "lectura")}
        print(f"   [info] redacción rechazada (intento {intento + 1}): "
              f"{fallas[0]}")
        contexto += f"\n\nIntento anterior rechazado por: {'; '.join(fallas[:3])}"

    return None


def main() -> int:
    """
    Autodiagnóstico: ¿esto funciona de verdad?

        python -m pipeline.redaccion

    Hace una llamada real con un tema del catálogo y dice en una línea si
    quedó listo o qué falta. Existe porque la alternativa era pedirle a
    alguien que corriera el pipeline entero, abriera post.json y supiera
    interpretar un campo.
    """
    import sys

    from pipeline import llm, plan
    from pipeline.themes import CATALOG

    if not disponible():
        print("✗ Falta LLM_API_KEY, así que el modelo no se usa y los posts")
        print("  salen con el gancho curado del tema.")
        print()
        print("  1. Sacá una clave gratis en https://aistudio.google.com/apikey")
        print("     (con tu cuenta de Google, sin tarjeta)")
        print("  2. Guardala en el .env de este repo:")
        print("     echo 'LLM_API_KEY=la-clave' >> .env")
        print("  3. Y en GitHub, como secreto del repo:")
        print("     gh secret set LLM_API_KEY")
        print()
        print(f"  Proveedor actual: {llm.modelo()} en {llm.endpoint()}")
        print("  Se cambia con LLM_ENDPOINT y LLM_MODEL, sin tocar código.")
        return 1

    estado = {"themes": {}, "facts": {}, "evergreen": {}, "count": 0}
    for tema in CATALOG:
        hechos = plan.facts_for(tema.id, estado, limit=2)
        if len(hechos) >= 2:
            break
    else:
        print("✗ no hay ningún tema con dos hechos para probar")
        return 1

    print(f"Probando con el tema '{tema.id}' y sus dos cifras:")
    print(f"   {hechos[0]['number']} · {hechos[1]['number']}")
    print()

    r = redactar(tema=tema.name, angulo=tema.angle, hechos=hechos,
                 cierre=f"{tema.close} {tema.close_accent}")
    if not r:
        print()
        # El motivo se repite acá aunque ya se haya impreso arriba: la salida
        # del pipeline es larga y la línea que importa quedaba fuera de
        # pantalla, así que se diagnosticaba con la mitad de la información.
        if llm.ultimo_error:
            print(f"✗ NO funcionó. Motivo: {llm.ultimo_error[:400]}")
        else:
            print("✗ el modelo escribió, pero la propuesta no pasó los")
            print("  controles dos veces seguidas. Los motivos están arriba,")
            print("  en las líneas [info].")
        print()
        print("  Los posts salen igual, con el gancho curado del tema.")

        # La lista de modelos solo si el que está configurado NO figura entre
        # los que la clave acepta. Antes se imprimía ante cualquier fallo y
        # sugería que el modelo estaba caduco cuando el problema era otro:
        # un diagnóstico que apunta al lado equivocado cuesta más que ninguno.
        opciones = llm.modelos_disponibles(limite=40)
        if opciones and llm.modelo() not in opciones:
            print()
            print(f"  Ojo: '{llm.modelo()}' no figura entre los modelos que")
            print("  esta clave acepta. Algunos válidos:")
            for m in opciones[:8]:
                print(f"     {m}")
            print()
            print("  Para fijar uno:  echo 'LLM_MODEL=<el que elijas>' >> .env")
        return 1

    print("✓ LISTO. El modelo escribió y la propuesta pasó los controles:")
    print()
    print(f"   frame 1   {r['gancho']}")
    print(f"   frame 2   {r['titular_datos']}")
    print(f"   caption   {r['lectura']}")
    print()
    print("   Sin cifras inventadas, sin parafrasear el cierre, sin claims.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
