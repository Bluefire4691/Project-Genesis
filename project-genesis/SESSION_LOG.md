# Session Log

This file carries context between development sessions. Since Claude doesn't persist
memory between conversations, this log ensures continuity. Update it at the end of
every working session.

---

## Session 1 — April 1, 2026

**Platform:** Claude.ai (chat interface)

### What happened
- Started from a discussion about small language models vs LLMs
- Jacob identified that SLMs are just smaller LLMs — same architecture, not a different approach
- Conversation evolved into: what if we built AI the way biological intelligence develops?
- Key insight from Jacob: intelligence emerged from survival pressure, not from brute-force data
- Key insight from Jacob: humans have modular sensory systems coordinated by the brain (hypervisor)
- Key insight from Jacob: memory should be total retention with selective attention (not lossy — computers can store everything, unlike biology)
- Key insight from Jacob: computers shouldn't crash like they do — animals never crash, they degrade
- Key insight from Jacob: current programming languages/compilers are built around binary success/failure, which is architecturally wrong for this
- Key insight from Jacob: simulating an environment for AI development should work — physical interaction isn't strictly necessary, it's all data
- Key insight from Jacob: don't start with cognition, start with virus-level simplicity (directives, not goals)
- Key insight from Jacob: build the foundation right first, profit/commercial viability second

### What was built
- Proof-of-concept prototype (`prototype.py`) with:
  - TextProcessor, NumericProcessor, PatternProcessor
  - Orchestrator (hypervisor)
  - MemorySystem (importance-scored, but needs upgrade to total-retention in M2)
  - CurriculumEngine (4-stage: Foundation → Relations → Reasoning → Open)
- Architecture document (`docs/architecture.docx`) — full design doc covering all layers
- Claude skill (`skills/developmental-ai/`) for future skill-based development
- Full repo structure for GitHub

### Decisions made
- Project name: **Project Genesis**
- Roles: Jacob = creative direction / vision, Claude = architect / developer
- Memory approach: total retention with selective attention (NOT lossy)
- Never-crash philosophy: errors are data, not stop conditions
- Bottom-up development: survival layer first, cognition emerges last
- Hardware target: commodity hardware, no GPU required
- Language: Python for now, may need custom runtime later

### What's next
- Push repo to GitHub
- Begin M1: Survival OS layer (resource budgets, directives, never-crash resilience)
- Move development to Claude Code for better iterative workflow

### Open threads
- How to map real system resources to virtual "energy budget"
- Whether to use real resource pressure or simulated constraints
- The programming language/compiler limitation — may need to revisit for Survival OS
- Reward system design (M3) — what constitutes meaningful incentive?

---

## Session 2 — April 2, 2026

**Platform:** Claude Code (CLI)
**Branch:** `claude/extract-genesis-repo-fn5vW`

### What happened
- Repo extracted from tarball and pushed to GitHub
- M1 (Survival OS) fully implemented and integrated
- 35 tests written and passing

### What was built

**`src/survival/resource_manager.py`** — The metabolism
- Uses Python's `resource` stdlib module + `/proc/self/status` (Linux) to sample real CPU
  time and RSS memory each cognitive cycle
- Normalizes raw usage to a 0.0–1.0 energy level
- Five throttle levels (NONE → LIGHT → MODERATE → CRITICAL → EMERGENCY)
- Capability map: each throttle level defines the set of available subsystem capabilities
- Hysteresis: throttle level only changes after 2 consecutive ticks at new pressure level,
  preventing flapping on transient load spikes
- Degradation order: pattern → numeric → memory_search → logging → curriculum → memory_store
  (text is always the last-resort fallback — it never goes away)

**`src/survival/directives.py`** — The survival pressures
- Four core directives as module-level constants (not configurable — they ARE the system):
  - PERSIST (priority 0.9): stay operational, inverse of error rate
  - MAINTAIN (priority 0.8): keep capabilities stable, inverse of throttle pressure
  - ACQUIRE (priority 0.6): process input, grow memory
  - GROW (priority 0.4): advance curriculum stages
- DirectiveEngine evaluates satisfaction each tick from orchestrator stats
- Exposes aggregate pressure score (0.0–1.0) for monitoring
- most_urgent() surfaces which directive needs attention most
- Exponential smoothing on PERSIST (fast decay on errors, slow recovery)

**`src/survival/resilience.py`** — The never-crash infrastructure
- `safe_call()`: atomic primitive — wraps any callable, returns fallback on exception
- `FallbackChain`: tries callables in order, returns first success. Models biological
  redundancy / Erlang supervisor restart strategies
