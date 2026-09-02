# Genesis v2 — Architecture

**Target hardware:** Ryzen + **AMD RX 9070 XT, 16 GB VRAM**, Windows. Local-only,
always. No cloud APIs at runtime.

---

## 0. Diagnosis of v1

v1 had the right **ontology** (drives, provenance, contradictions,
consolidation, an autonomous loop) and the wrong **substrate**. Every quantity
that should have been *fit from data* was a literal: `hunger: float = 0.5`, a
frozen 9-member `RELATION_TYPES` set, 30 regex extractors with hand-assigned
confidences. `wanting = −d(pred_error)/dt` is the correct idea with no learned
predictor behind it.

**v2 keeps the ontology and replaces every hand-tuned constant with a fitted
parameter — and makes the substrate itself the thing that changes.**

---

## 1. The AMD constraint (read this first)

| Capability | Status on RX 9070 XT / Windows |
|---|---|
| LLM inference | ✅ Fine. Ollama ships ROCm Windows support; llama.cpp Vulkan is a strong fallback and often beats ROCm on Windows. |
| Embeddings | ✅ Fine (also runs on CPU). |
| Small PyTorch models (world model, RND, ranker) | ✅ Fine — few-MB models; ROCm or plain CPU both work. |
| **QLoRA / bitsandbytes fine-tuning** | ❌ **Effectively blocked.** bitsandbytes is CUDA-only; the Windows+ROCm training stack is not viable for a solo dev. |

**Consequence:** weight-level learning (adapters) is **out of scope for v2**.

This is not a loss. Both the red team and the ML architect independently
recommended deferring it: highest collapse risk, slowest feedback, unmeasurable
until C4 exists. If it's ever wanted, the path is a rented GPU-hour producing a
versioned GGUF adapter — an offline, gated, optional job, never a runtime
dependency.

**So v2's learning lives in L1–L3 below, and that is enough to be interesting.**

---

## 2. Model roster (all local, fits 16 GB)

| Role | Model | ~VRAM | Trainable? |
|---|---|---|---|
| Reasoner / extractor / reflector | **Qwen3-8B-Instruct** GGUF Q4_K_M | ~5 GB | **Frozen forever** |
| Embeddings | **Qwen3-Embedding-0.6B** (1024-d, Matryoshka → 512) | ~1.2 GB | **Frozen forever** |
| Reranker | **Qwen3-Reranker-0.6B** cross-encoder | ~1.2 GB | Frozen |
| Entailment (contradictions) | DeBERTa-v3-large-MNLI class, or the 8B with a fixed rubric | ~1 GB | Frozen |
| **World model** | 2-layer MLP on frozen embeddings, predicts next chunk embedding | ~5 M params | **Trained continuously** |
| **RND novelty** | frozen random target net + trained predictor net | ~2 M params | **Trained continuously** |
| **Retrieval ranker** | LightGBM / tiny MLP over retrieval features | ~10 K params | **Retrained nightly** |

**Two frozen-forever commitments.** The embedder is frozen because re-embedding
invalidates the whole memory store and silently rewrites the agent's past. The
base LLM is frozen because it is the collapse firewall.

---

## 3. Component map

