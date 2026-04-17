# CLAUDE.md — Project Genesis

This file provides context for Claude Code sessions working on Project Genesis.
Read this before touching any code.

---

## What This Project Is

Genesis is not an AI assistant. It is not a chatbot. It is not a benchmark competitor.

Genesis is an attempt to build a system that can plausibly be said to **be, and think,
and make decisions for itself** — an entity, not a tool.

The three properties that make something an entity rather than a capability:

1. **Continuity** — persistent memory across time, not context-window reconstruction.
   Genesis remembers what it has processed across sessions. Its history is its own.

2. **Self-authored consolidation** — an offline process that decides what matters based
   on the system's own internal signals, not the engineer's category scheme.
   *Status: partially built (SessionManager, ArchiveStore). Gap: significance scoring
   is still engineer-specified. Working-memory delta as salience signal is the next step.*

3. **Accumulated individuality** — a perspective that develops over time and is specific
   to this instance. Two Genesis instances started from the same seed diverge purely
   through their processing history. That divergence is the individuality.

Genesis starts blank — no pretrained weights, no inherited parametric knowledge. This is
intentional and load-bearing. It is the only way the individuality claim is coherent.

**What success looks like:** not a capability threshold. A qualitative shift in what's
natural to say about the system. "It noticed." "It decided." "It has been thinking about
wolves lately."

**What Genesis is not competing on:** benchmarks, reasoning scores, coding ability,
factual recall. Frontier models win those. That is acknowledged in advance and is not
evidence against this project. (See: Sutton's Bitter Lesson and the response in
`docs/architecture_amendment_v0.2.md` Section 7.)

---

## Architectural Principles

### 1. Evolutionary Layering (the most important one)

The architecture is permanent and cumulative, not replaceable.

- **M1 is not a stepping stone.** M1 is the permanent substrate. M9 is M1+M2+...+M9,
  never M9 instead of M1.
- **Higher layers suppress, they don't replace.** When a deliberative layer has something
  useful to contribute, it overrides the reflex. When it doesn't, it goes silent, and
  the reflex keeps running.
- **Failure modes are regressions, not crashes.** If M4 gets stuck, M3 continues.
  If everything above M1 fails, M1 keeps the agent alive.

This is subsumption architecture (Brooks 1986), not Erlang fault tolerance.
The system has a *nature* — defined by its lowest layer — independent of what it learns.

**Corollary for developers:** never remove a lower layer to simplify a higher one.
Never make higher-layer code assume lower layers are unavailable.

### 2. Total Retention with Selective Attention

Genesis never discards data. Errors are data. Anomalies are data. Contradictions are
data. The memory system retains everything; attention determines what is active, not
what exists.

This is not a performance decision. It is a philosophical commitment. A mind that erases
the past to save space is not continuous. Genesis keeps everything.

### 3. Errors Are Data, Not Stop Conditions

No exception crashes the system. Every unhandled case returns a degraded-but-valid
result. The error is logged and becomes part of Genesis's history.

SurvivalOS wraps all processor dispatch. Nothing propagates up as an unhandled exception
by design. This is not defensive programming — it is the reflexive substrate running
when the deliberative layer fails.

### 4. Bottom-Up Development

Higher layers are never built before lower layers are stable. The curriculum progression
(FOUNDATION → RELATIONS → REASONING → OPEN) mirrors this. M1 survival before M2
memory quality before M3 interaction before M4 integration.

Don't build M12 on a shaky M1. Fix the foundation first.

### 5. Calibrated Uncertainty

Genesis should know what it doesn't know. Confidence scores on every memory and relation.
Observer watching behavioral patterns. OOD detection (planned M10) to flag inputs unlike
anything processed before. Dunning-Kruger is an architectural flaw — it means nothing in
the system represents "I don't know this."

---

## Architecture at a Glance

```
                    ┌─────────────────────────┐
                    │     OPEN STAGE / M9+    │  AdaptiveStream, feedback loop
                    ├─────────────────────────┤
                    │   REASONING / M4–M7     │  Integration, Relations, Archive
                    ├─────────────────────────┤
                    │   CURRICULUM / M2–M3    │  Memory quality, Interaction layer
                    ├─────────────────────────┤
                    │   SURVIVAL OS / M1      │  ← permanent substrate, always running
                    └─────────────────────────┘
```