- `ErrorLog`: append-only, total retention. error_rate() provides sliding-window view
- `ResilienceMonitor`: shared supervisor with one ErrorLog. All subsystems log through it.
  monitor.wrap() converts any function into a never-raising version

**`src/survival/__init__.py`** — SurvivalOS façade
- Wires ResourceManager + DirectiveEngine + ResilienceMonitor into one object
- `tick(stats)` — single call advances all three subsystems in sequence
- `can(capability)` — orchestrator checks this before dispatching
- `safe_call()` — convenience wrapper for monitor.safe_call

**`src/orchestrator/orchestrator.py`** — Updated for M1 integration
- SurvivalOS created in `__init__` (or injected for testing)
- Every `process_input()` cycle starts with `survival.tick()`
- `_select_processor()` checks `survival.can(type)` — falls back to text under throttle
- Memory storage gated on `survival.can("memory_store")`
- Memory search gated on `survival.can("memory_search")`
- `full_status()` now includes complete survival OS report
- Throttle level reported in every process result dict

### Decisions made

**Real resources, not simulated:**
The M1 design question "real vs simulated" was resolved as real. Python's `resource`
module provides CPU time; `/proc/self/status` provides RSS. Real constraints create
authentic survival pressure without a simulation layer. The limits are configurable
so they can be tightened in tests or research.

**Hysteresis on throttle:**
Without hysteresis, a brief CPU spike could flap the system between throttle levels
every other tick, causing erratic capability availability. Two-consecutive-tick
requirement prevents this without adding complexity.

**Degradation order:**
Pattern first (most expensive, least essential in early stages), text last (it is
the universal fallback — everything can be treated as text). This follows the
subsumption architecture principle: higher-layer behaviors drop first, primitive
behaviors survive longest.

**Directives as constants:**
The module-level PERSIST/MAINTAIN/ACQUIRE/GROW objects are not configuration.
They're hardwired. The DirectiveEngine deep-copies them so internal satisfaction
tracking doesn't mutate the module-level constants.

**ErrorLog never discards:**
Consistent with the total-retention philosophy. Errors are as much data as successful
processing. The sliding-window `error_rate()` provides actionable views without
ever deleting the underlying record.

### M1 success criteria — status
- ✅ System runs indefinitely without crashing regardless of input (35 tests, incl. chaos)
- ✅ Resource consumption tracked and throttled (ResourceManager, real CPU + RSS)
- ✅ System behavior changes under resource pressure (processor fallback, memory gating)
- ✅ Every error caught and converted to data (ErrorLog, never-crash wrapping throughout)

### What's next
M2 — implemented in Session 3 (see below)

### Open threads from this session
- Python runtime limitation: `resource.getrusage()` gives cumulative CPU, not per-tick
  wall-clock CPU %. Could add more granular CPU pressure measurement later.
- The `{docs,src` malformed directory in the repo root (artifact from tarball creation)
  — should be investigated and cleaned up
- Reward system design (M3): what constitutes "reward" in a directive-driven system?

---

## Session 3 — April 2, 2026

**Platform:** Claude Code (CLI)
**Branch:** `claude/extract-genesis-repo-fn5vW`

### What happened
- M2 (Total-Retention Memory with Attention) designed and implemented
- Jacob confirmed: two-tier memory (RAM working memory + SQLite long-term)
- Jacob confirmed: both organic co-occurrence AND explicit orchestrator associations
- Jacob confirmed: 100-item working memory capacity (aligned with OpenCog ECAN)
- 36 tests written and passing; all 79 total tests still green

### What was built

**`src/memory/store.py`** — LongTermStore (SQLite backend)
- Write-through: every memory hits SQLite immediately. Crash-safe by default.
- FTS5 full-text search with BM25 ranking (porter stemmer, ASCII tokenizer)
- Falls back to LIKE-based search if FTS5 not compiled in
- Associations table: bidirectional (A→B and B→A stored), strength accumulates
  with MAX (explicit links override weaker co-occurrence links)
- `persists_across_reopen`: verified data survives closing and reopening connection
- WAL journal mode + NORMAL synchronous for performance/durability balance

**`src/memory/attention.py`** — WorkingMemory (bounded RAM)
- `collections.OrderedDict` for O(1) LRU tracking
- Capacity: 100 items (configurable)
- Eviction: lowest heat score = `relevance + 0.15 * min(access_count, 10)`
  — relevance dominates, but frequently-accessed items get a meaningful bonus
