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
