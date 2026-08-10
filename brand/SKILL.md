---
name: dentread-carousels
description: Crea carruseles de marca DentRead (slides 4:5, 1440x1800 PNG) para LinkedIn, Instagram y Facebook, usando el motor HTML→Playwright ya construido en "carousel-kit Maker/". Aplica el brand guide de DentRead, compliance médico, y cita fuentes al pie cuando hay datos. Úsala cuando Santiago diga "hazme un carrusel", "un carrusel de X frames", "posteo/publicación para LinkedIn/IG/FB", "adapta esto a carrusel", o pase datos/tema para volверlos slides. Genera EN para LinkedIn y ES para Instagram/Facebook. NO inventa cifras: verifica siempre las fuentes antes de ponerlas en una slide.
---

# DentRead Carousel Creator

Convierte un tema o dato en un carrusel vertical 4:5 (1440x1800) de alta calidad con la marca DentRead. **No reconstruyas el motor**: copia una plantilla HTML existente, edita el texto y renderiza.

Antes de escribir texto con claims clínicos o comparaciones de mercado, lee `references/brand-and-compliance.md`.

## Motor y ubicación

```
/Users/santi/Desktop/carousel-kit Maker/
  render.py            ← Playwright: HTML → PNG 1440x1800
  logo-cyan.png        ← logo sobre fondo oscuro
  logo-ink.png         ← logo sobre fondo claro
  <tema>-en-0X.html    ← plantillas (usar de referencia / copiar)
  <tema>-es-0X.html
```
Nota: la Mac de Santiago mueve archivos generados a carpetas "Nueva carpeta con elementos N" automáticamente. Si un archivo "desaparece", búscalo ahí con `find`. Si renderizas dentro de esas subcarpetas, copia primero `logo-cyan.png` y `logo-ink.png` a la subcarpeta (las rutas de logo son relativas).

## Flujo (token-eficiente)

1. **Define el brief**: tema, nº de frames (default 3), idioma(s), y si empieza en claro u oscuro.
2. **Si hay datos/investigación**: NO inventes. Extrae cifras de fuentes que Santiago aprobó o de sus PDFs (usa markitdown + grep de líneas con %/$/número, nunca leer PDFs enteros). Verifica SIEMPRE la cifra y su fuente antes de ponerla. Cita la fuente al pie de la slide de datos. Excluye datos de competidores (Pearl, Overjet) salvo que Santiago lo pida.
3. **Copia una plantilla** cercana (`cp <tema-existente>-en-01.html nuevo-01.html`) y edita solo el texto. Estructura típica: 01 hook, 02 contenido/datos, 03 cierre + CTA. Alterna fondos oscuro/claro entre frames.
4. **Render**: `cd "carousel-kit Maker" && python3 render.py nuevo-01.html nuevo-02.html ...`
5. **QA ligero** (ahorra créditos): abre máximo 1 PNG (la slide de datos, la más propensa a error). No revises las 3.
6. **Entrega**: rutas de los PNG + caption. EN para LinkedIn; ES para Instagram/Facebook.

## Reglas de marca (siempre) — detalle en references/brand-and-compliance.md

- Colores: Navy #0B1626, Midnight #0A0F18, Electric Cyan #0AA6C9 (on-dark #22C2E0, on-light #07728C), Mist #F4F7F9, Slate #586575. Cyan como acento ≤10%.
- Tipografías: Schibsted Grotesk (titulares), Hanken Grotesk (cuerpo), Space Mono (kickers/labels).
- Logo abajo-izquierda; sin em dashes.
- Compliance: "AI assists, the dentist decides" / "la IA apoya, el odontólogo decide". Nunca "diagnóstico autónomo", "FDA-cleared", "garantizado", "reemplaza al dentista". Lenguaje seguro: "apoyo diagnóstico", "hallazgos compatibles", "asistencia al profesional".
- Orden del ciclo si aplica: diagnóstico → explicación → tratamiento → seguimiento.

## Detalle de layout aprendido

- Números comparativos (ej. "$942K → $207K", "23% → 39%") van en UNA sola línea: usa `white-space:nowrap` y baja el `font-size` del `.big` si es necesario. Nunca uno sobre otro.
- Cada slide de datos lleva `.source` al pie (Space Mono, gris) con la fuente citada.

## Cómo pasar los detalles (para Santiago)

En cualquier conversación: invoca `/dentread-carousels` y di algo como:
"Carrusel de 3 frames, EN para LinkedIn, tema: [X]. Datos: [pega cifras + fuente, o el PDF]. Empieza en [claro/oscuro]."
Con eso genero, renderizo y te doy el caption.

Relacionado: la línea de marca y compliance es la misma que [[dentread-video-hooks]], [[no-hallucinate-ask]], [[dentread-loop-order]] y [[token-efficient-video-qa]].