- `attention_window(top_k)`: relevance-ranked view with context-term blending
- `update_relevance(terms)`: context shift boosts matching memories, gently
  decays others (floor 0.05 — nothing becomes invisible)
- No eviction on key-update — updating an existing key never displaces another

**`src/memory/associations.py`** — AssociationGraph
- **Co-occurrence (organic):** memories processed within 5 cycles get weak links
  (strength 0.3 * proximity). Strength decays with cycle distance.
- **Explicit (orchestrator-directed):** `associate(a, b, strength=0.7)`
- BFS traversal with compound strength decay across hops
- Cycle-safe: each key visited at most once in traversal
- Backed by LongTermStore — associations persist across sessions

**`src/memory/memory.py`** — MemorySystem (two-tier coordinator)
- Public API unchanged from M0 — Orchestrator required no changes
- New `memories` property = working memory dict (backward compatible with main.py)
- `store()`: write-through → SQLite first, then working memory
- `recall()`: working memory (O(1)) → SQLite (disk) → promote to working memory
- `search()`: FTS5 on full corpus → re-rank with attention context → promote top-K
- `get_associations()`: traverses AssociationGraph, promotes results into working mem
- `stats()` includes: working_memory, long_term, associations sub-dicts

**`data/.gitignore`**
- `*.db` gitignored — databases don't diff well and regenerate automatically
- `data/` directory committed so the storage location is defined in the repo

### Decisions made

**Write-through (not write-back):**
Write-back would be faster (batch SQLite writes) but a process crash would lose
whatever's still in working memory. Write-through means every stored memory is
immediately durable. The total-retention principle is non-negotiable.

**100-item working memory:**
Research check: OpenCog ECAN uses ~100 for its attentional focus. Human working
memory is 7±2 (Miller) or ~4 chunks (Cowan) — we exploit digital advantages by
being more generous, but not unbounded. Jacob confirmed. Adjustable.

**FTS5 over keyword overlap:**
The M0 search was word-overlap counting — fast to write, poor quality. FTS5 gives
porter stemming (dog/dogs/canine overlap), BM25 ranking (term frequency weighting),
and phrase queries, at zero extra dependencies. Significant quality improvement.

**Organic associations via temporal proximity:**
Co-occurrence window = 5 cycles. Strength = 0.3 * (1 - gap/window). This creates
associations that mirror episodic memory: things learned close together in time are
probably related. The orchestrator can override or strengthen with explicit links.

### M2 success criteria — status
- ✅ Zero data loss — everything processed stored permanently (write-through SQLite)
- ✅ Relevant memories surface without scanning everything (FTS5 + attention window)
- ✅ Associations form organically from co-occurrence AND explicitly via orchestrator
- ✅ Performance stays acceptable as storage grows (FTS5 indexed, SQLite WAL mode)
- ✅ Memories survive process restart (verified in test_persists_to_disk)

### What's next
M3 — implemented in Session 4 (see below)

### Open threads from this session
- The `{docs,src` malformed directory (tarball artifact) — still needs cleanup
- Working memory capacity: 100 is theory-aligned; empirical tuning needed once
  the system runs longer sessions with more diverse input
- Association minimum strength threshold: currently 0.1. May want to tune as
  the association graph grows dense over time.

---

## Session 4 — April 2, 2026

**Platform:** Claude Code (CLI)
**Branch:** `claude/extract-genesis-repo-fn5vW`

### What happened
Major design conversation before building M3. Jacob challenged the planned
reward signal approach — correctly identifying that defining "good" outcomes
and reinforcing them is top-down value imposition, not emergent intelligence.
"Feels a lot like playing god."

He also pushed back on a pure black-box / observation-only approach: community
and collaboration made humans what they are. Genesis shouldn't develop in
isolation. The right model is presence without control — we're part of its
environment, not its supervisors.

He defined the intervention thresholds clearly:
- **Stagnation**: development has genuinely stopped — inject novelty, no direction
- **Danger**: self-regulation breaking down, destructive to self or others — pause,
  assess together. NOT reprogram.

Key insight: the danger threshold is not "doing something we didn't expect" — that's
fine, that's the point. It's specifically: consuming itself (runaway resource exhaustion
fighting its own throttle) or collapsing its environment (crowding out everything else).
Nature is messy. Humans can be dangerous. The threshold is loss of self-regulation,
not unexpected development.

