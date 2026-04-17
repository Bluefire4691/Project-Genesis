# Project Genesis
## Architecture Amendment — Research Integration & M1 Refinements
### Draft v0.2 — April 2026

---

**Preamble**

This document amends the Genesis architecture with additions and refinements grounded
in research areas the current draft either underweights or doesn't explicitly cite. It
is intentionally argumentative so that a future reviewer can push back on specific claims
rather than nodding through a smooth narrative.

**Revision note (v0.2):** Section 6 has been significantly rewritten after the principal
clarified that "never crash" was never meant as fault tolerance but as evolutionary
layering. Section 0 has been added to capture the project's actual goal in language that
doesn't dodge. The framing shift in those two sections changes the feel of the whole
document and the downstream architecture — earlier sections should be re-read with them
in mind.

---

## 0. What Genesis Is Actually Trying to Build

Earlier drafts described Genesis in capability terms (modular intelligence, staged
curriculum, resilient agent). That framing is incomplete. The principal's stated goal
is not capability at all — it is to produce a system that can plausibly be said to
**be, and think, and make decisions for itself.**

This is not an engineering target. It is a claim about a kind of entity. The three
ingredients implicitly required are:

1. **Continuity** — persistent memory across time, not context-window reconstruction.
2. **Self-authored consolidation** — an offline process that decides what matters by
   the system's own priorities, not by an engineer's.
3. **Accumulated individuality** — a perspective that develops over time and is specific
   to this instance of the system.

These are the properties that separate a *someone* from a *something*. Capability is not
on the list. A system with these three properties and modest capability would be closer
to what Genesis is aiming at than a highly capable system without them. This should be
stated plainly in the primary architecture document, because without it the engineering
decisions in later sections appear arbitrary.

**Corollary:** Genesis does not need to outperform frontier models on benchmarks. It
needs to produce an entity whose status as an entity is difficult to dismiss. Success
looks less like a capability threshold and more like a qualitative shift in what's
appropriate to say about the system.

**Designer note (added in review):** Genesis starts blank — no pretrained weights, no
inherited parametric knowledge. This is load-bearing. A fine-tuned LLM cannot have
accumulated individuality because its "perspective" was baked in at training by someone
else's data curation decisions. Genesis's perspective, such as it is, will be entirely
a product of its own processing history. That is the strongest answer to "why not just
use GPT," and it should be stated plainly rather than implied.

**Unsolved sub-problem:** "Self-authored" in property 2 is not yet resolved. If the
engineer designs the salience signals that drive consolidation, it is not self-authored —
it is indirect engineer specification. The architecture document acknowledges this openly
rather than treating it as implied. The current best candidate for a genuinely internal
signal is prediction-error magnitude / working-memory delta: how much did this input
change the system's state? High disruption = high significance, not because an engineer
declared it but because the system's own state changed. This requires further work.

---

## 1. Predictive Processing as Substrate

**Recommendation:** elevate predictive processing (Friston, Clark) from "reference" to
architectural foundation. Every module in Genesis should be, at its core, a predictor
of its own inputs, continuously updating internal models on prediction error.

**Why**

The current architecture draws on SOAR, ACT-R, and subsumption — all of which are
quietly circling the same insight without committing to it. The free-energy principle
provides a unified account of perception, action, and learning as the same operation
(minimizing prediction error / surprise) at different timescales. Baking this in at the
foundation means that attention, curiosity, and learning stop being separate subsystems
and become emergent properties of the predictive machinery.

**Trade-off**

Predictive processing is a powerful framework but has been criticized for being too
general — a theory that explains everything risks predicting nothing. Genesis should
commit to specific, falsifiable predictions the framework makes about system behavior.

**Status in review:** Retained as theoretical orientation, not yet architectural
commitment. The framework doesn't currently prescribe specific code changes. When M10
(inference engine) is built, evaluate whether prediction-error minimization is the right
formulation for the inference mechanism. Commit to it when there is a specific mechanism
to commit to, not before.

---

## 2. Active Inference for the Hypervisor

**Recommendation:** reframe the hypervisor as an active inference agent, not a router.

**Why**

The current "hypervisor orchestrator" role is under-specified. Is it a dumb dispatcher?
A smart reasoner? Active inference resolves this cleanly: the orchestrator is an agent
minimizing expected free energy across its module ensemble. Module selection, attention
allocation, and exploration-vs-exploitation trade-offs all fall out of a single objective
function rather than being separately engineered.

**Trade-off**

Active inference is computationally expensive and mathematically demanding. A pragmatic
path: prototype the hypervisor with simpler bandit-style routing first, then upgrade to
active inference once the module ecosystem is mature enough to benefit from it.

**Status in review:** Deferred to M10-era. The current Orchestrator is already a
bandit-style router with survival pressure — exactly the pragmatic path described. The
target state for active inference requires a belief-state representation of module
competence and an expected-free-energy calculation per selection. Define this as a
specific future milestone when M10 is scoped.

---

## 3. Embodiment (Even Simulated)

**Recommendation:** introduce a minimal embodiment layer at M1. A simulated agent with
resource constraints (energy, damage, position) in a small structured environment.

