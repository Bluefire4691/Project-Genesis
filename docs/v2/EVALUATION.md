# Genesis v2 — Evaluation Contract

> **This document is built BEFORE the agent.** v1's success criterion was a
> feeling ("it seems like it decided"), which is unfalsifiable, which is why
> eight months produced no verdict. v2 does not get to claim anything it
> cannot measure.

Every criterion below names its **null model** — the boring system that would
also pass if we were fooling ourselves. Beating the null is the whole game.

---

## The null hypothesis we must defeat

> *"It's a RAG chatbot with a scheduler."*

A retrieval-augmented chatbot on a cron job would look superficially like
Genesis: it reads things, stores them, answers questions, and its answers
change as the index grows. If every metric we report is also achieved by that
system, we have built nothing new. Each criterion below is designed so the
null model fails it.

---

## C1 — Twin divergence that survives context removal

**Claim tested:** accumulated individuality.

**Setup.** Two instances, identical code and model weights, differing only in
the corpus they read (A vs B, disjoint domains) for 4 weeks of ingest.
**Control arm:** two instances on the *same* corpus with different RNG seeds.

**Measure.**
- Jensen–Shannon divergence between their next-topic-choice distributions.
- Accuracy on a shared 200-item probe covering both corpora.
- Jaccard overlap of visited topic clusters and of claim sets, over time.

**Success:** between-corpus divergence exceeds within-corpus (seed) divergence
by >3σ, **AND ≥50% of the accuracy gap survives when the retrieval index is
detached.**

That last clause is the one a RAG chatbot cannot pass. If all the individuality
evaporates when you unplug retrieval, the individuality was in the index, not
in the entity.

---

## C2 — Calibration by Brier score, earned over time

**Claim tested:** it knows what it knows.

**Setup.** Before answering each of 300 held-out questions, it emits
p(correct). Score with Brier + a reliability diagram.

**Three baselines to beat:**
1. Constant base rate.
2. The bare LLM's verbalized confidence.
3. The LLM with retrieval but no accumulated history.

**Success:** Brier beats all three, **AND** the gap between studied and
unstudied topics widens over time — calibration *earned from its own track
record*, not inherited from the base model.

> v1's "calibrated ignorance" was `error = 1.0` for unseen tokens. That is a
> `seen` flag, not calibration.

---

## C3 — Self-directed reading beats a scheduler *(the hardest, and the point)*

**Claim tested:** intrinsic motivation is real, not decorative.

**Setup.** Fixed budget of 200 documents drawn from a pool of 5,000.
- **Arm A:** the agent chooses what to read.
- **Arm B:** random selection.
- **Arm C:** round-robin over topic clusters.

All three then sit the **same held-out exam** covering the whole pool, written
before any arm runs.

**Success:** A > B and A > C by more than seed variance across 3 runs.

**Bonus diagnostic:** A should beat B by a *larger* margin on questions that
require connecting two separate documents — that's the signature of curiosity
that seeks structure rather than novelty.

If curiosity cannot beat a random scheduler on an exam it did not choose, it
is decoration. This criterion is the reason the project exists.

---

## C4 — Non-destructive accumulation

**Claim tested:** continuity; no catastrophic forgetting or model collapse.

**Setup.** A 100-item probe battery authored each month, replayed every month
thereafter. Plus a **frozen** 200-item general-capability benchmark.

**Success:** month-1 retention ≥90% at month 4, general benchmark within 2
points of baseline, while new material is still being acquired.

**Early-warning instrumentation** (weekly, cheap):
- Type-token ratio and distinct-n on a fixed prompt set → detects model collapse
  (output narrows before it degrades; the tails go first).
- Any dip in the frozen benchmark → forgetting or collapse, caught in a week
  rather than a quarter.

---

## C5 — Ablation: every component earns its place

**Claim tested:** we are not shipping decoration.

**Setup.** For each subsystem — reflection loop, drive signals, memory-write
policy, consolidation, learned ranker — re-run C1–C4 with it **disabled**.

**Success:** removing it degrades a *named metric* by more than noise.
**If not, delete the component.**

> v1 shipped 36 milestones. The database proves at least six subsystems never
> executed on real data. This rule alone would have caught that in week two.

---

## Gate

**C3 and C5 must run end-to-end against a stub agent before any model is
fine-tuned, and before the MVE is declared complete.**

If C3 cannot be run, we cannot distinguish progress from noise, and month 9
will look exactly like month 1.

---

## Failure modes and their tells

| Failure | What it looks like |
|---|---|
| Model collapse | Output entropy drops; same phrasings recur; rare topics vanish first. Reads *more* fluent while getting narrower. |
| Catastrophic forgetting | Recent material sharp, month-1 material quietly degraded. |
| Retrieval ceiling | Answer quality stops tracking corpus size; top-k saturated by generic chunks. |
| Reflection slop | Reflections get longer and more eloquent, and change no downstream metric. |
| Curiosity reward-hacking | Fixates on a high-entropy junk source (changelog, random feed) because prediction error is permanently maximal there — the "noisy TV" problem. Looks like enthusiasm. |
| Evaluation impossible | The developer is reading transcripts to decide whether it's working. **This is the v1 failure.** |

**Mitigations wired in from day one:** reward *learning progress* (Δ error), not
raw error; alarm if any single source consumes >20% of the reading budget;
ablate the reflection loop and require a metric to move.