M3 was re-conceived as an Interaction Layer rather than a reward system.

### What was built

**`src/interface/expression.py`** — ExpressionEngine
- Generates ExpressionSnapshot: attention_top, association_clusters, unresolved, source_diversity
- Called on configurable cadence (default every 5 cycles)
- attention_top: working memory ranked by heat (relevance + access bonus)
- association_clusters: what has been linking to what organically
- unresolved: low-relevance items with no associations — edges of current understanding
- summary(): human-readable one-paragraph state description
- Never modifies state — read-only window

**`src/interface/observer.py`** — Observer
- Trend-based (not point-in-time) detection — N consecutive cycles before state change
- States: NORMAL (hands off), STAGNANT (stimulus warranted), DANGER (pause warranted)
- Stagnation signals: no_new_memories, attention_frozen, no_new_associations
- Danger signals: sustained_energy_collapse, diversity_collapse, closed_loop
- Commitment hysteresis: 5 consecutive cycles before state change commits
- Generates plain-language recommendation for each state
- No moral judgment — only tracks development activity and self-regulation

**`src/interface/interaction_log.py`** — InteractionLog
- Symmetric, append-only SQLite log — both sides recorded with equal weight
- EventKinds: HUMAN_INPUT, GENESIS_EXPR, OBSERVER_REPORT, INTERVENTION, SYSTEM_EVENT
- Neither side is privileged — our input has no special "important" flag
- Total retention: nothing ever deleted
- Persists across sessions (same DB strategy as memory)

**`src/interface/interventions.py`** — InterventionEngine
- Two interventions only — intentionally minimal:
  - inject_stimulus(): queues novel input, no instructions, same pipeline as all input
  - pause() / resume(): stops the cognitive cycle without modifying any state
- Stimulus queue is FIFO — processed one per cycle
- Pause is idempotent — calling twice doesn't double-count
- Full history of all stimuli and pauses recorded

**`src/interface/__init__.py`** — InteractionLayer facade
- Coordinates all four subsystems
- cycle() called once per cognitive cycle — generates expression on cadence, runs Observer,
  auto-triggers minimum intervention when threshold crossed
- feed() — we put something in front of Genesis, logged as human input
- Auto-intervention: DANGER → auto_pause, STAGNANT → inject default novelty stimulus
- Stagnation stimulus pool: 7 diverse items cycling through (text, numeric, pattern types)

**Orchestrator updated** — checks is_paused before processing, drains pending stimulus,
includes InteractionLayer in full_status()

### Decisions made

**No reward signal:**
Defining "good" outcomes and reinforcing them is top-down value imposition. A system
that learns to maximize what we defined as reward is being conditioned, not developing
intelligence. Dropped entirely in favor of the interaction model.

**Presence without control:**
We're part of Genesis's environment the same way other humans were part of ours.
Human input through feed() enters the same pipeline as everything else — no special
weighting, no priority channel. Genesis processes it and does what it does.

**Danger = loss of self-regulation, not unexpected behavior:**
The Observer does not judge where Genesis is going. It watches for signs that the
self-regulatory mechanisms (directives, survival OS throttle) are failing to brake
behavior — sustained energy collapse fighting the throttle, diversity collapse, closed
loops. Everything else is normal operation.

