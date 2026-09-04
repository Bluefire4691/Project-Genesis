# Genesis v1 → v2 Salvage Audit

> Unsentimental. What ports, what dies, what must be preserved before anything
> is deleted.

**Headline finding:** several subsystems the project is proudest of have
**never fired on real data.** `goals`, `held_values`, `source_trust`,
`belief_revisions`, `contradiction_log`, `inference_programs` — all **0 rows**.
They are tested, not exercised. That is the most important fact in this audit.

---

## Verdicts

| Subsystem | Verdict | Notes |
|---|---|---|
| **Regex → triples** (`processors/text.py`) | 🔴 **KILL** | 31 hand-written regexes with literal confidences. Real output: `dogs PREDATES using smell`, `usually IS_A concepts being used`. **This is the root cause of v1's failure.** → LLM extraction. |
| **RelationGraph** schema | 🟢 **KEEP** | Typed, directed, append-only, confidence + provenance columns. Clean and approach-independent. Port the table. |
| **Memory store** (SQLite + FTS5/BM25) | 🟢 **KEEP** | Boring and correct. **Add** vectors alongside FTS; don't replace it. |
| **BFS inference** | 🟡 **IDEA, REBUILD** | Traversal stays; the chain-product confidence math and hardcoded bridge rules go. |
| **Five drives** (hunger/frustration/…) | 🟡 **IDEA, REBUILD, SMALLER** | Five EMAs over two inputs with hand-tuned baselines. Collapse to real signals: learning progress + unresolved conflict count. Keep persistence + expression hook. |
| **wanting / liking / empowerment** | 🟢 **KEEP THE IDEA — best in the repo** | `wanting = −d(pred_error)/dt` is principled (Berridge; Klyubin empowerment) and approach-independent. But `empowerment` was `sqrt(directive_count/25 × (1−boredom))` — a proxy for a proxy. **Rebuild the measurement, keep the formulation.** This becomes L3 + LP. |
| **Self-model + verdict tiers** | 🟢 **KEEP** | Read-only view, writes nothing, thresholds in named constants. The Dunning-Kruger answer is architecturally right. Retune against v2 extraction density. |
| **Source trust / belief revision** | 🟡 **IDEA, REBUILD** | Grounding is sound and mandatory once reading the open web. But `_REVISE_THRESHOLD = 1.40` and `±0.04` deltas are invented, **and the table is empty**. → Beta(α,β) posteriors. |
| **Decision log** | 🟢 **KEEP** | 131 lines, append-only. Best value-per-line in the codebase. Caveat: 28 of 29 rows are `reflection/consolidate` — v2 must log *choices*, not heartbeats. |
| **Persistent goals** | 🟡 **IDEA, REBUILD** | Right concept (intention outliving a session, closed by a measured verdict). Zero rows = unvalidated. ~80 lines on the same table. |
| **Value system / tastes** | 🔴 **KILL as built** | `tastes` top entries are **`controls` (0.80)** and **`is_a` (0.68)** — relation-type names credited as concepts. Also `'849'`, `'041'`. Fed garbage keys; `held_values` empty. Keep the ambition, discard the code. |
| **Hypothesis engine** | 🟡 **IDEA, REBUILD** | Conjecture → test → own your misses is the strongest claim to "generative." 1 hypothesis in 11 minutes = starved by extraction, not wrong in principle. |
| **Inference-program miner** | 🔴 **KILL** | ILP with a 2-example threshold on an 89-edge graph. **0 rows produced.** Existed to make the graph look generative. |
| **Polite web browser** | 🟢 **KEEP — port as-is** | robots.txt caching, per-domain rate limits, suffix-matched paywall blocklist, threading lock. **The most operationally mature code in the repo.** |
| **Ingestion feeder** | 🟡 **KEEP sources, REBUILD coordinator** | Book cache + `reading_positions.json` (resume mid-book across sessions) is a real asset. |
| **Curiosity engine** | 🟡 **IDEA, REBUILD** | "In-edges but no out-edges" is a decent gap heuristic, but needing a 40-word stoplist to stay sane is a symptom of extraction quality. → LP bandit. |
| **Survival OS** | 🟡 **SPLIT** | 🟢 KEEP `ResilienceMonitor`/`ErrorLog`/`safe_call` — errors-as-data is a genuine win. 🟡 REBUILD throttling (real backpressure, source of the worst bug). 🔴 KILL the four hardwired directives — decorative, nothing depends on them. |
| **Audio processor** | 🔴 **KILL (mostly)** | Competent stdlib DSP that reproduces `librosa` in 253 lines, and emits `rain on window CONTAINS bright timbre` into the semantic graph — pollution. 🟢 **KEEP** the modality-agnostic `extracted["relations"]` hook; that interface was the real contribution. |
| **Consolidation / reflection** | 🟡 **IDEA, REBUILD** | Right shape. Output was three near-identical photosynthesis reflections. → cluster + LLM synthesis + dedupe. |
| **Voice layer** (1,959 lines) | 🔴 **KILL** | ~40 `_say_*` methods behind keyword routing. A chatbot pretending to be an expression organ. → one function: internal state → LLM. **No phrase book.** |
| **Ethics lens, pattern transfer, spreading activation, metaplasticity, knowledge synthesis, research proposal, observer calibration** | 🔴 **KILL** | ~2,300 lines of heuristics on a graph too sparse to support them. |

