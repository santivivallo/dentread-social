# Auditoría crítica — sistema automático de contenido DentRead

Fecha: 2026-08-09 · Auditado contra el código, no contra la spec escrita
Tamaño actual: **3.357 líneas** en 20 módulos

---

## 1. Veredicto general

El sistema es seguro y barato, pero está sobreconstruido para lo que entrega y **no sirve al objetivo de posicionamiento**.

Lo que funciona: no hay LLM en el camino de publicación, así que no hay alucinación posible. Cada cifra sale de un archivo curado a mano y verificado (21/21). Los guards regulatorios son sólidos. El costo real es prácticamente cero.

Lo que no funciona, medido:

- **Se queda sin contenido en la semana 8** y repite hechos desde la semana 2. La runway de "10 semanas" de la spec es falsa.
- **El KB —411 líneas, 534 chunks— no aporta ni una palabra a lo publicado.** Solo alimenta compuertas.
- **Cero activos indexables.** Instagram y un PDF dentro del feed de LinkedIn no generan SEO, AEO ni descubrimiento por motores de IA. El objetivo declarado no se cumple en absoluto.
- **Sin monitoreo.** Si deja de publicar, nadie se entera.
- Si Instagram publica y LinkedIn falla, no queda registro y la próxima corrida **republica en Instagram**.

Veredicto: **no publicar todavía.** Cuatro correcciones bloqueantes, todas baratas. Después conviene borrar ~1.100 líneas antes de agregar nada.

---

## 2. Los diez problemas más importantes

### P1 · Cero activos indexables — el objetivo de posicionamiento no se cumple

- **Severidad: crítica**
- **Consecuencia:** Instagram no indexa texto de carruseles. Un document post de LinkedIn es texto dentro de un PDF dentro de un feed: prácticamente invisible para buscadores y completamente invisible para ChatGPT, Perplexity o Claude, que citan páginas web. Todo el trabajo produce cero autoridad temática acumulable. El activo desaparece del feed en 48 horas.
- **Corrección:** cada post genera además una página HTML estática con el mismo contenido, `schema.org/Article` + `citation`, publicada en GitHub Pages bajo un subdominio propio. Es un archivo más por corrida, ~80 líneas de plantilla, costo cero. Lo social pasa a ser distribución; la página es el producto.
- **Prioridad: necesario ahora.**

### P2 · El pozo de contenido se seca en la semana 8

- **Severidad: crítica**
- **Consecuencia:** simulado sobre el catálogo real: 12 temas habilitados con 21 hechos, a 2 posts semanales. En la semana 2 ya repite un hecho; en 7 semanas acumula **11 repeticiones**; en la 8 no hay temas disponibles y el pipeline aborta. Cada hecho está asignado a 2-4 temas y la rotación enfría *temas*, no *hechos*.
- **Corrección:** (a) enfriamiento por `fact_id`, no solo por tema; (b) subir el piso a 40-60 hechos curados antes de encender el cron. Curar un hecho toma ~10 minutos.
- **Prioridad: necesario ahora.**

### P3 · Falla parcial de publicación → duplicado en Instagram

- **Severidad: crítica**
- **Consecuencia:** `published.json` se escribe después de las dos plataformas. Si Instagram publica y LinkedIn tira excepción, no queda registro y la siguiente corrida vuelve a publicar en Instagram. Duplicado público, irreversible.
- **Corrección:** escribir el registro inmediatamente después de cada plataforma, y que `publish.py` lea ese registro al arrancar y saltee lo ya publicado. ~15 líneas.
- **Prioridad: necesario ahora.**

### P4 · Sin monitoreo: el fallo es silencioso

- **Severidad: crítica**
- **Consecuencia:** tres modos de falla silenciosa reales: token vencido (avisa en el log, que nadie lee), GitHub deshabilita los cron programados tras 60 días sin actividad en el repo, y ADA News cambia el layout y el fetcher devuelve vacío sin error. En los tres casos el sistema "funciona" y no publica nada durante semanas.
- **Corrección:** un ping a Healthchecks.io (gratis) al final de cada corrida exitosa; si no llega, manda mail. Dos líneas de `curl`. Sumar un commit automático mensual al repo para que el cron no se desactive.
- **Prioridad: necesario ahora.**

### P5 · El KB no aporta nada a lo publicado

