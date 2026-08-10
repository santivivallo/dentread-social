# DentRead — sistema automático de contenido

Publica tres veces por semana desde hechos verificados: carrusel en Instagram (español), document post en LinkedIn (inglés) y **una página HTML indexable** por publicación.

```bash
python -m pipeline.run --slots 3                    # genera la tanda
python -m pipeline.run --inventory                  # cuánto contenido queda
python publish.py out/2026-08-09-<slug> --dry-run
python publish.py out/2026-08-09-<slug>
```

**¿Listo para publicar solo?** → `python -m pipeline.readiness --slots 3` · detalle en [GO-LIVE.md](GO-LIVE.md)

**Configurar credenciales** → [SETUP-CREDENCIALES.md](SETUP-CREDENCIALES.md) · verificar con `python -m tools.check_credentials`

Herramientas:

```bash
python -m pipeline.readiness --slots 3 # qué falta para esa cadencia
python -m pipeline.verify              # auditoría: 4 controles
python -m pipeline.themes              # catálogo y disponibilidad
python -m pipeline.site --rebuild      # regenera índices y sitemap
python -m tools.pubmed --preset acceso # buscar literatura para curar
python -m tools.exchange_meta_token    # token corto de Meta → uno de 60 días
python -m tools.check_credentials      # ¿funcionan las credenciales?
python -m tools.suggest_facts --pending
```

---

## La marca manda

`brand/` es la fuente de verdad: `SKILL.md` y `references/brand-and-compliance.md`, copiados de la skill `dentread-carousels`. Viven en el repo a propósito — si la spec cambia y el renderer no, alguien tiene que verlo en un diff.

Tres frames: **01 gancho** (oscuro) · **02 datos** (claro) · **03 cierre** (oscuro). 1440×1800, safe de 110px, logo abajo a la izquierda, cian como acento ≤10%.

**No se dibuja con Pillow.** El brand guide dice "no reconstruyas el motor": se genera HTML y lo renderiza Chromium. Reimplementar a mano el orbe, el tracking negativo y el logo nunca iba a coincidir con lo ya shipeado.

Ojo: `carousel-design-system.md` de `carousel-kit Maker/` **no es de DentRead** — es de otro proyecto (Space Mono, teal/púrpura, ManyChat). No usarlo como spec.

---

## Las cuatro reglas del sistema

**1. Todo sale de hechos leídos en su fuente.** `data/facts.json`. No hay LLM en el camino de publicación, así que no hay alucinación posible. `verify` confirma que cada cifra aparece en el documento citado.

**2. El texto no repite el carrusel.** Los slides traen las cifras con su cita; el copy solo da una razón para deslizar. 300-500 chars, gancho corto, siempre una pregunta.

**3. Cada post deja un activo indexable.** Un carrusel desaparece del feed en 48 horas y no lo indexa nadie; para ChatGPT o Perplexity vale cero porque citan URLs. Cada publicación escribe además una página con `schema.org/Article` y sus citas en `docs/`, servida por GitHub Pages. **Lo social es distribución; la página es el producto.**

**4. Nada se repite.** Enfriamiento a tres niveles: tema 60 días, **hecho 90 días**, evergreen 120. El enfriamiento por hecho fue la corrección central — antes solo se enfriaban temas y, como cada hecho pertenece a 2-4 temas, la misma cifra volvía a la semana siguiente bajo otro título.

---

## Qué se publica

| Tipo | Fuente | Aporte |
|---|---|---|
| **Datos** | Hechos curados · 50+ fuentes autorizadas en `data/sources.json` | 0,75/semana |
| **DentRead** | 15 bloques de mensajes en `data/evergreen.json` | 0,75/semana |
| **ADA News** | Flujo semanal + stock de ~75 artículos de 2026 | ~1/semana |
| **Journals** | PubMed en modo señalizador — qué se preguntó, no qué se encontró | ~0,5/semana |

Los evergreen **no consumen hechos**: la cifra ahí es contexto, no contenido. Hablar de la empresa no debe reducir el inventario editorial.

---

## Inventario: la métrica que importa

```
python -m pipeline.run --inventory
```

Cuando el runway baja de 4 semanas, `verify --strict` falla y el workflow no publica. El sistema prefiere frenar antes que repetirse.

**Hay dos restricciones, no una.** Los hechos determinan qué temas están disponibles hoy; los **temas** fijan el techo (22 temas ÷ 60 días de enfriamiento = 2,57 posts de datos/semana, tenga uno 21 hechos o 200). Para subir el techo se agregan ángulos, no cifras — y un ángulo nuevo sobre hechos existentes cuesta minutos contra los diez de curar un hecho.

Para encontrar material: `tools/pubmed.py` (API oficial del NCBI, sin scraping) y `tools/suggest_facts.py`.

---

## Estructura