```
              ┌──────────────── WAKE LOOP ────────────────┐
              │                                            │
 ┌─────────┐ topic ┌──────────┐ text ┌──────────────┐      │
 │CURIOSITY├──────►│ INGESTOR ├─────►│ PERCEPTION   ├──┐   │
 │ UCB1    │       │ wiki/RSS │      │ chunk+embed  │  │   │
 │ bandit  │◄──┐   │ arXiv    │      │ +claim extr  │  │   │
 └─────────┘   │LP └──────────┘      │  (Qwen3-8B)  │  │   │
      ▲        │                     └──────┬───────┘  ▼   │
      │   ┌────┴──────────┐   ┌─────────────▼──┐ ┌─────────┴┐
      │   │ MOTIVATION    │◄──┤ WORLD MODEL    │ │ EPISODIC │
      └───┤ LP·novelty·   │   │ ê(t+1)=g(e(t)) │ │  STREAM  │
          │ dissonance    │◄──┤ + RND novelty  │ │ (append) │
          └───────┬───────┘   └────────────────┘ └────┬─────┘
                  │ rest gate                          │
   ┌──────────────▼──────────────────────────────────▼─────────┐
   │           MEMORY — ONE SQLITE FILE = THE ENTITY            │
   │  episodes(FTS5 + sqlite-vec) │ claims + provenance DAG     │
   │  sources(Beta trust) │ contradictions │ self_model         │
   └──────────┬───────────────────────────────▲─────────────────┘
              │ hybrid retrieve                │ writes
              ▼                                │
   ┌──────────────────────────┐      ┌─────────┴──────────┐
   │ BM25 ∪ vector → RRF      │      │  SLEEP PASS        │
   │ → reranker → LEARNED     ├─────►│ cluster → reflect  │
   │   RANKER (nightly fit)   │      │ → claims → NLI     │
   └──────────┬───────────────┘      │ → trust → refit    │
              ▼                      └────────────────────┘
     ┌────────────────┐  semantic entropy
     │   Qwen3-8B     │──────► CALIBRATION
     └────────────────┘
```

---

## 4. Memory — one SQLite file is the entity

Copy the file = fork the individual. `sqlite-vec` for ANN, `FTS5` for BM25,
ordinary tables for the rest. No server, no Docker, backs up to a USB stick.
**The graph is a derived table, not the authoritative store** — v1's mistake was
making the typed graph the substrate.

**Episodic record** (append-only, never edited):

```sql
episode(id, t, kind{perceive|act|reflect|dialogue|error},
        text, embedding BLOB, source_id,
        surprise REAL, novelty REAL, lp_at_time REAL,
        importance REAL, parent_ids JSON,   -- provenance DAG
        access_count, last_access)
```

**Claims** are the distilled semantic layer:
`claim(id, subject, predicate, object, text, embedding, confidence,
support_ids, refute_ids, source_id, first_seen, last_confirmed)`.
**Predicates are open vocabulary** (embedding-clustered), not v1's frozen nine.

**Retrieval — hybrid, then learned.** top-50 BM25 ∪ top-50 vector → Reciprocal
Rank Fusion → reranker top-15 → learned ranker. Features: rerank score, cosine,
`exp(−λΔt)` recency, importance, source trust, access count, contradiction flag.

Initialize with the Generative Agents prior (`recency + importance + relevance`)
and **replace it with a fitted model as soon as labels exist**. Labels are free:
after each generation, NLI-check which retrieved episodes the answer actually
used — cited = positive, retrieved-but-uncited = negative. A real gradient from
real usage.

**Sleep pass** (idle/nightly): HDBSCAN over the day's embeddings → the 8B writes
reflections with `parent_ids` pointing at supporting episodes (provenance DAG
all the way down to a URL) → extract claims → NLI each new claim against its 10
nearest existing claims → contradiction rows → update source trust → refit
ranker and world model.

---

## 5. Learning — what durably changes

Three loci, all viable on AMD.

**L1 — Structured memory growth.** Zero risk, always on. Claims, reflections,
edges, trust posteriors. **80% of observable individuality**, durable from day one.

**L2 — Learned retrieval ranker.** Nightly refit on citation labels. The most
under-rated locus: it changes *what the entity thinks of when it thinks*. Two
instances with different histories retrieve differently from an identical query.
Visible divergence, no collapse risk.

**L3 — World model.** Self-supervised on **externally ingested text only** —
never on self-generated text. Predict `e(t+1)` from `e(t)` + context, MSE, small
replay buffer. Its error **is** the intrinsic reward. As a domain is learned,
error drops, LP drops, and the entity moves on — curiosity that terminates
honestly.

**L4 — Identity adapter: OUT OF SCOPE** (AMD; and deferred on merit anyway).

---

## 6. Intrinsic motivation — computed, not tuned

Per candidate topic cluster `c` (clusters from HDBSCAN in embedding space, so
the topic vocabulary grows on its own):

