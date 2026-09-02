# Genesis v2 — Research Survey

> Standing on shoulders. Every technique below is published, reproduced, and
> buildable by one person. Citations are load-bearing: if it isn't cited, we
> haven't earned it.

---

## 1. Agent memory architectures

| Work | Contribution | Difficulty |
|---|---|---|
| **Generative Agents** (Park et al., UIST '23) [doi](https://dl.acm.org/doi/fullHtml/10.1145/3586183.3606763) | Memory stream + retrieval scored `recency(exp decay) × relevance(embedding) × importance(self-rated)`, plus periodic **reflection** synthesizing higher-level beliefs from raw observations. | LOW |
| **MemGPT / Letta** ([arXiv:2310.08560](https://arxiv.org/abs/2310.08560)) | Tiered memory: core (in-context, **agent-editable**), recall, archival. Self-editing memory blocks as tool calls. | LOW–MED |
| **A-MEM** (Xu et al., NeurIPS '25) ([arXiv:2502.12110](https://arxiv.org/abs/2502.12110)) | Zettelkasten notes with LLM-generated tags, dynamic linking, and *memory evolution* — old notes update when new ones arrive. | MED |
| **Zep / Graphiti** ([arXiv:2501.13956](https://arxiv.org/abs/2501.13956)) | **Temporal** knowledge graph: every edge carries a validity window (`valid_from`, `invalidated_at`). Bi-temporal belief revision as a data model. | MED |

**Adopt:** the Generative Agents scoring formula and reflection loop (week one),
Letta's editable persona block as the seat of identity, Graphiti's validity
windows as schema discipline.

**Hype check:** the LOCOMO leaderboard war is noise — [Zep documented wrong gold
answers and top_k=50 inflating scores](https://blog.getzep.com/lies-damn-lies-statistics-is-mem0-really-sota-in-agent-memory/),
and the conversations are short enough to fit in a modern context window anyway.
**Never pick a memory design by leaderboard. Build our own probe set.**

---

## 2. Continual learning without catastrophic forgetting

- **"LoRA Learns Less and Forgets Less"** (Biderman et al., TMLR 2024)
  [openreview](https://openreview.net/forum?id=aloEru2qCG) — the load-bearing
  result: LoRA underperforms full fine-tuning at *acquiring* new domain skill
  but is markedly better at *preserving* base capability. For Genesis that
  trade is exactly right: we want a personality delta, not a new model.
- **SEAL** (Zweiger & Pari, NeurIPS '25) [arXiv:2506.10943](https://arxiv.org/abs/2506.10943)
  — model generates its own finetuning data ("self-edits"); held-out success
  20% → 72.5%. The outer RL loop is lab-scale; **the inner loop is not**, and is
  the most Genesis-shaped result of 2025.
- **Model collapse** (Shumailov et al., *Nature* 631:755)
  [doi](https://www.nature.com/articles/s41586-024-07566-y) — recursive
  self-training degrades models; tails vanish first.
- **Accumulate, don't replace** ([arXiv:2404.01413](https://arxiv.org/abs/2404.01413))
  — collapse is driven by *replacing* real data with synthetic. Accumulating
  (keeping real data in the mix) is stable. This is the mitigation that works.

**Adopt:** if we ever train weights, ≥50% real external text in every batch,
versioned adapters, frozen held-out eval, auto-rollback.
**Reject:** EWC and classic regularizers (LoRA's low-rank constraint already
buys most of the forgetting resistance); model editing (ROME/MEMIT) — [it does
not compose or revise rationally](https://arxiv.org/pdf/2406.19354).

---

## 3. Intrinsic motivation — real drives, not authored scalars

- **ICM** (Pathak et al. 2017) [arXiv:1705.05363](https://arxiv.org/abs/1705.05363)
  — curiosity = forward-model prediction error in a *learned* feature space.
- **RND** (Burda et al. 2018) [arXiv:1810.12894](https://arxiv.org/abs/1810.12894)
  — novelty = error of a predictor chasing a *fixed random* network. Trivially
  portable: run it on our embedding vectors. **~50 lines.**
- **Learning Progress / IMGEP** (Oudeyer et al., JMLR 23)
  [pdf](https://www.jmlr.org/papers/volume23/21-0808/21-0808.pdf) and
  **MAGELLAN** ([arXiv:2502.07709](https://arxiv.org/pdf/2502.07709)) — LP (the
  *derivative* of competence) beats raw novelty because it self-limits: it
  abandons both the mastered and the impossible.
- **Voyager** ([arXiv:2305.16291](https://arxiv.org/html/2305.16291)) — existence
  proof that an LLM can run its own open-ended curriculum.

**This is the section that replaces v1's five hand-tuned drive floats.** LP and
RND are *computed*, not authored — which alone kills the "engineer-written
intelligence" problem. Raw novelty chases noise (the noisy-TV failure); LP does
not.

---

## 4. World models / predictive coding

- **DreamerV3** (Hafner et al., *Nature* 2025) [doi](https://www.nature.com/articles/s41586-025-08744-2)
- **V-JEPA 2** (Meta 2025) [arXiv:2506.09985](https://arxiv.org/abs/2506.09985)
  — predict in *latent* space, not pixel space.

**Do not reimplement either.** No environment, no actions, no reward. Take the
idea, leave the architecture.

**The usable distillation — "predict-then-read":** before reading a document,
have the model predict what it will say; embed prediction and reality;
**surprise = distance**. High surprise → high importance → prioritized
consolidation. Implementable in a weekend, and it yields one principled scalar
that simultaneously drives curiosity, memory importance, and replay priority —
replacing "ask the LLM to rate importance 1–10".

---

## 5. Semantic memory without a hand-built graph

- **Hybrid retrieval** (BM25 ∪ dense → Reciprocal Rank Fusion → cross-encoder
  rerank). Unglamorous, highest-value swap available: reported recall@10
  ~78% → ~91% from hybrid, +15–40% Hit@1 from reranking. **Do this first.**
- **Embeddings:** Qwen3-Embedding (0.6B/4B) tops MTEB multilingual;
  EmbeddingGemma-300M is the best sub-500M CPU option.
- **LazyGraphRAG** ([Microsoft](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/))
  — defers LLM work to query time at ~0.1% of indexing cost. Use this pattern;
  full GraphRAG indexing will burn GPU-days.

**This replaces `processors/text.py` — the 30 regexes that caused v1's failure.**

---

## 6. Epistemics — knowing what it knows

- **Semantic entropy** (Farquhar et al., *Nature* 2024) — cluster semantically
  equivalent samples, take entropy over *meanings*, not tokens.
- **Semantic Entropy Probes** ([arXiv:2406.15927](https://arxiv.org/abs/2406.15927))
  — approximate it from one generation's hidden states, cost ≈ 0.
  **Running locally gives us hidden states — an advantage API agents lack.**
- **NLI-based contradiction detection** — small entailment model over new claim
  vs. retrieved beliefs. Cheap, works today.
- **Provenance** — every belief carries source span, extractor version,
  timestamp. Schema discipline, not ML.

**Adopt:** confidence becomes `(semantic entropy, provenance, contradiction
status)` instead of a constant from a table.

---

## 7. Local model landscape

See `INFRASTRUCTURE.md` for the AMD-specific plan. Summary: Qwen3-8B class at
Q4_K_M for reasoning, Qwen3-Embedding-0.6B for vectors, both comfortably within
16GB VRAM.

---

## TOP 6 TECHNIQUES TO ADOPT (value × feasibility)

1. **Generative-Agents retrieval + reflection loop** — best value/effort in the survey.
2. **Hybrid retrieval (BM25 + dense + RRF + reranker)** — the direct replacement for regex triples.
3. **Predict-then-read surprise scoring** — one loop supplying curiosity, importance, and replay priority.
4. **RND novelty over embedding space** — converts drive scalars into a learned quantity.
5. **Provenance + NLI contradictions + temporal validity** — epistemic honesty in one schema.
6. **Learned retrieval ranker** — changes *what it thinks of when it thinks*; real divergence, no collapse risk.

*(Weight fine-tuning is deliberately absent from the top 6. See below.)*

---

## TRAPS — will waste months

- **Reimplementing Dreamer/JEPA for text.** Enormous engineering, no environment, no reward.
- **Full SEAL.** The outer RL loop is lab-scale. Take the inner loop.
- **Building a memory framework from scratch** because Letta/A-MEM "aren't quite right." You'll rebuild them worse. Steal the *designs*.
- **Chasing leaderboard numbers.** Contaminated gold answers. Build your own probe set from your agent's history.
- **Full GraphRAG indexing.** Use LazyGraphRAG's defer-to-query pattern.
- **Editing beliefs into weights.** Beliefs live in the database with provenance; weights hold style and priors.
- **Continual fine-tuning on purely self-generated text.** Model collapse is *Nature*-published. A single agent talking to itself is the pathological case.
- **"Cognitive architecture" framing as an end in itself.** [CoALA](https://arxiv.org/abs/2309.02427) is useful *vocabulary*. Mapping onto ACT-R/SOAR boxes feels productive and produces nothing that learns. **This is precisely what v1 did.**

---

## One-line thesis

> Genesis's goals never needed a new architecture. They needed (a) an LLM doing
> extraction and reflection instead of regex, (b) embeddings instead of
> hand-built edges, (c) prediction error instead of authored constants, and
> (d) an evaluation harness that can tell whether any of it is working.
