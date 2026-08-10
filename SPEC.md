# DentRead Social Auto-Publisher — Spec

Versión 2 · 2026-08-09 · Estado: código listo, bloqueado por aprobaciones de plataforma

---

## 1. Qué hace y qué decidió el diseño

Publica dos veces por semana, sin intervención: carrusel en Instagram (español) y document post en LinkedIn (inglés, página DentRead `102793096`).

La decisión que ordena todo lo demás: **autopublicar sin revisión humana**. Eso obliga a que cada control de calidad y de riesgo sea mecánico y esté antes de la llamada a la API, porque no hay nadie mirando entre la generación y el feed.

### La arquitectura de contenido

El contenido es **odontología, mercado, tendencias y datos** — más lo propio de DentRead. No es un canal sobre IA en imagenología; eso es un tema entre varios.

Tres modos, y el primero es el principal:

| Modo | Disparador | Cuándo | Riesgo de copyright |
|---|---|---|---|
| **`data`** | Un tema del catálogo, sostenido por los estudios | Siempre. Es la base de la cadencia | Ninguno |
| `news` | Una noticia de ADA News que lo amerite | Máximo 1 por tanda | Exige atribución + `newsguard` |
| `dentread` | Novedad propia, anclada en un dato del sector | Cada dos semanas | Ninguno |

En los tres, la misma estructura:

```
DISPARADOR  →  qué motiva el post
SUSTANCIA   →  el dato del corpus, con cita verificable
TESIS       →  qué significa para una clínica el lunes
```

**Por qué `data` es el modo principal.** Atar todo a ADA News tiene tres problemas: limita la cadencia a lo que la ADA publique esa semana, hace que cada post arrastre riesgo de atribución, y en el mejor de los casos produce un comentario sobre la agenda de otro. Los estudios sostienen contenido por sí solos.

El modo `dentread` tiene un slide obligatorio de "qué todavía no está resuelto". No es humildad decorativa: es lo que hace creíbles a los otros cinco cuando venís de una startup sin tracción pública.

Tu corpus de estudio de mercado — 14 documentos, **529 chunks indexados** — es lo que convierte un refrito en un punto de vista. El umbral de 60% de contenido original no es cosmético: es la línea entre las dos cosas, y está enforced en código.

Además del corpus, el generador recibe el **mapa de industria**: las cinco capas de la cadena de valor, los cuatro hechos estructurales y las reglas de citación. Sin eso escribe sobre odontología en general; con eso escribe desde una posición. El más importante de los cuatro: **la IA dental no tiene código CDT**, y por eso es un gasto y no un ingreso. Es lo que explica la narrativa de aceptación de tratamiento de todo el sector, incluida la tuya.

---

## 2. Flujo

```
 cron (Mar/Jue 09:00 ET, GitHub Actions)
   │
   ├─ 1. ada_news.discover()        listado server-side, sin JS
   │     └─ excluye patrocinados, ya-vistos, y >14 días
   ├─ 2. ada_news.score()           ranking: IA ×1.25 > workflow/pagadores
   ├─ 3. kb.evidence_pack()         BM25 sobre 529 chunks → hechos + citas
   ├─ 4. compose.build_brief()      disparador + evidencia + ground truth
   │     └─ brief_is_publishable()  ¿hay ≥2 hechos con cifras? si no, aborta
   ├─ 5. generador de carrusel      (tu automatización existente)
   │
   ├─ 6. specs.py        formato: ratios, pesos, JPEG, longitudes
   ├─ 7. newsguard.py    copyright, marca ADA, originalidad, atribución
   ├─ 8. guard.py        claims regulatorios, tracción, garantías, PHI
   ├─ 9. cuota + tokens
   └─10. publicación → published.json → artifact de auditoría (90 días)
```

Cada compuerta falla más barato que la siguiente. La 4 aborta antes de gastar una llamada al modelo; la 6 antes de subir nada; la 7 y 8 antes de tocar una API pública.

