#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <frontend-origin> <api-origin>" >&2
  echo "Example: $0 https://secondtrip.example.com https://api.secondtrip.example.com" >&2
  exit 2
fi

frontend_origin="${1%/}"
api_origin="${2%/}"

if [[ "${ALLOW_INSECURE_LOCAL:-0}" != "1" ]]; then
  if [[ "$frontend_origin" != https://* || "$api_origin" != https://* ]]; then
    echo "Both origins must use HTTPS. Set ALLOW_INSECURE_LOCAL=1 only for local checks." >&2
    exit 2
  fi
fi

smoke_dir="$(mktemp -d "${TMPDIR:-/tmp}/secondtrip-smoke-XXXXXXXX")"
trap 'rm -rf -- "$smoke_dir"' EXIT

request() {
  local name="$1"
  local url="$2"
  shift 2
  curl --silent --show-error \
    --connect-timeout 10 \
    --max-time 30 \
    --dump-header "$smoke_dir/$name.headers" \
    --output "$smoke_dir/$name.body" \
    --write-out '%{http_code}' \
    "$@" \
    "$url"
}

require_status() {
  local actual="$1"
  local expected="$2"
  local label="$3"
  if [[ "$actual" != "$expected" ]]; then
    echo "$label returned HTTP $actual; expected $expected." >&2
    exit 1
  fi
  echo "ok  $label ($actual)"
}

require_header() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if ! awk -v pattern="$pattern" \
    'BEGIN { IGNORECASE=1 } $0 ~ pattern { found=1 } END { exit !found }' "$file"; then
    echo "$label is missing or incorrect." >&2
    exit 1
  fi
  echo "ok  $label"
}

require_header_value() {
  local file="$1"
  local header_name="$2"
  local expected="$3"
  local label="$4"
  if ! awk -F ':' -v name="$header_name" -v expected="$expected" '
    {
      current_name=tolower($1)
      if (current_name != tolower(name)) next
      value=substr($0, index($0, ":") + 1)
      sub(/^[[:space:]]+/, "", value)
      sub(/[[:space:]\r]+$/, "", value)
      if (value == expected) found=1
    }
    END { exit !found }
  ' "$file"; then
    echo "$label is missing or incorrect." >&2
    exit 1
  fi
  echo "ok  $label"
}

health_status="$(request api-health "$api_origin/health")"
require_status "$health_status" "200" "API liveness"
if ! awk '/"status"[[:space:]]*:[[:space:]]*"ok"/ { found=1 } END { exit !found }' \
  "$smoke_dir/api-health.body"; then
  echo "API liveness response did not contain status=ok." >&2
  exit 1
fi

ready_status="$(request api-ready "$api_origin/ready")"
require_status "$ready_status" "200" "API readiness"

login_status="$(request frontend-login "$frontend_origin/login")"
require_status "$login_status" "200" "Frontend login page"

app_status="$(request frontend-app "$frontend_origin/app/rework")"
if [[ "$app_status" != "302" && "$app_status" != "307" && "$app_status" != "308" ]]; then
  echo "Unauthenticated app route returned HTTP $app_status; expected a login redirect." >&2
  exit 1
fi
echo "ok  Auth gate redirects unauthenticated requests ($app_status)"
require_header \
  "$smoke_dir/frontend-app.headers" \
  '^cache-control:.*private.*no-store' \
  "Private app cache policy"
require_header \
  "$smoke_dir/frontend-app.headers" \
  '^x-robots-tag:.*noindex.*nofollow' \
  "Private app robots policy"

cors_status="$(request api-cors "$api_origin/api/v1/me" \
  --request OPTIONS \
  --header "Origin: $frontend_origin" \
  --header 'Access-Control-Request-Method: GET')"
require_status "$cors_status" "200" "API CORS preflight"
require_header_value \
  "$smoke_dir/api-cors.headers" \
  "access-control-allow-origin" \
  "$frontend_origin" \
  "Exact CORS origin"
require_header_value \
  "$smoke_dir/api-cors.headers" \
  "access-control-allow-credentials" \
  "true" \
  "Credentialed CORS"

private_status="$(request api-private "$api_origin/api/v1/orgs")"
require_status "$private_status" "401" "Unauthenticated tenant API"
require_header \
  "$smoke_dir/api-private.headers" \
  '^cache-control:.*private.*no-store' \
  "Tenant API cache policy"
require_header "$smoke_dir/api-private.headers" '^x-request-id:' "API request ID"
require_header \
  "$smoke_dir/api-private.headers" \
  '^x-content-type-options:[[:space:]]*nosniff' \
  "API content-type protection"

echo
echo "SecondTrip deployment smoke check passed."
echo "This read-only check does not verify email delivery, R2, migrations, or login."
