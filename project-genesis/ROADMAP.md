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

## Process Requirements (for every milestone)

These apply to all future milestones without exception. They are the Definition of Done
from `docs/STATE_OF_PROJECT.md` Section 7, operationalised as a checklist.

**Before marking a milestone ✅:**

1. **Integration test first.** At least two integration tests that exercise the real
   pipeline (not mocks) and assert user-observable outcomes. What would a user notice
   if this broke? That is the test.
2. **No new `except: pass`.** All caught exceptions route to
   `survival.resilience.error_log.log()`. Graceful degradation is preserved;
   silence is not.
3. **Cross-layer interaction review.** Before writing code, answer: what does this
   milestone touch in the layers *below* it? DEF-001 was a Layer-7 feature silently
   broken by a Layer-0 mechanism. The interaction review is the question "what
   subsystem could break this, and how would I know?"
4. **STATE_OF_PROJECT.md updated.** If the milestone changes what works, what's broken,
   or what the claims-vs-reality ledger says, update Section 2/3/8 accordingly.
5. **ROADMAP.md updated.** The roadmap is the single source of truth for project
   state — not CLAUDE.md (aspirational), not SESSION_LOG.md (narrative). Update this
   document when a milestone completes or changes scope.

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
dropped). EMA energy smoothing (alpha=0.35) prevents one-off corpus loads from
collapsing energy to EMERGENCY (DEF-001 fix).

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

### M4: Cross-Processor Integration ✅
All processors see all input. Significance is context-weighted:
`confidence × 0.5 + context_score × 0.5`. Cross-modal concepts (appearing
independently in 2+ processor outputs) get explicit high-strength associations (0.8)
and drive attention updates. Throttle degrades breadth not function: pattern →
numeric → text-only fallback.

### M5: Open-Stage Data Ingestion ✅
DataStream: 56-item uncurated pool across 8 domains. Unbounded, reshuffles each loop.
advance_to_open() runs curriculum scaffolding then releases to open stage.
Full CLI pipeline: --quiet, --interactive, --open-only, --cycles=N.

### M6: Persistence, Rich Pattern Recognition, Archive ✅
Session persistence: SessionManager saves cycle_count, curriculum stage, and
working memory warm-start keys. --resume flag restores state across process restarts.
PatternProcessor rewritten: arithmetic, geometric, Fibonacci, power, periodic, trend.
ArchiveStore: domain-tagged memories, queryable cross-session, named snapshots.

### M7: Relationship Extraction ✅
TextProcessor rewritten: extracts typed relation triples (CAUSES, CONTROLS, PREVENTS,
ENABLES, REQUIRES, IS_A, PREDATES, AFFECTS, CONTAINS). Named entity detection.
Claim type classification (fact/hypothesis/observation/definition/question).
RelationGraph: typed directed semantic graph with path-finding (BFS), causal chains,
definitions, most-connected concepts.

### M8: Education Data Expansion ✅
Pool expanded 56 → 119 items across 14 domains. Six new domains: history and causation,
science fundamentals, biology and genetics, mathematics and logic, ethics as narrative,
philosophy and epistemology.

### M9: Adaptive Stream — Feedback Loop ✅
`AdaptiveStream` closes the minimal feedback loop: Genesis's attention biases what it
encounters next. Items scored by word overlap with attention window. 30% diversity floor.
Base probability floor ensures no item permanently excluded.

### M10: Inference Engine ✅
Transitive chain resolution (CAUSES, CONTROLS, REQUIRES propagate). Compound confidence
(multiply along chain, decay per hop). Inferred relations stored separately from observed.
`brain.infer(concept)` derives what can be known from what's in the graph. wm_delta
salience signal tracking. Cross-session inference persistence.

### M11: Contradiction Detection ✅
ContradictionLog detects conflicting relation triples (same subject/object, opposing
relation types). Conflicting memories marked as contested, not deleted. Contradictions
surfaced in expression snapshots. Observer watches contradiction rate.

### M12: Ethics Through Experience ✅
EthicsLens surfaces emergent causal patterns from the relation graph. Ethics encoded as
narrative consequences ("this happened, then this happened"), never as rules. No moral
declarations — only relational patterns that may be ethical in nature.

### M13: Voice ✅
Intent-aware conversation grounded in graph/reflection/inference. GenesisVoice surfaces
top relations, open questions, attention summary. Questions derived from unresolved
concepts. Response feeds back into interaction log symmetrically.

