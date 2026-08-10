#!/usr/bin/env bash
# Carga en GitHub los secrets que ya están en .env, sin que ninguno pase por
# pantalla, por el historial del shell ni por un chat.
#
#   brew install gh && gh auth login
#   bash tools/gh_secrets.sh
#
# Idempotente: correlo de nuevo cuando LinkedIn apruebe y agregues sus tokens.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] || { echo "No hay .env en $(pwd)"; exit 1; }

ENV_NAME="production"

KEYS=(
  TOKEN_STORE_KEY HEALTHCHECK_URL
  META_APP_ID META_APP_SECRET META_ACCESS_TOKEN IG_USER_ID
  LINKEDIN_CLIENT_ID LINKEDIN_CLIENT_SECRET
  LINKEDIN_ACCESS_TOKEN LINKEDIN_REFRESH_TOKEN LINKEDIN_ORG_URN
  S3_ENDPOINT S3_ACCESS_KEY_ID S3_SECRET_ACCESS_KEY S3_BUCKET S3_PUBLIC_BASE
)

loaded=0; skipped=0
for key in "${KEYS[@]}"; do
  # Se lee del .env sin evaluarlo: un `source` ejecutaría cualquier cosa que
  # tenga el archivo, y acá solo queremos el valor literal.
  value="$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- || true)"
  if [ -z "$value" ]; then
    printf '  ·  %-24s vacío en .env, se omite\n' "$key"
    skipped=$((skipped + 1))
    continue
  fi
  printf '%s' "$value" | gh secret set "$key" --env "$ENV_NAME" --body -
  printf '  ✓  %-24s cargado\n' "$key"
  loaded=$((loaded + 1))
done

echo
echo "$loaded cargados, $skipped omitidos, en el environment '$ENV_NAME'."
[ "$skipped" -gt 0 ] && echo "Volvé a correr esto cuando completes los que faltan."
exit 0