---

## 3. Modelo de seguridad

El principio: **este sistema nunca toca datos de pacientes.** Todo lo demás es proteger tres credenciales y un bucket.

### Amenazas y controles

| Amenaza | Control | Costo |
|---|---|---|
| Refresh token de LinkedIn (365 días) filtrado desde el caché de CI | Token store **cifrado con Fernet** (`TOKEN_STORE_KEY`). El caché de Actions es legible por cualquier workflow del repo — en claro era un pasivo de un año | $0 |
| Secrets en el repo | Solo GitHub encrypted secrets. `.env` en `.gitignore`. `persist-credentials: false` en checkout | $0 |
| Action comprometida en la cadena de suministro | Pinear cada action por SHA (marcado como TODO en el workflow) + `--require-hashes` en pip | $0 |
| Workflow con más permisos de los necesarios | `permissions: contents: read` a nivel workflow | $0 |
| Llave de R2 con alcance de cuenta | Token de R2 acotado a **un bucket**, Object Read & Write, sin permisos de cuenta | $0 |
| Slides quedan expuestos indefinidamente | Regla de lifecycle: borrado a 24 h. Además el script borra tras publicar | $0 |
| Publicación descontrolada | `concurrency` (nunca dos corridas), kill switch (`vars.SOCIAL_PUBLISHING_PAUSED`), `timeout-minutes: 15`, 1 post por plataforma por corrida | $0 |
| No saber qué se publicó | `published.json` + `seen_articles.json` como artifact, retención 90 días | $0 |
| PHI en el pipeline | Regla dura: el sistema no ingiere imágenes clínicas. `guard.phi.*` bloquea identificadores y exige declarar de-identificación | $0 |
| Token vencido en silencio | Aviso a los 10 días en cada corrida | $0 |

**Todos los controles cuestan cero.** No hay ninguno acá que justifique gasto; lo que cuesta es configurarlos una vez.

### Lo que quedó fuera a propósito

- **Vault / gestor de secretos externo.** Para tres credenciales de marketing, GitHub Secrets es suficiente. Un Vault agregaría costo y una dependencia sin reducir riesgo real.
- **Base vectorial.** 529 chunks se resuelven con BM25 en memoria. Un índice vectorial sumaría una API por consulta y costo recurrente para ganar poco a esta escala. Reevaluar sobre ~500 documentos.
- **Rotación automática de llaves de R2.** Rotación manual semestral en el calendario. Automatizarla cuesta más de lo que protege.

---

## 3-bis. El corpus: niveles de evidencia y cobertura real

Los 14 documentos no valen lo mismo. Cada chunk lleva su nivel, su fecha y su cautela de uso, y el nivel entra en el **ranking**, no solo en la cita:

| Nivel | Peso | Docs | Chunks | Cómo se cita |
|---|---|---|---|---|
| `primary` | 1.0 | 9 | 406 | Se puede afirmar |
| `consultancy` | 0.7 | 1 (L.E.K.) | 24 | Orden de magnitud, nunca cifra exacta |
| `reference` | 0.7 | 1 | 13 | Definiciones |
| `vendor` | 0.4 | 3 (Planet DDS, Pearl, Forbes/Overjet) | 86 | Señal de mercado, con el proveedor a la vista |

Reglas que quedaron en código, no en una guía de estilo:

- Un pack cuya **única evidencia cuantitativa sea de proveedor** no es publicable. Sostener un claim de DentRead con material de Pearl no es defendible.
- Máximo 2 chunks por documento: obliga a variar fuentes en vez de apoyarse en una sola.
- Los estudios financiados por aseguradoras se marcan solos y arrastran la cautela "usar la dirección del efecto, nunca la magnitud".
- El SCDI White Paper es de dic-2022. En IA eso es antiguo: sirve para marcos, no para estado del arte. La cautela viaja con la cita.