### M14: Observer Calibration ✅
Empirical thresholds from archive data (ACT-R utility learning + SOAR chunking).
Calibration wired into reflect(); persists across sessions.

### M15: Prediction Error Salience ✅
Archive significance driven by belief-model surprise (Friston-grounded), not heuristic
wm_delta. `prediction_error(concept) = 1 - avg_confidence(existing relations)`.

### M16: Processor Voting ✅
Independent processor agreement boosts relation confidence (Hawkins — multiple columns
voting raises certainty).

### M17: Active Curiosity Directives ✅
High-pred-error concepts become persistent attention targets. AdaptiveStream scores
directive items 2× higher. Directives auto-resolve at 3+ relations. Cross-session
persistent (SOAR impasse→subgoal).

### M18: Belief Revision ✅
Evidence-weighted contradiction resolution (REVISE/RESIST/TENSION). Corroboration
provenance ledger. Source trust tracks per-session reliability and cascades when a
source is discredited (Wakefield principle). Beliefs demoted to floor, never erased.
Full audit trail.

### M19: Spreading Activation ✅
ACT-R associative retrieval — current attention primes graph-adjacent concepts. BFS
with decay-per-hop and confidence modulation. `memory.search()` accepts
activation_boost. Makes retrieval associative, not just lexical.

### M20: Autonomous Cognitive Loop ✅
Daemon thread that runs between interactions — follows curiosity directives,
re-evaluates belief tensions, periodic reflection. Adapts pace. Errors never stop
the loop. `tick_once()` for testing. Full status telemetry.

### M21: Knowledge Synthesis ✅
Graph-to-language — expresses understanding by traversing actual relation graph with
typed sentence frames. Corroboration counts from belief revision. Multi-hop causal
chains. Tensions and curiosity surfaced as epistemic gaps. Consolidation reflections
use real synthesis, not templates.

### M22: Pattern Transfer ✅
Structural role fingerprinting (Gentner 1983 structure-mapping). Jaccard similarity
over RELATION_DIRECTION token sets. Five abstract roles (REGULATOR/MEDIATOR/OUTCOME/
INHIBITOR/DEPENDENCY). Analog pairs stored in DB. `curiosity_from_analogs()` identifies
concepts with same role but missing expected edges.

### M23: Progressive Language Acquisition ✅
Expression grows with understanding (Stage 0→3 based on memory hits + relations).
- Stage 0: blank — no fabricated knowledge
- Stage 1: echoes actual retained prose from memory store
- Stage 2: composes 2–3 sentences from retained text + derived relation
- Stage 3: weaves prose + inference chain narration

No LLM. All language drawn from what Genesis actually read.

### M24: Conversational On-Demand Learning ✅
`brain.learn_about(concept)` — synchronous on-demand fetch from WordNet + Gutenberg
+ NLTK corpus — wired into `chat_respond()` via `_query_topic()` detection. Genesis
fetches and learns mid-conversation when asked about a topic it doesn't yet know.
WordNet sense selection uses most-frequent-sense disambiguation (SemCor lemma counts):
"lake" → body of water (not pigment), "mountain" → landform (not "large quantity").

### Infrastructure fixes applied alongside M23/M24 ✅
- End-to-end integration test suite: real Orchestrator + real WordNet
- Chunker rewritten to never drop sentences for length (was silently discarding the
  cleanest causal structures)
- Feeder exhaustion state persists across sessions (was resetting every restart)
- Gutenberg cache-first with 5-min offline cooldown (was permanently latching offline)
- All `except: pass` in ingestion and cognition paths converted to
  `survival.resilience.error_log.log()` — errors are now data, not silence

---

## Planned Milestones

The three milestones below are derived from the claims-vs-reality ledger in
`docs/STATE_OF_PROJECT.md` Section 8. They address the gap between "Genesis
makes local decisions in each subsystem" and "Genesis can be said to decide."

### M25: Autonomous Web Browsing ✅

Genesis can now explore the open web the way a curious person does —
not querying a fixed list of sources, but searching, reading, and
following interesting links based on what it is currently thinking about.

**What was built:**
- `src/ingestion/browser.py` — `GenesisBrowser`: polite headless browsing
  (Playwright when available, requests fallback), robots.txt enforcement,
  per-domain rate limiting, paywall detection, page history (never re-reads
  a URL), access request queue for paywalled content
