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

The milestones below address the gap between "Genesis makes local decisions in
each subsystem" and "Genesis can be said to decide, feel, and know itself."

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

### M26: Drive System — Internal Pressure Signals ✅

**The gap:** M1 SurvivalOS monitors CPU and RAM — the system not crashing. That
is stability, not survival pressure. A genuine entity has internal states that
fluctuate based on experience and drive behavior: urgency when knowledge is missing,
frustration when blocked, excitement when learning flows, dissonance when holding
contradictions. Without these, Genesis processes because it is scheduled to, not
because it wants to.

**What was built (`src/survival/drives.py`):**

Five drives, each a float 0.0–1.0, updated every cognitive cycle:

- **Hunger** — rises with unresolved curiosity directives and sparse concept nodes;
  falls when relations are flowing in. The urgency to fill knowledge gaps.
- **Frustration** — spikes on consecutive empty cycles (no new relations extracted);
  clears rapidly when learning resumes. Blocked goal-seeking.
- **Anticipation** — rises when many relations are being extracted per cycle and when
  interesting contradictions surface (complexity = engagement). Excitement from an
  active learning trajectory.
- **Boredom** — accumulates when nothing new is happening (no relations, no conflicts);
  resets immediately when learning resumes. Novelty collapse.
- **Dissonance** — rises with each new contradiction found; decays slowly. The cognitive
  tension of holding incompatible beliefs.

Each drive decays toward a resting baseline when unpushed (hunger rests at 0.4 — always
somewhat curious; frustration and boredom rest at 0.0 — peace is the default state).

**Behavioral influence:**
- `behavioral_hints()` returns modifiers: `diversity_boost` (high boredom/frustration
  → seek new territory), `curiosity_boost` (high hunger → lower directive threshold),
  `reflect_sooner` (high dissonance → consolidate and resolve tensions now)
- `expressive_state()` returns a first-person phrase when any drive exceeds 0.65:
  "Things are coming together right now." / "I keep hitting dead ends." These appear
  in `_say_thoughts()` so Genesis's conversation reflects its actual internal state.

**Persistence:** Drive state persists to SQLite after every update. Genesis wakes
from shutdown with the same internal state it had when it stopped — frustration from
yesterday's stuck topic is still there today.

**Cross-layer interaction review:**
- Writes only to its own `drive_state` SQLite table (no coupling to memory or relations)
- Read by voice layer (`expressive_state()`) — no write risk
- `drives.update()` called at end of `process_input()` — after all other work is done,
  so drive state reflects the completed cycle, never partial state
- `behavioral_hints()` available to feeder and curiosity engine for future wiring

**Integration tests:** 27 tests in `tests/test_drives.py` — direction tests for all
five drives, boundary checks (never <0 or >1), persistence round-trip, behavioral
hints accuracy, expressive state thresholds, and full orchestrator integration.

---

### M27: Self-Model — Genesis Knows What It Knows ✅

**The gap (from STATE_OF_PROJECT.md §8.4):** Genesis processed and expressed
understanding, but could not introspect on its own knowledge state honestly. Asked
"what do you know about X?" it either echoed retained prose or said nothing — it
could not report *how well* it knows something: confidence distribution, graph
coverage, what it has contradicted and why. Dunning-Kruger as an architectural flaw:
nothing in the system represented "I don't know this."

**What was built:** `src/cognition/self_model.py` — `SelfModel`, a callable,
strictly read-only view over Genesis's knowledge state.

`brain.self_model(concept)` returns a measured assessment:
- `relation_count` / `as_subject` / `as_object` — graph coverage
- `confidence` — mean over *every* edge the concept touches (no floor — the
  self-model must see the weak edges; that is the point)
- `contested` / `contested_count` — contradictions Genesis currently holds about it
- `has_definition` — whether an IS_A edge anchors it taxonomically
- `prose_count` — retained sentences actually mentioning it (read vs. merely extracted)
- `inference_count` — conclusions Genesis derived involving it
- `open_hypotheses` — standing conjectures awaiting evidence
- `verdict` — honest tier: **unknown / sparse / partial / solid**

