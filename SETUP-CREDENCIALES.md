# Credenciales — paso a paso con tus valores

Lo que ya está resuelto y no hay que tocar:

```bash
IG_USER_ID=17841434843464885                      # @dentread_ · verificado
LINKEDIN_ORG_URN=urn:li:organization:102793096    # página DentRead · verificado
```

Al terminar cada bloque, corré el verificador. Te dice si funciona antes de
que el cron lo descubra un martes a las nueve.

```bash
python -m tools.check_credentials --only meta
python -m tools.check_credentials --only linkedin
python -m tools.check_credentials --only bucket
python -m tools.check_credentials              # todo junto
```

---

## 1 · Clave de cifrado — 30 segundos, hacelo primero

Ya la generé:

```
TOKEN_STORE_KEY=C3IGeqJ32m6jKWf_m6gyigYAL3LZIuI3U6KyBFY7rDU=
```

Va en `.env` local y como secret en GitHub. **No la commitees.** Si la perdés,
hay que rehacer el OAuth de todo.

Para generar otra: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

---

## 2 · Meta / Instagram — hecho el 2026-08-09, salvo el token

App **DentRead Social Publisher** · `META_APP_ID=1702371920994712`

### 2.1 Lo que ya está configurado

| | |
|---|---|
| Caso de uso | Administrar mensajes y contenido en Instagram |
| Vía | **API con inicio de sesión con Facebook** |
| Portfolio | DentRead \| AI powered Dentistry |
| Permisos | `instagram_basic` `instagram_content_publish` `pages_show_list` `pages_read_engagement` `business_management` |
| App Review | no hace falta |

**Ojo con el asistente de Meta:** por defecto abre *API setup with Instagram
login*, que usa un App ID distinto y permisos `instagram_business_*`. Ese no
es el nuestro. `publisher/instagram.py` habla con `graph.facebook.com` contra
el `IG_USER_ID`, que es la vía de **Facebook login**. Si alguna vez hay que
rehacer la app, elegir esa.

**El rol "Instagram Tester" no aplica** — es de la Instagram Basic Display
API, deprecada. Siendo administrador de la app y del portfolio que controla
la Página y la cuenta, alcanza para publicar en dev mode.

### 2.2 App Secret

**Configuración de la app → Básica → Mostrar** → a `.env` como
`META_APP_SECRET`. No pasa por ningún otro lado.

### 2.3 Token de larga duración

El del Explorador dura una o dos horas. Para canjearlo:

1. **Herramientas → Explorador de la API Graph**, app *DentRead Social
   Publisher* → **Generate Access Token** → consentimiento
   (elegir **solo las Páginas actuales**, marcar solo *DentRead APP*)
2. Copiar el token a `.env` como `META_SHORT_TOKEN`
3. ```bash
   python -m tools.exchange_meta_token
   ```

Canjea por uno de ~60 días, **verifica que resuelva `@dentread_` antes de
guardar nada**, lo escribe en `META_ACCESS_TOKEN` y borra el corto. No
imprime el token: pegarlo en una terminal lo deja en el historial del shell,
que no se cifra. Desde ahí `publisher/tokens.py` lo refresca solo.

**Verificá:** `python -m tools.check_credentials --only meta`
Confirma que el token vive, cuántos días le quedan, que los permisos estén y
que el `IG_USER_ID` devuelva **@dentread_**.

---

## 3 · LinkedIn — 30 min más la espera de aprobación

### 3.1 Crear la app

1. developers.linkedin.com → **Create app**
2. Asociala a la página **DentRead** (sos admin, aparece en el selector)
3. Verificá la app desde la página — genera un link que confirmás como admin

### 3.2 Pedir Community Management API

**Products** → **Community Management API** → *Request access*

Pedí el **Development Tier**, que da acceso a las organizaciones que
administrás. Es lo que necesitás; el Standard Tier exige screencast y se
reporta en meses.

Scopes: `w_organization_social`, `r_organization_social`, `w_member_social`.

### 3.3 OAuth y refresh token

En **Auth** → habilitá **Refresh Tokens** antes de generar nada. Sin eso hay
que rehacer el OAuth cada 60 días a mano.

```bash
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
LINKEDIN_ACCESS_TOKEN=
LINKEDIN_REFRESH_TOKEN=
```

**Verificá:** `python -m tools.check_credentials --only linkedin`
Un **403 en organizationAcls** significa que Community Management todavía no
está aprobada. Es el error esperable mientras esperás.

---

## 4 · Cloudflare R2 — hecho el 2026-08-10

Instagram no acepta bytes: exige una URL HTTPS pública por slide.