```
data/facts.json          hechos verificados ← única fuente de contenido
data/evergreen.json      posts sobre DentRead
data/rotation.json       estado de enfriamiento
pipeline/plan.py         qué se publica y cuándo
pipeline/generate.py     hechos → slides + copy (determinista)
pipeline/spec.py         Slide y PostSpec
pipeline/render_html.py  HTML de marca → PNG 1440×1800 vía Playwright
brand/                   SKILL.md + brand guide + logos ← fuente de verdad
pipeline/site.py         HTML + schema.org + sitemap  ← el activo
pipeline/verify.py       los 4 controles
publisher/               guard, specs, Instagram, LinkedIn, tokens cifrados
docs/                    sitio estático (GitHub Pages)
tools/                   curación offline: pubmed, kb, suggest_facts
deferred/                ADA News y newsguard — fuera del MVP a propósito
```

**2.235 líneas activas**, contra 3.357 antes de la auditoría. Otras 1.276 quedaron en `tools/` y `deferred/`, fuera del camino de publicación.

---

## Los cuatro controles (`pipeline/verify.py`)

Corren en CI antes de publicar. Si alguno falla, no se publica.

| Control | Qué verifica |
|---|---|
| Verificabilidad | Cada cifra aparece en el documento citado |
| Brevedad | Gancho ≤125/≤210 chars, total <700/<900, pregunta obligatoria |
| Inventario | ≥4 semanas de contenido disponible |
| Activo indexable | Cada página con `schema.org` y `canonical`, sitemap presente |

---

## Riesgos y cómo están cubiertos

| Riesgo | Estado |
|---|---|
| Alucinación | **Imposible** — sin LLM, hechos curados |
| Claim clínico o regulatorio | Claims guard con reglas bilingües auditables |
| Duplicado por falla parcial | Registro por plataforma, escrito apenas cada una confirma |
| Repetición de contenido | Enfriamiento por hecho · verificado: 0 repeticiones en 14 semanas simuladas |
| Quedarse sin contenido | `verify` falla bajo 4 semanas de runway |
| Silencio prolongado | Ping a Healthchecks.io + commit automático que mantiene vivo el cron |
| Token vencido | Store cifrado con aviso a los 10 días |
| Publicar en mal momento | `SOCIAL_PUBLISHING_PAUSED` |
| Secreto filtrado en un traceback | Ningún `raise_for_status()` en llamadas con token en la URL |
| Chequeo que miente | Un control informa OK solo si leyó el dato; si no, dice que no lo leyó |
| Dato correcto, interpretación errada | **Sin cubrir** — ningún código lo detecta |
| Cifra desactualizada | **Sin cubrir** — falta `review_by` |

---

## Costo

| Componente | Costo |
|---|---|
| GitHub Actions · Pages | $0 (free tier) |
| Cloudflare R2 (staging IG) | $0 (free tier) |
| Healthchecks.io | $0 |
| LLM | $0 — no se usa |
| **Total** | **$0/mes** |

---

## Cadencia: 3 por semana, con margen

```
techo garantizado (22 temas + 15 evergreen)   3,33 / semana
flujo de ADA News en su p25                   1,00 / semana
                                              ────────────
                                              4,33 / semana
más ~75 artículos de 2026 en stock ≈ 75 semanas de colchón
```

`python -m pipeline.readiness --slots 3` da verde en inventario:
21/19 hechos · 12/6 temas · 15/13 evergreen.

## Cuentas verificadas

| | Valor | Estado |
|---|---|---|
| Instagram | **@dentread_** · `IG_USER_ID=17841434843464885` | Business, vinculada a "DentRead APP" ✓ |
| App de Meta | DentRead Social Publisher · `1702371920994712` | ✓ token de 60 días, 5/5 permisos, cuota 100/100 |
| Bucket R2 | `dentread-social` · `pub-af83c99af903416e98da3000418a50cc.r2.dev` | ✓ escritura y URL pública verificadas |
| LinkedIn | `urn:li:organization:102793096` | Santiago admin ✓ |
| App de LinkedIn | DentRead Social Publisher · `263015564` | Dev Tier de Community Management **pedido**, esperando |
| Dominio | **dentread.app** · sitio en `insights.dentread.app` | — |

Ojo: **@dentread** (sin guion bajo) y **dentread.com** son de otra empresa del
mismo rubro. Ver [GO-LIVE.md](GO-LIVE.md) §0.

## Pendientes antes de encender el cron

Detalle en [GO-LIVE.md](GO-LIVE.md) y [SETUP-CREDENCIALES.md](SETUP-CREDENCIALES.md).

1. ~~Meta~~ ✓ · ~~R2~~ ✓ — **Instagram ya puede publicar**.
2. **LinkedIn**: esperar la aprobación del Dev Tier, después OAuth. Es lo único con espera externa.
3. **Healthchecks + GitHub**. Verificar todo con `python -m tools.check_credentials`.
4. Correr `pipeline.ada_news.backlog()` una vez para archivar los ~75 artículos de 2026.
5. Revisar los 22 ángulos del catálogo y los 15 bloques evergreen — son la voz de la empresa.
6. Activar GitHub Pages sobre `docs/` y el DNS de `insights.dentread.app`.
7. **Dos semanas en `--dry-run`** revisando cada salida antes de soltar el cron.