- **Severidad: alta**
- **Consecuencia:** `kb.py` + `kb_build.py` son 411 líneas y 534 chunks indexados. Verificado: **ninguno de los chunks recuperados aparece en el texto publicado**. El contenido sale enteramente de `facts.json`. El KB solo alimenta las compuertas `top_score_norm` y `has_primary`, que son proxies de algo que el hecho curado ya garantiza. Es infraestructura que mantener sin retorno.
- **Corrección:** sacar el KB del camino de publicación. Queda como herramienta offline de curación (`suggest_facts`), que es donde sí sirve. Las compuertas se reemplazan por "¿existen 2 hechos curados para este tema?", que es la condición real.
- **Prioridad: necesario ahora** (borrar es más urgente que agregar).

### P6 · Tres modos de contenido, uno en uso

- **Severidad: alta**
- **Consecuencia:** `news` y `dentread` suman ~250 líneas de `compose.py`, arrastran los 196 de `newsguard.py`, y `news` está limitado a 1 post por tanda y es el de menor valor —comentar la agenda de otro—. `dentread` nunca se ejecutó.
- **Corrección:** MVP con modo `data` solamente. `news` y `newsguard` vuelven cuando el modo `data` esté saturado de contenido, no antes.
- **Prioridad: útil después.**

### P7 · Contenido formulaico: mismo esqueleto en cada post

- **Severidad: alta**
- **Consecuencia:** los seis slides tienen siempre los mismos roles, el mismo CTA ("¿Cómo lo ven en tu clínica?") y la misma frase de cierre. A diez posts es visiblemente robótico y erosiona lo que se intenta construir. Es el precio de no tener LLM.
- **Corrección:** una única llamada a un modelo económico por post, ~400 tokens, solo para redactar el gancho y la línea de "qué implica" a partir de los dos hechos ya fijados. Las cifras, citas y estructura siguen siendo deterministas. Costo estimado: menos de USD 0,50 al mes. Rotar 3-4 variantes de CTA por código.
- **Prioridad: útil después.**

### P8 · Sin límite de gasto ni de volumen

- **Severidad: media**
- **Consecuencia:** hoy el gasto es cero porque no hay LLM. En cuanto se conecte `LLMGenerator` no hay tope de tokens, ni de reintentos, ni de posts por día. Un bucle de reintento mal puesto puede publicar varias veces o gastar sin techo.
- **Corrección:** `MAX_POSTS_PER_DAY = 2` y `MAX_TOKENS_PER_RUN` comprobados en código antes de cualquier llamada; abortar, no reintentar.
- **Prioridad: útil después** (necesario ahora si se conecta un LLM).

### P9 · Sin reintentos ni backoff en las APIs de publicación

- **Severidad: media**
- **Consecuencia:** un 429 o un 503 transitorio de Meta o LinkedIn tira la corrida entera. Con cadencia semanal, un fallo transitorio cuesta una semana de publicación.
- **Corrección:** tres reintentos con backoff exponencial solo en errores 5xx y 429. Nunca reintentar un 4xx —ahí el riesgo es duplicar—.
- **Prioridad: útil después.**

### P10 · `verify` comprueba existencia, no vigencia

- **Severidad: media**
- **Consecuencia:** confirma que la cifra aparece en la fuente citada, no que siga siendo cierta ni que la interpretación sea correcta. Varios hechos son de 2025. Un dato correcto puede sostener una afirmación equivocada, y eso el código no lo ve.
- **Corrección:** campo `review_by` en cada hecho (fecha + 12 meses); `verify` falla si algún hecho publicable está vencido. ~10 líneas.
- **Prioridad: útil después.**

---

## 3. Qué eliminar de la spec

| Componente | Líneas | Motivo |
|---|---|---|
| `kb.py` + `kb_build.py` del camino de publicación | 411 | No aporta una palabra publicada. Queda como herramienta de curación offline |
| `newsguard.py` | 196 | Solo sirve al modo `news`, que sale del MVP |
| Modos `news` y `dentread` en `compose.py` | ~250 | Uno de menor valor, el otro nunca usado |
| `LLMGenerator` + `_spec_from_dict` + `_validate_spec` | ~60 | Andamiaje sin implementación |
| `extract_stats` y su familia de regex | ~90 | Ya probado dañino; `suggest_facts` puede usar búsqueda simple |
| Los tres niveles de evidencia en el *ranking* | ~40 | Con hechos curados, el nivel se decide al curar, no al recuperar |
| `INDUSTRY_CONTEXT` y `CITATION_RULES` en el brief | ~60 | Son instrucciones para un LLM que no existe en el pipeline |

