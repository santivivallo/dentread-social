# Puesta en marcha

`python -m pipeline.readiness --slots 3` responde esto mismo en cualquier momento.

---

## 0. Instagram: verificado y listo

Comprobado el 2026-08-09 en Meta Business Suite. **El bloqueante está resuelto:**

| | |
|---|---|
| Cuenta | **@dentread_** |
| Tipo | Professional · Business · categoría "Empresa de software" |
| Página de Facebook vinculada | **DentRead APP** ✓ |
| Portfolio comercial | DentRead \| AI powered Dentistry |
| `IG_USER_ID` | `17841434843464885` — ya cargado en `.env.example` |

Todo lo que la Graph API necesita está en su lugar. No falta nada del lado de Instagram.

### Aparte, y es más importante que el pipeline: existe otra empresa llamada Dentread

@dentread (sin guion bajo) no es una cuenta falsa. Es la cuenta de **otra
compañía real que también se llama Dentread**, en el mismo rubro.

| | DentRead (vos) | Dentread (la otra) |
|---|---|---|
| Dominio | **dentread.app** | **dentread.com** |
| Instagram | @dentread_ | @dentread |
| LinkedIn | /company/dentread (org 102793096) | /company/dentread.com |
| Sede | — | Houston, TX · +1 (646) 228 8751 |
| Qué hace | IA para radiografías dentales y flujo clínico | Plataforma de gestión de imágenes 2D/3D, servicios de diseño CAD, servicios radio-diagnósticos, guías quirúrgicas, alineadores |
| Tracción declarada | — | 1.000.000+ imágenes gestionadas · 10.000+ servicios · 1.000+ usuarios · 50+ expertos |
| Clientes visibles | — | Testimonios de clínicas en Gurugram, India |
| Partner | — | Alliedstar |

Tienen el `.com`, el handle de Instagram, `@Dentread` en Twitter, canal de
YouTube y página de Facebook. Operan al menos desde 2023.

**Por qué importa más que cualquier cosa de este repositorio:**

1. **Marca.** Dos empresas con el mismo nombre en imagenología dental. Si
   tienen uso previo en comercio en EE.UU. dentro de la misma clase, eso es
   un obstáculo real para registrar DENTREAD allá. Es exactamente el tipo de
   cosa que conviene poner sobre la mesa con Cooley antes de avanzar.
2. **SEO y AEO.** Todo el sitio de insights compite por el término "DentRead"
   contra un `.com` establecido en el mismo rubro. Buscar la marca no lleva
   necesariamente a vos.
3. **Confusión comercial.** Un DSO que busque "DentRead" puede terminar
   pidiendo una demo a la otra empresa. Y al revés.

**No es una decisión que tome este sistema**, pero condiciona el nombre del
subdominio, el copy de marca y la estrategia de registro. Conviene resolverlo
antes de invertir en posicionamiento sobre el término.

Recomendación inmediata para el contenido: usar **DentRead** con R mayúscula
de forma consistente, mencionar siempre **dentread.app**, y nunca
"dentread.com" en material propio.

---

## La respuesta corta

**3 por semana es alcanzable con margen.** El inventario ya está. Lo que falta son credenciales.

```
techo garantizado (temas + evergreen)    3,33 / semana
flujo de ADA News en su p25              1,00 / semana
                                         ────────────
                                         4,33 / semana

más un stock de ~75 artículos de 2026 ≈ 75 semanas de colchón
```

### El stock, que el primer modelo ignoraba

Todo 2026 cabe en ~3 páginas del listado de ADA News: **~150 artículos, de los cuales ~75 superan el piso de relevancia**. Medido sobre 20 titulares reales de enero-marzo: pasa el 50%, el doble que la tasa del flujo reciente, porque el backlog acumula los buenos.

Los dos de mayor puntaje del stock son exactamente tu territorio:

- *ADA calls for improved interoperability standards for dental imaging* (marzo) — 13,12
- *ADA seeks dental imaging experts to inform response to federal interoperability request* (febrero) — 13,12

Y hay más: la respuesta de la ADA a HHS sobre adopción de IA en odontología, y el pedido a Principal sobre documentación de radiografías periapicales, que es literalmente radiografías como adjunto de reclamo.

**Condición innegociable:** un artículo de febrero no se publica como novedad. `is_fresh=False` activa una regla que bloquea "nuevo", "esta semana", "reciente" y equivalentes en inglés. El stock se enmarca con su fecha —"en febrero la ADA pidió…"— y así es material honesto en vez de primicia falsa.

### El mix a 3/semana

| Fuente | Aporte | Tipo |
|---|---|---|
| ADA News + journals | ~1,5 | Variable — el 18% de las semanas da cero |
| Evergreen DentRead | 0,75 | Garantizado |
| Hechos curados | 0,75 | Garantizado |

