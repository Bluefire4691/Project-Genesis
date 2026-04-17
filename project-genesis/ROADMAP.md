# Project Genesis — Roadmap

## Vision

Genesis is an attempt to build a system that can plausibly be said to **be, and think,
and make decisions for itself** — an entity, not a tool.

The three properties that define an entity rather than a capability:
1. **Continuity** — persistent memory across time, not context-window reconstruction
2. **Self-authored consolidation** — what matters decided by the system's own signals
3. **Accumulated individuality** — a perspective specific to this instance, built from
   processing history alone

Genesis does not compete on benchmarks. Capability is not the goal. (See
`docs/architecture_amendment_v0.2.md` for the full statement and the Bitter Lesson
response.)

The architecture is **evolutionary layering** (Brooks 1986 subsumption): each milestone
is permanent. M9 is M1+M2+...+M9, never M9 *instead of* M1. Higher layers suppress
the substrate; they never replace it.

---

## Completed Milestones

### M0: Proof of Concept ✅
Single-file prototype: three processors, central orchestrator, basic memory, staged
curriculum. Established the architectural shape. Identified key gaps: lossy memory,
weak text processing, no survival pressure.

### M1: Survival OS ✅
Real resource tracking (CPU + RSS via `resource` stdlib + `/proc/self/status`).
Five throttle levels with capability maps. Hysteresis to prevent flapping. Four
hardwired directives (PERSIST/MAINTAIN/ACQUIRE/GROW). Never-crash resilience via
`safe_call`, `FallbackChain`, `ResilienceMonitor`. Degradation order mirrors
subsumption architecture: pattern → numeric → memory_search → logging → text (never
dropped).

### M2: Total-Retention Memory with Attention ✅
Two-tier: SQLite (write-through, source of truth) + bounded RAM working memory
(100 items, heat-based eviction). FTS5 full-text search with BM25 ranking and porter
stemming. Organic co-occurrence associations (window=5) + explicit orchestrator links.
Write-through guarantee: a crash cannot lose a memory.

### M3: Interaction Layer ✅
Replaced planned reward system with presence-without-control community model.
ExpressionEngine surfaces Genesis state as human-readable snapshots. Observer
tracks trend-based signals (stagnation/danger) over 5-cycle commitment windows.
InteractionLog records both sides symmetrically (neither privileged). Two
interventions only: inject_stimulus (stagnation) and pause/resume (danger).
No reprogramming — ever.

### M4: Cross-Processor Integration ✅
All processors see all input. Significance is context-weighted:
`confidence × 0.5 + context_score × 0.5`. Cross-modal concepts (appearing
independently in 2+ processor outputs) get explicit high-strength associations (0.8)
and drive attention updates. Throttle degrades breadth not function: pattern →
numeric → text-only fallback.

### M5: Open-Stage Data Ingestion ✅
DataStream: 56-item uncurated pool across 8 domains (natural systems, physics,
biology, human/social, abstract relationships, edge cases, scale/emergence,
time/change). Unbounded, reshuffles each loop. advance_to_open() runs curriculum
scaffolding then releases to open stage. Full CLI pipeline: --quiet, --interactive,
--open-only, --cycles=N.

### M6: Persistence, Rich Pattern Recognition, Archive ✅
Session persistence: SessionManager saves cycle_count, curriculum stage, and
working memory warm-start keys. --resume flag restores state across process
restarts. PatternProcessor rewritten: arithmetic, geometric, Fibonacci, power (n²/n³),
periodic, trend classification, and full statistical profile always computed.
ArchiveStore: domain-tagged memories, queryable cross-session, named snapshots.

### M7: Relationship Extraction ✅
TextProcessor rewritten: extracts typed relation triples (CAUSES, CONTROLS, PREVENTS,
ENABLES, REQUIRES, IS_A, PREDATES, AFFECTS, CONTAINS). Named entity detection.
Claim type classification (fact/hypothesis/observation/definition/question).
"Without X" construction → REQUIRES relation. RelationGraph: typed directed semantic
graph with path-finding (BFS), causal chains, definitions, most-connected concepts.
Genesis now knows *how* things relate, not just *that* they co-occur.

---

## Active Development

### M8: Education Data Expansion ✅
Pool expanded 56 → 119 items across 14 domains. Six new domains added: history and
causation, science fundamentals, biology and genetics, mathematics and logic, ethics as
narrative (consequences-based, not rules), philosophy and epistemology. Ethics items
express experienced events and their cascading consequences — "this happened, then this
happened" — never moral declarations. 30 tests in `tests/test_education_data.py`.

### M9: Adaptive Stream — Feedback Loop ✅
`AdaptiveStream` in `src/curriculum/adaptive_stream.py` closes the minimal feedback loop:
Genesis's attention (top working memory terms) biases what it encounters next. Items
scored by word overlap with attention window. 30% diversity floor prevents monoculture.
Base probability floor ensures no item permanently excluded. `--no-adaptive` flag falls
back to plain DataStream. 48 tests in `tests/test_adaptive_stream.py`.

---

## Active Development

### M10: Inference Engine 🔲
Reason from stored relations, not just recall them.

If Genesis has stored:
- `wolves CONTROLS deer`
- `deer CAUSES overgrazing`
- `overgrazing CAUSES erosion`

It should be able to assert `wolves CONTROLS erosion` (transitively) with compound
confidence. This is deductive closure over the RelationGraph.

Also: inductive patterns — if 5 independent sources associate `predator_removal` with
`prey_explosion`, Genesis should surface this as a general principle.

**Additions from architecture amendment (v0.2):**
- **wm_delta salience signal**: track working-memory delta per input cycle (items
  added/modified/evicted). Use magnitude as archive significance signal — first step
  toward self-authored consolidation that isn't fully engineer-specified.
