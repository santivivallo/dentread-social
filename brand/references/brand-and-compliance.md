# DentRead Brand Guide + Compliance (para carruseles)

## Colores
| Rol | Hex |
|-----|-----|
| Navy Ink (texto principal / fondos) | #0B1626 |
| Midnight (fondo oscuro) | #0A0F18 |
| Electric Cyan (acento) | #0AA6C9 |
| Cyan on-dark | #22C2E0 |
| Cyan on-light | #07728C |
| Mist (fondo claro) | #F4F7F9 |
| Tint (fondo claro alt.) | #E2F1F5 |
| Slate (texto secundario) | #586575 |

Cyan como acento, máximo ~10% de la superficie. Nunca fondo dominante.

## Tipografías
- Schibsted Grotesk 700/800 → titulares (letter-spacing negativo, -2 a -3px)
- Hanken Grotesk 400/500 → cuerpo
- Space Mono 700 → kickers, labels, fuentes (mayúsculas, tracking amplio)

Cargar por Google Fonts. En render.py, Playwright espera ~3.5s para que carguen (no reducir).

## Layout estándar (slide 1440x1800, safe inset 110px)
- Top: kicker (Space Mono, izquierda) + frame-num "0X / 03" (derecha).
- Dots de progreso (3 barras, la activa en cyan).
- h1 grande con una palabra/frase en `.accent` (cyan).
- Cuerpo/sub en Slate.
- Bottom: logo abajo-izquierda + "Desliza/Swipe →" o "Guarda/Save this post".
- Alternar frames: oscuro (midnight, logo-cyan) / claro (mist, logo-ink).

## Slide de datos
- Filas `.stat`: `.big` (cifra en cyan, Schibsted 800) + `.desc` (Hanken).
- Números comparativos SIEMPRE en una línea: `white-space:nowrap`, bajar font-size si hace falta.
- `.source` al pie: Space Mono, gris, "Source(s): …". Citar la fuente real y verificada.

## Compliance (no negociable)
- Frase ancla: "AI assists, the dentist decides" / "La IA apoya, el odontólogo decide".
- Lenguaje seguro: apoyo diagnóstico, hallazgos compatibles, asistencia al profesional, no reemplaza el criterio clínico.
- PROHIBIDO: diagnóstico autónomo, FDA-cleared, resultados garantizados, reemplaza al dentista, cifras sin fuente.
- Datos: separar tipo de evidencia (encuesta vs clínica vs carga global). No usar cifras de competidores (Pearl, Overjet) salvo pedido explícito; preferir fuentes neutrales (CareQuest, ADA Health Policy Institute, FDI, Planet DDS, ADA).
- Verificar SIEMPRE la cifra en el documento antes de ponerla (no confiar en grep de gráficos, que salen desordenados).

## Orden del ciclo DentRead
Diagnóstico → Explicación → Tratamiento → Seguimiento. El seguimiento va SIEMPRE al final (después del tratamiento).

## Formato de salida
- LinkedIn: inglés. Instagram/Facebook: español. Mismo PNG 4:5 sirve para las 3 plataformas.
- Caption: 2-4 líneas + 1 emoji dental + CTA + 4-6 hashtags. Incluir la fuente si el carrusel usó datos.