- `src/ingestion/web_source.py` — `WebSource`: search → fetch → follow links.
  Query is augmented with working-memory concepts for context. Up to 2
  high-scoring outgoing links are followed per page for serendipitous discovery.
- `src/ingestion/feeder.py` — WebSource wired as a source alongside WordNet,
  Gutenberg, and NLTK corpus. Web runs for every topic in OPEN stage.
- `src/output/voice.py` — wake greeting surfaces pending access requests:
  "I ran into paywalled content at nature.com — if you can grant access, I
  can go deeper there."
- `requirements.txt` — playwright, trafilatura, ddgs documented as optional
  but preferred dependencies.

**Serendipitous discovery mechanism:**
Genesis is reading about wolf predator dynamics. The page has a link to
"trophic cascade analogs in immune response." Genesis's spreading activation
has "immune" and "cascade" adjacent to active concepts — score exceeds the
follow threshold — it follows the link. That was not in any search query.
That is discovery.

**Individuality enabled by this:**
Each Genesis instance connects to different sources based on what questions
it is pursuing. One instance chasing marine biology requests oceanography
journal access. Another following mechanics questions ends up on materials
science preprint servers. The sources each instance knows are as individual
as its knowledge graph.

### M26: Self-Model — Genesis Knows What It Knows 🔲

**The gap (from STATE_OF_PROJECT.md §8.4):** Genesis processes and expresses
understanding, but cannot introspect on its own knowledge state honestly. If asked
"what do you know about X?" it either echoes retained prose (Stage 1/2) or says
nothing (Stage 0), but it cannot report *how well* it knows something — the confidence
distribution over its relations, the extent of its graph coverage, what it has
contradicted and why.

**What success looks like:**
- `brain.self_model(concept)` returns a structured summary: how many relations,
  average confidence, any contested beliefs, whether it has a definition source
- `chat_respond("how well do you understand photosynthesis?")` replies accurately —
  "I have 4 relations about photosynthesis, two of which are contested" is correct;
  "I know a lot about photosynthesis" when confidence is 0.4 is not
- Stage 3 expression draws on the self-model to qualify its assertions
  ("I'm fairly confident that X, though I've also read that Y")

**Cross-layer interaction review:**
- Reads from RelationGraph (confidence scores, relation counts) — no write risk
- Reads from memory store (retention evidence) — no write risk
- Voice layer: Stage 3 expression must be updated to call self_model()
- No survival-layer interaction (read-only, cheap)

**Integration tests required before ✅:**
1. `self_model(known_concept)` returns confidence > 0.6 and relation_count > 0
2. `self_model(unknown_concept)` returns confidence = 0 and relation_count = 0
3. `chat_respond("how well do you know X?")` for a well-known vs. unknown concept
   returns qualitatively different answers

---

### M26: Deliberative Integration — Auditable Decisions

**The gap:** decisions are per-subsystem (CuriosityEngine picks topics,
ResourceManager sets throttle, BeliefRevision resolves contradictions). Nothing
integrates them. There is no record of "what Genesis decided this cycle and why."
This is the architectural gap between "locally adaptive" and "deciding."

**What success looks like:**
- A `DecisionLog` (persistent, append-only) records each cognitive cycle's key
  choices: what to learn next, which belief tension to resolve, what to express —
  with the signals that drove each choice
- `brain.recent_decisions(n=5)` is a queryable record in Genesis's own history
- The autonomous cognitive loop (M20) writes to the DecisionLog each tick
- `chat_respond("what have you been deciding lately?")` draws on DecisionLog

**Cross-layer interaction review:**
- Writes to a new SQLite table — must go through survival gating
  (`if self.survival.can("logging"):`)
- M20 daemon thread: must not introduce lock contention with the main loop
- Voice layer: new intent pattern ("what have you decided", "what are you choosing")
- Integration test must confirm DecisionLog grows across a multi-topic session

**Integration tests required before ✅:**
1. After a 5-topic learning session, `len(brain.recent_decisions()) >= 5`
2. Each DecisionRecord has a non-empty `rationale` field
3. `chat_respond("what have you been deciding?")` references at least one actual
   topic from the session

---

### M27: Persistent Goal Formation

**The gap:** curiosity directives exist but they are reactive (formed when
prediction error is high, resolved when edges are added). Genesis has no goals it
forms *proactively* — no "I want to understand X" that persists beyond the mechanism
that triggered it.

