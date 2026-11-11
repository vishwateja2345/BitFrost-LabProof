#!/usr/bin/env bash
# Live check: `labproof brief --live` against a real Bifrost gateway container, a real local language model served by
# Ollama and the real Tavily API. Needs Docker, Python 3.12+, curl,
# an Ollama server with the model already pulled, and TAVILY_API_KEY in the environment. One run of a single-class
# pack costs about 1 Tavily credit per search mode; the three-class replay costs about 3. See docs/BRIEF.md.
#
#   TAVILY_API_KEY=... scripts/live-brief/run.sh               # searches directly, then through the Bifrost relay
#   MODES=relay LIVE_MODEL=qwen2.5:3b CALL_TIMEOUT=150 scripts/live-brief/run.sh
#   RUN_DIR=runs/demo scripts/live-brief/run.sh                 # any completed run that passes verify-artifacts
#   KEEP_GATEWAY=1 scripts/live-brief/run.sh                    # leave the gateway running
#   OLLAMA_URL=http://127.0.0.1:11434 BIFROST_IMAGE=maximhq/bifrost:v2.4.0 GATEWAY_PORT=8080 are the defaults
#
# The Tavily key is handed to the gateway container (relay mode) and, in direct mode, to the labproof process only.
# The virtual key is generated per run and written only into the output directory when KEEP_GATEWAY=1.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
IMAGE="${BIFROST_IMAGE:-maximhq/bifrost:v2.4.0}"
PORT="${GATEWAY_PORT:-8080}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
OLLAMA_PROVIDER_URL="${OLLAMA_PROVIDER_URL:-}"
LIVE_MODEL="${LIVE_MODEL:-qwen2.5:3b}"
MODES="${MODES-direct relay}"   # an empty MODES only starts the gateway (with KEEP_GATEWAY=1 it stays up)
RUN_DIR="${RUN_DIR:-$ROOT/evidence/local-python-01}"
CALL_TIMEOUT="${CALL_TIMEOUT:-60}"
[[ "$CALL_TIMEOUT" =~ ^[0-9]+$ ]] && [ "$CALL_TIMEOUT" -ge 10 ] && [ "$CALL_TIMEOUT" -le 180 ] || { echo "CALL_TIMEOUT must be a whole number of seconds from 10 to 180" >&2; exit 2; }
OUT="${OUT_DIR:-$ROOT/runs/live-brief-$(date +%Y%m%d-%H%M%S)}"
PYTHON_BIN="${PYTHON:-python3}"
NAME="labproof-bifrost-$$"
WORK="$(mktemp -d)"
network=(--network host)
bind_host=127.0.0.1
platform="$(uname -s)"
if [ "$platform" = Darwin ] || [ -n "${BIFROST_DOCKER_NETWORK:-}" ]; then
  network=(--network "${BIFROST_DOCKER_NETWORK:-bridge}" -p "127.0.0.1:$PORT:$PORT")
  bind_host=0.0.0.0
fi
if [ -z "$OLLAMA_PROVIDER_URL" ]; then
  OLLAMA_PROVIDER_URL="$OLLAMA_URL"
  if [ "$platform" = Darwin ]; then
    case "$OLLAMA_URL" in
      http://127.0.0.1:*) OLLAMA_PROVIDER_URL="http://host.docker.internal:${OLLAMA_URL#http://127.0.0.1:}" ;;
      http://localhost:*) OLLAMA_PROVIDER_URL="http://host.docker.internal:${OLLAMA_URL#http://localhost:}" ;;
    esac
  fi
fi

