# Deploy on Alibaba Cloud ECS (deploy-proof requirement)

The hackathon requires the **backend to run on Alibaba Cloud**. The DashScope API
key alone is not enough — it must be *called from* an Alibaba Cloud ECS instance.

## 0. Prerequisite check (do this FIRST)
You have **no payment card**. Before investing time, confirm you can actually
create an ECS instance:
- Alibaba Cloud Console → **ECS → Create Instance**. If it demands a card before
  letting you launch the smallest instance, STOP and check whether the hackathon
  **coupon/credits cover ECS compute** (they may cover only DashScope tokens).
- If ECS is blocked without a card, fall back to **Function Compute** (often has a
  no-card free tier) or ask the hackathon manager how entrants without a card
  should satisfy the deploy-proof requirement.

## 1. Provision the instance
- **Type**: smallest burstable is fine — e.g. `ecs.t6-c1m2.large` (2 vCPU / 4 GB)
  or any 2 vCPU / 4 GB. Qdrant runs in embedded local mode, so no DB server.
- **Image**: Ubuntu 22.04 LTS.
- **Network**: assign a public IP. Security group: allow inbound TCP **8000**
  (the API) and **22** (SSH) from your IP.
  - ⚠️ **Lock both ports to your own IP/32, not `0.0.0.0/0`** — the box holds a live
    DashScope key. If your home IP is dynamic (most consumer ISPs), it can rotate
    between sessions; if SSH/curl suddenly can't connect, re-check the security-group
    source against your current IP (`curl -s ifconfig.me`) before debugging anything else.

## 2. Install + run (on the ECS box, over SSH)
```bash
# system deps
sudo apt-get update && sudo apt-get install -y git curl
curl -LsSf https://astral.sh/uv/install.sh | sh        # uv
source $HOME/.local/bin/env

# get the code
git clone https://github.com/rduffyuk/qwen-memory-agent.git
cd qwen-memory-agent
uv sync

# secret — set the key as an env var (NEVER commit it)
export DASHSCOPE_API_KEY="sk-...your-key..."
export DASHSCOPE_BASE_URL="https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# run the backend, reachable on the public IP
uv run uvicorn memory_agent.api:app --host 0.0.0.0 --port 8000
```

For a persistent run, wrap it in a `systemd` unit or `tmux`; or use the
`docker-compose.yml` in this folder.

## 2a. Redeploy after an update (box already running)
When `main` moves ahead of what's on the box (e.g. new endpoints), pull + restart:
```bash
cd ~/qwen-memory-agent
git pull                       # fetch the latest main
uv sync                        # pick up any dependency changes
# restart the server: Ctrl-C the tmux/foreground process, or if it's a systemd unit:
sudo systemctl restart qwen-memory-agent
```
**Restarting is required, not optional** — `git pull` only updates files on disk; the
already-running server keeps serving the OLD code until its process is restarted (a
`404`/`405` on a route you just added is the tell). If `uvicorn` prints
`address already in use`, an old instance still holds the port:
```bash
pkill -f "uvicorn memory_agent.api"      # stop the stale server
ss -ltnp | grep :8000                    # confirm the port is free (prints nothing)
```
Confirm the new surface is live: `curl -X POST http://<ECS_PUBLIC_IP>:8000/dream`
should return `200` with a `proposals` list (older builds without the dreaming loop
return `404`; a `405 Method Not Allowed` means you sent a GET — `/dream` is POST-only).

## 3. Smoke-test it's live (and show off the memory engine)
From your laptop (replace with the ECS public IP). This sequence is also a good
**demo script** — it exercises supersession, budget recall, portability, usage
metering, and the dreaming loop in order:
```bash
IP=<ECS_PUBLIC_IP>

# 1. liveness
curl http://$IP:8000/health                     # -> {"status":"ok"}

# 2. agentic memory + supersession: teach a preference, then update it
curl -sX POST http://$IP:8000/chat -H 'content-type: application/json' \
  -d '{"message":"Remember I prefer coffee in the morning.","session_id":"demo"}'
curl -sX POST http://$IP:8000/chat -H 'content-type: application/json' \
  -d '{"message":"Actually I prefer tea now. What is my morning drink?","session_id":"demo"}'
# -> answers "tea"; the retired "coffee" fact is not surfaced

# 3. token & model observability (per-model usage accumulates across the calls above)
curl -s http://$IP:8000/usage

# 4. portable memory: export the whole store (JSON + Markdown, vectors preserved)
curl -s http://$IP:8000/memory/export

# 5. the dreaming loop: propose consolidations, then apply only what you approve
curl -sX POST http://$IP:8000/dream              # POST (not GET) -> {"proposals":[{ "id": ..., "kind": ... }]}
# review the proposals, then apply the approved ids:
curl -sX POST http://$IP:8000/dream/apply -H 'content-type: application/json' \
  -d '{"proposals":[<paste proposals from /dream>],"approved_ids":["<id-to-approve>"]}'
```

## 4. Capture the deploy proof (separate from the demo video)
A short screen recording that shows the backend is on Alibaba Cloud:
1. The Alibaba Cloud **ECS console** showing your running instance (region + ID).
2. An SSH session on that box running `uvicorn` (the log output).
3. A `curl` from outside hitting `http://<ECS_PUBLIC_IP>:8000/health` → 200.

Then, per the rules, also provide a **link to the code file** that uses Alibaba
Cloud APIs: [`src/memory_agent/qwen.py`](../src/memory_agent/qwen.py) (the DashScope
client). That file + the recording together satisfy the requirement.

## Cost / credit note
- Embedded Qdrant = no managed-DB cost. The only compute cost is the ECS VM.
- Stop/release the instance after recording the proof + demo to avoid burning
  credits while idle.