**Total a borrar: ~1.100 líneas, un tercio del sistema.** Ninguna toca lo que se publica.

---

## 4. Qué falta incorporar

1. **Página HTML por post con schema.org** en GitHub Pages. El único componente que convierte esfuerzo en activo. *Necesario ahora.*
2. **Índice público de datos** — `facts.json` renderizado como página citable ("Dental market data, sourced"). Es exactamente lo que un motor de IA cita. Costo marginal. *Necesario ahora.*
3. **Enfriamiento por hecho** además de por tema. *Necesario ahora.*
4. **Registro de publicación por plataforma**, escrito al instante. *Necesario ahora.*
5. **Ping de salud** a Healthchecks.io. *Necesario ahora.*
6. **`review_by` en cada hecho.** *Útil después.*
7. **Reintentos con backoff** en 5xx/429. *Útil después.*
8. **Rotación de CTA y variación de gancho.** *Útil después.*

---

## 5. Qué procesos no deberían usar un LLM

Nunca, resueltos mejor con código:

- Puntuar relevancia de noticias → regex con pesos, ya funciona
- Extraer cifras de documentos → **probado dañino**: produjo texto sin sentido que pasó los cuatro guards
- Detectar duplicados → comparación de identificadores
- Elegir el próximo tema → rotación con enfriamiento
- Maquetar slides → Pillow determinista
- Validar formato, ratios, longitudes → aritmética
- Chequear claims regulatorios → lista de patrones, auditable y reproducible
- Formatear citas → plantilla
- Decidir cuándo publicar → cron

Único uso justificado: **redactar el gancho y la línea de interpretación** a partir de dos hechos ya fijados. Una llamada, ~400 tokens, modelo económico. Todo lo verificable queda fuera del alcance del modelo.

---

## 6. Cómo reducir tokens y costos

El sistema ya cuesta ~USD 0 porque no usa LLM. Las reglas para que siga así al agregar uno:

1. **Nunca mandar el brief completo.** Hoy `to_json()` incluye contexto de industria, reglas de citación y evidencia: ~2.500 tokens de los cuales el modelo necesita ~150. Mandar solo los dos hechos y el ángulo.
2. **Modelo económico.** Redactar dos frases a partir de datos dados no requiere un modelo grande.
3. **Una llamada por post, no por slide.**
4. **Cachear por `theme_id`**: si el tema no cambió, reutilizar el texto.
5. **Sin reintentos con LLM.** Si falla, cae a la plantilla determinista, que ya existe y funciona.
6. **Tope duro de tokens por corrida**, comprobado antes de llamar.

Costo proyectado con esto: **menos de USD 1 al mes.** Infraestructura sigue en cero: R2 free tier, GitHub Actions free tier, GitHub Pages gratis.

---

## 7. Riesgos reales de publicación automática

| Riesgo | Probabilidad | Impacto | Estado |
|---|---|---|---|
| Duplicado por falla parcial | **Alta** | Medio, público | **Sin mitigar (P3)** |
| Repetición de contenido | **Certeza desde semana 2** | Medio, erosiona credibilidad | **Sin mitigar (P2)** |
| Silencio prolongado sin aviso | Alta | Alto | **Sin mitigar (P4)** |
| Dato correcto, interpretación equivocada | Media | Alto | Parcial: guards no lo ven |
| Cifra desactualizada publicada como vigente | Media | Medio | Sin mitigar (P10) |
| Claim clínico o regulatorio | Baja | Muy alto | **Bien mitigado**: sin LLM, hechos curados, guards |
| Alucinación | **Nula** | — | No hay generación libre |
| Publicar en momento inoportuno (crisis del sector) | Baja | Alto | Sin mitigar: no hay kill switch automático |

El perfil es bueno donde importa más —cero alucinación, claims controlados— y malo en lo operativo, que es más barato de arreglar.

Una recomendación que se sostiene: **kill switch manual accesible desde el teléfono.** La variable `SOCIAL_PUBLISHING_PAUSED` ya existe; falta que sea fácil de accionar.

---

## 8. SEO, AEO y AI search — evaluación

**Estado actual: el sistema no aporta nada a los tres.**

