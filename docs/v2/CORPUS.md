# Genesis v2 — Bootstrap Corpus

> **The corpus is the experimental apparatus, not just food.** Every criterion in
> `EVALUATION.md` depends on it: C1 needs two disjoint domains, C3 needs a pool
> coupled to an exam, C2 needs gold answers, C4 needs a frozen benchmark. Choose
> badly and the evaluation becomes unmeasurable.

**Web crawling is deliberately deferred to Phase 4** — it is non-reproducible
(twins would read different pages), gives C3 no denominator, and risks
benchmark contamination. v1's polite browser is ported *after* reading quality
is measurable on a fixed corpus.

---

## THE STACK

| | Choice | Why |
|---|---|---|
| **Spine** | **HotpotQA distractor + HotpotQA's own Wikipedia dump** | The only pair shipping corpus, questions, gold answers **and per-sentence supporting-fact labels** together. Solves C3 alignment outright. |
| **General KB** | `wikimedia/wikipedia` `20231101.en` + `.simple` | Background knowledge; Simple is the minutes-long dev loop |
| **C1 domains** | Two topic super-clusters carved from the HotpotQA wiki dump | Exam falls out free, difficulty is matched by construction |
| **Exams** | HotpotQA (multi-hop) + SQuAD v2 (single-hop) + **MMLU frozen** | Passages included; MMLU stays untouched for C4 |
| **Disk** | **≈ 34 GB core**, 64 GB with FineWeb-Edu | Plus ~4 GB embedding index |

---

## 1. Corpus