### Correcciones a cálculos anteriores

Dije tres veces que faltaba contenido. Las tres estaban mal, por motivos distintos:

**Uno:** calculé con noticias y journals apagados, que era el estado del MVP recortado. Con las fuentes variables encendidas el banco de hechos solo cubre 0,75 posts semanales, no 2,25.

**Dos:** hay **dos restricciones, no una**. Los hechos determinan qué temas están disponibles hoy, pero los **temas** fijan el techo: 22 temas con enfriamiento de 60 días dan como máximo 2,57 posts de datos por semana, tenga uno 21 hechos o 200.

**Tres, y el más grande:** modelé solo el **flujo** semanal e ignoré el **stock**. Hay ~75 artículos de 2026 disponibles desde el primer día. A un post por semana eso solo ya es año y medio de contenido.

```
22 temas ÷ 8,6 semanas = 2,57 posts de datos/semana
13 evergreen ÷ 17,1 semanas = 0,76
                    techo garantizado = 3,33/semana
```

Simulado sobre 26 semanas con varianza real de Poisson: con 21 hechos el 31% de las semanas queda corta; con 50-60 hechos baja a 10-14%; **y de ahí no baja aunque se agreguen más, porque el límite pasa a ser el catálogo de temas**.

### Qué conviene hacer, entonces

| Prioridad | Acción | Efecto |
|---|---|---|
| 1 | Correr `pipeline.ada_news.backlog()` una vez | Archiva los ~75 artículos de 2026 y los deja disponibles |
| 2 | Encender journals en modo señalizador | Suma volumen sin riesgo de claim clínico |
| 3 | Sumar ~8 ángulos al catálogo | Sube el techo de 3,33 a 4,26 · un ángulo sobre hechos existentes cuesta minutos |
| 4 | Curar hechos hasta ~40 | Da holgura, ya no es bloqueante |

**Ruta recomendada:** arrancar directo a 3/semana. El stock cubre el arranque mientras se curan hechos y se suman ángulos con el sistema andando.

El orden importa: el paso 1 es un comando y desbloquea 75 semanas de colchón. Curar hechos, que era mi recomendación anterior, pasó a ser lo último.

---

## Parte 1 · Qué tenés que revisar vos

Son decisiones de contenido y de marca. Ninguna la puede tomar el código.

### 1.1 Los 22 ángulos del catálogo — **los escribí yo**

```bash
python -m pipeline.themes
```

Cada tema tiene una tesis de una o dos frases que define qué dice DentRead sobre ese dato. Es la voz de la empresa. Revisá que suenen a vos y no a un consultor.

Los que más conviene mirar, porque son los más opinables:

- `cdt-sin-codigo-ia` — "la IA dental es un gasto, no un ingreso"
- `utilizacion` — "el software se construye sobre los que ya van"
- `higienistas` — "no se puede contratar la salida del problema"
- `ia-odontologia` — "la profesión es más cauta que el mercado"

Editar en `pipeline/themes.py`, campos `angle` y `angle_en`.

### 1.2 Los 15 bloques de mensajes — **son la voz de la empresa**

`data/evergreen.json`. Ya no son posts cerrados: cada bloque ofrece varios
mensajes aprobados (afirmables) y matizados (con "busca", "puede"), y el
generador rota entre ellos. **Editar un mensaje cambia el posicionamiento sin
tocar código.**

| Bloque | Categoría | Mensajes |
|---|---|---|
| `que-es-dentread` | company_positioning | 3 aprobados · 2 matizados |
| `ia-radiografias-dentales` | product_capability | 3 aprobados · 2 matizados |
| `apoyo-analisis-radiografico` | product_capability | 3 aprobados · 2 matizados |
| `consistencia-evaluacion` | clinical_context | 3 aprobados · 2 matizados |
| `comunicacion-visual-paciente` | product_capability | 3 aprobados · 2 matizados |
| `comprension-y-confianza` | patient_outcome | 3 aprobados · 2 matizados |
| `aceptacion-tratamientos` | clinical_context | 3 aprobados · 2 matizados |
| `seguimiento-continuidad` | product_capability | 3 aprobados · 2 matizados |
| `eficiencia-flujo-clinico` | operational_context | 3 aprobados · 2 matizados |
| `innovacion-radiologia-oral` | industry_context | 3 aprobados · 2 matizados |
| `tecnologia-organizaciones` | operational_context | 3 aprobados · 2 matizados |
| `educacion-dental` | education | 3 aprobados · 2 matizados |
| `salud-publica-oral` | public_health | 3 aprobados · 2 matizados |
| `evolucion-ecosistema` | company_positioning | 3 aprobados · 2 matizados |
| `uso-responsable-ia` | regulatory_and_ethics | 3 aprobados · 2 matizados |

