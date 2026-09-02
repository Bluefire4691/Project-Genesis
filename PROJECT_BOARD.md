# Project Genesis v2 — Board & Timeline

**Status:** Pivot approved. v1 (symbolic) frozen for reference; v2 built alongside.
**Hardware:** Ryzen + AMD RX 9070 XT (16 GB VRAM), Windows. **Local-only, always.**
**Team artifacts:** [`docs/v2/RESEARCH_SURVEY.md`](docs/v2/RESEARCH_SURVEY.md) ·
[`docs/v2/ARCHITECTURE_V2.md`](docs/v2/ARCHITECTURE_V2.md) ·
[`docs/v2/EVALUATION.md`](docs/v2/EVALUATION.md) ·
[`docs/v2/SALVAGE_AUDIT.md`](docs/v2/SALVAGE_AUDIT.md) · [`docs/v2/CORPUS.md`](docs/v2/CORPUS.md)

---

## The one-paragraph brief

v1 failed for a measurable reason: 30 regexes produced a graph with 89 relations,
162 nodes, and a maximum reasoning chain of 2 hops. Every faculty above it —
inference, curiosity, drives, values — was a correct algorithm computing over
nothing. v2 replaces the extractor with a local LLM, the hand-built graph with
embeddings, the authored constants with prediction error, and — most
importantly — **builds the evaluation harness before the agent**, so we can tell
progress from noise. The goal is unchanged: continuity, self-direction,
accumulated individuality, calibrated self-knowledge.

---

## Definition of Done (applies to every milestone)

1. **Measured, not asserted.** Each milestone names the metric it moves.
2. **No new hand-tuned constant** without an entry in the `UNFIT_PARAMETERS` log.
3. **Ablation-ready.** Every component can be disabled by config for C5.
4. **Errors are data** — structured error log, no bare `except: pass`. *(carried from v1)*
5. Board updated; this file is the source of truth.

---

## PHASE 0 — Preserve & Falsify · *Week 0–1*

> Cheap, decisive work before committing to a rewrite.

| # | Task | Definition of Done | Priority |
|---|---|---|---|
| 0.1 | **Back up the live databases** | `backup_genesis_data.bat` run; copy stored **off** the machine. `interaction_log.db` (4,580 conversations) is irreplaceable and one `del` away from gone. | 🔴 **DO TODAY** |
| 0.2 | **Compute abstraction + capability probe** | Four backend interfaces (`LLMBackend`, `EmbeddingBackend`, `RerankBackend`, `TrainerBackend`), NumPy-only boundary, startup probe that enumerates available runtimes and **micro-benchmarks** to pick per-workload winners. CI grep rejecting vendor strings outside `backends/`. | 🔴 |
| 0.2b | Backend spike | `llama-server` built with both ROCm and Vulkan; pp512/tg128 recorded for Qwen3-8B Q4_K_M; winners pinned per workload by measurement, not guess. | 🔴 |
| 0.3 | **Falsification test on v1** | Swap `processors/text.py` regexes for a local-LLM extractor emitting canonical triples. Re-run `knowledge_eval.py`. **Question: does inference reach rise above zero and stay there?** | 🔴 |
| 0.4 | Decide: patch or rebuild | If 0.3 lights up the graph → v1 salvage is real and v2 inherits a working corpus. If chains still don't form → the bottleneck is architectural, rewrite is justified. **Either way we learn it in a week, not a year.** | 🔴 |

**Phase gate:** 0.3's result is recorded in this file with numbers before Phase 2 starts.

---

## PHASE 1 — Evaluation Harness · *Week 1–3* · **BEFORE the agent**

> The team was unanimous: the absence of this is why eight months produced no
> verdict. Build the scoreboard before the player.

| # | Task | Definition of Done |
|---|---|---|
| 1.1 | Probe battery infrastructure | 200-item held-out question set + scorer; monthly-battery format defined. |
| 1.2 | Twin runner | Launch 2 instances with disjoint corpora + a same-corpus/different-seed control; collect topic-choice distributions and claim sets. |
| 1.3 | Divergence metrics (C1) | Jensen–Shannon over topic choices; Jaccard over claims; **retrieval-detach switch** implemented. |
| 1.4 | Calibration harness (C2) | Brier score + reliability diagram; the three baselines (base rate, verbalized confidence, retrieval-no-history) runnable. |
| 1.5 | **Reading-choice experiment (C3)** | 5,000-doc pool + 1,000-question exam built from HotpotQA per the recipe in `CORPUS.md` §3 — **hash-frozen before any arm runs**. 3 arms (agent / random / round-robin), 200-doc budget each. Scores per arm: answer EM/F1, **gold-doc recall**, supporting-fact precision. |
| 1.6 | Ablation framework (C5) | Every subsystem disableable by config flag; harness re-runs C1–C4 per ablation. |
| 1.7 | Collapse tripwires | Weekly type-token ratio + distinct-n on a fixed prompt set; frozen 200-item capability benchmark. |
| 1.8 | **Corpus acquisition** *(prerequisite for 1.1–1.6)* | Fixed, offline, **version-pinned** corpus downloaded and indexed. Provides: disjoint domains A/B for C1, the ~5k pool + coupled held-out exam for C3, gold-answer QA for C2, frozen benchmark for C4. See `docs/v2/CORPUS.md`. | 🔴 |