| Dataset | Path | Disk | Docs | License | For |
|---|---|---|---|---|---|
| **HotpotQA wiki abstracts** ★ | [`nlp.stanford.edu/projects/hotpotqa/enwiki-20171001-...-abstracts.tar.bz2`](https://hotpotqa.github.io/wiki-readme.html) | 1.55 GB bz2 (~8 GB raw) | ~5.23 M intro paragraphs | CC BY-SA 4.0 | **The C3 pool + claim extraction** |
| Wikipedia EN | `wikimedia/wikipedia` · `20231101.en` | ~20 GB* | 6.41 M | CC BY-SA 4.0 | General KB |
| Simple Wikipedia | same repo · `20231101.simple` | ~250 MB | 242 k | CC BY-SA 4.0 | Dev loop |
| arXiv abstracts | `common-pile/arxiv_abstracts` | ~3 GB | ~2.5 M | **CC0** | C1 hard-mode variant |
| FineWeb-Edu *(optional)* | `HuggingFaceFW/fineweb-edu` · `sample/10BT` | 30.6 GB | ~9 M | ODC-By 1.0 | Scale/noise robustness only |

**Primary is the HotpotQA wiki dump, not full Wikipedia.** Full articles are
long, multi-topic, and coupled to no questions — you can ingest them but you
cannot *grade* them. The dump is the same knowledge as ~5.2 M atomic,
single-entity paragraphs pre-linked to 113 k questions with sentence-level
evidence. Perfect shape for claim extraction *and* for measurement.

---

## 2. Exams

| Dataset | Path | Size | License | Ships passages? |
|---|---|---|---|---|
| **HotpotQA (distractor)** | `hotpotqa/hotpot_qa` · `distractor` | 599 MB; 90,447 train / 7,405 dev | CC BY-SA 4.0 | **Yes** — 10 paras (2 gold + 8 TF-IDF distractors) + `supporting_facts` |
| SQuAD v2 | `rajpurkar/squad_v2` | ~45 MB, 150 k Q | CC BY-SA 4.0 | Yes — inline |
| MuSiQue | [`StonyBrookNLP/musique`](https://github.com/stonybrooknlp/musique) | ~25 k Q, 2–4 hop | CC BY 4.0 | Yes — `is_supporting` flags |
| 2WikiMultihopQA | `framolfese/2WikiMultihopQA` | 167 k / 12.6 k / 12.6 k | Apache 2.0 | Yes |
| **MMLU** *(frozen, C4 only)* | `cais/mmlu` · `all` | ~166 MB, 14,042 test | MIT | No — that's the point |

**Multi-hop pick:** HotpotQA operationally (it's the only one with a matching
5.2 M-doc corpus), **MuSiQue as the adversarial check.** MuSiQue is the better
science — composed from single-hop questions with counterfactual filtering so no
reasoning step is skippable — while HotpotQA is documented as partly solvable
single-hop. Hold out ~500 MuSiQue items as a shortcut-resistant secondary score.

> **If the agent beats random on HotpotQA but not on MuSiQue, we measured
> retrieval luck, not reading.**

---

## 3. C3 construction — the alignment recipe

HotpotQA's gold titles are **exact keys into the 5.2 M-doc dump**. That coupling
is what makes the experiment possible.

1. Sample **1,000 dev questions** from `hotpot_qa/distractor` validation (7,405
   available). **Freeze with a hash before any arm runs.**
2. Pull the **2 gold titles** per question from `supporting_facts.title` →
   ~1,600–1,900 distinct gold docs after dedup.
3. Pull the **8 distractor titles** per question from `context`; sample to fill
   the pool to exactly **5,000 docs**. These are topically adjacent TF-IDF
   decoys — real distractors, not random noise.
4. Fetch paragraph text for all 5,000 titles from the wiki dump.
   **Do NOT use the `context` field as the corpus** — it is already the answer
   key. The agent must retrieve from the pool, not be handed ten candidates.
5. Emit `pool.jsonl` (5,000 docs, stable IDs) and `exam.jsonl` (1,000 Q, gold
   answer, `gold_doc_ids`, `supporting_sent_ids`).

**Three scores per arm instead of one:**
- **Answer EM/F1**
- **Gold-doc recall** — did its 200 chosen docs contain both golds?
- **Supporting-fact precision** — sentence level

**The null is razor sharp.** Random-200 has ~8% expected coverage of *either*
gold doc and **~0.6% of both**. The agent arm has enormous headroom, and any
real reading strategy should be unmistakable against that floor.

**C2 falls out free:** carve 300 questions from the unused 6,405 dev items —
gold answers already present, agent emits p(correct) pre-answer.

---

## 4. C1 disjointness

1. Embed all 5.2 M dump titles with `sentence-transformers/all-MiniLM-L6-v2`
   (80 MB, Apache 2.0); k-means to k=200.
2. Hand-merge into two super-domains — **A ≈ STEM/geography/science**,
   **B ≈ arts/media/biography/sport** — matched on doc count (~150 k each) and
   median doc length.
3. Assign each dev question to A or B **only if both gold docs are in the same
   domain**; discard cross-domain questions. Both twins sit the combined exam.

**Verify the split three ways before committing:**
- **Vocabulary overlap** — Jaccard on top-10k content words **< 0.25**
- **Embedding separation** — logistic probe predicting domain, **AUC > 0.95**
- **Leakage** — no shared titles; no B-doc linked from an A gold doc within one hop

**Control arm:** same corpus (A), different seed. That divergence is the noise
floor; C1 means nothing unless A-vs-B exceeds it.

*Why not arXiv `cs.*` vs `q-bio.*` as primary: cleaner separation, but the exam
must be LLM-generated, so you can't prove the two domains' questions are equally
hard. Keep as the stress variant (CC0, uniform genre and length). PubMed-vs-arXiv
is worse — it confounds domain with readability.*

---

## 5. NLI / contradiction detection

**Train nothing.** Use `MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli`
(MIT, ~870 MB — MNLI + FEVER-NLI + ANLI + LingNLI + WANLI, 885 k pairs). The
`-base-` variant (~370 MB) if CPU-latency-bound. FEVER-style claim verification
is already in the mix, which is exactly the contradiction use case.

---

## 6. Acquisition

```bash
pip install -U huggingface_hub datasets
$env:HF_HOME="D:\genesis\hf"          # Windows: keep the cache off C:

# PIN EVERY ONE TO A COMMIT SHA, NOT A BRANCH.
hf download wikimedia/wikipedia --repo-type dataset --include "20231101.simple/*" --revision <SHA> --local-dir D:\genesis\wiki-simple
hf download wikimedia/wikipedia --repo-type dataset --include "20231101.en/*"     --revision <SHA> --local-dir D:\genesis\wiki-en
hf download hotpotqa/hotpot_qa         --repo-type dataset --revision <SHA> --local-dir D:\genesis\hotpot
hf download rajpurkar/squad_v2         --repo-type dataset --revision <SHA> --local-dir D:\genesis\squad2
hf download cais/mmlu                  --repo-type dataset --revision <SHA> --local-dir D:\genesis\mmlu
hf download framolfese/2WikiMultihopQA --repo-type dataset --revision <SHA> --local-dir D:\genesis\2wiki
hf download common-pile/arxiv_abstracts --repo-type dataset --revision <SHA> --local-dir D:\genesis\arxiv
hf download MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli --revision <SHA> --local-dir D:\genesis\nli

# Not on HF — direct, and the single most important file:
curl -o D:\genesis\hotpot-wiki.tar.bz2 https://nlp.stanford.edu/projects/hotpotqa/enwiki-20171001-pages-meta-current-withlinks-abstracts.tar.bz2
```

**Pinning is not optional.** `wikimedia/wikipedia`'s `main` moves as languages
are added. Get SHAs via `HfApi().dataset_info("...").sha`, record every one in a
committed **`corpus.lock.json`** alongside a SHA-256 of each downloaded file,
and verify by re-downloading at that revision on a clean machine.

**Download:** ~2–4 h on 100 Mbit. **None of the above are gated.**

---

## 7. Explicitly skip

| Skip | Why |
|---|---|
| **S2ORC** | Bulk files retired; API-key only. Not pinnable — fails reproducibility outright |
| **Natural Questions** | ~140 GB of full HTML pages; messy passage gold. SQuAD v2 dominates on cost/benefit |
| **Dolma** | Multi-TB; FineWeb-Edu gives better quality for less disk |
| **C4** | 300+ GB of unfiltered sludge, heavily benchmark-contaminated |
| **WikiText-103** | Stale *shuffled fragments* for LM perplexity — not documents. Wrong shape |
| **Project Gutenberg (raw)** | Pre-1929 narrative prose is near-useless for claim extraction, plus redistribution friction. *(Note: v1 leaned on this heavily.)* |
| **MMLU for anything but C4** | Its entire value is being frozen and untouched. Contaminate it and C4 measures nothing |

> **Contamination warning to record in `corpus.lock.json`:** MuSiQue's dev/test
> single-hop components were drawn from SQuAD, Natural Questions, T-REx, MLQA and
> Zero-Shot-RE. **If we ever fine-tune on SQuAD, the MuSiQue score is
> compromised.** Currently clean because we train nothing.

---

## Verification caveat

The research proxy blocked direct `huggingface.co` fetches, so paths, sizes and
licenses come from search snippets of the dataset cards plus the papers/GitHub
repos. **Confirmed hard:** HotpotQA (599 MB, 90,447/7,405, CC BY-SA 4.0, 2+8
distractor structure), the wiki dump (1,553,565,403 bytes), FineWeb-Edu
`sample/10BT` (30.6 GB), MMLU (14,042 test, MIT), SQuAD v2, 2Wiki (Apache 2.0),
MuSiQue (CC BY 4.0), arXiv abstracts (CC0), the NLI model (MIT).
**Softer:** `20231101.en` at ~20 GB is *inferred* (the repo's all-languages total
is 71.8 GB) — **check the actual config size before sizing the SSD.**
