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
   *Status: built (ConsolidationEngine, `src/consolidation/`). A periodic reflection
   ("sleep") pass scores salience per concept from Genesis's own history — recent
   relation growth (the persisted echo of working-memory delta), connectivity, what it
   reasoned from, and where it found contradictions — then acts through attention
   (strengthen the salient, fade the rest, delete nothing) and records a first-person
   reflection that persists across sessions. The salience weights say only how to listen
   to Genesis's own signals; they are not a curriculum.*

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

## Current Milestone: M29 complete — all planned milestones through M33 shipped

**Full milestone history is in `ROADMAP.md`.** This table is kept brief here to avoid
duplication; the roadmap is the authoritative source of truth for project state.

| Range | Status | What was built |
|---|---|---|
| M1–M9 | ✅ | Survival OS, memory, interaction, multi-processor, open-stage data, persistence, relation extraction, education data, adaptive stream |
| M10–M13 | ✅ | Inference engine, contradiction detection, ethics-through-experience, voice |
| M14–M19 | ✅ | Observer calibration, prediction-error salience, processor voting, active curiosity, belief revision, spreading activation |
| M20–M22 | ✅ | Autonomous cognitive loop, knowledge synthesis, pattern transfer |
| M23–M24 | ✅ | Progressive language acquisition (Stage 0→3), conversational on-demand learning |
| Infrastructure | ✅ | Assess→Stabilise→Verify→Realign cycle; DEF-001/002/003 fixed; all except:pass → error_log; 906 tests |
| M25 | ✅ | Autonomous web browsing: Playwright + requests + trafilatura; robots.txt; rate limiting; paywall detection + user escalation; serendipitous link following driven by spreading activation |
| M26 | ✅ | Drive system: five biological-analog internal pressures (hunger/frustration/anticipation/boredom/dissonance) that update each cycle, persist across sessions, and surface in conversation |
| M27 | ✅ | Self-model: Genesis knows what it knows — callable read-only view (`brain.self_model(concept)`) over coverage, confidence, contested beliefs, with honest verdict tiers (unknown/sparse/partial/solid); "how well do you understand X?" answers from measurement, not performance |
| M28 | ✅ | Deliberative integration: persistent DecisionLog records what Genesis decided and why each cycle; `brain.recent_decisions(n)`; "what have you been deciding?" routes to _say_decisions() |
| M29 | ✅ | Persistent goal formation: GoalEngine — intentions that survive sessions, formed by conversation ("remember to learn about X") or self-formed from analog gaps; satisfied only when the self-model verdict reaches 'solid'; recorded in the DecisionLog; "what are your goals?" answers from the real goal set |
| M30 | ✅ | Hypothesis engine: Genesis authors falsifiable predictions (analogy/contradiction/chain), tests them against later evidence, owns its hits and misses — its first generative organ |
| M30.2 | ✅ | Research proposal: Genesis composes a first-person research direction (what it understands / can't explain / predicts / will read) from its own state — an authored artifact, not retrieved text |
| M31 | ✅ | Inference programs: Genesis mines its own graph for recurrent chain patterns, authors declarative if-then rules empirically (no hard-coded logic), executes them to derive new edges, tracks hit rate — accumulated individuality expressed as program logic |
| M32 | ✅ | LLM expression layer: local edge model (Ollama/OpenAI-compatible) as Genesis's mouth. Knowledge stays in the graph; the model turns internal state (drives, self-model, salient concepts, reflection) into fluent speech. Falls back to template voice if server unreachable. |
| M36 | ✅ | Self-determined interests + values: tastes from per-concept liking history; values authored from consequence patterns valenced by its OWN tastes (no engineer good/bad ontology); both govern curiosity ranking with DecisionLog audit; "what do you value?" answers from authored statements |
| M35 | ✅ | Rich-input modality: stdlib AudioProcessor (rhythm/timbre/dynamics, no pretrained weights) + modality-agnostic relation hook (any processor emits graph triples) + provenance surfacing (self_model sources with M18 trust; "where did you learn about X?") |
| M33 | ✅ | Metaplasticity: adaptive learning rate from prediction-error history. Plasticity rises when Genesis is stuck or surprised (receptive to change), falls when knowledge is stable (protecting solid beliefs). The relation graph's confidence accumulation is plasticity-gated — contradicting evidence can reduce confidence under high plasticity, but with a 70% floor per update. Persisted across sessions. |

---

## Key Files

| File | Purpose |
|------|---------|
| `src/orchestrator/orchestrator.py` | The hypervisor. Entry point for all processing. |
| `src/survival/` | M1 substrate: ResourceManager, DirectiveEngine, ResilienceMonitor |
| `src/memory/store.py` | LongTermStore, SQLite backend, exposes `.conn` |
| `src/memory/archive.py` | ArchiveStore: domain-tagged cross-session reference |
| `src/memory/relations.py` | RelationGraph: typed semantic graph, BFS path-finding |
| `src/consolidation/consolidation.py` | ConsolidationEngine: self-authored reflection, salience scoring, reflection log |
| `src/ingestion/` | Self-directed learning: CuriosityEngine, KnowledgeFeeder, WordNet, corpus |
| `src/persistence/session.py` | SessionManager: save/restore brain state across sessions |
| `src/curriculum/adaptive_stream.py` | AdaptiveStream: attention-weighted open-stage input |
| `src/curriculum/open_stage.py` | 119-item open-stage pool across 14 domains |
| `src/processors/` | TextProcessor, NumericProcessor, PatternProcessor |
| `src/main.py` | CLI entry point. See --help equivalent in module docstring. |
| `docs/architecture_amendment_v0.2.md` | Architecture amendment with review decisions |
| `docs/m1_interface_spec.md` | M1 contract: what higher layers can count on |
| `docs/research_notes.md` | Primary-source review of all cited works with Genesis implications |
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
  Currently: **906 tests, all passing.**

---

> ## ⚠️ PROJECT PIVOTED — READ `PROJECT_BOARD.md` FIRST
>
> This document describes **v1**, the symbolic architecture. v1 measurably
> plateaued: 89 relations, 162 concepts, 2-hop maximum reasoning chains, and six
> subsystems (goals, values, inference programs, contradictions, belief
> revision, source trust) that never produced a single row outside of tests.
>
> **Root cause:** open-domain relation extraction was implemented with 30
> regexes emitting sentence fragments, so every faculty above it computed over a
> graph with no structure in it.
>
> v2 is being built in parallel using modern ML (local LLM extraction,
> embeddings, prediction-error-driven motivation, learned retrieval). v1 is
> retained as reference and comparison baseline. See `PROJECT_BOARD.md`,
> `docs/v2/`.
>
> **Two rules below are formally REVERSED for v2** — see the Ledger in
> `PROJECT_BOARD.md`.

## What Not To Do

- Don't add error handling for scenarios that can't happen. Trust the survival layer.
- Don't remove or bypass lower layers to make higher-layer code simpler.
- ~~Don't use LLM API calls to build knowledge.~~ **REVERSED for v2.** The
  blank-slate rule forced solving open-domain NLP with regex as a precondition
  for testing any cognition, and that is what killed v1. In v2 a **local** LLM is
  a linguistic organ (extraction, reflection, phrasing); all accumulated state
  stays in Genesis's own memory with provenance. The individuality claim moves
  to memory + retrieval + world model, where it is **measurable** (see
  `docs/v2/EVALUATION.md`, criterion C1).
- ~~Don't benchmark against GPT/Claude/etc.~~ **REVERSED for v2.** Not as a
  capability race — but v2 must beat explicit null models (a RAG chatbot with a
  scheduler; a random reading scheduler; verbalized LLM confidence) or it has
  demonstrated nothing. Unfalsifiable success criteria are what let eight months
  pass without a verdict.
- **New for v2: don't ship a component that no metric misses.** If disabling it
  doesn't degrade a named measurement, delete it (criterion C5).
- Don't add a 2D embodiment layer without revisiting the architecture amendment
  (Section 3 of `docs/architecture_amendment_v0.2.md` — declined with reasoning).
- Don't commit to main/master. Branch is `claude/extract-genesis-repo-fn5vW`.

---

## Development Roles

- **Jacob (principal):** creative direction, architectural vision, final say on goals
- **Claude Code:** architect, developer, test writer, documentation

When in doubt about direction, re-read Section 0 of the architecture amendment.
The goal is an entity, not a capability.