```
surprise(x) = ||e(x) − ĝ(e(prev), ctx)||²        # world-model error, z-normed
novelty(x)  = ||f_pred(e(x)) − f_tgt(e(x))||²    # RND, f_tgt frozen random

err_fast[c] ← 0.2·surprise + 0.8·err_fast[c]
err_slow[c] ← 0.02·surprise + 0.98·err_slow[c]
LP[c]       = err_slow[c] − err_fast[c]          # >0 ⇒ improving ⇒ learnable

value(c) = w_lp·|LP[c]| + w_n·novelty[c] + w_d·dissonance[c] − w_cost·cost(c)
```

Topic choice = **UCB1 bandit over clusters** with `value(c)` as reward — no
epsilon to tune; the exploration bonus is `sqrt(2 ln N / n_c)`.

**Why LP and not raw novelty:** raw novelty chases noise (random strings are
maximally novel — the noisy-TV failure). LP goes to zero on *both* mastered and
unlearnable topics — a property v1's `boredom` float could not express.

The four `w` weights are the **only** remaining hand-set numbers. They stay at
1.0 and are logged in an explicit "unfit parameters" list until there's evidence.

---

## 7. Knowing what it knows

- **Calibration:** semantic entropy — sample k=8 at T=1.0, cluster by
  bidirectional NLI, entropy over clusters. Train a semantic-entropy probe on
  mid-layer hidden states for the fast path. Track ECE on a stored self-quiz;
  **ECE should visibly improve as memory grows.** Verbalized confidence is not
  trusted as a primary signal.
- **Provenance:** every claim reaches a URL + timestamp + extractor version via
  `parent_ids`. "Why do you believe that?" is a DAG walk, not a generated story.
- **Trust:** per source, a **Beta(α, β) posterior**. α += 1 on independent
  corroboration, β += 1 on refutation by a higher-posterior source. Learned
  trust replacing v1's constants.
- **Contradictions:** NLI-detected, first-class rows, **never auto-resolved**.
  An open contradiction *raises* `dissonance[c]`, which raises `value(c)`, which
  makes the bandit go read about it. Dissonance becomes a reason to investigate.

---

## 8. Collapse defenses

1. **Frozen base + frozen embedder** — the representation space cannot drift.
2. **Facts never enter weights** — anything falsifiable lives in SQLite with provenance.
3. **World model trains on external text only** — never on its own output.
4. **Verifier gate** — a self-generated claim is only durable if it entails from
   a cited source chunk under NLI, has no open contradiction, and has survived
   ≥7 days without refutation.
5. **No weight training in v2** — the strongest defense of all, free on AMD.

---

## 9. Minimum Viable Entity (4 weeks)

Stack: Ollama (Qwen3-8B Q4_K_M + Qwen3-Embedding-0.6B) → Python 3.12 → one
SQLite file with `sqlite-vec` + FTS5.

- **Week 1** — episode stream; chunk+embed ingest from Wikipedia/RSS; hybrid
  retrieval with the fixed Generative-Agents prior; chat loop.
- **Week 2** — world model MLP + RND + LP bandit topic chooser (~150 lines; the
  entire intrinsic-motivation section).
- **Week 3** — sleep pass: cluster → reflect → claims with `parent_ids` → NLI
  contradictions → Beta trust.
- **Week 4** — semantic-entropy calibration + ECE dashboard; swap the fixed
  retrieval prior for the learned ranker.

**No LoRA. No graph reasoning. No GUI. No voice layer.**

**What it demonstrates** (two instances, identical code, different seed topics,
200 h ingest each): topic-cluster and claim-set Jaccard overlap falling over
time; LP rising then falling per topic with the bandit *abandoning* mastered
topics unprompted; ECE decreasing as memory grows; every claim rendering a
provenance DAG to a URL; kill the process and one file restores everything.

**That is the falsifiable core of the whole project.** If two instances don't
diverge, or LP doesn't decay on mastered topics, the architecture is wrong —
and we learn it in a month instead of at 44k lines.

---

## Open uncertainties (stated, not hidden)

1. Whether the LP signal is stable on text at this scale — embedding-space
   prediction error may be dominated by stylistic rather than semantic variance.
   **Instrument early**; fallback is per-cluster NLL under the frozen base.
2. Whether ROCm or Vulkan is the better Ollama backend on this specific card.
   **Spike in week 0.**
3. The four `w` weights in §6.
