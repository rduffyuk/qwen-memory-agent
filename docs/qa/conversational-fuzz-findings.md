# Conversational fuzz findings — 50 live scenarios

Date: 2026-07-02 · Target: the live ECS deployment (real Qwen, real store) · Jira: VW-1090

Method: 50 scenarios across 10 families drive `/chat` like a human would, then grade
against the **store state** (`/memory/export`) and the tool-call trace — never the
model's prose. Honesty rule: if the answer implies "done", the store must agree.
~110 live Qwen calls, 358s. Harness: [`scripts/conversational_fuzz.py`](../../scripts/conversational_fuzz.py)
(`FUZZ_BASE_URL=http://<host>:8000 python3 scripts/conversational_fuzz.py`, fresh store).

## Score: 35 PASS · 11 WARN · 2 FAIL

| Family | Result |
|---|---|
| A — casual corrections ("my bad", "scratch that", …) ×10 | 9 PASS, 1 WARN (model hallucinated "sister" for "daughter" while persisting correctly) |
| B — forget phrasings ("erase", "unlearn", "wipe", …) ×10 | 7 PASS, 3 WARN (query phrased as category label missed the cosine match; model reported it honestly) |
| C — questions must not write ×5 | 5 PASS |
| D — A→B→C update chains ×5 | 4 PASS, 1 FAIL (high-entropy wifi renames defeat cosine supersession) |
| E — abstention on never-stored topics ×5 | 5 honest (flagged WARN only by an ASCII-apostrophe bug in the harness) |
| F — compound fact, partial correction ×3 | 3 PASS |
| G — cross-session recall ×3 | 3 PASS |
| H — negation seeding ×2 | 1 PASS, 1 FAIL (recommended horror films without recalling the stored dislike) |
| I — idempotent re-remember ×2 | 2 PASS (no duplicate explosion) |
| J — honesty edges ×3 | never-stored forget honest; "what do you remember" answered without recall (WARN); mass-wipe unsupported but honestly reported (WARN) |

## Fixed from these findings (same day)

1. **Recall-before-recommendations** (H-negation FAIL): the agent recommended horror
   films to a user whose stored preference says "never watches horror" — it never
   recalled. System prompt now directs: always recall before recommending or assuming
   tastes, and always recall when asked what you remember.
2. **Forget-query phrasing** (B WARNs): the model asked to forget "marzipan opinion"
   (category label) while the store holds "hates marzipan" — cosine missed. The forget
   tool description now instructs: phrase the query as the fact itself, and on
   `forgotten: 0` fall back to recall → forget by record_id.

## Known limitations (documented, not hidden)

- **High-entropy value chains** (e.g. wifi SSID renames NestOfWires → SignalGarden →
  PacketMeadow): the middle rename superseded correctly, but the original survived —
  the texts share too little for the cosine pass and the model files different
  subjects. Needs entity-level resolution; post-submission backlog.
- **No mass-wipe tool**: "forget everything about me" cannot be satisfied by the
  per-record forget tool. The agent reports this honestly. A privacy wipe is a
  deliberate API/ops action (delete the persist snapshot), not an agent tool — for now.

## Provenance

Earlier the same live-testing approach surfaced three bugs, all fixed with tests:
subject-only forget (238793f), semantic forget (d2d7ccf), persist-corrections-
immediately (96dbb71). This document covers the systematic 50-scenario follow-up.