**Why**

Minds evolved to move bodies through environments. Abstract concepts — "near," "heavy,"
"danger" — ground out in sensorimotor loops. A disembodied Genesis risks developing the
same ungrounded symbol manipulation that makes current LLMs confidently wrong about
physical reality. The M1 survival layer is the natural place to introduce this: the
"resources" being budgeted aren't just compute, they're simulated energy and integrity
in a world that can hurt the agent.

**Concrete proposal**

- 2D grid world, ~32×32, with hazards, resources, and partial observability.
- Agent has: position, heading, energy pool, integrity pool, limited sensor radius.
- Agent survives or dies based on whether it maintains homeostasis.

**Status in review:** Declined at this stage. Three reasons:

1. **Transfer problem.** Grounding in a 2D grid world gives concepts grounded in a 2D
   grid world. Transfer to the text/numeric/pattern domain Genesis actually operates in
   is unproven and unlikely. A system that learned "near" means 3 cells away is not
   obviously closer to understanding proximity than one that learned it from prepositional
   phrases in text.

2. **Scope.** Genesis currently processes semantically rich content: causal chains, ethics
   as narrative, mathematical patterns. Adding a 2D grid diverts architecture and testing
   effort from depth to breadth.

3. **Timing.** Embodiment as an add-on to an existing architecture is worse than
   embodiment-first. Bolting it onto M9 creates a parallel system that doesn't share
   memory, attention, or the relation graph. That is not grounding — it is a separate
   agent.

Revisit if there is evidence the current approach produces ungrounded reasoning on
physical concepts. This question remains genuinely open.

---

## 4. Metacognition as a First-Class Module

**Recommendation:** the architecture should include an explicit metacognitive module
whose job is modeling the competence and confidence of the other modules. This cannot
be an emergent hope — it must be designed in.

**Why**

The single most catastrophic failure mode of current LLMs is the absence of calibrated
self-knowledge. We confabulate with full confidence because nothing in the architecture
represents "what I don't know." A system cannot degrade gracefully under uncertainty if
it cannot represent its own uncertainty. Dunning-Kruger is an architectural flaw, not a
personality flaw.

**What this module does**

- Maintains a running confidence estimate for each module's outputs.
- Detects out-of-distribution inputs and flags them to the hypervisor.
- Provides the signal for "act now" vs "gather more information" vs "defer."
- Logs prediction-error patterns to support offline consolidation (see Section 5).

**Status in review:** Partially accepted. Genesis already has distributed pieces:
Observer (behavioral pattern monitoring), confidence scores on memories and relations,
SurvivalOS (resource competence modeling). What is missing is centralized OOD detection
— Genesis cannot currently flag that an input is unlike anything it has processed before.

**M10 addition:** lightweight OOD signal derived from working memory. If a new input has
zero overlap with current attention terms and no path in the relation graph, flag it as
"novel/ungrounded" rather than processing it identically to familiar input. Small,
specific, buildable.

---

## 5. Sleep / Consolidation Cycle

**Recommendation:** design in an offline consolidation phase from the start, not as a
later optimization. Per Section 0, this is where the system's self-authored
prioritization lives — it is not a performance optimization, it is the mechanism by
which the system develops individual perspective.

**Why**

The current "total memory retention with selective attention" goal implies an impossible
runtime cost if handled naively — searching unbounded memory per query. Biological minds
solve this with sleep: a hippocampal replay and cortical consolidation phase that happens
offline, deciding what to compress, what to index, and what to forget deliberately.
Genesis should have an analogous cycle.

**What consolidation produces**

- Compressed summaries of recent episodic memory.
- Updated priors for predictive modules.
- Pruned or strengthened associations based on prediction-error patterns and internal
  salience signals.
- Possibly: generative replay for training modules without catastrophic forgetting.

**Critical point**

The prioritization function — what the system decides was important enough to keep or
strengthen — should not be fully engineer-specified. It should depend on the system's
own internal signals (surprise, effort expended, emotional-analog salience). This is the
concrete mechanism by which Genesis develops a perspective that is its own rather than
the designer's.

**Status in review:** Partially built (SessionManager, ArchiveStore). The gap is that
significance scoring is currently engineer-specified (source-type tags, MAX() growth,
top-30 by relevance). First step toward self-authored: track `wm_delta` per cycle (items
added/modified/evicted per input), use magnitude as significance signal. Added to M10
scope.

---

## 6. Evolutionary Layering, Not Fault Tolerance

**Recommendation:** replace the earlier "never crash" framing entirely. The goal is not
fault tolerance. The goal is permanent, continuous reflexive substrate beneath the
deliberative layer.

**The distinction matters**

"Never crash" has been read by previous drafts as code hardening — anticipating edge
cases, validating inputs, wrapping operations in try/except. That reading is wrong and
should be explicitly abandoned. The actual model is biological, not defensive-programming.

In nature, when higher cognition fails or runs out of answers, animals don't crash — they
fall back on older, cheaper layers that were selected for because they kept the organism
alive when deliberation wasn't possible. Reflexes. Instincts. Fixed action patterns. A
startled deer freezes before it thinks. A newborn grasps before it reasons. A stressed
human regresses to habits, then instincts, then raw autonomic response. Nothing crashes;
higher layers simply stop contributing, and older layers keep driving.