### Cobertura del corpus, medida

Score normalizado por largo de consulta (el BM25 crudo no es comparable entre temas). Piso de publicación: **1.6**. Medido sobre 23 temas candidatos: **21 pasan, y todos con evidencia primaria cuantitativa.**

| Tema | Fuerza | | Tema | Fuerza |
|---|---|---|---|---|
| Medicaid, beneficio adulto | 12.43 | | Adultos mayores | 5.91 |
| Medicaid, participación | 9.93 | | Escasez de higienistas | 5.18 |
| Utilización | 7.34 | | Consolidación DSO | 5.17 |
| Economía de la clínica | 6.98 | | Demografía del dentista | 4.18 |
| Sin seguro dental | 6.88 | | Costo como barrera | 3.60 |
| Niños y CHIP | 6.86 | | Tecnología en clínica | 3.25 |
| CBCT y 3D | 6.09 | | Radiología e imagen | 3.22 |
| Salud oral y sistémica | 6.05 | | Urgencias por dolor dental | 3.09 |
| Gasto nacional dental | 6.01 | | Prevención · Periodontal | 2.87 · 2.67 |

Dos quedaron abajo del piso: **teleodontología** (0.88, solo material de proveedor) y **sesgo/validación de modelos** (1.27). Están fuera del catálogo hasta que haya fuente.

El catálogo operativo tiene **20 temas curados a mano**, cada uno con su ángulo y su audiencia. A dos posts por semana con enfriamiento de 60 días, son ~10 semanas de contenido antes de repetir.

**Corrección respecto de la versión anterior de este spec.** Medí la cobertura con lente de IA en imagenología y concluí que el corpus tenía huecos donde vivía la tesis. Con el alcance real —odontología, mercado, tendencias, datos— la lectura se invierte: el corpus es fuerte justamente donde debe estar el contenido. Los estudios de ADA HPI, CareQuest, MACPAC y L.E.K. son la sustancia, y son abundantes.

**Qué sigue faltando, y sí importa:**

1. **CDT 2026 y su ausencia de códigos de IA.** El hecho estructural más fuerte del sector y no está citable.
2. **Fuente primaria sobre denegaciones y downcoding.** Hoy solo hay material de competidores.
3. **Algo actual sobre regulación de IA** — el SCDI es de 2022.

---

## 4. Modelo de costos

| Componente | Uso real | Costo/mes |
|---|---|---|
| Cloudflare R2 | ~80 objetos/mes, borrados a 24 h. Free tier: 10 GB + 1M ops Clase A. Sin egress fee | **$0** |
| GitHub Actions | ~3 min × 8 corridas = 24 min. Free tier privado: 2000 min | **$0** |
| Dominio `media.dentread.com` | Subdominio del que ya tenés, en Cloudflare | **$0** |
| KB / retrieval | BM25 local, 0.7 MB versionado en el repo | **$0** |
| Triage de noticias | ~25 artículos/semana. Clasificación por regex, sin modelo | **$0** |
| Generación de copy | ~8 posts/mes con un modelo de gama alta | **$1–3** |
| **Total** | | **$1–3/mes** |

El costo real del proyecto no es la infraestructura. Es tu tiempo en las aprobaciones de Meta y LinkedIn, y el riesgo de reputación de publicar sin mirar.

---

## 5. Barra de calidad

Mecánica, porque no hay humano en el loop.

| Chequeo | Umbral | Nivel |
|---|---|---|
| Relevancia de la noticia | ≥3.5 | aborta antes de generar |
| Fuerza de la evidencia recuperada | ≥6.0 | aborta antes de generar |
| Hay al menos un dato primario | sí | aborta antes de generar |
| Las cifras no son solo de proveedores | sí | aborta antes de generar |
| Contenido original vs. fuente | ≥60% | BLOCK |
| N-grama compartido más largo | ≤7 palabras | BLOCK |
| Solapamiento léxico con la fuente | ≤35% | REVIEW |
| Citas textuales | ≤1, ≤15 palabras | BLOCK |
| Atribución a ADA News | obligatoria | BLOCK |
| Hechos citables del corpus | ≥2, con cifras | aborta antes de generar |
| Primera línea IG / LinkedIn | ≤125 / ≤210 chars | warn |
| Hashtags | ≤12 IG, ≤5 LinkedIn | warn |
| CTA presente | pregunta real | INFO |