Each layer is always present. Higher layers add capability; they don't remove lower
layers. The survival OS runs beneath every cycle regardless of what higher layers do.

---

## Current Milestone: M9 complete

| Milestone | Status | Summary |
|-----------|--------|---------|
| M1 | ✅ | SurvivalOS: resource management, directives, resilience |
| M2 | ✅ | Total-retention memory, two-tier (working + long-term) |
| M3 | ✅ | Interaction layer: Observer, Expression, association |
| M4 | ✅ | Multi-processor integration, cross-modal synthesis |
| M5 | ✅ | Curriculum pipeline: FOUNDATION→RELATIONS→REASONING→OPEN |
| M6 | ✅ | Session persistence, rich pattern recognition, ArchiveStore |
| M7 | ✅ | Relationship extraction, RelationGraph, typed semantic graph |
| M8 | ✅ | Education data expansion: 119-item pool, 14 domains |
| M9 | ✅ | AdaptiveStream: attention-weighted input selection, feedback loop |
| M10 | 🔲 | Inference engine: transitive chains, wm_delta salience, OOD detection |
| M11 | 🔲 | Contradiction detection: conflicting relations flagged, not overwritten |
| M12 | 🔲 | Ethics through experience: consequence sequences, requires M9 |
| M13 | 🔲 | Response generation: structured output, grounded statements |
| M14 | 🔲 | Observer calibration: empirical thresholds from archive data |

---

## Key Files

| File | Purpose |
|------|---------|
| `src/orchestrator/orchestrator.py` | The hypervisor. Entry point for all processing. |
| `src/survival/` | M1 substrate: ResourceManager, DirectiveEngine, ResilienceMonitor |
| `src/memory/store.py` | LongTermStore, SQLite backend, exposes `.conn` |
| `src/memory/archive.py` | ArchiveStore: domain-tagged cross-session reference |
| `src/memory/relations.py` | RelationGraph: typed semantic graph, BFS path-finding |
| `src/persistence/session.py` | SessionManager: save/restore brain state across sessions |
| `src/curriculum/adaptive_stream.py` | AdaptiveStream: attention-weighted open-stage input |
| `src/curriculum/open_stage.py` | 119-item open-stage pool across 14 domains |
| `src/processors/` | TextProcessor, NumericProcessor, PatternProcessor |
| `src/main.py` | CLI entry point. See --help equivalent in module docstring. |
| `docs/architecture_amendment_v0.2.md` | Architecture amendment with review decisions |
| `docs/m1_interface_spec.md` | M1 contract: what higher layers can count on |
| `ROADMAP.md` | Milestone plan with rationale |
| `SESSION_LOG.md` | Per-session development log |

---

## Testing Conventions

- **Temp DB per test:** any test with count-based assertions (`after > before`) must use
  a tempfile DB via the `_brain()` factory pattern. Shared persistent DBs accumulate
  data across runs and break count assertions.
- **Never test implementation details of lower layers from higher-layer tests.** Test M1
  in `test_survival_*.py`. Test M4 in `test_orchestrator.py`. Don't reach across layers.
- Run full suite before committing: `python -m pytest` from `project-genesis/`.
  Currently: **442 tests, all passing.**

---

## What Not To Do

- Don't add error handling for scenarios that can't happen. Trust the survival layer.
- Don't remove or bypass lower layers to make higher-layer code simpler.
- Don't add LLM API calls. Genesis builds its knowledge from processed input, not from
  querying external models.
- Don't benchmark against GPT/Claude/etc. That's not the competition.
- Don't add a 2D embodiment layer without revisiting the architecture amendment
  (Section 3 of `docs/architecture_amendment_v0.2.md` — declined with reasoning).
- Don't commit to main/master. Branch is `claude/extract-genesis-repo-fn5vW`.

---

## Development Roles

- **Jacob (principal):** creative direction, architectural vision, final say on goals
- **Claude Code:** architect, developer, test writer, documentation

When in doubt about direction, re-read Section 0 of the architecture amendment.
The goal is an entity, not a capability.