Los tres que más conviene mirar primero:

- **`que-es-dentread`** — la definición de la empresa. Es la que más se va a repetir.
- **`uso-responsable-ia`** — el más sensible al cambio regulatorio; ciclo de revisión de 60 días.
- **`ia-radiografias-dentales`** — describe la capacidad central del producto.

Todos van a la página web indexada, que es permanente. Pesan más que un carrusel.

### 1.3 Muestreo de hechos

`verify` confirma que la cifra aparece en el documento citado, **no que la interpretación sea correcta**. Elegí 4 o 5 al azar de `data/facts.json`, abrí la fuente y confirmá que dicen lo que el `statement` dice.

Los que más pesan porque se usan en varios temas: `intencion-vs-visita` (77% vs 37%), `dental-vs-medico` (27% vs 9,5%), `medicaid-reembolso`.

### 1.4 El disclaimer del sitio

`pipeline/site.py`, constante `DISCLAIMER`. Aparece al pie de cada página indexada:

> DentRead es software de apoyo al flujo de trabajo clínico. No es un dispositivo diagnóstico y no cuenta con autorización de la FDA. Las cifras citadas provienen de las fuentes indicadas; no son resultados de DentRead.

### 1.5 El dominio

Hoy `BASE_URL` apunta a `dentread.github.io/insights`. Definilo antes del primer post: cambiarlo después implica redirecciones y perder indexación.

Recomendación: subdominio propio, `insights.dentread.com` apuntando a GitHub Pages. Gratis y el valor SEO queda en tu dominio, no en el de GitHub.

---

## Parte 2 · Qué falta, mecánico

### Bloqueantes

**1. Instagram — el que puede tirar todo abajo.** Verificar que @dentread sea cuenta **Professional** vinculada a una **Página de Facebook**. Sin eso no hay API y no lo puedo comprobar por vos. Después: app en developers.facebook.com, agregarte como tester, token de larga duración, y sacar el `IG_USER_ID` numérico.

**2. LinkedIn.** Confirmar que el Development Tier de Community Management cubre la página `102793096` (sos admin, debería alcanzar). Habilitar refresh tokens.

**3. Bucket R2** con dominio público, y la clave Fernet:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**4. Un comando para archivar el stock.** Desbloquea los ~75 artículos de 2026:

```bash
python -c "from pipeline.ada_news import backlog; print(len(backlog()))"
```

Tarda unos minutos: hace un fetch cada 1,5 segundos por cortesía con el NCBI y con la ADA.

### Ya no bloquean

- **Curación de hechos.** 21 alcanzan con el stock encendido. Seguir curando da holgura, pero con el sistema andando.
- **Evergreen.** 13 escritos, los 13 pasan el claims guard.

### Conviene, no bloquea

- Crear el check en Healthchecks.io y cargar `HEALTHCHECK_URL`. **Sin esto el fallo es silencioso**, que es el modo de falla más probable.
- Pinear las actions por SHA y crear el environment `production`.
- Agregar `review_by` a cada hecho.
- Activar GitHub Pages sobre `docs/`.

---

## Parte 3 · Orden de ejecución

| | Qué | Tiempo |
|---|---|---|
| 1 | Verificar la cuenta de Instagram | 15 min — **hacelo primero, puede cambiar todo** |
| 2 | Revisar los 6 evergreen y los ángulos de los temas | 1 h |
| 3 | Definir el dominio y actualizar `BASE_URL` | 15 min |
| 4 | Credenciales: Meta, LinkedIn, R2, Fernet | 2-3 h |
| 5 | Archivar el backlog de 2026 (un comando) | 10 min |
| 6 | Healthchecks + Pages + environment | 30 min |
| 7 | `python -m pipeline.readiness --slots 3` → verde | |
| 8 | **Dos semanas con `--dry-run`**, revisando cada salida a mano | 2 semanas |
| 9 | Encender el cron a 3/semana | |
| 10 | Sumar ángulos y hechos con el sistema andando | |

El paso 8 no es burocracia. El sistema publica sin que nadie mire; dos semanas de salidas revisadas a mano es lo que te dice si el filtro sirve, y cuesta cero.

---

## Comandos de control

```bash
python -m pipeline.readiness --slots 3   # ¿qué falta para esa cadencia?
python -m pipeline.run --inventory       # cuánto contenido queda
python -m pipeline.verify                # los 4 controles
python -m pipeline.run --slots 2         # generar la tanda
python publish.py out/<carpeta> --dry-run
```

Para frenar todo: variable de repositorio `SOCIAL_PUBLISHING_PAUSED = true`.