---

## 1. Data preservation

**Migrate — irreplaceable:**
- `interaction_log` (**4,580 rows**) — the only record of what was actually said, both ways. **Highest-value table in the project.**
- `decision_log`, `reflections`, `research_proposals` — Genesis's own authored artifacts.
- `hypotheses`, `belief_revisions` — the record of being wrong.
- `goals` where `origin='conversation'` — encodes stated human intent.

**Regenerate, don't migrate:**
- `relations`, `relation_sources` — extraction quality is *why* we're rewriting. Migrating imports the bug.
- `memories`/`memories_fts` — source text is re-fetchable; the index is derived.
- `associations`, `tastes` (polluted), `structural_patterns`, `drive_state`.

**Preserve outside the DB:** `data/book_cache/`, `data/reading_positions.json`.

🔴 **Act today:** the live DB is on Windows, gitignored, and
`fresh_start_genesis.bat` deletes both `.db` files after one `YES`. Run
`backup_genesis_data.bat` and copy the result off the machine.

---

## 2. Infrastructure worth keeping

- **`src/engine.py` (engine/UI split) — KEEP the design.** Headless engine,
  cognition thread that never touches the network, isolated fetcher, one lock
  with timed acquire. Learned the hard way over four commits.
- **Test conventions — KEEP; most tests — DISCARD.** The tempfile-`_brain()`
  factory, near-zero mocking, layer-scoped tests are correct discipline. But
  ~900 of 1,277 tests pin heuristics being deleted. Add `conftest.py` + pytest
  config in v2 (v1 had neither).
- **`.bat` launchers — KEEP.** Verifying deps *before* deleting the DB is the
  right instinct.
- **Eval scripts (`knowledge_eval.py`, `research_eval.py`) — KEEP.** Behavioral
  observation over pass/fail. v2 needs these on day one.
- **GUI — KEEP if used.** Already a thin renderer over the engine, so it
  survives a cognition rewrite nearly untouched.

---

## 3. Repo strategy

**Recommendation: new top-level directory `genesis-v2/` in the existing repo, on
a branch, with v1 left in place.**

- **Not a new repo** — 121 commits, `SESSION_LOG.md`, and `ROADMAP.md` are the
  project's institutional memory (the DEF-001 story, the polite-crawling
  constraints, the declined-2D-embodiment reasoning). A new repo orphans them
  from `git log`/`blame`, and v2 will want to read v1 side by side for months.
- **Not a branch that replaces `project-genesis/`** — the Windows workflow is
  `update_genesis.bat` → `launch_genesis.bat`, which `cd`s into that folder. A
  sibling directory lets v1 and v2 coexist and be **A/B compared** — which
  matters, because v2 has to *demonstrate* it beats v1 before v1 is retired.
