#!/usr/bin/env bash
# End-to-end smoke test of the Compose stack (api + worker + postgres), used in CI.
# Without a Groq key the incident must travel api -> queue -> worker container and end as
# failed/llm_not_configured, which proves migrations, the API, the queue and the separate worker all work.
set -euo pipefail
LOG="$(mktemp)"
exec > >(tee "${LOG}") 2>&1

KEY="ci-smoke-$(date +%s)"
cat > .env <<EOF
API_KEY=${KEY}
ALLOWED_REPOSITORIES=demo/inventory
LOG_LEVEL=WARNING
EOF

cleanup() {
  code=$?
  if [ "${code}" -ne 0 ] && [ -n "${GITHUB_ACTIONS:-}" ]; then
    # Surface the cause as an annotation (readable without access to the raw job log).
    report="$( { echo "--- script output"; tail -n 25 "${LOG}"; echo "--- containers"; docker compose ps -a; } 2>&1 | tail -c 6000 )"
    report="${report//'%'/'%25'}"; report="${report//$'\r'/}"; report="${report//$'\n'/'%0A'}"
    echo "::error title=compose smoke test failed::${report}"
  fi
  docker compose logs --no-color --tail=50 || true
  docker compose down -v || true
  rm -f .env
}
trap cleanup EXIT

docker compose up -d --build --wait --wait-timeout 180

curl -fsS http://localhost:8000/readyz
echo
ID=$(curl -fsS -X POST http://localhost:8000/webhook/incident \
  -H "X-API-Key: ${KEY}" -H "Content-Type: application/json" \
  -d '{"repo_name":"demo/inventory","error_message":"TypeError: smoke"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["incident_id"])')
echo "submitted ${ID}"

for _ in $(seq 1 30); do
  BODY=$(curl -fsS "http://localhost:8000/incidents/${ID}" -H "X-API-Key: ${KEY}")
  STATUS=$(echo "${BODY}" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["status"], d["error_category"])')
  echo "status: ${STATUS}"
  if [ "${STATUS}" = "failed llm_not_configured" ]; then
    echo "OK: processed by the worker container"
    exit 0
  fi
  sleep 2
done
echo "incident was not processed in time" >&2
exit 1
