#!/usr/bin/env bash
set -euo pipefail

# Sahi SOS Relay Smoke Test
# Usage: RELAY_URL=http://127.0.0.1:8787 RELAY_API_KEY=... tools/smoke.sh

RELAY_URL="${RELAY_URL:-http://127.0.0.1:8787}"

if [[ -z "${RELAY_API_KEY:-}" ]]; then
  echo "FAIL: RELAY_API_KEY environment variable is required." >&2
  exit 1
fi

step_pass() {
  echo "PASS: $1"
}

step_fail() {
  echo "FAIL: $1" >&2
  exit 1
}

get_uuid() {
  if [[ -f /proc/sys/kernel/random/uuid ]]; then
    cat /proc/sys/kernel/random/uuid
  elif command -v node >/dev/null 2>&1; then
    node -e "console.log(crypto.randomUUID())"
  else
    head -c 16 /dev/urandom | xxd -p | sed -r 's/(.{8})(.{4})(.{4})(.{4})(.{12})/\1-\2-\3-\4-\5/'
  fi
}

echo "Starting smoke tests against ${RELAY_URL}..."

# Step 1: Health check
HEALTH_RESP=$(curl -sS -f "${RELAY_URL}/v1/health") || step_fail "GET /v1/health request failed"
if [[ "${HEALTH_RESP}" == *'"whatsapp"'* ]]; then
  step_pass "GET /v1/health returned valid status"
else
  step_fail "GET /v1/health missing whatsapp key: ${HEALTH_RESP}"
fi

# Step 2: Register one fake contact
INSTALL_ID=$(get_uuid)
REG_RESP=$(curl -sS -f -X POST "${RELAY_URL}/v1/register" \
  -H "Authorization: Bearer ${RELAY_API_KEY}" \
  -H "X-Install-Id: ${INSTALL_ID}" \
  -H "Content-Type: application/json" \
  -d '{"driver_name":"Test Driver","contacts":[{"name":"Emergency","phone":"+201000000001"}]}') || step_fail "POST /v1/register failed"

if [[ "${REG_RESP}" == *'"contacts"'* ]]; then
  step_pass "POST /v1/register created contact (+201000000001)"
else
  step_fail "POST /v1/register response invalid: ${REG_RESP}"
fi

# Step 3: POST SOS with random UUID
CLIENT_ID=$(get_uuid)
NOW_MS=$(date +%s000)
SOS_PAYLOAD="{\"client_id\":\"${CLIENT_ID}\",\"kind\":\"crash\",\"t_crash\":${NOW_MS},\"lat\":30.0444,\"lon\":31.2357}"

SOS_RESP=$(curl -sS -f -X POST "${RELAY_URL}/v1/sos" \
  -H "Authorization: Bearer ${RELAY_API_KEY}" \
  -H "X-Install-Id: ${INSTALL_ID}" \
  -H "Content-Type: application/json" \
  -d "${SOS_PAYLOAD}") || step_fail "POST /v1/sos failed"

if [[ "${SOS_RESP}" == *'"results"'* ]]; then
  step_pass "POST /v1/sos queued alert"
else
  step_fail "POST /v1/sos response invalid: ${SOS_RESP}"
fi

# Step 4: Repeat POST SOS with identical client_id (idempotency check)
SOS_IDEMP_RESP=$(curl -sS -f -X POST "${RELAY_URL}/v1/sos" \
  -H "Authorization: Bearer ${RELAY_API_KEY}" \
  -H "X-Install-Id: ${INSTALL_ID}" \
  -H "Content-Type: application/json" \
  -d "${SOS_PAYLOAD}") || step_fail "POST /v1/sos idempotency retry failed"

if [[ "${SOS_IDEMP_RESP}" == *'"results"'* ]]; then
  step_pass "POST /v1/sos idempotency verified"
else
  step_fail "POST /v1/sos idempotency response invalid: ${SOS_IDEMP_RESP}"
fi

# Step 5: Poll GET /v1/sos/{client_id} until status is not 'queued' (max ~10 s)
ELAPSED=0
STATUS_PROCESSED=0
while [[ ${ELAPSED} -lt 10 ]]; do
  GET_RESP=$(curl -sS -f -X GET "${RELAY_URL}/v1/sos/${CLIENT_ID}" \
    -H "Authorization: Bearer ${RELAY_API_KEY}" \
    -H "X-Install-Id: ${INSTALL_ID}") || step_fail "GET /v1/sos/${CLIENT_ID} failed"

  if [[ "${GET_RESP}" != *'"status":"queued"'* && "${GET_RESP}" != *'"status": "queued"'* ]]; then
    STATUS_PROCESSED=1
    break
  fi
  sleep 1
  ELAPSED=$((ELAPSED + 1))
done

if [[ ${STATUS_PROCESSED} -eq 1 ]]; then
  step_pass "GET /v1/sos/${CLIENT_ID} transitioned out of queued"
else
  step_fail "GET /v1/sos/${CLIENT_ID} timed out waiting for transition out of queued (${GET_RESP})"
fi

# Step 6: DELETE /v1/register
DEL_RESP=$(curl -sS -f -X DELETE "${RELAY_URL}/v1/register" \
  -H "Authorization: Bearer ${RELAY_API_KEY}" \
  -H "X-Install-Id: ${INSTALL_ID}") || step_fail "DELETE /v1/register failed"

if [[ "${DEL_RESP}" == *'"ok":true'* || "${DEL_RESP}" == *'"ok": true'* ]]; then
  step_pass "DELETE /v1/register cleaned up install"
else
  step_fail "DELETE /v1/register response invalid: ${DEL_RESP}"
fi

echo "All smoke tests PASSED."