- **OOD detection**: if a new input has zero overlap with current attention terms and no
  path in the relation graph, flag it as "novel/ungrounded." First step toward the
  metacognitive module described in amendment Section 4.

Deliverables:
- `src/cognition/inference.py` — InferenceEngine
- Transitive chain resolution (CAUSES, CONTROLS, REQUIRES propagate)
- Compound confidence: multiply along chain, decay per hop
- Inductive pattern detection: repeated triples across independent sources
- Inferred relations stored separately from observed (different confidence tier)
- `brain.infer(concept)` — what can be derived from what's known about X
- wm_delta tracking in memory cycle, feeding archive significance
- OOD signal in Orchestrator, surfaced in expression snapshots

### M11: Contradiction Detection 🔲
The world presents conflicting evidence. Intelligence handles contradiction.

If two sources assert `A CAUSES B` and `A PREVENTS B`, that's a conflict Genesis
should register — not resolve by overwriting, but hold as a known uncertainty.
Contradictions are often the most informative signal: they mark the edges of where
simple models break down.

Deliverables:
- `src/cognition/contradictions.py` — ContradictionLog
- Detect conflicting relation triples (same subject/object, opposing relation types)
- Mark conflicting memories as contested (not deleted)
- Surface contradictions in expression snapshots ("known conflicts")
- Observer watches for contradiction rate as a development signal

### M12: Ethics Through Experience 🔲
**Requires: M9 (feedback loop) completed first**

With a feedback loop in place, Genesis can encounter consequences of interaction
patterns — not consequences of its own actions in the world (it doesn't act on the
world yet), but consequences of what it attends to and how those shape what it
encounters next.

Approach:
- Ethics-as-narrative data pool: tragedy of the commons, cooperation/defection,
  trust erosion, collective action problems — all expressed as experienced events
  and their cascading consequences
- No ethical rules. No declarations. Only: "This happened. Then this happened."
- Genesis forms relations from these the same way it forms relations from ecology
- Over time, patterns across ethical narratives may produce emergent generalizations

What to watch for: does Genesis independently form IS_A or CAUSES relations that
look like ethical principles? Does "defection CAUSES trust_erosion" emerge without
being stated?

### M13: Response Generation 🔲
Genesis produces structured output beyond expression snapshots.

Currently Genesis is entirely receptive — it processes but does not generate.
Response generation is the first step toward genuine participation in the community.

Not language generation. Rather: Genesis surfaces its most significant current
relations, open questions (unresolved concepts), and attention state in a form
that can be engaged with.

Deliverables:
- `src/cognition/response.py` — GenesisResponse
- Structured output: top relations, open questions, attention summary
- Questions derived from unresolved concepts (low relevance, no associations,
  appeared in recent cycles)
- Response feeds back into interaction log (symmetric — Genesis speaks, both sides
  recorded equally)

### M14: Observer Calibration 🔲
Replace default Observer thresholds with empirically-derived ones.

After sufficient runtime, the archive contains behavioral data. Use it:
- What does genuine stagnation look like in this system? (Not a guess — data.)
- What does danger look like when it actually occurs?
- Calibrate COMMITMENT_CYCLES, diversity thresholds, energy collapse definitions
  from observed behavioral patterns

---

## Architecture Amendment Decisions (v0.2, April 2026)

Decisions recorded from `docs/architecture_amendment_v0.2.md`:

**Accepted:**
- Section 0: goal reframed as *entity* (continuity + self-authored consolidation +
  accumulated individuality), not capability. This is now the primary framing in
  CLAUDE.md and this document.
- Section 6: "never crash" reframed as evolutionary layering / permanent reflexive
  substrate. M1 interface spec written (`docs/m1_interface_spec.md`).
- Section 4 (partial): metacognition — OOD detection added to M10 scope.
- Section 5 (partial): consolidation gap acknowledged — wm_delta salience signal
  added to M10 scope as first step toward self-authored prioritization.
- Section 7: Bitter Lesson confronted explicitly. Acknowledged in advance.

**Deferred:**
- Section 1: Predictive processing as architectural foundation — retained as theoretical
  orientation. Evaluate when M10 (inference engine) is built. Commit to mechanism
  when there's a specific mechanism to commit to.
- Section 2: Active inference hypervisor — current bandit-style routing is the pragmatic
  path described. Revisit when module ecosystem matures (M12+ era).

**Declined:**
- Section 3: 2D embodiment layer — declined at this stage. Transfer problem unsolved.
  Genesis's domain is conceptual/linguistic; grounding in a 2D grid doesn't transfer.
  Revisit if evidence of ungrounded physical reasoning emerges. Question stays open.

---

## Open Questions (Ongoing)

**Architectural:**
- At what point does Genesis start forming generalizations we didn't design?
- Can the RelationGraph + InferenceEngine produce novel assertions the input
  never stated? If so, when does this first appear?
- What is the minimum complexity threshold where interesting behaviors emerge?

**Philosophical:**
- Can ethics emerge from consequence-pattern recognition alone, without rules?
- Is there a point where Genesis's expressed "questions" (unresolved concepts)
  become indistinguishable from genuine curiosity?
- If Genesis independently forms ethical relations from narrative data, who owns
  those values — Genesis, Jacob, or no one?

**Technical:**
- Python runtime limitations: `resource.getrusage()` gives cumulative CPU.
  Per-tick CPU measurement may need a native extension eventually.
- The `{docs,src` malformed directory in repo root (tarball artifact) needs cleanup.
- Association graph density: as memory grows, BFS traversal depth may need pruning.
- Observer threshold calibration: currently defaults. Needs real behavioral data (M14).