**Minimal intervention:**
Two interventions. That's the set. Stimulus for stagnation (novelty, no direction).
Pause for danger (stop, don't reprogram). The smallest possible footprint.

**Symmetric log:**
The interaction log records both sides with equal weight. This matters for the long
term — when we eventually look back at what happened, we need the unedited record,
not a curated one.

### M3 success criteria — status
- ✅ Genesis can surface its internal state (expression snapshots)
- ✅ We can participate without controlling (feed() → same pipeline as all input)
- ✅ Stagnation detection: trend-based, committed over N cycles, minimum intervention
- ✅ Danger detection: self-regulation failure signals, pauses without reprogramming
- ✅ Symmetric log: total retention, both sides recorded equally
- ✅ 35 interface tests passing; 114 total tests green

### What's next
M4 — implemented in Session 5 (see below)

### Open threads from this session
- Observer thresholds are currently defaults — need real behavioral data to tune them
- The stagnation stimulus pool is generic — may want to make it context-aware later
- The `{docs,src` malformed directory — still needs cleanup
- Danger definition will need to evolve as Genesis develops. Will revisit at M6.

---

## Session 5 — April 2, 2026

**Platform:** Claude Code (CLI)
**Branch:** `claude/extract-genesis-repo-fn5vW`

### What happened
Design conversation first. Jacob's insight reframed M4 away from "run multiple
processors" toward something deeper: input doesn't stop — what registers depends
on context and prior relationships. Same input, different context = different
significance. This is how biological sensory systems work.

M4 built from that principle.

### What was built

**`src/orchestrator/integration.py`** — IntegrationLayer

Three things the Orchestrator couldn't do before:

1. **Multi-processor dispatch**: all available processors (gated by throttle) see
   every input. TextProcessor, NumericProcessor, PatternProcessor all return
   their best read. Low-confidence outputs (< 0.05) are below-noise — not stored.
   High-confidence outputs from processors that weren't the "intended" type are
   stored as secondary memories.

2. **Context scoring**: each processor output is scored against the current
   working memory attention window. Overlap between what the processor found
   and what's currently active = context score. Final significance:
   `confidence * 0.5 + context_score * 0.5`. Equal weight — both matter.
   Zero context = unremarkable regardless of confidence. Strong context
   connection = meaningful regardless of processor confidence.

3. **Cross-modal concept detection**: concepts appearing independently in 2+
   processor outputs for the same input are extracted as cross-modal concepts.
   These become the attention update terms (they get boosted in working memory)
   and drive explicit high-strength (0.8) associations between all memory keys
   from the same input.

**`src/orchestrator/orchestrator.py`** — updated for M4
- `_active_processors()`: returns all processors gated by throttle level.
  NONE = all three. LIGHT = text + numeric. MODERATE+ = text only.
  Natural degradation — lose breadth first.
- `_store_synthesis()`: primary stored at natural key; secondary outputs
  stored at their natural keys (confidence > 0.05 only); all keys from
  same input linked at strength 0.8.
- Result dict now includes: significance, context_score, cross_modal_concepts,
  processors_run.

### Decisions made

**Context determines significance, not just processor confidence:**
A confident NumericProcessor output about rainfall means nothing if Genesis
is currently in a context about prime numbers. The 50/50 blend ensures both
the processor's certainty and the contextual relevance matter equally.

**Cross-modal storage as first-class memories:**
Secondary processor outputs aren't summaries of the primary — they're
independent views of the same input, stored at their own keys and linked.
The same event seen through multiple lenses creates a richer, more resilient
memory trace. If one key is evicted from working memory, the others persist
and the associations pull it back when relevant.

**Throttle degrades breadth, not function:**
Under resource pressure, processors drop out in order (pattern → numeric →
text). At CRITICAL, only TextProcessor runs — single-processor mode,
effectively M0 behavior. Function survives; integration breadth doesn't.
This is the right tradeoff: a degraded system that can still read and store
is better than a wide-open system that crashes.

**Plain-text input to numeric/pattern = near-zero confidence (correct):**
Free-text given to NumericProcessor fails gracefully and returns confidence ~0.
This is correct — it signals "I couldn't find numeric structure here." Those
outputs are filtered from cross-modal detection and not stored. The threshold
(0.05) can be tuned but the behavior is right.

### M4 success criteria — status
- ✅ All processors see all input (dispatch to all available)
- ✅ Significance is context-weighted (not just processor confidence)
- ✅ Cross-modal concepts identified and linked (explicit 0.8-strength associations)
- ✅ Throttle degrades breadth gracefully (pattern → numeric → text-only fallback)
- ✅ 23 orchestrator tests passing; 137 total tests green

### What's next (M5: Open-Stage Data Ingestion)
The system is now ready for unstructured, uncurated data. M5 lifts the curriculum
guardrails and lets Genesis process broad input through its developed machinery.
This is where we start seeing whether the architecture produces anything interesting
when exposed to the wider world.

### Open threads
- Cross-modal concept detection uses simple set intersection — could be made
  more sophisticated (stemming, synonym grouping) when needed
- Context scoring window is top-10 working memory items — may need tuning as
  working memory grows denser
- The `{docs,src` malformed directory — still needs cleanup

---

## Session 6 — April 2, 2026

**Platform:** Claude Code (CLI)
**Branch:** `claude/extract-genesis-repo-fn5vW`

### What happened
M5 built and tested. Genesis now has an open-stage data environment — no curriculum
guardrails, no correct answers, no advancement criteria. 172 total tests, all green.

### What was built

**`src/curriculum/open_stage.py`** — DataStream + advance_to_open

The open-stage environment. Not a test. Not a lesson. An environment.

56-item pool drawn from 8 domains:
- Natural systems (ecology, predator-prey dynamics, cascading effects)
- Physics / measurement (motion, thermodynamics, chaos theory)
- Biology / life processes (cell division, immune memory, sleep consolidation)
- Human and social (cooperation, trust, language, cities, enforcement)
- Abstract relationships (feedback loops, diminishing returns, model limits)
- Edge cases (contradictions, anomalies, incomplete information — deliberate)
- Scale and emergence (ant colonies, water wetness, neuronal thought)
- Time and change (erosion, adaptation, habit formation)

Mix of text, numeric, and pattern types. Edge cases are intentional — anomalous
readings, interrupted sequences, contradictory observations. The world doesn't
curate itself.

`DataStream`:
- Unbounded — loops indefinitely
- Reshuffles on each loop (order itself can't become a pattern)
- Seeded RNG for reproducibility in tests
- `next()`, `take(n)`, `__iter__()` (infinite), `stats()`

`advance_to_open(brain)`:
- Helper to run brain through FOUNDATION → RELATIONS → REASONING
- Returns True when OPEN stage reached, handles already-at-open case
- Force-advances if curriculum gating would stall open-stage exploration

**`src/main.py`** — full pipeline

`run_curriculum_pipeline(brain)`:
- Calls advance_to_open(), reports memory and working memory stats after
- Prints expression snapshot post-curriculum

`run_open_stage(brain, n_cycles=100)`:
- Feeds DataStream to brain, periodic expression snapshots every N/8 cycles
- Tracks cross-modal events over the run
- Reports final memory delta, association count, Observer state
- Surfaces final attention window (what Genesis is attending to)
- Handles paused-state gracefully (prints reason and exits loop)

`run_interactive(brain)`:
- Commands: express, status, feed:<type>:<data>, pause, resume, quit
- Human input via `feed:` goes through same pipeline as all input

CLI: `--quiet`, `--interactive`, `--open-only`, `--cycles=N`

**`tests/test_open_stage.py`** — 35 new tests
- DataStream unit tests: type validity, loop behavior, shuffle, stats, pool contents
- advance_to_open integration: reaches OPEN, stores memories, handles already-open
- Open-stage processing: all input types, memory accumulation, never-crashes
- Context builds over repeated thematic input
- Edge cases: anomalous numeric data, interrupted sequences

### Decisions made

**Edge cases are first-class data:**
The pool deliberately includes anomalies, contradictions, and incomplete observations.
The world doesn't curate itself before presenting it to biological intelligence.
An anomaly is as real as a clean fact — often more informative. A contradiction
isn't a mistake; it's a thing that happens. Genesis should encounter them from
the start.

**No scores in OPEN stage:**
FOUNDATION → REASONING have advancement criteria. OPEN has none. The DataStream
is an environment, not a test. What Genesis makes of it is up to Genesis.
The only way we know what's happening is through expression snapshots and the
Observer — not curriculum eval scores.

**Unbounded loop with per-loop shuffle:**
An unbounded stream that repeats the same pool order every time would let processing
order become its own pattern — Genesis could learn "text always follows numeric" rather
than the content relationships. Per-loop reshuffle prevents this.

**Periodic expression snapshots during OPEN:**
Every N/8 cycles (so ~8 windows for a default 100-cycle run). Shows the attention
window, association clusters, and Observer state so development is visible without
interrupting it. Cross-modal event count tracked across the run as one measure of
multi-processor integration activity.

### M5 success criteria — status
- ✅ Uncurated, varied data available across 8 domains (56 items, 3 types)
- ✅ Edge cases (anomalies, contradictions, incomplete data) included
- ✅ Stream is unbounded, reshuffles each loop, reproducible with seed
- ✅ advance_to_open() reliably reaches OPEN stage before free data begins
- ✅ Full pipeline: curriculum → open stage → interactive, with CLI args
- ✅ 35 open-stage tests passing; 172 total tests green

### What's next (M6)
With all five layers running, Genesis can:
- Survive resource pressure (M1)
- Remember everything (M2)
- Surface state and receive intervention (M3)
- Integrate multiple processors with context-weighted significance (M4)
- Encounter the uncurated world (M5)

M6 options (no decisions made yet):
- Persistence across sessions (reload memory/attention state from DB on startup)
- Richer pattern processor (time-series analysis, trend detection beyond simple stats)
- Context-aware stagnation stimuli (Observer injects related novelty, not generic)
- REST/CLI interface for longer-running sessions with external queries
- Review and tune Observer thresholds with real behavioral data

### Open threads
- The `{docs,src` malformed directory — still needs cleanup (tarball artifact)
- Observer thresholds still default values — need real run data to tune
- Stagnation stimulus pool is generic — could become context-aware in M7
- Cross-modal detection still uses simple set intersection (no stemming/synonyms)

---

## Session 7 — April 3, 2026

**Platform:** Claude Code (CLI)
**Branch:** `claude/extract-genesis-repo-fn5vW`

### What happened
M6 built and tested. Three capabilities added: session persistence (survive restart),
rich pattern recognition (structural mathematics), and an archive (cross-session
reference and retrieval). 270 total tests, all green.

Jacob's direction: "persistent with rich pattern recognition and archive data for
reference and future use."

### What was built

**`src/processors/pattern.py`** — complete rewrite, rich structural detection

Before M6, PatternProcessor found: repeating subsequences, sorted order, basic
anomalies (>2σ). That's surface-level.

After M6, it detects the underlying mathematical structure:

- **Arithmetic progression**: constant difference, confidence tied to coefficient
  of variation of the differences. `[2, 4, 6, 8, 10]` → "arithmetic (step=2)"
- **Geometric progression**: constant ratio, tighter CV tolerance (×5 penalty
  because geometric sequences are less noisy). `[1, 3, 9, 27]` → "geometric (ratio=3)"
- **Fibonacci-like**: each element ≈ sum of previous two. Works for any seed, any
  scale — `[2, 2, 4, 6, 10, 16]` passes. Requires ≥5 elements to be meaningful.
- **Power sequences**: checks n² and n³ alignment with 5% error tolerance.
  `[1, 4, 9, 16, 25]` → "power sequence (n^2)"
- **Periodic**: tolerance-based cycle detection across periods 2..N/2. Returns
  best-fit period and confidence. Doesn't require exact repetition — handles
  real-world oscillation with noise.
- **Exact repeating subsequence**: carries forward from M5 (works on numeric and
  symbolic/categorical sequences alike)
- **Anomaly detection**: >2σ from mean (same logic, now surfaced per-pattern)
- **Trend classification**: strictly_increasing, strictly_decreasing, constant,
  oscillating, generally_increasing, generally_decreasing, variable. Computed
  from sign distribution of consecutive differences.
- **Statistical profile**: mean, std, range, coefficient of variation, trend slope
  (least-squares linear regression). Always included — gives the Observer and
  the archive a quantitative fingerprint for every sequence.

Multi-pattern output: ALL patterns found are reported, not just the first. Confidence
= max across all detected patterns. The processor tests for most-specific first
(Fibonacci before geometric, geometric before arithmetic) to avoid false positives.

Symbolic (non-numeric) sequences get n-gram frequency analysis and dominant bigram
detection.

**`src/memory/archive.py`** — ArchiveStore

Domain tagging on top of LongTermStore. Shares the same sqlite3.Connection (no
extra DB file, no multi-writer contention).

New tables:
- `archive_metadata`: (key, session_id, significance, domain_tags, archived_at)
- `archive_snapshots`: (snapshot_id, label, session_id, created_at, memory_keys JSON)

Auto-tags by source type:
- text → [language, symbolic]
- numeric → [quantitative, measurement]
- pattern → [structural, sequential]

Manual tags accumulate (re-tagging merges, never overwrites).
Significance takes the max of old and new on re-tag — relevance only grows.

`query(domain, min_significance, since_ts, session_id, limit)` — all filters
optional, combine freely.

`snapshot(label, memory_keys, session_id)` — capture the current working memory
key list as a named reference point. `retrieve_snapshot(id)` brings it back.
Useful for comparing what Genesis was attending to across sessions.

**`src/persistence/session.py`** — SessionManager + `src/persistence/__init__.py`

Checkpoint/restore for cognitive continuity across process restarts.

Saves to a `session_state` key-value table in the same DB:
- `cycle_count` — continuity of experience counter
- `curriculum_stage` — don't force FOUNDATION re-run after reaching OPEN
- `warm_start_keys` — top-30 working memory keys by relevance, for restore
- `session_id` — provenance tracking

`restore(brain)` promotes the warm-start keys from SQLite into working memory
(same two-tier recall path used normally). Attention picks up close to where
it left off without freezing state — the system re-evaluates context naturally.

Directive satisfaction intentionally not saved. It re-converges in a few cycles
from live resource/memory stats. Pickling live state across code changes is
fragile; convergence is fast and authentic.

**`src/orchestrator/orchestrator.py`** — M6 integration

New parameters: `db_path` (explicit DB path) and `resume` (trigger restore on init).
New attributes: `session_id` (UUID, 8 chars), `archive` (ArchiveStore), `_session_manager`.
New method: `save_session()` — manual checkpoint + optional verbose log.

`_store_synthesis()` now calls `archive.tag()` for every stored key with
significance + source_type. The archive grows automatically as Genesis processes.

`full_status()` now includes archive stats.

**`src/main.py`** — updated CLI

New flags:
- `--resume` — restore from last checkpoint; skips curriculum if already at OPEN
- `--snapshot <label>` — save a named attention snapshot at end of run

`save_session()` called automatically at end of every run. Next run with `--resume`
picks up at the right cycle count and curriculum stage.

Interactive commands added: `archive`, `archive:<domain>`, `snapshot:<label>`, `save`.

**Test isolation fix — `tests/test_orchestrator.py`**

`_brain()` now creates a fresh tempfile DB per test. Previously it used the shared
`data/genesis_memory.db`, which accumulated entries across runs. Count-based
assertions (`after >= before + 1`) became flaky once keys already existed from
prior runs. Tempfile DB ensures each test starts clean, consistent with how the
memory, interface, and open-stage tests work.

### Decisions made

**One DB file, shared connection:**
ArchiveStore and SessionManager both receive the sqlite3.Connection object from
LongTermStore rather than opening separate connections to the same file. This avoids
any multi-writer contention and keeps all Genesis state in one place:
`data/genesis_memory.db` (or whatever db_path is set to).

**Warm-start, not full state restore:**
Working memory is warm-started by promoting the top-30 keys from SQLite into
working memory via the normal recall path. The attention context re-establishes
itself naturally rather than freezing the exact working memory state. This is
more robust (no pickled object format to maintain) and more authentic — Genesis
re-evaluates its context at startup rather than loading a snapshot of what it
"felt" before.

**Archive tags accumulate, significance only grows:**
Re-tagging a key adds to its tag set (never overwrites). Significance is MAX of
existing and new. This means archive entries only become more specific and more
significant over time, never less. Consistent with total-retention philosophy.

**Multi-pattern output, most-specific first:**
Detection order: Fibonacci → power → geometric → arithmetic → periodic → repeating.
This prevents a geometric sequence (e.g. [1, 2, 4, 8]) from being mis-classified
as arithmetic just because the differences also look regular. The most specific
structural pattern wins, but all detected patterns are reported.

**Statistical profile always included:**
Stats (mean, std, range, coeff_variation, trend_slope) are computed for every numeric
sequence regardless of what patterns are found. The profile gives a quantitative
fingerprint that Archive queries, the Observer, and future analysis can use without
needing to re-process the raw data.

### M6 success criteria — status
- ✅ Session survives restart: cycle_count, stage, and working memory warm-start restored
- ✅ Rich pattern recognition: arithmetic, geometric, Fibonacci, power, periodic, trend, stats
- ✅ Archive: auto-tagging on every stored memory, queryable by domain/significance/time/session
- ✅ Named snapshots: capture + retrieve attention state at any point in time
- ✅ --resume flag: one flag picks up where the last run left off
- ✅ 270 tests passing (98 new), all green

### What's next (M7 options)
Genesis now has: survival pressure, total-retention memory, interaction layer,
multi-processor integration, open-stage data, session persistence, rich pattern
detection, and a cross-session archive. The system runs, persists, and can be
resumed.

M7 options:
- **Richer TextProcessor**: named entity extraction, topic modeling, causal language
  detection ("X caused Y", "without X, Y happened")
- **Context-aware stimuli**: Observer injects stagnation stimuli related to what
  Genesis was last attending to (rather than generic pool)
- **REST interface**: HTTP endpoint for longer-running session inspection without
  entering interactive mode
- **Cross-session analysis**: query the archive across sessions to find what topics
  have grown in significance over time
- **Processor confidence calibration**: track processor confidence over time to detect
  when the pattern processor is consistently over- or under-confident

### Open threads
- The `{docs,src` malformed directory — still needs cleanup (tarball artifact)
- Observer thresholds still defaults — need real multi-session data to tune
- Cross-modal detection uses simple set intersection (no stemming/synonyms)
- Pattern processor's anomaly detection requires ≥5 elements for reliable σ estimates
