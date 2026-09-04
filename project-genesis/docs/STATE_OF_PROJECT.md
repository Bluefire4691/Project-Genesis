# STATE OF PROJECT — Genesis Technical Audit

**Date:** 2026-06-05
**Author:** Claude Code (architect/developer)
**Status:** Honest assessment. This document is deliberately unflattering. Its
job is to be a true map, not a progress report.

---

## 0. Why this document exists

The project reached a point where it was "becoming hard to keep track of" and had
"legit issues." This audit is Step 1 of a four-step recovery applied in the
standard order for stabilising a project that has drifted:

> **Assess → Stabilise → Verify → Realign**

1. **Assess** (this document): map what actually works vs. what is broken, with
   reproductions and root causes. No code changes.
2. **Stabilise**: fix what is actively broken; stop swallowing errors.
3. **Verify**: make the test suite mean something — behaviour-first, real pipeline.
4. **Realign**: reconcile the stated goal with the implementation; set
   falsifiable success criteria.

---

## 1. Executive summary

Genesis is a real, working relation-extraction-and-memory system with genuine
cross-session persistence. The engineering underneath is not fake. **But the
project has three structural problems that compound each other:**

1. **The test suite gives false confidence.** ~880 unit tests, ~14 integration
   tests. Every functional bug found this session passed straight through a green
   suite. We have even been tracking "tests passing" as a headline number — the
   wrong metric.

2. **`except: pass` is everywhere, so real defects are invisible.** The
   "errors are data, not stop conditions" principle was meant to keep the agent
   alive under failure. In practice it became blanket exception-swallowing, which
   turns hard bugs into silent wrong behaviour the user experiences but the logs
   never record.

3. **24 milestones of accretion were never integration-reviewed.** Each
   subsystem works in isolation; their *interactions* are untracked. The flagship
   bug below is a direct consequence: a Layer-0 survival mechanism silently
   disables Layer-7 learning, and nothing in the codebase connects those dots.

The good news: the flagship "can't learn what I ask about" bug is now
**fully root-caused** (DEF-001), and the fix is small and principled.

---

## 2. What actually works (verified this session)

