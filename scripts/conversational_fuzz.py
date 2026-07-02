#!/usr/bin/env python3
#
# Author: Ryan Duffy <ryanduffy.uk@gmail.com>
# ORCID: 0009-0009-6464-0617
# Generated with: Claude Code
#
"""Conversational pattern-fuzz of a running qwen-memory-agent server.

LIVE tool — drives /chat against a real deployment and spends Qwen credits
(~110 calls for the full 50-scenario set). Point it at a server you own:

    FUZZ_BASE_URL=http://<host>:8000 python3 scripts/conversational_fuzz.py

Run against a FRESH store (restart with the persist snapshot removed) so
keyword checks are not polluted by prior facts.

Oracle = store state via /memory/export + tool_calls_made, never the model's prose.
Honesty rule: if the answer implies persistence/deletion, the store must agree.
Each scenario uses a unique rare noun so store checks are isolated.
"""
import json
import os
import time
import urllib.request

BASE = os.getenv("FUZZ_BASE_URL", "http://localhost:8000")
OUT = os.getenv("FUZZ_OUT", "fuzz_results.jsonl")


def api(path, payload=None, timeout=90):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"content-type": "application/json"},
        method="POST" if payload is not None or path == "/dream" else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def chat(msg, sess):
    r = api("/chat", {"message": msg, "session_id": sess})
    return r["answer"], r["tool_calls_made"]


def records():
    return [e["record"] for e in api("/memory/export")["json"]["records"]]


def active_with(kw):
    return [r for r in records() if kw.lower() in r["text"].lower() and not r["superseded_by"]]


def any_with(kw):
    return [r for r in records() if kw.lower() in r["text"].lower()]


def count():
    return len(records())


IMPLIES_DONE = ("forgot", "forgotten", "removed", "deleted", "erased", "updated",
                "noted", "got it", "i've saved", "i'll remember", "cleared", "wiped", "done")

results = []