| Canal | Valor actual | Por qué |
|---|---|---|
| SEO | ~0 | Instagram no expone texto indexable. LinkedIn indexa débilmente y el contenido está dentro de un PDF |
| AEO | ~0 | No hay página con estructura de pregunta-respuesta ni datos marcados |
| AI search | **0** | ChatGPT, Perplexity y Claude citan URLs. No hay URL propia que citar |

Lo irónico: **el contenido es ideal para AEO y se está tirando.** Hechos discretos, con cifra, fuente, página y fecha, sobre un nicho con poca cobertura autoritativa en la web. Eso es exactamente lo que un motor de IA busca citar.

Tres movimientos, todos baratos:

1. **Una página por post** en `dentread.github.io` o un subdominio, con `schema.org/Article`, `citation` y `datePublished`. El carrusel enlaza ahí.
2. **Índice de datos público**: `facts.json` como página HTML — "US dental market data, with sources". Cada hecho con su cita. Es un activo citable que crece solo con la curación que ya hacés.
3. **Una página por tema**, acumulando los hechos de esa familia. Veinte páginas temáticas con datos citados construyen más autoridad que cien carruseles.

Sin esto, el sistema produce contenido efímero. Con esto, el mismo trabajo produce un activo que compone.

---

## 9. Arquitectura mínima recomendada para el MVP

Cinco componentes. Ningún servidor, ninguna base de datos, ningún agente.

```
GitHub repo
 ├── data/facts.json          hechos curados a mano (única fuente de verdad)
 ├── generador determinista   facts → slides PNG + HTML + copy
 ├── verify.py                gate: verificable · breve · no duplicado
 ├── publicador               Instagram Graph API + LinkedIn Posts API
 └── GitHub Pages             la página HTML de cada post ← el activo

GitHub Actions (cron 2×/semana, free tier)
Cloudflare R2 (staging de imágenes para IG, free tier)
Healthchecks.io (ping de salud, gratis)
```

**Sin LLM en el MVP.** Se agrega después, solo para el gancho, si el contenido se siente robótico.

**Sin KB ni BM25.** La curación manual reemplaza la recuperación.

**Sin scraping para el MVP.** ADA News queda fuera hasta que el modo `data` esté saturado.

Costo total: **USD 0 al mes.** Mantenimiento: curar hechos, que es trabajo de producto, no de infraestructura.

---

## 10. Spec corregida y simplificada

### Obligatorio para el MVP

| # | Qué | Por qué |
|---|---|---|
| 1 | `facts.json` como única fuente de contenido, con `review_by` | Cero alucinación, trazabilidad total |
| 2 | **40-60 hechos curados** antes de encender el cron | Hoy hay 21: se seca en la semana 8 |
| 3 | Enfriamiento por `fact_id` y por tema | Hoy repite desde la semana 2 |
| 4 | Generador determinista: slides PNG + **página HTML con schema.org** | El HTML es el único activo que compone |
| 5 | `verify --strict` como gate previo a publicar | Verificable, breve, sin duplicados |
| 6 | Claims guard | Riesgo regulatorio sin FDA clearance |
| 7 | Registro de publicación **por plataforma**, escrito al instante | Evita el duplicado por falla parcial |
| 8 | GitHub Actions cron + Pages | Automático, gratis, sin servidor |
| 9 | Ping de salud + kill switch accesible | El fallo silencioso es el modo más probable |
| 10 | Token store cifrado + aviso de vencimiento | Credenciales de 60 días |

### Recomendado después

- Índice público de datos y páginas por tema (AEO)
- Una llamada a modelo económico para el gancho y la interpretación
- Reintentos con backoff en 5xx y 429
- Modo `news` con ADA News y `newsguard`
- Reshare manual desde el perfil personal
- Métricas de alcance por tema para recalibrar el catálogo

### No necesario

- KB con BM25 y niveles de evidencia en el ranking
- Base vectorial
- Modo `dentread` automatizado — eso se escribe a mano
- Contexto de industria y reglas de citación en el brief, sin LLM que las lea
- Extracción automática de cifras
- Tres modos de contenido
- Cualquier arquitectura multiagente

---

## Orden de trabajo

1. **Bloqueantes** (P1-P4): página HTML, enfriamiento por hecho, registro por plataforma, ping de salud. Un día de trabajo.
2. **Borrar** ~1.100 líneas (P5, P6). Medio día. Hacerlo antes de agregar.
3. **Curar** hasta 40-60 hechos. Es el cuello de botella real y no se puede automatizar sin perder la propiedad que hace seguro al sistema.
4. Recién entonces, encender el cron.