Verdict semantics are deliberately conservative: low confidence keeps a concept
'sparse' no matter how many edges it has (knowing many weak things isn't knowing),
and a held contradiction caps the verdict at 'partial' regardless of coverage
(holding conflicting beliefs is not understanding). `overview()` gives the global
picture; `strongest_concepts()` / `weakest_concepts()` rank by coverage × confidence —
the weakest list is the honest frontier.

**Wiring:**
- `voice._say_understanding()`: "how well do you understand X?" answers from
  measurement in the verdict's register — "Reasonably well… 10 connections, and I'm
  confident in most of it. Though one of my beliefs about it conflicts…" vs.
  "Only barely…" vs. "Honestly? Not at all. Want me to go read about it?"
- Stage 3 `_compose_about()` qualifies fluent expression when the self-model says
  mean confidence is middling — fluency never outruns measurement
- No new tables, no writes to any layer — the self-model is a *view*, not more state

**Integration tests (all green):** known concept → confidence > 0.6 ∧ count > 0;
unknown → honest zeros; known-vs-unknown chat replies qualitatively different;
contested concept disclosed in conversation; read-only invariant asserted.

**Status:** ✅ — 19 tests in `test_self_model.py`; full suite 1050 passing.

---

### M28: Deliberative Integration — Auditable Decisions ✅

**The gap:** decisions are per-subsystem (CuriosityEngine picks topics,
ResourceManager sets throttle, BeliefRevision resolves contradictions). Nothing
integrates them. There is no record of "what Genesis decided this cycle and why."
This is the architectural gap between "locally adaptive" and "deciding."

**What was built:** `src/cognition/decision_log.py` — `DecisionLog`.

A persistent, append-only SQLite table (`decision_log`) that lives in the main
memory DB alongside memories, relations, and hypotheses.  Each record carries:
subsystem, decision (plain-language summary), rationale (the signals that drove
it), cycle_count, and timestamp.

Decision recording is wired at four points:
- `fetch_knowledge()` — one record per succeeded topic ("learn about wolves")
  plus an aggregate yield record; rationale includes hunger/wanting/directive count
- `reflect()` consolidation — records salient concepts identified
- `reflect()` hypothesis generation — records how many hypotheses formed/resolved
- `reflect()` inference program mining — records new rules authored and derivations run

`brain.recent_decisions(n=5)` is the public interface, returning
`list[DecisionRecord]`.  Voice layer: "what have you been deciding?" / "recent
decisions?" / "what choices have you made?" all route to `_say_decisions()`, which
groups records by subsystem and narrates what Genesis has been spending attention on.

**Cross-layer interaction review:**
- Writes only to its own `decision_log` table; no coupling to memory or relations
- Uses the existing shared `_conn` — no extra DB file, same ACID guarantees
- DecisionLog.record() never raises — errors silently dropped, callers unaffected
- Voice pattern added before the broad "what causes X" handler to avoid shadowing

**Integration tests:** 12 tests in `tests/test_decision_log.py` — all three
roadmap requirements met plus unit, persistence, and voice-layer tests.
Full suite: 1197 passed, 24 skipped.

---

### M29: Persistent Goal Formation ✅

**The gap:** curiosity directives exist but they are reactive (formed when
prediction error is high, resolved when edges are added). Genesis had no goals it
forms *proactively* — no "I want to understand X" that persists beyond the mechanism
that triggered it.

**What was built:** `src/cognition/goals.py` — `GoalEngine`.

A `goals` table in the main memory DB holds intentions: topic, first-person
statement, origin (`conversation` | `self`), status (`active` | `satisfied`).
Satisfied goals are kept forever — an intention fulfilled is part of Genesis's
history, never deleted.

- **Formation** — `brain.form_goal(topic)` dedupes per topic and caps active
  goals at 12 (an intention list needs focus).  Conversation: "remember to
  learn about X" / "keep studying X" / "I want you to understand X" form a
  goal — recognised *before* the M32 LLM delegation because formation is an
  action, not phrasing.  Self-formation: each reflection, one pattern-transfer
  analog gap may be promoted to a goal ("understand X — it mirrors a
  structural pattern I already know").
- **Pursuit** — every reflection re-arms the curiosity frontier with active
  goal topics at weight 0.9 (above analog hunches).  This is what "worked on
  without being re-stated" means: the goal re-injects its own directive each
  session until satisfied.
- **Satisfaction** — measured, not counted: a goal is satisfied when the M27
  self-model verdict for its topic reaches **solid** (Stage-3-answer
  territory), never by a fixed edge count.
- **Audit** — formation and satisfaction are recorded in the M28 DecisionLog,
  so "what have you been deciding?" covers intentions too.
- **Voice** — "what are your goals?" / "what are you trying to learn?" →
  `_say_goals()`: active topics, oldest intention's age, which goals are
  self-formed, recent satisfactions.  The M32 LLM grounding context includes
  the active goal set.

**Cross-layer interaction review:**
- Goals write only to their own table on the shared conn; all failures route
  to `survival.resilience.error_log` (no `except: pass`)
- Satisfaction check runs per-reflection (not per-cycle) and only over ≤12
  active goals — bounded self-model queries
- The goal-query intent is deliberately narrow: "what are you working on?"
  still belongs to the plans handler (caught by an existing regression test)

**Integration tests (all green, `tests/test_goals.py`):** the three roadmap
requirements verified — cross-session persistence with resumed pursuit,
self-formed goal without conversation trigger, chat reflecting the goal set —
plus dedupe/cap, solid-verdict satisfaction, DecisionLog records, and honest
no-goals answers.  Full suite: 1234 passed.

---

### M30: Hypothesis Engine — Generative Cognition ✅

**The gap (this was the first open architectural question, now answered):** until
M30 every relation in the graph traced back to a sentence Genesis processed. The
system absorbed structure at high bandwidth but produced none of its own. There was
no path from the existing graph to a *new* claim — no conjecture, no original thought,
only consumption.

**What was built:** `src/cognition/hypothesis.py` — `HypothesisEngine`. Genesis now
authors falsifiable predictions by reasoning over its own graph, stores them as its
own conjectures (kept out of the relation graph so they cannot pollute fingerprinting
or contradiction scans), and *tests* them against evidence acquired later. Conjecture,
then seek the evidence that decides.

Three generators, each grounded in a cited mechanism:
- **Structural analogy** (Gentner 1983): if wolves PREVENTS overgrazing and lions is a
  structural analog of wolves (M22 fingerprint match) but has no PREVENTS edge,
  hypothesize lions PREVENTS something too — transferring relational structure across
  a surface-dissimilar pair.
- **Contradiction moderation:** a held X CAUSES Y / X PREVENTS Y tension implies a
  hidden moderating variable; Genesis conjectures the relationship is conditional.
- **Chain extension:** A CAUSES B and B CAUSES C held, A→C not — hypothesize A CAUSES C.
  Unlike the InferenceEngine (which asserts transitive closure as derived fact), this
  stays a *prediction* until independent evidence confirms it.

**The falsifiability loop:** `verify()` runs each reflection pass. An open hypothesis
whose predicted edge now appears in the graph is marked `confirmed` (and object-specified
confirmations are promoted into the graph as a modest observed edge — Genesis's
prediction became knowledge); one contradicted by an opposing observed edge is marked
`refuted`. Nothing is deleted — a wrong guess is kept, because being wrong is part of
Genesis's history. `stats()` reports a `hit_rate`: Genesis's own calibration as a
hypothesizer.

**Wiring:**
- `reflect()` verifies-then-generates each pass; open-hypothesis subjects are pushed
  into the curiosity frontier so Genesis goes reading for the deciding evidence
- `GenesisVoice._compose_hypothesis()` lets Genesis speak its conjectures and own its
  hits and misses ("I had guessed X… and what I've read since bears it out" /
  "…but the evidence points the other way. I was wrong about that.")

**Status:** ✅ — 13 tests in `test_hypothesis.py`; full suite 992 passing.

### M30.2: Research Proposal — Authoring a Direction ✅

**The gap:** M30 produces single conjectures. A mind that *wonders in an organized way*
does more — it can state where its understanding should go and why. Genesis had no way
to assemble its scattered signals (gaps, analogs, contradictions, hypotheses) into one
coherent statement of intent.

**What was built:** `src/cognition/research_proposal.py` — `ResearchProposal`. Genesis
composes a first-person research-direction document from its current cognitive state,
in five sections that degrade gracefully (absent material is omitted, never faked):
1. *What I understand* — anchored on a salient, well-connected concept it can speak to
2. *What I don't yet grasp* — a pure knowledge gap and/or a held contradiction
3. *A parallel I've noticed* — a structural analog across domains (M22)
4. *What I predict* — an open hypothesis with its rationale (M30) — the generative core
5. *What I'll read to find out* — concrete curiosity targets

The artifact is the point: a document Genesis produced that existed in no source,
recording an intention to find something out. It is stored and persists across
sessions; two instances with different histories write different proposals, and the
same instance writes a different one later because its state has moved. No LLM —
deterministic phrasing assembled from graph state.

**Wiring:** `brain.propose_research()` drafts on demand; `reflect()` drafts every 5th
pass (spaced so a direction is a considered statement, not churn); `voice._say_plans()`
points to the drafted direction when asked about plans.

**Status:** ✅ — 14 tests in `test_research_proposal.py`; full suite 1006 passing.

### M31: Inference Programs — Declarative Rule Authoring ✅

**The gap:** M30 produces single hypotheses — one conjecture at a time, about a
specific subject.  Genesis had no mechanism to *generalize* a pattern into a reusable
rule.  M10's InferenceEngine runs rules the *engineer* wrote; nothing let Genesis
discover and author rules from its own accumulated data.  Two instances that processed
different texts would produce different knowledge graphs, but the same inference rules —
the accumulated individuality didn't reach the reasoning layer.

**What was built:** `src/cognition/inference_programs.py` — `InferenceProgramEngine`.

Three phases, each adding a distinct capability:

**1. Discovery** — Genesis scans its relation graph for recurrent two-hop chain
patterns: cases where A --rel_a--> B --rel_b--> C co-occurs with a direct A --result_rel--> C
shortcut.  A SQL three-way JOIN counts these; when ≥ 2 independent instances of the
same (rel_a, rel_b, result_rel) triple appear, Genesis has empirical grounds for a rule.
IS_A is excluded (M10 handles inheritance).

**2. Authoring** — Each promoted pattern is stored as a named rule in the
`inference_programs` table:  `rel_a + rel_b → result_rel`, evidence count, confidence
(starts at 0.45 + 0.05 × extra evidence, capped at 0.75 — a new rule is a conjecture).
The rule is a first-class artifact Genesis wrote.  It persists across sessions.

**3. Execution + Tracking** — `run_all()` applies every stored rule to the full
graph, deriving new edges stored in `program_derivations` (never in the `relations`
table — observed facts stay clean).  `verify_derivations()` checks open derivations
against later-observed edges; each confirmation increments the rule's `hit_count`.
`stats()` reports a `hit_rate` — Genesis's calibration as a rule-author.

**Why this produces accumulated individuality:**
Two Genesis instances that processed different texts will mine different rules because
their graphs have different chain patterns.  The programs Genesis authors are a record
of what *this* instance found in its specific data — not a table the engineer wrote.
An instance that read about ecology might author `CONTROLS + CAUSES → CAUSES`;
one that read about circuits might discover `ENABLES + REQUIRES → ENABLES`.  Same
mechanism, different programs.

**Wiring:**
- `reflect()` calls `mine()` then `run_all()` then `verify_derivations()` each pass,
  after hypothesis generation so both layers see the same enriched graph
- `GenesisVoice._compose_rule()` lets Genesis state a pattern it formalized:
  "I've noticed that when one thing controls another, and that second thing causes a
  third, the first tends to cause the third too — I found that pattern 3 times and made
  it a rule I run across what I know"
- `voice._say_rules()` handles direct queries ("what rules have you worked out?")
- No LLM, no hard-coded patterns — pure empirical discovery from Genesis's own graph

**Status:** ✅ — 20 tests in `test_inference_programs.py`; full suite 1031 passing.

### M35: Rich-Input Modality — Audio + Provenance Surfacing ✅

**The gap:** the seed claimed modularity over "audio, video, sound, or
otherwise" but only sensed text/numeric/pattern; and M18 tracked source trust
internally with no way for Genesis (or a user) to ask "where did you learn
that, and do you trust it?"

**What was built:**
- `src/processors/audio.py` — `AudioProcessor`: extracts structure from raw
  WAV/sample input with the stdlib only (no pretrained weights — the
  blank-start principle applies to hearing too): loudness envelope + trend,
  onset events, rhythm via envelope autocorrelation (tempo + regularity),
  timbre brightness via zero-crossing rate, silence ratio.  Non-audio input
  is quietly skipped (all processors see all input).  Registered in the
  orchestrator and in the survival capability map at NONE only — the most
  expensive sense degrades first; text still survives to EMERGENCY.
- **Modality-agnostic relation hook:** the orchestrator now accepts
  `extracted["relations"]` triples from ANY processor (was text-only), so
  sound structure lands in the same graph Genesis reasons over — and any
  future modality (video, imagery, "or otherwise") plugs in by implementing
  `BaseProcessor` and emitting triples.  That registry is the modularity.
- **Provenance surfacing:** `self_model(concept)` now returns `sources` —
  per-source relation counts with M18 trust scores.  Voice intent "where did
  you learn about X?" answers from that ledger, including how trust is
  re-weighed when a source proves wrong.

**Tests:** 8 in `tests/test_audio_modality.py` — synthesized WAV with known
rhythm recovered (onsets, regularity, silence), relations stored through the
real pipeline, corrupt audio processed as data not crash, throttle
degradation order, source reporting with trust, honest no-source answers.
Full suite: 1242 passed.

### M36: Self-Determined Interests and Values ✅

**The gap (named by Jacob):** Genesis chose topics, but never chose *how it
chooses* — the interest-scoring functions were engineered, static, identical
in every instance.  And M12's ethics lens could notice consequence patterns
but nothing promoted them into held values, and no value ever changed a
decision.  It could notice what looks moral; it could not care.

**What was built:** `src/cognition/values.py` — `ValueSystem`, mirroring how
humans acquire values without dictation:
- **Tastes** — every cycle, the M34 liking signal is credited (slow EMA) to
  that cycle's active concepts.  What rewarded THIS instance becomes what it
  prefers; the `tastes` table persists across sessions.
- **Values** — each reflection, recurring EthicsLens consequence patterns are
  promoted into first-person value statements ("I avoid overgrazing — in
  what I've processed it leads to collapse, which I've disliked in my own
  experience").  **Valence comes from Genesis's own taste for the outcome —
  there is no engineer-supplied good/bad ontology, and a value cannot form
  before Genesis has lived any feeling about the outcome.**  Conflicting
  patterns lower confidence and annotate the statement (tension, not
  erasure); nothing is deleted.
- **Governance** — `curiosity_adjustment()` feeds taste (±0.3) and stance
  (favor +0.25 / avoid −0.4) into curiosity ranking.  When preference
  materially changes the top-n reading choice, the shift is recorded in the
  M28 DecisionLog ("preference shaped my reading: chose X over Y").
- **Testimony, not directive** — user statements already enter as evidence
  from a trust-scored source (M18); nothing in M36 gives the user's words
  rule status.  Parent, not programmer.
- **Voice** — "what do you value / what are your morals?" → `_say_values()`:
  authored statements with evidence counts, strongest tastes, and an honest
  "I haven't lived enough to hold values yet" before history accumulates.
  LLM grounding context includes held values and tastes.

**Tests:** 11 in `tests/test_values.py` — taste accumulation/flip/persistence,
no-value-without-lived-valence, avoid-value formation from disliked outcomes,
conflict-as-tension, ranking governance, DecisionLog audit of a
preference-shaped choice, honest voice.  Full suite: 1253 passed.

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