**Phase gate: C3 and C5 run end-to-end against a stub agent.** If we cannot run
C3, we cannot tell progress from noise. **This gate does not get skipped.**

---

## PHASE 2 — Minimum Viable Entity · *Week 4–8*

| # | Task | Definition of Done | Metric |
|---|---|---|---|
| 2.1 | Foundation | Ollama + Qwen3-8B + Qwen3-Embedding-0.6B; one SQLite file with `sqlite-vec` + FTS5; episode stream schema. | process restart restores all state |
| 2.2 | Ingest + perception | Chunk, embed, LLM claim-extraction with provenance to source span — **from the fixed local corpus (1.8), not the web.** | claims/doc; % with valid provenance |
| 2.3 | Hybrid retrieval | BM25 ∪ vector → RRF → reranker; Generative-Agents scoring prior. | recall@10 on 50-query gold set |
| 2.4 | **Intrinsic motivation** | World-model MLP + RND + LP-per-cluster + UCB1 bandit. ~150 lines. | LP curve rises then falls per topic |
| 2.5 | Sleep pass | HDBSCAN cluster → LLM reflections with `parent_ids` → claims → NLI contradictions → Beta trust update. | contradictions found; trust separates good/bad sources |
| 2.6 | Calibration | Semantic entropy (k=8 + NLI clustering) + ECE dashboard. | **C2** |
| 2.7 | Learned ranker (L2) | Nightly LightGBM refit on citation labels; replaces the fixed prior. | recall@10 improves over 2.3 |

**Explicitly NOT in Phase 2:** **web crawling/auto-pull** (see below), LoRA/weight
training (deferred on merit), GUI, voice layer, audio, multimodal, 24/7
autonomous loop, multi-agent. *(v1 shipped a 1,959-line `voice.py` that produced
zero knowledge.)*

> ### Why web ingestion is deliberately deferred
>
> It is not merely "later tooling" — during Phases 1–3 it would **actively
> invalidate the experiments**:
> - **Non-reproducible.** Two twins for C1 would read different pages on
>   different days, so divergence could not be attributed to the agent rather
>   than to the internet.
> - **Uncontrolled pool.** C3 compares agent-choice against random over a *fixed*
>   200-of-5,000 budget. An open web has no denominator.
> - **Benchmark contamination.** Live pages can contain the answers to the very
>   exam questions being used to score it.
> - **Confounded failure.** v1 could never separate "bad extraction" from "bad
>   diet" because both varied at once.
>
> v1's polite browser (robots.txt, rate limiting, paywall blocklist) is
> **KEEP-as-is** in the salvage audit and gets ported in **Phase 4**, once
> reading quality is measurable on a fixed corpus first.

---

## PHASE 3 — Prove the Claims · *Week 9–12*

> This phase produces **numbers**, not transcripts. It is the phase v1 never had.

| # | Task | Success criterion |
|---|---|---|
| 3.1 | Twin divergence run | **C1** — between-corpus divergence > within-seed by 3σ, **and ≥50% of the gap survives retrieval detachment** |
| 3.2 | Calibration study | **C2** — Brier beats all 3 baselines; studied/unstudied gap widens over time |
| 3.3 | **Reading-choice study** | **C3** — agent beats random *and* round-robin on a held-out exam, >seed variance, 3 runs |
| 3.4 | Ablation study | **C5** — every component degrades a named metric when removed, or is **deleted** |

**Phase gate:** if C3 fails, intrinsic motivation is decoration — stop and
redesign it rather than building on top of it.

---

## PHASE 4 — Longitudinal · *Month 4+*

| # | Task | Success criterion |
|---|---|---|
| 4.1 | Monthly retention batteries | **C4** — month-1 retention ≥90% at month 4 |
| 4.2 | Long-run divergence | Twin Jaccard keeps falling; no collapse tripwire fires |
| 4.3 | *(Optional, gated)* Identity adapter | Only via rented GPU-hour; versioned GGUF, frozen-eval gate, auto-rollback. **Not required for success.** |