Verificado contra un artículo real de ADA News: un resumen cercano da 97% de solapamiento y 30 palabras literales → bloqueado. Un post con tesis propia da 4% y 96% original → pasa.

### Marca y copyright (`newsguard.py`)

Bloquea en duro: `ADA-approved`, `ADA Seal`, `in partnership with the ADA`, `ADA recommends DentRead`, y cualquier referencia a imágenes alojadas por la ADA. Estas son marcas registradas con procesos formales que DentRead no atravesó — la ambigüedad acá no es negociable.

---

## 6. Cadencia sostenible

Con el modo `data` como base, la cadencia ya no depende del ciclo de noticias:

| Fuente | Capacidad |
|---|---|
| Catálogo de temas | 20 temas × enfriamiento 60 días = **~10 semanas sin repetir** a 2/semana |
| ADA News | 38% de los titulares pasan el piso; ~1–2 por semana valen un post |
| DentRead | según lo que realmente pase |

**Mezcla recomendada: 2 por semana.** Un slot lo toma una noticia si la hay y la otra la cubre el catálogo; si no hay noticia, dos del catálogo. `plan_week()` lo resuelve solo y evita repetir familia en la misma tanda.

Verificado sobre 4 semanas simuladas: rotación correcta, familias variadas, evidencia primaria dominante en todas las tandas.

---

## 7. Riesgo residual, dicho sin vueltas

Elegiste autopublicar. La ingeniería reduce el riesgo pero deja tres cosas en pie:

1. **El guard es coincidencia de patrones, no comprensión.** Un claim mal formulado con palabras que no están en las reglas pasa. Los umbrales de originalidad son proxies estadísticos, no criterio editorial.
2. **La atribución no es una licencia.** Citar la fuente reduce el problema de copyright pero no lo elimina. Lo que lo elimina es que el contenido sea sustancialmente tuyo — por eso el 60% está en código y no en una guía de estilo.
3. **Publicar es irreversible en la práctica.** Borrar un post no borra las capturas. La primera semana conviene correr con `--dry-run` y revisar cada salida a mano antes de soltar el cron.

Mi recomendación sigue siendo correr en modo digest las primeras 3–4 semanas: mismo pipeline, mismo output, pero llega a tu inbox en vez del feed. Si a las cuatro semanas aprobás todo sin cambios, el filtro ya demostró que funciona y soltás el cron con evidencia. Si corregís la mitad, te enteraste sin costo público.

---

## 7-bis. La lección más cara: los guards no miden sentido

Durante la construcción, el generador por plantilla extraía cifras del texto crudo de los PDFs. Produjo, entre otros:

> *"142 of a total of 153 periapical lesions and the reliability of correctly detecting a periapical lesion was 92."*
> *"2024 % of adults without dental insurance % of adults without medical insurance."*

Ambos **pasaron los cuatro guards** — specs, claims, newsguard y los gates de brief — y quedaron listos para publicar. No hay nada regulatoriamente riesgoso ni plagiado en un pie de figura mal recortado. Simplemente no significa nada.

La conclusión rediseñó el sistema: **auto-publicar solo desde hechos verificados a mano.** `data/facts.json` contiene cifras que fueron leídas en su fuente, con enunciado completo en dos idiomas, cita, página y fecha. La extracción automática sigue existiendo pero solo como asistente para curar (`pipeline/suggest_facts.py`), nunca en el camino a publicación.

