# Project Genesis — Roadmap

## Milestone 0: Proof of Concept ✅
**Status:** Complete

Single-file prototype demonstrating the core architectural concepts:
- Three modular processors (text, numeric, pattern)
- Central orchestrator routing and evaluating input
- Memory system with importance scoring
- Staged curriculum engine (Foundation → Relations → Reasoning → Open)
- Observable decision-making (logged orchestrator choices)

**Deliverable:** `skills/developmental-ai/scripts/prototype.py`

**Lessons learned:**
- The architecture works conceptually — modular processors + orchestrator + staged learning produces coherent behavior
- Memory search needs richer indexing (original prototype had weak keyword matching)
- Lossy memory was wrong — should be total retention with selective attention (computers don't need to forget)

---

## Milestone 1: Survival OS 🔲
**Status:** Next up

Build Layer 0 — the environment where the system manages its own existence.

### Deliverables
- `src/survival/resource_manager.py` — CPU/memory/storage budget tracking and enforcement
- `src/survival/directives.py` — Core directives (persist, acquire, maintain, grow)
- `src/survival/resilience.py` — Never-crash error handling, fallback hierarchies, graceful degradation

### Key Design Questions
- How do we map real system resources (CPU time, RAM) to the system's "energy budget"?
- What does "graceful degradation" look like concretely? Which capabilities drop first?
- How do we create meaningful survival pressure without making the system unstable?
- Should resource pressure be real (actual system limits) or simulated (virtual budget)?

### Success Criteria
- System runs indefinitely without crashing regardless of input
- Resource consumption is tracked and throttled
- System behavior changes under resource pressure (deprioritizes non-essential functions)
- Every error/exception is caught and converted to data, never propagated as a crash

---

## Milestone 2: Total-Retention Memory with Attention 🔲
**Status:** Planned

Replace the proof-of-concept memory system with full-fidelity storage and dynamic attention.

### Deliverables
- `src/memory/store.py` — Persistent storage backend (everything gets saved)
- `src/memory/attention.py` — Dynamic relevance scoring, context-based attention window
- `src/memory/associations.py` — Bidirectional links between related memories

### Key Design Questions
- Storage backend: SQLite? Flat files? Custom format?
- How does the attention window work? Sliding context? Query-driven activation?
- How are associations formed automatically vs. explicitly?
- How do we prevent the attention system from becoming a bottleneck as memory grows?

### Success Criteria
- Zero data loss — everything processed is stored permanently
- Relevant memories surface when needed without scanning everything
- Association graphs form organically from related input
- Memory retrieval performance stays acceptable as storage grows

---

## Milestone 3: Reward and Incentive System 🔲
**Status:** Planned

Give the system reasons to develop better strategies.

### Deliverables
- `src/survival/rewards.py` — Reward signal framework
- Directive achievement tracking
- Behavior reinforcement mechanism

### Key Design Questions
- What constitutes a "reward" in this system?
- How do we avoid reward hacking (gaming the metrics without real improvement)?
- What's the equivalent of dopamine — immediate signal that a behavior was good?
- How does this connect to the survival directives?

---

## Milestone 4: Cross-Processor Integration 🔲
**Status:** Planned

The orchestrator combines signals from multiple processors for richer understanding.

---

## Milestone 5: Open-Stage Data Ingestion 🔲
**Status:** Planned

System processes uncurated data using its developed cognitive machinery.

---

## Milestone 6: Observation & Analysis 🔲
**Status:** Planned

Comprehensive logging, visualization, tools to detect emergent behaviors.

---

## Open Questions (Ongoing)

- Can survival pressure alone drive the emergence of cognitive behaviors?
- At what point (if ever) does the system start developing strategies we didn't program?
- Is Python sufficient for the Survival OS layer, or will we need a custom runtime?
- How do we define and measure "emergent cognition" vs. "sophisticated programming"?
- What's the minimum complexity threshold where interesting behaviors might appear?