cleanup() {
  # A gateway left running keeps its SQLite files in $WORK, so keep that directory with it.
  if [ "${KEEP_GATEWAY:-0}" = "1" ]; then return; fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

for tool in docker curl "$PYTHON_BIN"; do command -v "$tool" >/dev/null 2>&1 || { echo "$tool is required" >&2; exit 2; }; done
: "${TAVILY_API_KEY:?set TAVILY_API_KEY; it is handed to the gateway container (relay) and to the direct-search run only}"
[ -d "$RUN_DIR" ] || { echo "RUN_DIR $RUN_DIR is not a directory" >&2; exit 2; }
PYTHONPATH="$ROOT/src" "$PYTHON_BIN" -m labproof verify-artifacts "$RUN_DIR" >/dev/null || { echo "RUN_DIR does not pass verify-artifacts" >&2; exit 2; }
curl -fsS -m 10 "$OLLAMA_URL/api/tags" | "$PYTHON_BIN" -c '
import json, sys
wanted = sys.argv[1]
names = [m["name"] for m in json.load(sys.stdin).get("models", [])]
sys.exit(0 if wanted in names or wanted + ":latest" in names else "model " + wanted + " is not pulled in Ollama; have: " + ", ".join(names))' "$LIVE_MODEL"

export BIFROST_VIRTUAL_KEY="${BIFROST_VIRTUAL_KEY:-sk-bf-$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_hex(16))')}"
SETUP_TOKEN="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_hex(16))')"   # only protects the gateway's /api routes
mkdir -p "$WORK/data" "$OUT"
"$PYTHON_BIN" - "$HERE/config.json" "$WORK/data/config.json" "$LIVE_MODEL" "$OLLAMA_PROVIDER_URL" "$((CALL_TIMEOUT - 5))" <<'PY'
import json
from pathlib import Path
import sys

template, output, model, provider_url, timeout = sys.argv[1:]
config = json.loads(Path(template).read_text(encoding="utf-8"))
provider = config["providers"]["ollama"]
provider["network_config"].update(base_url=provider_url, allow_private_network=True, default_request_timeout_in_seconds=int(timeout))
provider["keys"][0].update(models=[model], ollama_key_config={"url": provider_url})
config["governance"]["virtual_keys"][0]["provider_configs"][0]["allowed_models"] = [model]
Path(output).write_text(json.dumps(config), encoding="utf-8")
PY
chmod -R a+rwX "$WORK/data"
# Behind a TLS-inspecting proxy the gateway must trust the host's CA bundle to reach api.tavily.com.
if [ -f /etc/ssl/certs/ca-certificates.crt ]; then
  network+=(-v /etc/ssl/certs/ca-certificates.crt:/etc/ssl/certs/ca-certificates.crt:ro)
fi

docker image inspect "$IMAGE" >/dev/null 2>&1 || docker pull "$IMAGE"
docker run -d --name "$NAME" "${network[@]}" \
  -e APP_HOST="$bind_host" -e APP_PORT="$PORT" -e BIFROST_SETUP_TOKEN="$SETUP_TOKEN" \
  -e BIFROST_VIRTUAL_KEY -e TAVILY_API_KEY \
  -v "$WORK/data:/app/data" "$IMAGE" >/dev/null
for _ in $(seq 1 90); do curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break; sleep 1; done
if ! curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  echo "the gateway did not become healthy; last log lines:" >&2
  docker logs --tail 30 "$NAME" >&2 || true
  exit 1
fi
echo "gateway: $(docker inspect --format '{{.Config.Image}}' "$NAME") on 127.0.0.1:$PORT, model ollama/$LIVE_MODEL, run $RUN_DIR, output $OUT"

# Load the model into memory first so that loading time does not eat into the per-call timeout.
curl -fsS -m 300 "http://127.0.0.1:$PORT/v1/chat/completions" -H "x-bf-vk: $BIFROST_VIRTUAL_KEY" -H 'Content-Type: application/json' \
  -d "{\"model\":\"ollama/$LIVE_MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with the word ready.\"}],\"max_tokens\":8}" \
  | "$PYTHON_BIN" -c 'import json, sys; r = json.load(sys.stdin); print("warm-up reply:", repr(r["choices"][0]["message"]["content"]), "usage:", r.get("usage"))'

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
status=0
for mode in $MODES; do
  search=(--tavily-key-env TAVILY_API_KEY)
  [ "$mode" = "relay" ] && search=(--search-relay tavily)
  code=0
  "$PYTHON_BIN" -m labproof brief "$RUN_DIR" --live --confirm-outbound --gateway-url "http://127.0.0.1:$PORT" \
    --model "ollama/$LIVE_MODEL" --gateway-token-env BIFROST_VIRTUAL_KEY "${search[@]}" --gateway-timeout "$CALL_TIMEOUT" \
    --output "$OUT/$mode" >"$OUT/$mode-summary.json" || code=$?
  echo "$mode: labproof brief exit code $code (0 = every class sourced, 2 = partial, 1 = refused)"
  if [ "$code" -eq 1 ]; then status=1; continue; fi
  "$PYTHON_BIN" -m labproof verify-brief "$RUN_DIR" "$OUT/$mode" >"$OUT/$mode-verify.json" || { echo "$mode: verify-brief FAILED" >&2; status=1; continue; }
  if [ "$code" -eq 2 ] && [ "$status" -eq 0 ]; then status=2; fi
  "$PYTHON_BIN" - "$OUT/$mode/brief.json" <<'PY'
import json, sys
brief = json.load(open(sys.argv[1], encoding="utf-8"))
for entry in brief["classes"]:
    print(f"  {entry['check_id']}: {entry['status']}, {len(entry['sources'])} source(s), {len(entry['recommendations'])} verified recommendation(s), {len(entry['rejected'])} rejected")
print(f"  search via {brief['search']['via']}: {brief['search']['calls']} call(s), credits {brief['search']['credits']}; model {brief['model']['requested']}: {brief['model']['calls']} call(s), tokens {brief['model']['tokens']}")
PY
done

curl -fsS -m 15 "http://127.0.0.1:$PORT/api/relay-logs/stats" -H "X-Bifrost-Setup-Token: $SETUP_TOKEN" | head -c 600 | sed 's/^/relay log stats: /' || true
echo
if [ "${KEEP_GATEWAY:-0}" = "1" ]; then
  (umask 077; printf '%s\n' "$BIFROST_VIRTUAL_KEY" >"$OUT/virtual-key.txt"; printf '%s\n' "$SETUP_TOKEN" >"$OUT/setup-token.txt")
  echo "gateway left running as $NAME on 127.0.0.1:$PORT (data in $WORK). The virtual key is in $OUT/virtual-key.txt."
  echo "Stop it with: docker rm -f $NAME && rm -rf $WORK"
fi
exit "$status"
