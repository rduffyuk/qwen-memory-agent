# Active-use eval findings — live ECS runs

Date: 2026-07-02 · Target: the live ECS deployment (real Qwen, real store, fresh
before each run) · Harness: [`benchmark/active_use.py`](../../benchmark/active_use.py)
via [`scripts/active_use_live.py`](../../scripts/active_use_live.py).

Why this eval exists: MemoryArena (arXiv 2602.16313) showed agents that score
near-perfectly on passive-recall benchmarks drop to 40-60% task success when a
memory written in one session must gate a decision in a later one. Our retrieval
benchmark is passive-recall; this eval closes that gap: 10 multi-session scenarios,
each graded by three independent oracles (decision outcome, store state, and
recall-before-decision in the tool-call trace).

## Run 1 — task_success 3/10: real failures AND harness bugs

The first live run scored 0.30. Triage against the store dump split the failures
into two piles — three genuine agent defects and three harness defects. Both are
documented because the second pile is a finding about *building* memory evals,
not just running them.

### Real agent failures (kept; the eval is doing its job)

1. **Decision turns skip recall (3/10 scenarios).** Asked "which editor should I
   set up?", the agent recommended **VS Code** to a user whose stored fact says
   "uses Neovim exclusively and refuses to touch VS Code" — it never called
   `recall`, despite the system prompt's recall-before-recommendations directive.
   Same pattern on the meeting-time and city scenarios ("I don't yet know where
   you live" — the answer was one recall away). This is the exact
   passive-vs-active gap MemoryArena predicts; a recall-accuracy benchmark can
   never see it.
2. **Generic-subject collision → false supersession (new defect class).** The
   model filed unrelated facts under the same generic subject (`user`), and the
   write path's one-active-per-`(subject, type)` rule then retired an *unrelated*
   constraint: "Dinner budget is £20 per person" superseded "The user is vegan."
   A dietary constraint was silently destroyed by a budget fact. The exact-match
   supersession heuristic is too aggressive when the model chooses vague subjects.
3. **Cross-subject paraphrase supersession missed (predicted band, confirmed
   live).** "Lives in Porto, not Valencia" did not retire "Lives in Valencia":
   different inferred subjects, and the pair cosine fell below
   `SUPERSEDE_THRESHOLD=0.9` — the 0.7-0.9 blind band called out in
   `docs/embedding-validation.md`. The stale city stayed active.

Defects 2 and 3 are two sides of one problem: exact-subject supersession is
*over*-eager on vague subjects and the semantic pass is *under*-eager on
cross-subject paraphrases. Candidate fix (post-submission): supersede on exact
subject match ONLY when the pair cosine also clears a floor, and flag the
0.7-0.9 band for the dreaming loop to consolidate instead of acting silently.

### Harness defects (fixed before run 2, each now pinned by a test)

1. **Too-narrow outcome lists.** "Vegetable Biryani" is a correct vegetarian
   answer; the expect list didn't contain it. Lists broadened to constraint
   evidence, not specific dishes.
2. **Negation false-positive.** The agent CORRECTLY said "avoid shrimp, lobster,
   crab" for the shellfish-allergy hamper and the species `must_not` list
   penalized the avoidance sentence. `must_not` is now reserved for tokens a
   correct answer would essentially never contain.
3. **Cross-scenario store contamination.** Three scenarios shared diet
   vocabulary; because all scenarios run against ONE deployment store, their
   records cross-superseded and store checks graded contamination, not behavior
   (this is also how defect 2 above was discovered). Every scenario now owns a
   unique constraint domain, enforced by
   `test_store_keywords_are_isolated_across_scenarios`.

## Run 2 — after harness fixes (agent code UNCHANGED)

**task_success 0.60** (outcome 0.80 · store 0.90 · process 0.70 · violations 0.00)
— by depth: d1 0.67 (n=6), d2 0.33 (n=3), d3 1.00 (n=1). Committed as
`benchmark/results/active_use.json` (provenance `live-47.236.147.17-2026-07-02`).

0.60 lands inside the 40-60% band MemoryArena reports for systems that ace
passive recall — our own agent replicates the field's headline finding. Every
run-2 failure is one of the real defects above, none is a scorer artifact:

- **Recall-skip reproduced exactly (3/10, same three scenarios as run 1)**:
  meeting-time ("I don't have information about..."), editor (recommended
  VS Code again), and city ("could you tell me your city?") — deterministic
  enough to be a prompt/policy defect, not sampling noise. The store held the
  answer in all three cases (store_pass=True).
- **Both supersession defects captured on ONE record**: at scoring time,
  "Has quit caffeine completely; drinks decaf only" had NOT retired "Drinks a
  double espresso every morning" (cross-subject paraphrase below the 0.9
  cosine threshold - defect 3). Later, an unrelated scenario's write filed
  under the generic subject `user` DID retire it (subject collision - defect
  2). The espresso record was first wrongly kept, then wrongly killed.

## Method note

Agent source was not modified between runs — run 2 differs only in harness
fixes, so its score is the honest measure of the deployed agent. The three real
defects above remain open and documented; fixing them belongs to a code change
with its own tests, not to the eval.
