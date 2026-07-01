# Demo script — qwen-memory-agent (~3 min)

Track 1 · MemoryAgent · Qwen Cloud / Alibaba ECS. Rubric: Technical Depth 30% · Innovation 30% · Problem Value 25% · Presentation 15%.

## Setup (off camera)
```bash
# on the ECS box (SSH):   export IP=localhost
# from your laptop:       export IP=47.236.147.17   (the public deploy)
source scripts/demo.sh
reset          # box only: clean store + fresh server, so you open on zeros
```
**Film in the memory inspector: `http://<ECS_PUBLIC_IP>:8000/demo`** — chat on the left,
live memory table on the right (superseded rows strike through on screen), dream panel below.
Judges *watch* forgetting happen instead of reading JSON. Keep a terminal beside it for the
`snapshot` beat; second browser tab on `docs/architecture.png` + `benchmark/results/context_efficiency.png`.

---

## [0:00–0:20] Hook — the problem
Show `health` then `usage` (all zeros — starting from nothing).
> "Every agent that meets a user twice hits the same wall: where memories live, when to forget stale ones, and how to fit the *right* memory into a tight context window. Most demos just stuff the whole history in. This treats memory as a measurable engineering problem — on Qwen Cloud, deployed on Alibaba ECS."

## [0:20–1:00] Beat 1 — agentic memory + supersession (the hero) · Innovation
In the inspector: type *"Remember I prefer coffee in the morning."* — the `tool: remember`
chip appears on the reply and the coffee row pops into the live table. Then type
*"Actually I prefer tea now. What is my morning drink?"* — on screen, **coffee strikes
through to `superseded` as tea lands**. That visual is the pitch. Back it with the terminal:
```bash
snapshot        # show the coffee record with superseded_by pointing at tea
```
> "The agent itself decides to call `remember` — that's Qwen function-calling; an agent *with* memory, not a database with an LLM bolted on." *(point at `tool_calls_made: ["remember"]`)*
> "Now I contradict myself… and it answers **tea**. The old fact wasn't just outranked — it was **retired**: here's coffee marked `superseded_by` the tea record. Timely forgetting — exact match plus a cosine pass for paraphrases."

## [1:00–1:30] Beat 2 — budget-constrained recall · Technical Depth
```bash
curl -sS -X POST "$BASE/chat" -H 'content-type: application/json' \
  -d '{"message":"What do I drink?","session_id":"demo","token_budget":32}' | jq
```
> "Retrieval scores every memory by cosine + recency + salience + a type prior, then greedily packs to a hard token budget — Qdrant-backed vector search, not an in-process shortcut. Relevant context stays small even as memory grows."

## [1:30–2:00] Beat 3 — token observability · engineering rigor
```bash
usage
```
> "Every Qwen call is metered per model — `qwen-plus` for reasoning, `text-embedding-v3` for vectors. Cost is a first-class signal, not a mystery."

## [2:00–2:35] Beat 4 — the dreaming loop · Innovation (the differentiator)
In the inspector: press **Dream** — proposals appear with checkboxes; tick one, press
**Apply approved**. Nothing changes until the human approves (say that out loud).
Terminal equivalent if you prefer:
```bash
dream           # proposes consolidations, each with an id
# then apply ONLY an approved id (human-in-the-loop):
curl -sS -X POST "$BASE/dream/apply" -H 'content-type: application/json' \
  -d '{"proposals":[<paste from dream>],"approved_ids":["<id>"]}' | jq
```
> "An out-of-band Qwen pass proposes consolidations — merge, forget, re-salience. But it's human-in-the-loop: nothing applies until I approve, and it validates every proposal against live record ids, so it **refuses to act on its own hallucinations.**"

## [2:35–3:00] Close — the proof · Presentation + credibility
Switch to the browser: `benchmark/results/context_efficiency.png`.
> "And this isn't 'it remembered my name.' A reproducible, offline benchmark scores four systems on a shrinking token budget. Ours — B3 — holds **recall 1.0, staleness 0.0 at every budget.** The sharp finding: naive RAG's staleness *rises* with budget — more context drags the retired fact back. Only ours stays correct **and** small. Measured, not asserted. MIT-licensed, portable, on Alibaba Cloud."

---

## Filming notes
- Show the **full object once** in Beat 1 (`ask`) so `tool_calls_made` is visible; use `answer` after that so it reads like a chat.
- The `snapshot` → `superseded_by` moment is your most convincing 5 seconds — don't rush it.
- Keep the **deploy-proof clip separate** (ECS console + `uvicorn` log + external `curl /health` → 200) per the rules; this video is about the features.
- Run `reset` right before the real take so `usage` opens on zeros.
