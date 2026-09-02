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

## 1. Hardware portability is a first-class requirement

**Design principle: the engine runs on anything. CUDA is an optimization, never
an assumption.**

Rationale: CUDA lock-in is a strategic risk, not merely a preference. Export
controls have already pushed a large share of the industry onto alternative
silicon (Huawei Ascend, Cambricon, Moore Threads), and any architecture that
assumes NVIDIA inherits that fragility. Portability is cheap to design in now
and expensive to retrofit.

### RETRACTED: "AMD blocks LoRA fine-tuning"

That claim was wrong. Corrections, with sources:

| Claim I made | Reality |
|---|---|
| "bitsandbytes is CUDA-only" | **False.** The ROCm backend is out of preview and stable as of the 0.50.x line, with published Windows wheels for ROCm 7.2/7.14, and the target list includes **gfx120X — RDNA4, i.e. this exact card**. Intel XPU/CPU stable; Apple MPS in beta. |
| "The Windows+ROCm training stack isn't viable" | **False.** [Unsloth ships official AMD support](https://unsloth.ai/docs/get-started/install/amd), built with AMD's engineering team, covering RDNA3/3.5/**4** across Windows, WSL, and Linux, one-line install. |
| "QLoRA on 8B is out of scope" | **Possible today** on this hardware — via WSL2+ROCm+Unsloth (highest confidence) or native Windows ROCm (works, preview-grade). |

**What *is* actually true:** bf16 LoRA on an 8B does not fit in 16 GB — because
8B in bf16 is 16 GB of *weights alone*, before activations or optimizer state.
That is a **VRAM** limit that applies identically to an RTX 4080. The fix is
4-bit (QLoRA at NF4 ≈ 5.5 GB), which this card can do. The conclusion ("we need
4-bit") was right; the premise ("AMD can't") was wrong.

Weight training remains **deferred in v2 on merit** — collapse risk, slow
feedback, unmeasurable until C4 exists — but it is now a *scheduling* decision
we can reverse, not a hardware wall.

### Measured backend performance (RDNA4, Llama-2-7B Q4_0)

| Backend | Prefill (pp512) | Decode (tg128) |
|---|---|---|
| ROCm/HIP + flash-attn | **4,903 t/s** | 97.3 t/s |
| Vulkan | 1,943 t/s | **124 t/s** |

**ROCm wins prefill; Vulkan wins decode.** The split is real and
workload-dependent — which is why backend selection is *measured at startup*,
not guessed (§2). For reference, the Vulkan-vs-CUDA portability tax on NVIDIA is
~10% decode / ~25–35% prefill: a tolerable price, not a disqualifier.

*Caveat: Windows ROCm measures ~30% slower decode than Linux on the same
hardware. WSL2 or dual-boot is the lever if we ever want that back.*

---

## 2. The compute abstraction (portability layer)

**Inference: `llama-server` (llama.cpp) directly, over its OpenAI-compatible
HTTP API.** One binary serves generation, embeddings (`--embeddings`), and
reranking (`--reranking --pooling rank`); one model format (GGUF); and the
widest backend coverage in the industry — CUDA, ROCm/HIP, Vulkan, SYCL, Metal,
OpenCL, **CANN (Huawei Ascend)**, **MUSA (Moore Threads)**, OpenVINO, ExecuTorch,
Snapdragon, IBM Z. The same `.gguf` runs on all of them.

> **Not Ollama.** Not for lock-in reasons — it speaks the same API and stays a
> drop-in fallback — but for measured performance. Its llama.cpp vendoring lags
> months behind, and on AMD it currently benchmarks **~34 t/s vs 52–56 t/s
> upstream: a 54–65% throughput tax** on exactly this hardware class.

**Four interfaces, and nothing more:**

```
LLMBackend        .generate(messages, **params) -> str
                  .generate_stream(...)         -> Iterator[str]
                  .tokenize(text)               -> list[int]
                  .capabilities()               -> {ctx_len, json_schema, ...}

EmbeddingBackend  .embed(texts, kind={"query","doc"}) -> np.ndarray
                  .dim -> int

RerankBackend     .rerank(query, docs) -> list[float]

TrainerBackend    .fit_step(batch) -> loss; .predict(x); .save/.load(path)
```

Everything returns **plain Python / NumPy**. `np.ndarray` is the lingua franca
at the boundary — never a `torch.Tensor`, never a device handle.

**Startup capability probe** (~50 lines, cached, re-run on driver change):
enumerate available runtimes → rank against a **declarative preference table in
config, not code** → **micro-benchmark on first run** (64-token prefill +
32-token decode, <5 s) and persist the winner *per workload*. That is what
resolves the ROCm-prefill / Vulkan-decode split automatically instead of by
guesswork. Emit a capability banner to the log and `/health`: a long-running
agent must be able to say what silicon it woke up on.

**Must NEVER cross the boundary:**
- Tensors, device objects, dtypes, streams, memory handles.
- The strings `cuda`, `rocm`, `vulkan`, `nvidia`, `amd` anywhere outside
  `backends/` and the probe. **Enforce with a CI grep** — the single most
  effective automatable guard.
- Model formats/paths (GGUF vs safetensors is a backend detail; callers ask for
  `"llm.main"`), quantization vocabulary (Q4_K_M/NF4), sampling-parameter
  dialects, tokenizer identity.
- Backend errors — catch and re-raise as `BackendUnavailable` / `OutOfMemory` /
  `ContextOverflow`, actionable without knowing who threw them.

**Model identity is a config alias, not a filename** (`llm.reflect →
qwen3-8b-q4km`). Swapping silicon and swapping model then become the same
one-line change — which is the actual test of whether the abstraction holds.

**Non-Western accelerators — honest position:** llama.cpp carries first-party
CANN and MUSA backends in-tree, so a GGUF inference layer *should* run on Ascend
and Moore Threads unchanged; PyTorch reaches them via out-of-tree device
registration (torch_npu tracks PyTorch 2.10; torch_musa lags at 2.5). We will
not have this hardware to test on, and operator gaps appear as runtime errors,
not build errors. **So: keep the abstraction clean, write nothing
vendor-specific, and describe this as "should work, unverified" — never as
"supported."**

---

## 2. Model roster (all local, fits 16 GB)

| Role | Model | Runs on | Trainable? |
|---|---|---|---|
| Reasoner / extractor / reflector | **Qwen3-8B-Instruct** GGUF Q4_K_M (~5 GB) | any llama.cpp backend | **Frozen forever** |
| Embeddings | **Qwen3-Embedding-0.6B** (1024-d, Matryoshka → 512) | same `llama-server` | **Frozen forever** |
| Reranker | **Qwen3-Reranker-0.6B** cross-encoder | same `llama-server` | Frozen |
| Entailment (contradictions) | DeBERTa-v3-MNLI class, or the 8B with a fixed rubric | GGUF or ONNX-CPU | Frozen |
| **World model** | 2-layer MLP on frozen embeddings → next chunk embedding | **CPU** (~5 M params) | **Trained continuously** |
| **RND novelty** | frozen random target net + trained predictor net | **CPU** (~2 M params) | **Trained continuously** |
| **Retrieval ranker** | LightGBM / tiny MLP over retrieval features | **CPU** (~10 K params) | **Retrained nightly** |

**All three trainable models run on CPU, and that is the fast choice, not a
compromise.** A 5 M-param MLP is ~3×10⁷ FLOP/sample; a modern Ryzen sustains
100–400 GFLOP/s, giving ~5–13 k samples/s — while on a GPU these are dominated
by kernel-launch overhead (~100–200 µs/step before any math). Below roughly
batch 1024 the CPU wins outright. It also leaves the GPU entirely free for the
8B, which is where VRAM contention actually lives, and costs zero vendor
dependencies. `device` stays configurable; the default is `cpu`.

*Validation gotcha:* some Qwen3-Reranker GGUF conversions ship without
`cls.output.weight` and silently emit ~1e-23 scores. **Assert on a known pair at
startup.**

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

**L4 — Identity adapter: DEFERRED, not blocked.** QLoRA on the 8B is achievable
on this hardware (WSL2+ROCm+Unsloth, or native Windows ROCm+bitsandbytes). It is
deferred because it carries the highest collapse risk, the slowest feedback
loop, and is **unmeasurable until C4 retention batteries exist** — not because
of the GPU vendor. Revisit after Phase 3. When revisited: versioned GGUF
adapters, ≥50% real external text in every batch, frozen-eval gate,
auto-rollback.

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
