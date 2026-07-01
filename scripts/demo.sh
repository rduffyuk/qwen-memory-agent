# qwen-memory-agent — demo helpers (source, don't run)
#
# Usage:
#   export IP=localhost        # on the ECS box (SSH session)
#   export IP=47.236.147.17    # from your laptop → the public deploy
#   source scripts/demo.sh
#
# Then each demo beat is one word:
#   health
#   ask     "Remember I prefer coffee in the morning."      # full JSON (shows tool_calls_made)
#   answer  "Actually I prefer tea now. What do I drink?"   # just the .answer line
#   usage                                                    # per-model token metering
#   snapshot                                                 # memory export (JSON + Markdown)
#   dream                                                    # propose consolidations (POST)
#   reset                                                    # box only: wipe store + restart server
#
# Notes:
# - 'export' is a bash builtin, so the memory-export helper is named 'snapshot'.
# - curl uses -sS: no progress bar, but connection errors still print (unlike -s).

: "${IP:=localhost}"
BASE="http://$IP:8000"

health()   { curl -sS "$BASE/health" | jq; }

# full chat object — keep for Beat 1 to show "tool_calls_made": ["remember"] (the agentic proof)
ask()      { curl -sS -X POST "$BASE/chat" -H 'content-type: application/json' \
               -d "{\"message\":\"$1\",\"session_id\":\"${2:-demo}\"}" | jq; }

# just the answer string — clean chat read; pass a 2nd arg for a different session_id
answer()   { curl -sS -X POST "$BASE/chat" -H 'content-type: application/json' \
               -d "{\"message\":\"$1\",\"session_id\":\"${2:-demo}\"}" | jq -r '.answer'; }

usage()    { curl -sS "$BASE/usage" | jq; }

snapshot() { curl -sS "$BASE/memory/export" | jq; }

# the dreaming loop is human-in-the-loop by design:
#   1) dream         -> prints proposals (each with an id)
#   2) review, then apply only the ids you approve:
#      curl -sS -X POST "$BASE/dream/apply" -H 'content-type: application/json' \
#        -d '{"proposals":[<paste from dream>],"approved_ids":["<id>"]}' | jq
dream()    { curl -sS -X POST "$BASE/dream" | jq; }

# box only: clean slate for a fresh take (needs .env in cwd with the DashScope key)
reset() {
  pkill -f "uvicorn memory_agent.api" 2>/dev/null
  rm -f memory.json
  set -a; source .env; set +a
  nohup uv run uvicorn memory_agent.api:app --host 0.0.0.0 --port 8000 > ~/api.log 2>&1 &
  until curl -sS "http://localhost:8000/health" >/dev/null 2>&1; do sleep 0.5; done
  echo "reset: store wiped, server restarted, health ok"
}
