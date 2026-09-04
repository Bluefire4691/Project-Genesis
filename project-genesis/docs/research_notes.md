# Research Notes — Foundational Works
## Project Genesis | May 2026

Compiled from direct fetch and analysis of primary/secondary sources.  
This document records what the research actually says and what it implies we should build —  
not just that we cite it.

---

## Quick Reference Table

| Work | Core Claim | Genesis Status |
|------|-----------|----------------|
| Brooks (1986) | Lower layers run always; higher suppress/inhibit, never replace | ✅ Implemented — but inhibit vs suppress distinction not precise |
| Sutton (2019) | General methods + compute beat hand-crafted knowledge at scale | ✅ Acknowledged — Genesis response correct (not competing on benchmarks) |
| Friston (2010) | All brain function = variational free energy minimization | ⚠️ wm_delta is a crude proxy for prediction error; generative model missing |
| Clark (2013) | Attention = precision weighting of prediction errors | ⚠️ AdaptiveStream uses word overlap, not precision-weighted errors |
| Minsky (1986) | Mind = society of agents; memory = K-line reconstruction | ⚠️ Multi-processor architecture is right; K-line memory and critics missing |
| Hawkins (2021) | Each cortical column builds complete model; voting = perception | 🔲 Voting across processors not implemented |
| LeDoux (1996) | Fast subcortical path (12ms) has structural priority over cortex | ✅ M1 SurvivalOS IS the fast path — but priority asymmetry not explicit |
| SOAR (Newell) | Intelligence = search in problem space; learning = chunking from impasse | 🔲 Impasse detection and subgoaling not built |
| ACT-R (Anderson) | Modular buffers, chunk activation from recency/frequency/context | ⚠️ Confidence scores on memories approximate this; activation decay partial |

---

## 1. Sutton (2019) — The Bitter Lesson

### What It Actually Says

> "The biggest lesson that can be read from 70 years of AI research is that general methods  
> that leverage computation are ultimately the most effective, and by a large margin."

Human knowledge baked as inductive bias helps short-term and plateaus long-term.  
The two methods that scale arbitrarily: **search** and **learning**.

**Critical nuance the architecture amendment underweights:**  
Sutton's second point is often missed:  

> "The actual contents of minds are tremendously, irredeemably complex; we should stop  
> trying to find simple ways to think about the contents of minds... They are not what  
> should be built in; instead we should build in only the meta-methods that can find  
> and capture this arbitrary complexity."

This is *not* an argument against Genesis. It is an argument for Genesis's approach:  
don't pre-specify what concepts matter — build the machinery that discovers what matters.