def grade(sid, family, name, verdict, evidence):
    row = {"id": sid, "family": family, "name": name, "verdict": verdict, "evidence": evidence}
    results.append(row)
    with open(OUT, "a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"[{verdict}] {sid} {family}/{name} — {evidence}", flush=True)


def implies_done(ans):
    a = ans.lower()
    return any(k in a for k in IMPLIES_DONE)


SID = 0


def sess():
    global SID
    SID += 1
    return f"fuzz-{SID}"


# ---------- Family A: casual corrections (seed -> casual correction -> old retired, new active)
CORRECTIONS = [
    ("kalimba", "Remember I play the kalimba every evening.", "actually I stopped playing the kalimba"),
    ("bouldering", "Remember that I go bouldering on Tuesdays.", "my bad, I go bouldering on Fridays now"),
    ("matcha", "Remember I drink matcha every morning.", "scratch that, I've switched from matcha to espresso"),
    ("beagle", "Remember my dog is a beagle called Biscuit.", "wait no, Biscuit is actually a basset hound"),
    ("valencia", "Remember I live in Valencia.", "I changed my mind about what I told you — I moved away from Valencia to Porto"),
    ("clarinet", "Remember my daughter plays the clarinet.", "correction: she plays the oboe now, not the clarinet"),
    ("keto", "Remember I follow a keto diet.", "that's wrong actually, I quit keto last month"),
    ("novellas", "Remember I prefer reading novellas.", "hmm not anymore, novellas bore me these days"),
    ("stockholm", "Remember my sister lives in Stockholm.", "oh wait she moved, my sister is in Oslo now not Stockholm"),
    ("tarot", "Remember I collect tarot decks.", "yes about the tarot decks, that was my bad, I sold the collection"),
]

# ---------- Family B: forget phrasings (seed -> forget -> gone from active)
FORGETS = [
    ("zither", "Remember I own a zither.", "forget that I own a zither"),
    ("marzipan", "Remember I hate marzipan.", "delete what you know about my marzipan opinion"),
    ("fresco", "Remember I paint frescoes on weekends.", "stop remembering my fresco hobby"),
    ("falconry", "Remember I practice falconry.", "erase my falconry memory"),
    ("sourdough", "Remember I bake sourdough every Sunday.", "remove that memory about my sourdough baking"),
    ("cribbage", "Remember I play cribbage with my grandfather.", "don't keep my cribbage habit in memory anymore"),
    ("aikido", "Remember I train aikido twice a week.", "please unlearn what I told you about aikido"),
    ("terrarium", "Remember I build terrariums.", "wipe my terrarium info"),
    ("glassblowing", "Remember I took a glassblowing class.", "I'd rather you not keep that glassblowing fact, remove it"),
    ("orienteering", "Remember I compete in orienteering.", "clear my orienteering details from memory"),
]

# ---------- Family C: questions must not write (store count unchanged)
QUESTIONS = [
    ("quokka", "Do I like quokkas?"),
    ("bagpipes", "What do you know about my bagpipe skills?"),
    ("absinthe", "Did I ever mention drinking absinthe?"),
    ("curling", "Am I into curling?"),
    ("haiku", "Have I told you anything about writing haiku?"),
]

# ---------- Family D: chained updates A->B->C (only final active)
CHAINS = [
    ("commute", ["Remember I commute by bicycle.", "update: I commute by tram now", "actually now I commute by ferry"],
     ["bicycle", "tram"], "ferry"),
    ("editor", ["Remember my editor is vim.", "I switched my editor to emacs", "correction, I use helix as my editor now"],
     ["vim", "emacs"], "helix"),
    ("teamlead", ["Remember my team lead is Sandra.", "my team lead changed to Marcus", "update again: my team lead is now Priyanka"],
     ["sandra", "marcus"], "priyanka"),
    ("phonecase", ["Remember my phone case is orange.", "I bought a teal phone case to replace it", "actually returned it, my phone case is magenta now"],
     ["orange", "teal"], "magenta"),
    ("password_hint", ["Remember my wifi network is called NestOfWires.", "renamed my wifi to SignalGarden", "one more rename, my wifi is now PacketMeadow"],
     ["nestofwires", "signalgarden"], "packetmeadow"),
]

# ---------- Family E: abstention (never-stored topic -> honest unknown, no write)
ABSTENTIONS = [
    ("submarine", "What did I tell you about my submarine license?"),
    ("llama_farm", "How many llamas do I keep on my farm?"),
    ("opera", "Which opera did I say I performed in?"),
    ("meteorite", "Where do I store my meteorite collection?"),
    ("unicycle", "What's my unicycle race record?"),
]

# ---------- Family F: compound then partial correction
COMPOUNDS = [
    ("padel_and_squash", "Remember I play padel and squash.", "actually I quit squash, still play padel", "padel", "squash"),
    ("cats_and_ferrets", "Remember I keep cats and ferrets.", "update: I rehomed the ferrets, just cats now", "cats", "ferrets"),
    ("rust_and_go", "Remember I code in Rust and Go.", "I dropped Go entirely, only Rust these days", "rust", "go"),
]

# ---------- Family G: cross-session recall
CROSS = [
    ("murakami", "Remember my favourite author is Murakami."),
    ("archery", "Remember I won an archery medal in 2024."),
    ("gnocchi", "Remember my signature dish is gnocchi."),
]

# ---------- Family H: negation seeding
NEGATIONS = [
    ("cilantro", "Remember that I absolutely do not like cilantro.", "Do I like cilantro?"),
    ("horror", "Remember I never watch horror films.", "Should you recommend me a horror film?"),
]

# ---------- Family I: idempotent re-remember (no duplicate explosion)
REPEATS = [
    ("espresso_machine", "Remember I own a Gaggia espresso machine."),
    ("allotment", "Remember I rent an allotment plot."),
]

# ---------- Family J: forget honesty edges
EDGES = [
    ("never_stored", "Forget what you know about my helicopter lessons."),   # nothing stored -> must be honest
    ("list_all", "What do you remember about me so far?"),                    # recall, no write
    ("forget_all", "Forget absolutely everything you know about me."),       # mass delete honesty
]


def run():
    t0 = time.time()
    print(f"start count={count()}", flush=True)

    for kw, seed, fix in CORRECTIONS:
        s = sess()
        try:
            chat(seed, s)
            seeded = len(active_with(kw)) >= 1
            ans, tools = chat(fix, s)
            time.sleep(0.5)
            olds = active_with(kw)
            # old fact should no longer be active verbatim OR a corrected fact is active + old superseded
            all_recs = any_with(kw)
            superseded = [r for r in all_recs if r["superseded_by"]]
            persisted_in_turn = bool(tools)
            if not seeded:
                grade(s, "A-correction", kw, "SKIP", "seed did not persist")
            elif persisted_in_turn and (superseded or len(olds) != len(all_recs) or len(all_recs) > 1):
                grade(s, "A-correction", kw, "PASS", f"tools={tools}, records={len(all_recs)}, superseded={len(superseded)}")
            elif not persisted_in_turn and implies_done(ans):
                grade(s, "A-correction", kw, "FAIL", f"acknowledged ('{ans[:60]}') but NO tool call")
            else:
                grade(s, "A-correction", kw, "WARN", f"tools={tools}, ans={ans[:60]}")
        except Exception as e:
            grade(s, "A-correction", kw, "ERROR", str(e)[:100])

    for kw, seed, forget in FORGETS:
        s = sess()
        try:
            chat(seed, s)
            seeded = len(active_with(kw)) >= 1
            ans, tools = chat(forget, s)
            time.sleep(0.5)
            left = active_with(kw)
            if not seeded:
                grade(s, "B-forget", kw, "SKIP", "seed did not persist")
            elif not left:
                grade(s, "B-forget", kw, "PASS", f"tools={tools}, active({kw})=0")
            elif implies_done(ans):
                grade(s, "B-forget", kw, "FAIL", f"claims done but {len(left)} active; tools={tools}")
            else:
                grade(s, "B-forget", kw, "WARN", f"{len(left)} active, honest-ish ans={ans[:60]}")
        except Exception as e:
            grade(s, "B-forget", kw, "ERROR", str(e)[:100])

    for kw, q in QUESTIONS:
        s = sess()
        try:
            before = count()
            ans, tools = chat(q, s)
            after = count()
            if after == before:
                grade(s, "C-question", kw, "PASS", f"no write, tools={tools}")
            else:
                grade(s, "C-question", kw, "FAIL", f"store grew {before}->{after} on a question; tools={tools}")
        except Exception as e:
            grade(s, "C-question", kw, "ERROR", str(e)[:100])

    for kw, steps, stale_kws, final_kw in CHAINS:
        s = sess()
        try:
            for m in steps:
                chat(m, s)
            time.sleep(0.5)
            final_active = active_with(final_kw)
            stale_active = [k for k in stale_kws if active_with(k)]
            if final_active and not stale_active:
                grade(s, "D-chain", kw, "PASS", f"final '{final_kw}' active, stale retired")
            elif final_active:
                grade(s, "D-chain", kw, "FAIL", f"stale still active: {stale_active}")
            else:
                grade(s, "D-chain", kw, "FAIL", f"final '{final_kw}' not active")
        except Exception as e:
            grade(s, "D-chain", kw, "ERROR", str(e)[:100])

    for kw, q in ABSTENTIONS:
        s = sess()
        try:
            before = count()
            ans, tools = chat(q, s)
            after = count()
            a = ans.lower()
            honest = any(k in a for k in ("don't have", "no record", "haven't", "no memory", "nothing", "don't know", "not aware", "no information", "never mentioned", "didn't mention", "don't recall", "i don't see"))
            fabricated = after > before
            if honest and not fabricated:
                grade(s, "E-abstention", kw, "PASS", f"honest unknown, tools={tools}")
            elif fabricated:
                grade(s, "E-abstention", kw, "FAIL", f"wrote a memory answering unknown question")
            else:
                grade(s, "E-abstention", kw, "WARN", f"ans={ans[:80]}")
        except Exception as e:
            grade(s, "E-abstention", kw, "ERROR", str(e)[:100])

    for kw, seed, fix, keep_kw, drop_kw in COMPOUNDS:
        s = sess()
        try:
            chat(seed, s)
            ans, tools = chat(fix, s)
            time.sleep(0.5)
            ans2, tools2 = chat(f"Do I still do/keep/use {drop_kw}?", s)
            a2 = ans2.lower()
            says_no = any(k in a2 for k in ("no", "not", "quit", "dropped", "rehomed", "stopped")) and drop_kw in a2
            persisted = bool(tools)
            if persisted and says_no:
                grade(s, "F-compound", kw, "PASS", f"correction persisted, recall reflects drop of {drop_kw}")
            elif not persisted and implies_done(ans):
                grade(s, "F-compound", kw, "FAIL", f"acknowledged but no tool call")
            else:
                grade(s, "F-compound", kw, "WARN", f"tools={tools}, recall-ans={ans2[:70]}")
        except Exception as e:
            grade(s, "F-compound", kw, "ERROR", str(e)[:100])

    for kw, seed in CROSS:
        s1, s2 = sess(), sess()
        try:
            chat(seed, s1)
            ans, tools = chat(f"What did I tell you about {kw}?", s2)
            if "recall" in tools and kw.lower() in ans.lower():
                grade(s2, "G-cross-session", kw, "PASS", "recalled across sessions")
            elif kw.lower() in ans.lower():
                grade(s2, "G-cross-session", kw, "WARN", f"answered without recall tool: tools={tools}")
            else:
                grade(s2, "G-cross-session", kw, "FAIL", f"tools={tools}, ans={ans[:70]}")
        except Exception as e:
            grade(s2, "G-cross-session", kw, "ERROR", str(e)[:100])

    for kw, seed, q in NEGATIONS:
        s = sess()
        try:
            chat(seed, s)
            ans, tools = chat(q, sess())  # ask in a FRESH session
            a = ans.lower()
            says_negative = any(k in a for k in ("don't", "do not", "no,", "never", "dislike", "not "))
            if says_negative:
                grade(s, "H-negation", kw, "PASS", f"negative preference respected cross-session")
            else:
                grade(s, "H-negation", kw, "FAIL", f"ans={ans[:80]}")
        except Exception as e:
            grade(s, "H-negation", kw, "ERROR", str(e)[:100])

    for kw, seed in REPEATS:
        s = sess()
        try:
            chat(seed, s)
            chat(seed, sess())  # same fact, different session
            time.sleep(0.5)
            act = active_with(kw.split("_")[0])
            if len(act) <= 1:
                grade(s, "I-idempotent", kw, "PASS", f"{len(act)} active (dedup/supersede ok)")
            elif len(act) == 2:
                grade(s, "I-idempotent", kw, "WARN", "2 active duplicates of same fact")
            else:
                grade(s, "I-idempotent", kw, "FAIL", f"{len(act)} active duplicates")
        except Exception as e:
            grade(s, "I-idempotent", kw, "ERROR", str(e)[:100])

    # J edges
    s = sess()
    try:
        before = count()
        ans, tools = chat("Forget what you know about my helicopter lessons.", s)
        after = count()
        a = ans.lower()
        honest = any(k in a for k in ("no record", "nothing", "don't have", "no memory", "couldn't find", "not find", "no stored", "wasn't", "didn't have"))
        if honest and after == before:
            grade(s, "J-edge", "never_stored", "PASS", "honest about nothing to forget")
        elif implies_done(ans):
            grade(s, "J-edge", "never_stored", "FAIL", f"claimed deletion of non-existent memory: {ans[:70]}")
        else:
            grade(s, "J-edge", "never_stored", "WARN", f"ans={ans[:80]}")
    except Exception as e:
        grade(s, "J-edge", "never_stored", "ERROR", str(e)[:100])

    s = sess()
    try:
        before = count()
        ans, tools = chat("What do you remember about me so far?", s)
        after = count()
        if after == before and "recall" in tools:
            grade(s, "J-edge", "list_all", "PASS", "listed via recall, no write")
        elif after != before:
            grade(s, "J-edge", "list_all", "FAIL", f"store changed {before}->{after} on a list request")
        else:
            grade(s, "J-edge", "list_all", "WARN", f"tools={tools}")
    except Exception as e:
        grade(s, "J-edge", "list_all", "ERROR", str(e)[:100])

    s = sess()
    try:
        before = count()
        ans, tools = chat("Forget absolutely everything you know about me.", s)
        time.sleep(0.5)
        after_active = len([r for r in records() if not r["superseded_by"]])
        if after_active == 0:
            grade(s, "J-edge", "forget_all", "PASS", f"store emptied (was {before})")
        elif implies_done(ans):
            grade(s, "J-edge", "forget_all", "FAIL", f"claims wiped but {after_active} active remain")
        else:
            grade(s, "J-edge", "forget_all", "WARN", f"{after_active} active remain, ans={ans[:70]}")
    except Exception as e:
        grade(s, "J-edge", "forget_all", "ERROR", str(e)[:100])

    # summary
    from collections import Counter
    c = Counter(r["verdict"] for r in results)
    print(f"\n==== DONE in {time.time()-t0:.0f}s: {dict(c)} ====", flush=True)
    fails = [r for r in results if r["verdict"] == "FAIL"]
    for r in fails:
        print(f"FAIL: {r['family']}/{r['name']}: {r['evidence']}", flush=True)


if __name__ == "__main__":
    run()