---

## Roles

| Role | Owns |
|---|---|
| **Research** | Literature; keeps `RESEARCH_SURVEY.md` current; vets every technique against a citation before adoption |
| **ML Architecture** | `ARCHITECTURE_V2.md`; model roster; the learning loci; says no to exotic components |
| **Infrastructure** | Ollama/ROCm, vector store, process split, dependency pinning, crash recovery |
| **Evaluation / Red Team** | `EVALUATION.md`; owns the phase gates; **has veto authority** on "it feels like it's working" |
| **Salvage** | `SALVAGE_AUDIT.md`; what ports from v1; the DO-NOT-RELEARN list |

---

## DO NOT RELEARN (hard-won in v1 — carried forward)

1. **A CPU spike must not collapse the energy budget.** WordNet loading once burned 2,920 ms, charged it to the next cycle, hit EMERGENCY throttle, and *silently disabled memory storage* — every subsequent learn stored nothing. Any throttle must smooth (EMA) and must **never** let a resource state silently disable persistence.
2. **No bare `except: pass`, ever.** It hid the above for weeks. Make it a lint rule.
3. **Paywall/domain matching is by netloc suffix, never substring** (`group.com` must not match `oup.com`).
4. **robots.txt + 3 s per-domain rate limit + honest UA + never re-fetch a URL in a session.**
5. **Never fetch on the cognition thread.** Web I/O gets its own thread; brain access uses a *timed* lock acquire that fails fast rather than hanging the UI.
6. **Long consolidation passes must not hold the write lock** — v1's launch freeze. Consolidation operates on a snapshot; writes back in short transactions.
7. **Count-based tests need a tempfile DB.**
8. **Verify dependencies before destroying state** (the fresh-start script installs PyQt6 *before* deleting the DB).
9. **Cross-layer review before any feature:** "what in the layers below could break this, and how would I know?"

---

## Ledger — decisions made

| Date | Decision | Rationale |
|---|---|---|
| — | **Pivot to modern ML** | v1 measurably plateaued: 89 relations, 2-hop max, 6 subsystems with 0 rows |
| — | **Reverse the "no pretrained weights" rule** | It forced solving open-domain NLP with regex as a precondition for everything else. The LLM is a *linguistic organ*; accumulated state stays in Genesis's own memory — the individuality claim moves to memory + retrieval + world model, where it can be measured |
| — | **Local-only confirmed** | Continuity and individuality claims are incoherent if the mind runs in someone else's datacenter |
| — | **Hardware portability is a first-class requirement** | CUDA lock-in is a strategic risk, not a preference — export controls have already moved much of the industry onto alternative silicon. `llama.cpp`/GGUF chosen for the widest backend coverage (CUDA, ROCm, Vulkan, SYCL, Metal, CANN/Ascend, MUSA). Backend selection is **measured at startup**, never assumed. Vendor strings are a lint failure outside `backends/`. |
| — | ~~No weight training in v2 (AMD blocks QLoRA)~~ **CORRECTED** | The AMD claim was **wrong**: bitsandbytes has a stable ROCm backend with Windows wheels covering gfx120X/RDNA4, and Unsloth ships official AMD support built with AMD. QLoRA on 8B is achievable on this card. Weight training stays **deferred on merit only** (collapse risk; unmeasurable until C4) — a reversible scheduling call, not a hardware wall. |
| — | **Not Ollama; `llama-server` directly** | Performance, not lock-in: Ollama's llama.cpp vendoring lags months, benchmarking ~34 t/s vs 52–56 t/s upstream on AMD — a 54–65% tax. Ollama remains a drop-in fallback since it speaks the same API. |
| — | **Small trainable models run on CPU** | 5 M-param MLPs are kernel-launch-bound on a GPU below batch ~1024; CPU is both faster here and fully portable, and leaves the GPU free for the 8B. |
| — | **Fixed offline corpus; web crawling deferred to Phase 4** | The corpus is the experimental apparatus. Crawling is non-reproducible (twins would read different pages), gives C3 no denominator, and risks benchmark contamination. HotpotQA + its own 5.2 M-doc Wikipedia dump chosen because it is the only source shipping corpus, questions, gold answers **and per-sentence supporting-fact labels** together — so we can measure whether the agent chose to read the *right documents*, not just whether it answered. See `docs/v2/CORPUS.md`. |
| — | **Eval harness before agent** | The single change most likely to prevent a repeat of v1 |
| — | v1 kept alongside v2, not deleted | Reference, comparison baseline, and the launchers still work |