| | |
|---|---|
| Cuenta | `e09ab2f10b4b3fdc6f5f97780171b77b` |
| Bucket | `dentread-social` · Eastern North America |
| URL pública | `https://pub-af83c99af903416e98da3000418a50cc.r2.dev` |
| Token | `dentread-social-autopost` · Object Read & Write · solo este bucket |
| Lifecycle | `borrar-slides-a-1-dia` — borra a las 24 h |

**Por qué la URL es `r2.dev` y no `media.dentread.app`:** el dominio propio
exige que `dentread.app` esté en Cloudflare DNS, y no lo está. Migrar el DNS
del dominio entero —web y correo incluidos— para alojar imágenes que viven
24 horas no compensa el riesgo. Cloudflare marca `r2.dev` como limitado por
tasa; con 18 imágenes semanales que Meta descarga una vez cada una, no es un
límite real. Si algún día el DNS se muda a Cloudflare, se cambia una línea.

El script borra cada objeto apenas Instagram lo consume; la regla de
lifecycle cubre el caso en que falle antes de limpiar.

**Verificá:** `python -m tools.check_credentials --only bucket`
Sube un archivo, **comprueba que la URL pública responda** y lo borra. Ese
segundo paso es el que importa: si el objeto existe pero la URL no funciona,
Instagram rechaza el post sin explicar por qué.

---

## 5 · Healthchecks.io — 5 min · **lo único que falta además de LinkedIn**

Period **2 días**, no 3: con cadencia lunes/miércoles/viernes, tres días de
silencio ya son dos publicaciones perdidas.

1. healthchecks.io → cuenta gratis → **Add Check**
2. Nombre: `dentread-social` · Period: **2 días** · Grace: **1 día**
3. Copiá la URL de ping

```bash
HEALTHCHECK_URL=https://hc-ping.com/<uuid>
```

Sin esto, si el sistema deja de publicar nadie se entera. Es el modo de falla
más probable.

---

## 6 · GitHub — 15 min

El repo ya está inicializado con dos commits en `main`.

```bash
brew install gh
gh auth login                       # abre el navegador, login tuyo
gh repo create dentread-social --private --source=. --push
```

Después, environment y secrets:

```bash
gh api -X PUT repos/:owner/dentread-social/environments/production
bash tools/gh_secrets.sh            # lee .env y los carga, sin mostrarlos
```

`gh_secrets.sh` es idempotente: volvé a correrlo cuando LinkedIn apruebe y
completes sus cuatro variables. Omite las vacías y avisa cuáles.

Falta a mano en **Settings**:

1. **Pages** → Source: rama `main`, carpeta `/docs`
2. **Secrets and variables → Actions → Variables** →
   `SOCIAL_PUBLISHING_PAUSED` = `false`
   (ponelo en `true` para frenar todo desde el teléfono)
3. DNS: `CNAME insights → <tu-usuario>.github.io`

**Repo privado, pero `docs/` sale por Pages.** Es a propósito: el sitio es el
activo indexable, el código y el estado de rotación no tienen por qué serlo.

---

## 7 · Antes de encender el cron

```bash
python -m tools.check_credentials     # todo verde
python -m pipeline.readiness --slots 3
python -m pipeline.run --slots 3
python publish.py out/<carpeta> --dry-run
```

Y después **dos semanas de `--dry-run` revisando cada salida a mano**. El
sistema publica sin que nadie mire; dos semanas revisadas es lo que te dice si
el filtro sirve, y cuesta cero.

---

## Orden real de tiempos

| | Bloque | Tiempo tuyo | Espera | Estado |
|---|---|---|---|---|
| 1 | Clave Fernet | 1 min | — | ✓ generada |
| 2 | Meta app + permisos | 45 min | — | ✓ 2026-08-09 |
| 2b | App secret + token largo | 5 min | — | pendiente |
| 2c | Verificación con la API | — | — | ✓ 5/5 · @dentread_ · cuota 100/100 |
| 3 | LinkedIn app + request | 30 min | **días** hasta la aprobación | ✓ pedido 2026-08-09 |
| 3b | LinkedIn OAuth | 10 min | bloqueado por la aprobación | pendiente |
| 4 | R2 | 20 min | — | ✓ 2026-08-10 · escritura y URL pública verificadas |
| 5 | Healthchecks | 5 min | — | pendiente |
| 6 | GitHub | 15 min | — | pendiente |

**Instagram ya puede publicar.** Falta LinkedIn (esperando), el ping de salud
y el cron.

Lo único con espera externa es la aprobación del Dev Tier de LinkedIn, ya
pedida. El correo llega de **Microsoft Vetting Services**, no de LinkedIn —
suele caer en spam.