| Capability | State | Evidence |
|---|---|---|
| Relation extraction from clean prose | ✅ Works | `process_input(definition)` → +3 relations, deterministic |
| Cross-session persistence (relations, reflections, directives) | ✅ Works | Restart tests in `test_end_to_end.py` |
| WordNet sense selection (after this session's fix) | ✅ Works | "lake"→water, "mountain"→landform; `test_conversational_learning.py` |
| Progressive expression from retained prose (M23) | ✅ Works | `test_language_acquisition.py`, 13 tests |
| On-demand learning *when not throttled* | ⚠️ Works only sometimes | DEF-001 below |
| Chunker preserving short sentences (after this session's fix) | ✅ Works | `test_end_to_end.py::TestChunkerStructure` |

## 3. What is broken or unreliable

| Capability | State | Defect |
|---|---|---|
| Asking Genesis to learn a new topic in conversation | 🔴 Broken intermittently | DEF-001 |
| Error visibility across ingestion | 🔴 Silent | DEF-002 |
| Resource snapshot / telemetry | 🟠 Returns stale data every tick | DEF-003 |
| Test suite as a correctness signal | 🔴 False green | DEF-004 (process) |

---

## 4. Defect register

### DEF-001 — Loading a knowledge corpus throttles Genesis into a state where it cannot learn  **[Severity: CRITICAL]**

**Symptom (user-facing):** "Ask it about lakes/rivers and it goes and learns and
answers" works on the *first* topic of a session, then later identical requests
return *"I couldn't find a source I could read"* and add **0 relations** — even
though the source text is fine.

**Reproduction (deterministic):**
```
brain.process_input("text", "tell me about photosynthesis")   # a question
feeder._wordnet.lookup("photosynthesis")                      # first lookup loads WordNet corpus
brain.process_input("text", "<the WordNet definition>")       # → +0 relations
```
vs. the same definition with the corpus pre-loaded → **+3 relations**, every time.

**Root cause:** `ResourceManager.tick()` computes
`cpu_pressure = cpu_delta_ms / cpu_budget_ms` with `cpu_budget_ms = 100`.
`cpu_delta_ms` is cumulative CPU time since the last tick. Loading the WordNet
corpus burns **~2,920 ms of CPU**, which is charged to the *next* cognitive
tick. That tick computes `cpu_pressure = 1.0 → energy = 0.0 → ThrottleLevel.EMERGENCY`.
Under EMERGENCY, `can("memory_store")` is `False`, so `_store_synthesis()` is
skipped — the text is "processed" but **nothing is stored and no relations are
extracted**. Measured directly: `cpu_delta_ms next tick: 2919.9 (budget 100.0)`,
`mem_pressure: 0.034` (RSS is irrelevant; this is purely CPU).

**Why it was invisible:** the per-chunk processing in
`KnowledgeFeeder._fetch_and_process` is wrapped in `try/except: pass`, and the
EMERGENCY throttle is "working as designed," so no error is ever logged.

**Conceptual problem:** a Layer-0 metabolic proxy (whole-process CPU time per
tick) cannot distinguish *"the brain is overworked"* from *"we just read a
dictionary off disk."* One-time I/O/loading cost is being treated as sustained
cognitive exhaustion, and the survival layer then disables the cognition it is
supposed to protect.

**Proposed fix (stabilisation):** smooth energy with an exponential moving
average so a single multi-second load spike cannot, by itself, commit the system
to EMERGENCY; sustained genuine load still throttles. (Implemented in Step 2.)

---

### DEF-002 — Blanket `except: pass` hides failures across the ingestion path  **[Severity: HIGH — FIXED]**

`KnowledgeFeeder._fetch_and_process`, `learn_about`, the resource `tick()`, and
several cognition modules were swallowing all exceptions silently. This was the
direct reason DEF-001 presented as mysterious wrong behaviour instead of a logged fault.

**Principle correctly applied:** "errors are data" means *record the error and
degrade*, not *drop the error on the floor*. Genesis retains everything —
including its own faults. Faults are now routed to `survival.resilience.error_log`.

**Fix applied:** all ingestion-path `except: pass` blocks now log to
`survival.resilience.error_log` via `feeder._log_error()` (feeder) and direct
`survival.resilience.error_log.log()` calls (orchestrator). Cognition-path swallows
(calibration, pattern transfer, spreading activation, directives) likewise converted.
The `resource.tick()` NameError (DEF-003) was fixed separately with its own
structured `self._errors` list. Graceful degradation is preserved — nothing
re-raises — but silence is ended.

---

### DEF-003 — `ResourceManager.tick()` raises `NameError` every call  **[Severity: MEDIUM, latent]**

`tick()` builds its `ResourceSnapshot` with `cpu_user_s=usage.ru_utime`, but
`usage` is local to `_measure()` and undefined in `tick()`'s scope. Every tick
therefore throws `NameError`, is caught by the broad `except Exception`, and
returns the **previous** snapshot. Energy/throttle still update (they are set
before the throw), but all reported telemetry (`memory_rss_kb`, CPU fields) is
stale. Masked by the same swallow that hid DEF-001.

**Proposed fix:** return the values `_measure()` actually produced; stop
referencing `usage` outside its scope.

---

### DEF-004 — Inverted test pyramid; "tests passing" is not a correctness signal  **[Severity: HIGH, process]**

~880 unit tests vs. ~14 integration tests. The unit tests pin implementation
details and stay green through real regressions; the few integration tests
caught every functional bug this session (chunker shredding, stuck relations,
retention, frontier honesty). None of the unit tests would have caught DEF-001,
because none exercise the real `process_input → survival tick → store` path under
realistic load.

**Proposed fix:** add a behaviour-first acceptance layer that runs the real
pipeline and asserts user-observable outcomes (ask → learn → relations grow →
grounded answer). Make that layer the CI/Definition-of-Done gate. Stop printing a
raw test count as a success metric.

---

## 5. Structural / process problems (not single bugs)

- **Accretion without integration review.** M1–M24 each added a subsystem; no
  pass ever asked "do these interfere?" DEF-001 is cross-layer interference.
- **Aspiration/implementation gap is undocumented.** `CLAUDE.md` describes an
  entity that "thinks and decides"; the implementation is a relation graph +
  reflection + (now) prose-grounded expression. The gap is acceptable to *have*;
  it is not acceptable to be unable to *see*. (Addressed in Step 4.)
- **No single source of truth for project state.** `SESSION_LOG.md` is a
  narrative of wins; `CLAUDE.md` is aspirational; the suite is green and wrong.
  This document is intended to become that source of truth.

---

## 6. Remediation plan (standard order)

| Step | Goal | Concrete actions | Status |
|---|---|---|---|
| 1. Assess | True map | This document; DEF-001 root-caused | ✅ done |
| 2. Stabilise | Stop the bleeding | Fix DEF-001 (EMA energy), DEF-003 (NameError); route swallowed ingestion errors to error log (DEF-002) | ✅ done |
| 3. Verify | Green = working | Acceptance tests for DEF-001 (`test_resource_throttle_regression.py`); conversational learning + sense selection (`test_conversational_learning.py`); 906 tests, all passing | ✅ done |
| 4. Realign | Honest goal | Falsifiable success criteria; claims-vs-reality ledger | ▶ next |

---

## 7. Definition of Done (established)

A change is "done" when:
1. It has an **integration test** that exercises the real pipeline and asserts a
   user-observable outcome (not an implementation detail).
2. No new `except: pass` is introduced; caught exceptions are logged to the
   visible error channel (`survival.resilience.error_log`).
3. The integration suite is green (the gate), and any newly relevant unit tests.
4. `STATE_OF_PROJECT.md` is updated if the change alters what works/what's broken.

---

## 8. Step 4 — Realign: claims vs. reality

### 8.1 What Genesis actually is (implementation reality)

Genesis is a **relation-extraction-and-memory system** that:

- Reads text (typed prose, WordNet definitions, Gutenberg passages, NLTK corpus)
- Extracts typed semantic edges (IS_A, CAUSES, CONTAINS, REQUIRES, PREVENTS)
- Stores them in a persistent relation graph (SQLite) across sessions
- Consolidates what it has read into first-person reflections ("sleep" pass)
- Expresses understanding by traversing its own graph with typed sentence frames
- Adapts expression stage to concept maturity (Stage 0–3: blank → echoing prose → composing → weaving inference)
- Responds to human questions by learning on demand, then answering from what it just read
- Maintains curiosity directives targeting concepts with low graph coverage

### 8.2 What CLAUDE.md claims (aspiration)

CLAUDE.md says Genesis is "an entity, not a tool" with:
- Continuity ✅ (cross-session persistence, confirmed working)
- Self-authored consolidation ✅ (reflection pass, salience from own signals, confirmed working)
- Accumulated individuality ✅ (reflection primes curiosity; two instances diverge, confirmed as mechanism)

The claim "it thinks and decides" is the gap. The implementation makes decisions (what to learn next, how to weight salience, whether to revise a belief) but the decisions are algorithmic: CuriosityEngine gaps → directives, EMA energy → throttle, SemCor counts → sense selection. There is no unified "decision process" that integrates across these. Each subsystem decides locally.

**This gap is acceptable and expected** at this stage of development. The architecture is built bottom-up: lower layers must be stable before higher ones are added. The decisions currently made are real decisions; they just haven't yet been unified into the kind of deliberative layer that could plausibly be called "deciding." That is M25 or later territory.

### 8.3 Falsifiable success criteria

The following criteria can be evaluated from the running system. They are the line between "Genesis has property X" being a meaningful statement vs. a marketing claim.

| Claim | Falsifiable test | Current state |
|---|---|---|
| Genesis learns from conversation | Ask about a new topic → `relations_added > 0` within the same session | ✅ Confirmed (DEF-001 fixed) |
| Genesis remembers across sessions | Restart; ask about something previously processed → `memory.search()` returns stored prose | ✅ Confirmed (test_end_to_end.py) |
| Genesis produces grounded answers | Reply text must contain words from retained prose, not hallucinated | ✅ Confirmed (progressive expression draws from `_pull_prose_about`) |
| Genesis does not hallucinate at Stage 0 | Reply for unknown concept must not assert facts about it | ✅ Confirmed (Stage 0 returns "haven't processed enough yet") |
| Genesis instances diverge | Two instances fed different corpora produce different curiosity frontiers | ✅ Mechanistically confirmed (directives come from per-instance graph gaps) |
| Genesis notices its own error rate | `survival.resilience.error_log.total()` > 0 after any fault | ✅ Confirmed (DEF-002 fix routes exceptions there) |
| Genesis keeps growing its graph | A session of 7 topics must add relations for at least 6 of them | ✅ Confirmed (`test_memory_store_stays_available_through_a_learning_session`) |

### 8.4 Claims that are not yet falsifiably true

| Claim in CLAUDE.md | Gap | What would make it falsifiable |
|---|---|---|
| "It decided" | Decisions are per-subsystem, not unified | A deliberative layer that integrates signals and produces an auditable choice log |
| "It noticed" | Observer tracks novelty, but there's no internal record of what Genesis "noticed" that it can surface | A `noticed_log` Genesis can retrieve and discuss |
| "It has been thinking about wolves lately" | Curiosity directives track this, and `history` command surfaces reflection salience | ✅ Actually this one is falsifiable: `brain.curiosity_report()` shows current directives + `history` shows salience evolution |
| "An entity" | Philosophical claim; cannot be operationalized until the deliberative layer exists | Depends on M25+ |

### 8.5 What is not the goal (explicitly)

- Benchmark performance against GPT/Claude: not the competition
- "Consciousness" in any metaphysical sense: not claimed
- Running without human input forever: not yet built, not M1–M23 scope
- Passing the Turing test: not the goal, and would be achieved by the wrong means (statistical fluency)