El costo es cobertura: 12 de 22 temas están habilitados. El resto espera curación. Es el intercambio correcto — el sistema prefiere no publicar antes que publicar algo sin sentido, y ese default es lo que hace defendible dejarlo solo.

---

## 7-ter. Las tres promesas, auditadas

`python -m pipeline.verify --strict` corre en CI antes de publicar. Estado real hoy:

| Promesa | Control | Estado |
|---|---|---|
| Contenido verificable | Cada cifra de `facts.json` debe aparecer en el documento citado | **21/21** |
| Texto breve que invita a leer | Gancho ≤125 / ≤210 chars, total <700 / <900, pregunta obligatoria | **2/2 posts · 333–467 chars** |
| Cobertura ADA creciente | Archivo acumulativo con profundidad progresiva | **mecanismo verificado offline; sin corridas reales aún** |

### Qué cambió para cumplirlas

**Brevedad.** El copy repetía el carrusel: 589–1011 chars, con las dos cifras completas y las citas con número de página. Ahora los slides cargan las cifras con su cita exacta y el caption solo da una razón para deslizar — gancho, una cifra, una consecuencia, pregunta, fuente compacta. Quedó en 333–467 chars.

**Cobertura.** No existía. Había un `seen_articles.json` que solo evitaba repetir, y con un bug: truncaba la lista por orden alfabético, no por recencia. Ahora `data/ada_archive.json` acumula todo lo escaneado con su score —se publique o no— y la profundidad crece de 2 a 12 páginas, una por corrida. La simulación de 5 corridas da 10 → 30 artículos, profundidad 2 → 6, sin repeticiones.

**Un bug serio encontrado al simular.** El campo `published` servía a la vez como fecha de publicación del artículo y como flag de "ya lo publicamos". Después de la primera corrida todo el archivo quedaba marcado como usado y el pipeline se quedaba sin candidatos en silencio. El flag pasó a llamarse `used`.

---

## 8. Estado

| Componente | Estado |
|---|---|
| Publicador IG + LinkedIn | Listo, 4 carruseles pasaron dry-run completo |
| Validación de specs | Listo, probado con ratios mezclados y sobredimensionados |
| Claims guard v2 | Listo, 18 hallazgos sobre copy tóxico; falsos positivos de terminología CDT corregidos |
| News guard | Listo, verificado contra artículo real |
| KB (534 chunks, 15 fuentes) | Construido, retrieval verificado, niveles de evidencia en el ranking |
| Hechos curados | 21 verificados a mano · **12/22 temas habilitados** |
| Catálogo de temas | 22 temas con ángulo y audiencia, rotación con enfriamiento |
| Renderizador | Listo, 1080×1350 con Hanken/Schibsted Grotesk |
| Generador | Plantilla determinista lista; interfaz `Generator` para conectar el tuyo |
| Orquestador `run.py` | Listo, end-to-end verificado |
| Token store cifrado | Listo |
| Workflow | Genera y publica; **faltan los SHA de las actions** |
| Ingesta ADA News | Escrita y calibrada; **falta smoke test en vivo** |

### Lo que falta, en orden

1. **Verificar que @dentread sea cuenta Professional vinculada a una Página de Facebook.** Bloquea todo el lado Instagram y no lo puedo comprobar por vos.
2. **Confirmar el Dev Tier de Community Management** para la página 102793096.
3. **Curar los 10 temas pendientes**: `python -m pipeline.suggest_facts --pending`. Cada uno son ~10 minutos de leer y copiar dos cifras.
4. **Smoke test en vivo del fetcher**: `python -m pipeline.ada_news` desde tu máquina.
5. **Pinear las actions por SHA** y crear el environment `production`.
6. **Revisar los ángulos del catálogo** en `pipeline/themes.py` — los escribí yo, corregí los que no suenen a vos.
7. Cuatro semanas en digest antes de soltar el cron.
