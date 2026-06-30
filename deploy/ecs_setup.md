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

## 3. Smoke-test it's live
From your laptop (replace with the ECS public IP):
```bash
curl http://<ECS_PUBLIC_IP>:8000/health
# -> {"status":"ok"}
curl -X POST http://<ECS_PUBLIC_IP>:8000/chat \
  -H 'content-type: application/json' \
  -d '{"message":"Remember I prefer tea, then tell me my drink.","session_id":"demo"}'
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
