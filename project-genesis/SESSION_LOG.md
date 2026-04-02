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

### What's next (M2)
- `src/memory/store.py` — persistent backend (SQLite is the leading candidate)
- `src/memory/attention.py` — dynamic relevance scoring, context-based window
- `src/memory/associations.py` — bidirectional association graph

### Open threads
- Python runtime limitation: `resource.getrusage()` gives cumulative CPU, not per-tick
  wall-clock CPU %. Could add more granular CPU pressure measurement later.
- The `{docs,src` malformed directory in the repo root (artifact from tarball creation)
  — should be investigated and cleaned up
- Reward system design (M3): what constitutes "reward" in a directive-driven system?
  Leading hypothesis: reward = directive satisfaction delta (positive change in any
  directive satisfaction is a reward signal)
- M2 SQLite decision: needs Jacob's input on whether persistent-to-disk is wanted now
  or if in-memory-with-file-dump is sufficient for M2