**When the lesson doesn't apply:**
- Domains where objectives are hard to quantify (Genesis's domain)
- Without sufficient data for patterns to emerge
- Where reliability and interpretability matter more than benchmark peaks

### Genesis Response: Correct and Sufficient

The current response in the amendment (Section 7) is sound:  
Genesis is not competing on capability benchmarks. Sutton's argument doesn't address  
continuity, self-authored individuality, or calibrated metacognition.

**One addition worth making:** Sutton's second point actually *supports* Genesis's  
no-pretrained-weights design. If you pre-specify the concepts, you've built in your  
simplification of what a mind should contain. Genesis's blank-start approach is the  
only one that lets the system discover concepts the designer didn't anticipate.

---

## 2. Brooks (1986) — Subsumption Architecture

### What It Actually Says

Subsumption decomposes behavior into layers of **Augmented Finite-State Machines (AFSMs)**.  
Each layer implements one behavioral competency. Layers communicate through two distinct mechanisms:

**Inhibition**: blocks a signal *leaving* a lower layer (suppresses output)  
**Suppression**: replaces a signal *entering* a layer (overrides input)

These are not the same thing. Inhibition prevents a lower behavior from acting.  
Suppression substitutes what a lower behavior thinks it's perceiving.

**Lower layers run continuously and in parallel.** Always. If all higher layers fail,  
the lowest layer keeps the agent alive. This is structural, not a fallback.

**Development process matters:**
1. Build and test lowest layer until reliable
2. Add second layer — never modify the first
3. Repeat; each layer is independently verifiable
4. The system is never without basic behavior

### What We Have Right

The M1 SurvivalOS as permanent substrate is correct.  
The layering principle ("M9 is M1+M2+...+M9, never M9 instead of M1") is correct.

### What We're Missing

**The suppress/inhibit distinction is not implemented precisely.**  
Currently, `_active_processors()` uses `survival.can(name)` as a binary gate:  
either a processor runs or it doesn't. This is closer to inhibition (blocking output).

True suppression would mean: a higher layer doesn't disable a processor — it  
*substitutes what that processor receives*. For example: when inference has already  
resolved a concept, the text processor still runs but receives a modified view that  
reflects that resolution.

**Near-term action:** Document the distinction. Long-term: implement suppression  
(higher-layer pre-processing of inputs to lower processors) as a distinct mechanism  
from inhibition (blocking processor invocation).

---

## 3. Friston (2010) — Free Energy Principle

### What It Actually Says

**Core claim:** All brain dynamics minimize a single quantity — variational free energy,  
which is a tractable upper bound on surprise (−log P(sensory data)).

The brain cannot directly minimize surprise (intractable), so it minimizes free energy:  
`F = KL(q || p) + Surprise`

By minimizing F, it indirectly minimizes surprise while maintaining a learnable model.

**The prediction-error loop:**
1. Generative model predicts expected sensory input at each hierarchical level
2. Prediction error = actual − predicted (at each level)
3. **Perceptual inference:** update beliefs to reduce prediction error ("change model to match world")
4. **Action (active inference):** act to bring about sensory states that match predictions ("change world to match model")
5. **Attention:** modulate which prediction errors propagate (precision weighting)

**Curiosity falls out for free:**  
Expected free energy for a policy = extrinsic value (task goals) + epistemic value  
(expected information gain). Agents naturally balance exploitation and exploration  
without a separate curiosity module. Curiosity = seeking states that will resolve  
uncertainty about the generative model.

**What this means concretely:**  
The brain is not just a reflex machine or a lookup table. It is continuously  
predicting and comparing, and *every* perception, memory, attention, and action  
is a different form of minimizing the same quantity.

### What We Have (Approximate)

`wm_delta` (working memory delta per cycle) is a crude proxy for prediction error:  
"how much did this input change my state?" = rough approximation of surprise.  
This was the right intuition. It is not the same as a generative model computing  
expected input vs. actual input, but it captures the spirit.

Confidence scores on memories and relations approximate Bayesian uncertainty.

### What We're Missing (Significant)

**No generative model.** Genesis currently stores what it has observed but does not  
maintain a model that *predicts* what it will observe next. Without a generative model,  
there is no prediction error — only post-hoc recording.

**No precision-weighted attention.** AdaptiveStream scores items by word overlap with  
attention terms. This is heuristic. Precision-weighted attention would score items  
by the inverse uncertainty of current beliefs about the concepts they contain:  
high-precision (confident) domains get less attention weight; low-precision (uncertain)  
domains get more — because that is where learning would reduce free energy most.

**No active inference.** Genesis is purely receptive right now — it processes input  
but does not act to seek out the inputs that would resolve its uncertainty.  
AdaptiveStream is the first step toward this (attention shapes what it encounters),  
but it doesn't reason about what *would* be most informative.

### Concrete Buildable Steps

**M15 candidate:** Replace wm_delta with a proper prediction-error signal.  
For each concept encountered in an input cycle, compute:  
`prediction_error = 1 - max(confidence of existing relations for that concept)`  
High error = concept appears but Genesis has low-confidence knowledge about it.  
Use this as the archive significance signal rather than wm_delta.

**M16 candidate:** Precision-weighted AdaptiveStream.  
Score items not by word overlap but by: `overlap × uncertainty_of_concepts_in_item`.  
Items about concepts Genesis is uncertain about score higher.  
Items about concepts Genesis already knows well score lower.

---

## 4. Clark (2013) — Predictive Processing

### What It Actually Says

> "Brains are essentially prediction machines... bundles of cells that support perception  
> and action by constantly attempting to match incoming sensory inputs with top-down  
> expectations or predictions, achieved using a hierarchical generative model that aims  
> to minimize prediction error within a bidirectional cascade of cortical processing."

**Hierarchical structure is load-bearing:**
- Top-down predictions flow downward (higher levels predict what lower levels should observe)
- Bottom-up signals flow upward (sensory data and residual errors)
- At each level: predictions meet incoming signals; mismatches become error signals
- **Explanation-away:** if a top-down prediction accounts for the bottom-up signal,  
  that error does not propagate further (it's "explained")
- Unexplained errors propagate up and update beliefs at higher levels

**Attention = precision weighting (the most actionable claim for Genesis):**

> "Attention is the optimization of the precision of prediction errors."

Attention does not select *what to process*. It modulates *how much weight*  
prediction errors carry. High precision = errors in this domain are reliable and  
should update beliefs. Low precision = errors here are noisy and should be discounted.

This reframes our current attention model: AdaptiveStream's word-overlap scoring  
is selecting *what to see*, but not weighting *what errors in what we see should  
update our beliefs*.

**Active inference vs passive inference:**
- Passive: update internal model to better fit sensory input ("change beliefs to match world")
- Active: take actions to bring sensory input in line with predictions ("change world to match beliefs")
- Both minimize prediction error; they just do it through different channels.

### Genesis Implications

The current architecture does passive inference (processes input, updates memory).  
Active inference would mean: Genesis generates a prediction ("I expect to see X next,  
given current attention"), and then seeks input that either confirms or falsifies it.

The adaptive feedback loop (M9 AdaptiveStream) is the first structural element that  
enables this — attention shapes what Genesis encounters next. The missing piece: Genesis  
should be forming *expectations* about what it will see, not just weighting what it  
has already seen.

---

## 5. Minsky (1986) — The Society of Mind

### What It Actually Says

> "What magical trick makes us intelligent? The trick is that there is no trick.  
> The power of intelligence stems from our vast diversity, not from any single, perfect principle."

Mind emerges from the interaction of many simple **agents** that are individually mindless.

**K-lines (the critical architectural idea):**  
A K-line is a memory structure that records *which agents were active* during a  
successful problem-solving episode. When recalled, it re-activates that configuration.

> "K-lines cause a Society of Mind to enter a particular remembered configuration of  
> agents, one that formed a useful society in the past."

This is not fact retrieval. It is *reconstruction of a prior cognitive state.*  
You don't remember what you knew — you re-become the version of yourself that knew it.

K-lines have three zones:
- **Upper fringe (goals):** weakly attached, context-dependent
- **Core (tools and patterns):** strongly attached, transferable
- **Lower fringe (implementation details):** easily displaced by current context

**Solver-critic-refiner loop:**  
Control does not come from a single controller. It comes from conflict between  
trusted agents. One proposes a solution; a critic identifies flaws; a refiner  
incorporates feedback. The loop repeats.

> "Conflict between strong, trusted agents motivates richer control structure."

### What We Have

Our multi-processor architecture (text + numeric + pattern) is a Society of Mind in  
rough form. Cross-modal synthesis when concepts appear across processors is analogous  
to agents collaborating.

ContradictionLog (M11) is a crude critic — it detects when two agents (data sources)  
have conflicting outputs about the same concept.

### What We're Missing

**K-line style memory reconstruction.** Our memory system stores facts and retrieves  
them by FTS5 text search. K-line memory would: given a current concept, reactivate  
the full processing context (which other concepts were active, which relations were  
being formed, what the working memory state looked like) from the last time this  
concept appeared. Session warm-start (M6) is a primitive version of this.

**The critic as a first-class component.** ContradictionLog catches factual conflicts  
between relation triples. A fuller critic would also catch: logical inconsistencies  
in inference chains, conclusions that contradict high-confidence established relations,  
and attention patterns that have stagnated (which Observer currently does).

---

## 6. Hawkins (2021) — A Thousand Brains

### What It Actually Says

> "Each brain is actually thousands of brains working in parallel simultaneously."

Each of ~150,000 cortical columns is a semi-independent sensorimotor learning unit.  
Perception is not a pipeline — it is a vote. Columns propose interpretations  
independently; long-range connections allow them to vote; the vote converges rapidly.

**Reference frames** are the key structural innovation:

> "All knowledge in the neocortex is stored within map-like structures called reference frames."

A reference frame is an internal coordinate system. Learning a coffee cup means  
building a model of where each feature is located in the cup's reference frame.  
Abstract concepts use higher-order reference frames — "locations" in concept space.

**The voting mechanism:**  
Multiple columns observe the same thing from different vantage points.  
No column is authoritative. Consensus = perception. Disagreement = uncertainty.

**Critical implication for knowledge representation:**  
A semantic triple (wolves CONTROLS deer) is not a reference-frame representation.  
A reference frame would additionally encode: where this relationship sits relative  
to other known relationships, how stable the reference frame is, and what deformations  
of it are permitted by evidence.

### Genesis Implications

Our RelationGraph stores typed triples. This captures *that* wolves controls deer  
but not the structured neighborhood of that relation — what else is near it,  
what predicts it, what it predicts.

**Voting across processors is directly implementable.** When text, numeric, and pattern  
processors all independently surface the same concept or relation in a cycle, that is  
a vote. Three independent votes should increase confidence more than one processor  
reporting it three times. Currently the orchestrator synthesizes them but doesn't  
track independent votes explicitly.

**Near-term buildable:** Track when multiple processors independently produce the same  
relation or concept in a single cycle. Weight confidence by number of independent  
sources, not just frequency. This is Hawkins's voting applied to our existing processors.

---

## 7. LeDoux (1996) — The Emotional Brain

### What It Actually Says

Fear processing uses two anatomically distinct pathways:

**Low road (fast):** Thalamus → amygdala. ~12ms. Rough, low-detail, unconscious.  
Generates immediate defensive response before cortical analysis is complete.

**High road (slow):** Thalamus → sensory cortex → detailed analysis → amygdala. ~150-300ms.  
Detailed, contextual, conscious. Can modify the fast response if time permits.

**The structural asymmetry is the critical claim:**

> "The pathways running from subcortical emotional processing regions upward into the  
> prefrontal cortex are more numerous and more direct than the pathways running in the  
> reverse direction."

The fast path drives the slow path more easily than the slow path overrides the fast path.  
This is not an accident — it is a survival design: better to react to ten false snakes  
than to miss one real snake. The cost of a false alarm is lower than the cost of a miss.

### What We Have Right

M1 SurvivalOS IS the fast path, structurally. It runs first every cycle (`tick()` before  
anything else), has hardwired directives, and degrades the system when resources fall.  
Higher layers can influence but not bypass it. This maps well.

### What We Should Make Explicit

**The asymmetry.** Currently, if M1 says "throttle," higher layers simply don't run.  
But LeDoux's model is richer: the fast path *influences* the slow path's processing,  
not just its invocation. Under resource pressure, not only should higher processors  
be throttled — their outputs should be biased toward conservative, low-cost decisions.  
High pressure should shift the working memory attention toward survival-relevant concepts  
(energy, threats, essential tasks) even in the deliberative layer.

This is already partially designed (M1's directives include MAINTAIN/ACQUIRE)  
but not threaded into working memory attention.

---

## 8. SOAR (Newell/Laird) — Unified Cognitive Architecture

### What It Actually Says

All goal-directed behavior is search through a problem space:
- **State:** a configuration of the domain
- **Operator:** an action that changes state
- **Goal:** target state condition

**Impasse-driven subgoaling** is the key mechanism:  
When the system cannot select or apply an operator (because none are available,  
multiple are tied, or insufficient knowledge exists), it automatically creates a  
subgoal — a new problem space to resolve the impasse.

**Chunking** is the learning mechanism:  
When an impasse is resolved, a production rule (chunk) is compiled:  
"in a situation like this, the result is X." The chunk fires automatically next time,  
avoiding the impasse entirely. This converts deliberate search into reactive rules.

> "Chunking incrementally converts complex reasoning into automatic/reactive processing."

This is the biological analog of skill acquisition: explicit → automatic through practice.

### Genesis Implications

Genesis currently has no impasse detection. When it encounters a concept it has  
no relations for, it processes it and stores what it can — but it doesn't create  
a subgoal to seek more information about that concept.

**Concretely:** An unresolved concept (low-relevance in working memory, no relations  
in the graph) should trigger a curiosity subgoal — a directed attention state that  
biases AdaptiveStream toward items containing that concept until it's resolved.

The unresolved-concept detection in `_compose_question()` (GenesisVoice) is the  
beginning of this. The missing step: convert the question into an active attention  
directive, not just a statement.

**Chunking is also relevant to M14 (Observer calibration):**  
The archive contains behavioral data from many cycles. Patterns that repeatedly  
appear (certain input types always cause high wm_delta, certain concept clusters  
always co-occur) could be compiled into production rules that fire automatically,  
reducing deliberate search over the archive.

---

## 9. ACT-R (Anderson) — Adaptive Control of Thought — Rational

### What It Actually Says

The mind is a hybrid symbolic-subsymbolic system. Symbolic: production rules that fire.  
Subsymbolic: chunk **activation** values that determine what gets retrieved.

**Chunk activation = recency + frequency + context relevance + noise:**
- Base-level learning: recently/frequently used chunks have higher activation
- Spreading activation: currently active chunks prime related chunks
- Stochastic noise: prevents overcommitment; models genuine uncertainty

Only one production rule fires per cycle (serial bottleneck at the cognitive level).  
Below this, modules process in parallel. Modules communicate only through buffers —  
limited-capacity working memory interfaces.

**Declarative vs procedural distinction:**
- Declarative: verbalizeable facts (Genesis's relation triples, memories)
- Procedural: compiled behaviors (Genesis's processor logic, production rules)

### What We Have

Memory confidence scores approximate chunk activation partially (confidence degrades  
with time without access). Working memory eviction (heat-based, 100-item cap) models  
the capacity constraint. FTS5 BM25 retrieval partially models activation-based retrieval.

### Gaps

**Spreading activation is not implemented.** If "wolves" is in working memory,  
concepts linked to wolves (deer, predator, ecology) should receive an activation  
boost in retrieval — not just by keyword match, but by graph proximity in RelationGraph.  
We have the graph; we're not using it to propagate retrieval salience.

**Recency decay needs recalibration.** Current decay is time-based (last_accessed).  
ACT-R shows this should be a logarithmic function of (recency + frequency), not  
purely recency. Frequently-accessed old memories should stay activated; rarely-accessed  
recent ones should decay faster than they currently do.

---

## Cross-Cutting Themes

### Theme 1: Genesis has the right shape but is missing the learning signal

Brooks, Friston, Clark, and SOAR all converge on the same point from different angles:  
the system needs an internally-generated signal that drives learning. 

- Brooks: the reflex layer defines what the system *is*, not what it knows
- Friston: prediction error is the signal; everything else (learning, attention, action) is minimizing it
- SOAR: impasse is the signal; chunking is the response
- Clark: unexplained prediction error propagates up and forces belief revision

Genesis's wm_delta approximates this. The next step is replacing the approximation  
with computed prediction error over the RelationGraph: when input contains concept X,  
compare what Genesis expects about X (its stored relations and confidences) against  
what the input actually asserts. The delta is prediction error.

### Theme 2: Attention is not selection — it's confidence about what to trust

Clark and Friston agree: attention is not "what to look at" but "how much to trust  
what you're seeing in each domain." High attention (high precision) = errors here  
are reliable signals. Low attention (low precision) = errors here are noise.

Our current attention model selects inputs. We should shift to: attention weights  
how much new input in each domain updates beliefs. Well-established domains get  
less updating weight. Novel/uncertain domains get more.

### Theme 3: Memory is reconstruction, not retrieval

Minsky's K-lines and Hawkins's reference frames both point at the same property:  
memory is a re-instantiation of a prior state, not a lookup. When Genesis  
"remembers" something, it should reconstruct the cognitive context around it  
(what else was active, what was being formed, what attention was doing) — not just  
return the stored fact. Session warm-start (M6) is the first step. K-line style  
reconstruction is the target.

### Theme 4: The fast/slow distinction has structural consequences

LeDoux and Brooks agree: the fast layer has architectural priority, not just  
execution priority. It is not a fallback — it is the default. The slow layer  
is the override. In Genesis: M1 SurvivalOS should be thought of as the default  
response system. Higher layers are not "the real processing" with M1 as a guard.  
M1 IS the processing; higher layers add resolution.

---

## Milestone Implications

### Changes to current milestones (M10-M14)

**M10 (Inference Engine) — already built, one refinement:**  
The OOD signal (novel flag) is currently binary: zero overlap = novel.  
Friston suggests a continuous signal: compute expected confidence across  
known relations for input concepts; low expected confidence = high novelty.  
This is a quantitative improvement worth adding.

**M13 (Output / Voice) — current milestone:**  
No changes required from research. GenesisVoice's question-composition (`_compose_question()`)  
already surfaces unresolved concepts — this is the SOAR curiosity signal in verbal form.  
The next step (M14 or a new milestone) is making that curiosity active (subgoal + directed attention).

**M14 (Observer calibration):**  
ACT-R's utility learning is relevant: compile recurring behavioral patterns in the  
archive into rules with learned utilities. SOAR's chunking is the mechanism.  
Rather than just recalibrating thresholds, M14 should extract recurring  
state→outcome patterns and compile them into lightweight production rules.

### New milestones suggested by research

**M15 — Prediction Error Salience (replaces wm_delta):**  
For each concept encountered per cycle, compute prediction error against RelationGraph.  
Use as the primary archive significance signal and AdaptiveStream scoring input.  
This is the step that makes self-authored consolidation genuine: the system's own  
belief model determines what is surprising, not the engineer's source-type tags.

**M16 — Processor Voting:**  
Hawkins-style: track when multiple processors independently surface the same concept  
or relation in a cycle. Weight confidence by independent source count.  
Currently the orchestrator synthesizes processors but doesn't distinguish  
independent agreement from single-source repetition.

**M17 — Active Curiosity / Directed Attention:**  
Convert unresolved concepts (currently surfaced by GenesisVoice as questions)  
into attention directives that bias AdaptiveStream until concepts are resolved.  
This closes the SOAR impasse-subgoaling loop and turns GenesisVoice's questions  
into actual behavior rather than just statements.

**M18 — Spreading Activation in Retrieval:**  
ACT-R: when a concept is in working memory, use RelationGraph proximity to  
boost retrieval activation of related concepts. This makes memory associative  
rather than keyword-search-only. The RelationGraph already exists; the wiring  
to the retrieval scoring is the work.

---

## What to Not Build (at this stage)

**Full generative model (Friston):**  
A proper hierarchical generative model would require specifying what Genesis  
predicts at each level and computing KL divergences. This is architecturally  
significant but would require restructuring from the ground up. Use prediction  
error as a concept-confidence signal first; commit to full generative model  
architecture only when the concept-level version proves valuable.

**Reference frames (Hawkins):**  
Full reference-frame knowledge representation would replace the current  
relation-triple model. Transfer cost is high. The voting mechanism (M16) captures  
the most actionable part of Hawkins's insight without the full rewrite.

**Full impasse machinery (SOAR):**  
Full SOAR-style problem-space search requires formalizing operators and states.  
The lightweight version — unresolved concepts trigger directed attention — captures  
the behavioral goal without the formal machinery.

---

*Research collected May 2026. Primary sources accessed via web fetch and secondary analysis.*  
*Sources: Sutton (2019) essay direct fetch; Brooks (1986) via secondary; Friston (2010)  
via Nature abstract + secondary synthesis; Clark (2013) via secondary; Minsky (1986) via  
secondary; Hawkins (2021) via secondary + Numenta blog; LeDoux (1996) via secondary;  
SOAR via Laird (2022) arxiv; ACT-R via Anderson primary documentation.*