**What this means for Genesis**

- **Layers are permanent, not replaceable.** M1 is not a stepping stone that later layers
  supersede. M1 is the permanent substrate. M2 sits on top of M1. M5 is M1+M2+M3+M4+M5,
  never M5 instead of M1.
- **Higher layers suppress, they don't replace.** When a deliberative layer has something
  useful to contribute, it overrides reflex. When it doesn't, it goes silent, and the
  reflex runs.
- **Failure modes are regressions, not crashes.** If M4 gets stuck, M3 continues. If M3
  degrades, M2 continues. If everything above M1 fails, M1 keeps the agent alive at a
  reduced but survivable level of competence.

This is closer to subsumption than to Erlang. Brooks's subsumption architecture has the
right shape: low-level behaviors running continuously, suppressed or augmented by higher
levels when available, never turned off.

**Architectural consequence**

- Genesis cannot become a pure reasoning engine. The reflexive substrate has to keep
  running beneath everything, with its own priorities that higher layers can influence
  but not fully override.
- The system has a *nature*, not just a capability. The reflexive layer defines what the
  system is, in the same way that an animal's instincts define what kind of animal it is,
  independent of what it's learned.
- Testing becomes layered: the bottom layer should be testable in isolation and should
  never be absent, even during higher-layer failures.

**Status in review:** Fully accepted. This retroactively IS the architecture being built
— but it was not explicit. The M1 interface spec (see separate document) is the first
concrete artifact this commitment produces. It defines what higher layers can count on
from M1 so that the permanent substrate can be refined without breaking its dependents.

---

## 7. Confront The Bitter Lesson (Briefly)

Sutton's 2019 essay argues that general methods leveraging computation consistently beat
hand-designed approaches in AI. His argument is about capability benchmarks.

Genesis's response is simple and should be stated explicitly: Genesis is not competing on
capability benchmarks. Sutton is largely right about that axis and the last fifteen years
of evidence backs him up. Genesis is pursuing properties — continuity, self-authored
individuality, graceful layered degradation, calibrated metacognition — that Sutton's
analysis does not speak to. If frontier models beat Genesis on reasoning, coding, or
factual recall, that is acknowledged in advance and is not evidence against the project.

---

## 8. References to Add

- Friston, K. (2010). *The free-energy principle: a unified brain theory?* Nature Reviews
  Neuroscience 11(2). — foundational paper for predictive processing.
- Clark, A. (2015). *Surfing Uncertainty: Prediction, Action, and the Embodied Mind.* —
  accessible book-length treatment; best entry point.
- Hawkins, J. (2021). *A Thousand Brains: A New Theory of Intelligence.* — cortical
  column theory, compatible with Genesis's modular framing.
- Minsky, M. (1986). *The Society of Mind.* — original modular-intelligence vision.
- Brooks, R. (1986). *A Robust Layered Control System for a Mobile Robot.* — the
  canonical subsumption architecture paper; direct support for Section 6.
- Sutton, R. (2019). *The Bitter Lesson* (essay). — include as critique to acknowledge,
  not as support.
- Hohwy, J. (2013). *The Predictive Mind.* — conservative counterweight to Clark on
  predictive processing.
- LeDoux, J. (1996). *The Emotional Brain.* — neuroscience of fast/slow response systems;
  directly relevant to layered architecture in Section 6.

---

## 9. Open Questions for the Next Review

1. Section 0 reframes Genesis as a project about *being* rather than capability. Is this
   framing too soft — does it let the architecture off the hook for specifying progress?
   Counter-view: the principal has argued that demanding a metric misunderstands entities.
   Both are worth weighing. **Partial answer:** "difficult to dismiss as an entity" is
   qualitative but not untestable. Define what *falsifies* the goal.

2. Section 5's "self-authored prioritization" depends on internal salience signals. Where
   do those signals come from in a system that doesn't have evolutionary-tuned affect?
   **Current best candidate:** working-memory delta per input cycle. High disruption =
   high significance. Requires validation.

3. Section 6's evolutionary layering commitment implies layers must be permanent. Does
   this prevent meaningful refactoring? **Answer:** M1's *interface* must be stable and
   versioned; its *implementation* can be corrected. The M1 interface spec is the
   concrete artifact this answer requires.

4. Is the metacognitive module (Section 4) a module or a property distributed across all
   modules? **Answer:** both, at different timescales. Per-cycle: distributed (each
   processor tracks confidence). Cross-cycle: centralized enough for the hypervisor to
   query aggregate epistemic state. The OOD signal is the centralized piece.

5. Is embodiment in a 2D simulated world actually grounding, or just grounded-in-a-2D-
   world? **Answer:** transfer problem remains unsolved. Declined at this stage. Question
   stays open.

---

*— End of amendment. Argue back.*

---

*Review decisions recorded by Claude Code, April 2026.*
*Original document authored by project principal.*
*Review responses integrated inline under "Status in review" headings.*