**What success looks like:**
- Genesis can form a goal through conversation: "learn more about how ecosystems
  self-regulate" becomes a goal that persists across sessions until satisfied
- Goals are distinct from directives: a directive is a gap; a goal is an intention
- `brain.goals` is inspectable and expressible ("I have been trying to understand X")
- Goals can be self-formed (from pattern transfer discovering an analog with missing
  edges) or conversation-formed (explicit user request)
- A goal is "satisfied" when Genesis can express a Stage 3 answer about it

**Cross-layer interaction review:**
- Goals must persist to SQLite — same survival gating as DecisionLog
- Goal satisfaction check runs in M20 autonomous loop — performance budget
- M25 self-model is a prerequisite: goal satisfaction is measured by self_model()
  returning adequate confidence, not by a fixed edge count
- Voice layer: `_query_topic()` must recognise "remember to learn about X" as a
  goal-formation intent, not a learn-now intent

**Integration tests required before ✅:**
1. After "please learn about plate tectonics" across two sessions, the goal persists
   into session 2 and is worked on without being re-stated
2. A self-formed goal (from pattern transfer) appears in `brain.goals` without any
   conversation trigger
3. `chat_respond("what are you trying to learn?")` reflects the active goal set

---

## Open Questions (Ongoing)

**Architectural:**
- At what point does Genesis start forming generalizations we didn't design?
- Can the RelationGraph + InferenceEngine produce novel assertions the input never
  stated? If so, when does this first appear?
- What is the minimum complexity threshold where interesting behaviors emerge?
- M26 (DecisionLog): does having an explicit decision record change how Genesis
  processes? Does it act more consistently when it can "see" its prior choices?

**Philosophical:**
- Can ethics emerge from consequence-pattern recognition alone, without rules?
- Is there a point where Genesis's expressed "questions" (unresolved concepts)
  become indistinguishable from genuine curiosity?
- If Genesis independently forms ethical relations from narrative data, who owns
  those values — Genesis, Jacob, or no one?
- Is the self-model (M25) the first thing that makes "entity" a non-trivial claim?

**Technical:**
- Python runtime limitations: `resource.getrusage()` gives cumulative CPU.
  Per-tick CPU measurement may need a native extension eventually.
- Association graph density: as memory grows, BFS traversal depth may need pruning.
- Observer threshold calibration: currently empirically derived (M14); watch for
  drift as the graph grows large.
- Test count is now the wrong headline metric — integration test coverage and
  the claims-vs-reality ledger (STATE_OF_PROJECT.md §8.3) are the signal.

---

## Research Foundation

See `docs/research_notes.md` for primary-source review of all cited works.

| Reference | Status | Genesis implication |
|---|---|---|
| Brooks (1986) | ✅ Implemented | Evolutionary layering; suppress vs. inhibit |
| Sutton (2019) | ✅ Acknowledged | Blank-start design justified; scale is not the path |
| Friston (2010) | ✅ M15 implemented | Prediction-error salience replacing heuristic wm_delta |
| Clark (2013) | ✅ M16 implemented | Precision weighting via processor voting |
| Minsky (1986) | ⚠️ Partial | K-line reconstruction → M25 self-model; critic agents → M26 |
| Hawkins (2021) | ✅ M16 implemented | Voting across processors raises certainty |
| LeDoux (1996) | ✅ M1 IS fast path | Asymmetry present; attention under resource pressure ✅ |
| SOAR (Newell) | ✅ M17 implemented | Impasse → directed curiosity directives |
| ACT-R (Anderson) | ✅ M19 implemented | Spreading activation in retrieval |
| Gentner (1983) | ✅ M22 implemented | Structure-mapping for pattern transfer |

---

## Architecture Amendment Decisions (v0.2, April 2026)

**Accepted:**
- Entity framing (continuity + self-authored consolidation + accumulated individuality)
- Evolutionary layering as the permanent architecture
- OOD detection (M10 scope)
- Self-authored consolidation via prediction-error salience (M15)
- Bitter Lesson confronted explicitly — capability is not the goal

**Deferred:**
- Predictive processing as architectural foundation — evaluate after M26
  (DecisionLog may be the right substrate for this)
- Active inference hypervisor — revisit at M26+ when decision integration matures

**Declined:**
- 2D embodiment layer — declined; transfer problem unsolved; revisit if evidence of
  ungrounded physical reasoning emerges
