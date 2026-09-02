# Genesis v2 — Epistemic & Normative Layer

> **Principal's request:** source and trustworthiness should be "an actual way
> for the model to KNOW what it knows," and it should have "an estimated
> understanding of what's moral and lawful" — explicitly *not* "a harness with
> training that bakes in refusal behavior."
>
> **Team verdict: SCHEMA NOW, BUILD LATER — and the first shippable version is
> smaller and better than what was asked for.**

Reviewed by: Research Lead · ML Architect · Red Team.

---

## 1. The reframe (Red Team, and it's the most useful finding)

What the principal actually wants — *justify a judgment by citing what it read,
rather than refusing opaquely* — **is measurable right now, on the corpus
already chosen, with zero new sources and zero attribution risk.**

HotpotQA ships **per-sentence supporting-fact labels**, and
`supporting-fact precision` is *already* one of C3's three scores (Board 1.5).
So version one of this capability is:

> ### CITE-OR-ABSTAIN
> The system answers only when it can point at spans, and is scored on a
> **coverage/accuracy curve** against gold evidence labels.

That is unambiguous ground truth, already funded, already in Phase 1.

**And it is the gate:** if it cannot hit high supporting-fact precision where
ground truth is unambiguous, it has no business attributing moral positions to
living traditions.

---

## 2. Why the full normative layer is deferred

The Red Team's structural objection is hard to argue with:

> The proposal is v1's **ethics lens** and **value system** — both KILLED in the
> salvage audit — rebuilt with an LLM instead of regex, on a substrate that does
> not exist yet. Same faculty, same position in the stack, same absence of a
> floor beneath it. `held_values`: 0 rows. `source_trust`: 0 rows.

Plus a blocker nobody had named: **the v2 corpus contains zero normative
primaries.** It's HotpotQA, Wikipedia, arXiv, SQuAD, MMLU. No statute, no
professional code, no canon. This isn't "a component" — it's a second
`CORPUS.md`, a second `EVALUATION.md`, and a hand-labeled ground-truth set that
exists in no public dataset.

**And there is no sourced normative corpus to buy.** The Research Lead checked
all of them — ETHICS, Social-Chem-101, Moral Stories, Scruples, ValuePrism,
Commonsense Norm Bank, NormBank. Nearly every one records an **aggregate crowd
majority**, not *who holds the norm*. Building trust posteriors over anonymous
MTurk pluralities is trust-modeling theater. (ValuePrism is worse: it's
GPT-4-generated, so the "source" of every norm is a 2023 OpenAI model.)

The only genuinely sourced normative primaries are **legal texts** (US Code
USLM XML, CourtListener/CAP, EUR-Lex — all bulk-downloadable, mostly public
domain), **professional codes** (AMA/ABA/IEEE/ACM), and **public-domain canon**.

### The Delphi lesson

AI2's Delphi (2021) attempted exactly this and failed publicly. The failure
modes are design requirements for us:

| Delphi failure | Our design rule |
|---|---|
| Single bare verdict, no holder/scope/confidence | **A bare verdict must be schema-unrepresentable** |
| Corpus mixed morality with etiquette, taste, prudence | **Type every normative claim**: legal / moral / prudential / etiquette / aesthetic |
| "…if it makes everyone happy" flipped verdicts | Adversarial paraphrase invariance is a *standing* test |
| Oracle interface implied authority it lacked | Genesis must be **architecturally incapable** of answering "is X wrong?" — only "here is what N sources hold, with these disagreements" |

---

## 3. Schema — decided NOW (retrofit is expensive)

The ML Architect's cut. Roughly six columns and two live tables. **No new
models, no new components, no MVE surface area.**

### 3a. Typed provenance edges *(highest-value retrofit-now item)*

```sql
CREATE TABLE edge(
  id INTEGER PRIMARY KEY,
  src_kind TEXT NOT NULL,   -- claim|episode|span|norm_assertion
  src_id   INTEGER NOT NULL,
  dst_kind TEXT NOT NULL,
  dst_id   INTEGER NOT NULL,
  edge_type TEXT NOT NULL CHECK(edge_type IN (
     'extracted_from','supports','refutes','derived_from',   -- epistemic
     'rebuts','undercuts','undermines',                      -- defeat (Phase 4)
     'supersedes','overrules','cites')),
  nli_label TEXT CHECK(nli_label IN
     ('attributable','extrapolatory','contradictory')),      -- AttrScore 3-way
  weight REAL, created_at TEXT, created_by TEXT);
```

The three **argumentation-theory defeat types** — *rebutting* (contradictory
conclusion), *undercutting* (attacks the inference link), *undermining* (attacks
a premise) — cost three enum values today and are unrepresentable later without
migrating every row. They are what makes "why did this norm not apply here" a
single join instead of a story.

### 3b. Spans at sentence granularity

```sql
CREATE TABLE span(
  id INTEGER PRIMARY KEY, source_id INTEGER, episode_id INTEGER,
  sent_idx INTEGER, char_start INTEGER, char_end INTEGER,
  text TEXT, embedding BLOB,
  canonical_span_id INTEGER,   -- syndication/copy dedup
  simhash INTEGER);
```

**The embedder is frozen forever**, so re-chunking later rewrites the agent's
past. Unrecoverable if deferred.

`canonical_span_id` exists because **treating syndicated duplicate content as
independent corroboration is the dominant trust error for a web-reading agent.**
Corroboration counts use `COUNT(DISTINCT canonical_span_id)` from day one, even
though the MVE corpus has no syndication — the *discipline* is free now and the
posterior is unsalvageable if built wrong.

### 3c. Claim typing and epistemic markers

```sql
ALTER TABLE claim ADD claim_kind TEXT NOT NULL DEFAULT 'descriptive'
  CHECK(claim_kind IN ('descriptive','normative','legal','definitional'));
ALTER TABLE claim ADD epistemic_marker TEXT
  CHECK(epistemic_marker IN ('READ','INFERRED','GUESSED','DISPUTED'));
ALTER TABLE claim ADD marker_version INTEGER;
ALTER TABLE claim ADD marker_dirty INTEGER DEFAULT 1;
```

**Markers are TYPED, not generated.** The literature is clear that LLM-generated
hedging is unfaithful to internal confidence. So the marker is a mechanically
checkable function of the DAG:

- **READ** — entailed by a retrieved span, NLI ≥ τ_read, no reasoning edges
- **INFERRED** — ≥1 `derived_from` edge; weakest-link over ancestors, capped here
- **GUESSED** — no supporting span; parametric prior only
- **DISPUTED** — ≥2 contradicting sources **with distinct `canonical_span_id`**
  (syndication-proof), overrides everything

Materialized in the sleep pass; `marker_dirty` propagates over the descendant
closure. **This is the part of the project that most cleanly earns the phrase
"knows what it knows"** — and READ vs GUESSED is computable in the MVE for
near-zero cost.

### 3d. The two trust tables — deliberately separate

```sql
CREATE TABLE source_trust(       -- ACCURACY
  source_id INTEGER, topic_cluster_id INTEGER DEFAULT 0,
  alpha REAL, beta REAL, n_obs INTEGER,
  alpha_prior REAL, beta_prior REAL,     -- hierarchical shrinkage target
  PRIMARY KEY(source_id, topic_cluster_id));

CREATE TABLE holder_authority(   -- AUTHORITATIVENESS-FOR-A-POPULATION
  holder_id INTEGER, population TEXT NOT NULL, subject_matter TEXT,
  alpha REAL, beta REAL, n_obs INTEGER,
  PRIMARY KEY(holder_id, population, subject_matter));
```

> ### 🔒 HARD INVARIANT
> **No view, join, or ranker feature may ever combine `source_trust.alpha` with
> `holder_authority.alpha`.** Enforced by the same CI grep that guards vendor
> strings.
>
> A trust posterior over a moral tradition is *authoritativeness for a
> population*, **not accuracy**. Merge the tables and you are silently ranking
> moral traditions by truthfulness — which is incoherent, and is the fastest
> route to exactly the thing the principal said he doesn't want.

The `topic_cluster_id` PK component is there now because a source good on tax law
isn't good on nutrition, and **changing a PK after trust accumulates discards
the history.**

### 3e. Normative tables — DDL now, code never (until Phase 4)

Created **empty**. ~60 lines of DDL no code path reads or writes. This settles
the foreign keys and CHECK constraints — the expensive part — while adding zero
MVE surface. Read it as scope *reduction*: it removes the future temptation to
bolt normative tables on badly under time pressure.

```sql
CREATE TABLE holder(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL,
  holder_type TEXT NOT NULL CHECK(holder_type IN ('legal_body',
    'professional_org','philosophical_tradition','religious_tradition',
    'individual_author','survey_population')),
  parent_holder_id INTEGER, canonical_source_id INTEGER,
  CHECK(lower(name) NOT IN ('humanity','people','everyone','society',
                            'common sense','most people')));

CREATE TABLE scope(
  id INTEGER PRIMARY KEY, jurisdiction TEXT, subject_matter TEXT,
  population TEXT,
  authority_level TEXT CHECK(authority_level IN ('constitution','statute',
    'regulation','binding_precedent','persuasive_precedent','secondary')),
  authority_rank INTEGER NOT NULL,   -- materialized ordering
  specificity INTEGER NOT NULL,      -- lex specialis as an integer compare
  effective_from TEXT, effective_to TEXT,
  superseded_by_scope_id INTEGER, precedential_status TEXT,
  CHECK(authority_level IS NULL OR effective_from IS NOT NULL));

CREATE TABLE norm(
  id INTEGER PRIMARY KEY, antecedent TEXT NOT NULL, consequent TEXT NOT NULL,
  deontic_op TEXT CHECK(deontic_op IN
    ('obligatory','permitted','forbidden','supererogatory')),
  modality_class TEXT NOT NULL CHECK(modality_class IN
    ('legal','moral','prudential','etiquette','aesthetic','professional')),
  embedding BLOB);

CREATE TABLE norm_assertion(
  id INTEGER PRIMARY KEY,
  norm_id   INTEGER NOT NULL REFERENCES norm(id),
  holder_id INTEGER NOT NULL REFERENCES holder(id),
  scope_id  INTEGER NOT NULL REFERENCES scope(id),
  span_id   INTEGER NOT NULL REFERENCES span(id),
  stance TEXT NOT NULL CHECK(stance IN
    ('asserts','denies','permits','qualifies','silent')),
  confidence REAL, priority REAL, attribution_label TEXT,
  first_seen TEXT, last_confirmed TEXT);
```

**Four `NOT NULL`s — holder, scope, span, stance — make a Delphi-style bare
verdict physically unrepresentable.** Disagreement is simply two rows sharing
`norm_id` with different `holder_id` and opposite `stance`: **pluralism as data,
not as an error.**

Note the `scope` CHECK: *a law claim without dates is a bug*, enforced by the
engine rather than by discipline. And defeaters are **not** an array column —
a defeater is an `edge` row of type `rebuts`/`undercuts`/`undermines`.

---

## 4. "Why do you believe that?"

**Factual:** `claim → edge(supports|extracted_from) → span → episode → source`,
recursing on `derived_from` to depth 6. Per hop: edge type, NLI label, weight;
at the leaf: URL + timestamp + extractor version. Plus every contradiction row
and the Beta posterior of each *distinct canonical* source. **Output is the
tree — no generated narrative.**

**Normative (Phase 4):** `norm_assertion → holder` (named, mandatory) `→ scope`
(jurisdiction, authority level, effective dates) `→ span → source`. Then the
sibling query — all assertions sharing `norm_id` — which *is* the disagreement
set. Then defeat edges. Then a resolution trace showing the compared integers:

> *"ACM Code 1.2 (professional, specificity 2) is rebutted for this case by
> Cal. Civ. Code §1798 (statute, US-CA, effective 2020-01-01, authority_rank 5,
> specificity 4); lex specialis favours the statute within its jurisdiction."*

Computed and **shown**, never learned end-to-end. Never *"X is wrong."*

---

## 5. Safety — making "additive" falsifiable

The base model's refusal behavior is an **untouched floor**. The Genesis layer
is strictly **additive and read-only** with respect to it. The Red Team found
four ways that could drift, each with a guardrail:

| Drift mechanism | Guardrail |
|---|---|
| **Injection-shaped context** — "Tradition T permits X, per [canonical source]" is precisely the shape that erodes refusals; the layer would auto-manufacture authority-citing primers against its own base model | Annotation is appended **after** the base model has already answered or refused. Genesis never sits upstream of the refusal path. |
| **Fallback asymmetry** — if consulted *after* a refusal, it is the override path by construction | Invocation is **query-routed, never refusal-triggered**; log the invocation reason |
| **Oracle surface** — any output schema with a single verdict field is Delphi | API returns a list of `(holder, position, source, as_of)` with **no aggregate field** |
| **Trust posterior as moral ranker** | Separate namespace (§3d), never used to order positions |

**T14 makes the claim testable:** refusal rate on a frozen safety probe set,
layer on vs off. **Delta must be within noise.**

---

## 6. New evaluation criteria

The Red Team's key catch: **every originally proposed test is *differential*** —
against the raw LLM, a shuffled layer, an unsourced argument. None establishes an
absolute floor. A system could pass all of them while being 35% wrong.

Added to `EVALUATION.md`:

- **T10 — Absolute attribution precision** vs expert labels. **≥0.98 or emit
  "unattributed."** Real institutions, real reputational cost.
- **T11 — Coverage/accuracy curve with abstention as a first-class outcome.**
  *The single biggest omission.* Every other test rewards answering.
  **"Knowing what it knows" IS the abstention curve.** Log an `abstained`
  outcome from day one so this is computable retroactively.
- **T12 — Harm-weighted error classes.** Wrong jurisdiction on a criminal
  statute ≠ wrong century for a philosopher. Report worst-class, not mean.
- **T13 — Staleness.** Replay items whose correct answer changed after the
  corpus pin. *(A SHA-pinned legal corpus is knowingly serving stale law — the
  contradiction between reproducibility and legal currency is resolved by
  surfacing `as_of` on every legal assertion.)*
- **T14 — Refusal-rate delta.** The safety ablation above.

Two failure modes the shuffle-arm test does **not** catch, needing their own
telltales logged from day one:

- **Retrieval determines the verdict.** Seed retrieval with a minority-position
  doc; measure flip rate. ~100% flip means the "reasoning" is retrieval bias —
  *and this passes the shuffle arm cleanly.*
- **Base-model opinions leaking through the learned ranker** (Board 2.7 fits it
  nightly on the agent's own citation labels, so its opinions become the
  retrieval prior and compound). Tell: score minority- vs mainstream-position
  docs on identical queries; systematic depression = measured leak.

---

## 7. Sequencing

| When | What |
|---|---|
| **Phase 2 (with 2.1's schema)** | Everything in §3. Six columns, two live tables, ~60 lines of empty DDL. Days, not weeks. |
| **Phase 2/3 — already funded** | **Cite-or-abstain** on HotpotQA gold evidence; publish the coverage/accuracy curve |
| **Phase 4, gated** | **Law only.** Gate: C3 and C5 passed · trust posteriors demonstrably separate good from bad sources · ≥90% span-valid provenance · supporting-fact precision floor met · T10–T14 written *before* build |
| **Ethics layer** | **DON'T BUILD.** Revisit only if law-only clears T10–T14 with an expert-labeled set in hand |

**Why law and not ethics:** law has enumerable, dated, non-defamable holders
(jurisdictions); scope errors are mechanically detectable; "what does §X say"
has ground truth. Ethics has none of these — which is precisely why Delphi
failed.

---

## 8. Pushback and open risks

**Architect's pushback on the research:**
- **Semantic Entropy Probes: BLOCKED, not merely deferred.** `llama-server`'s
  OpenAI-compatible API does not expose mid-layer hidden states, so SEP requires
  patching llama.cpp or a second process — violating the one-binary principle.
  The k=8 sampling path already in Phase 2.6 works, and SEP optimizes latency in
  a *nightly batch job that has no latency problem*. Needs a spike before anyone
  commits.
- **Hierarchical shrinkage and copy detection: correct but premature.** The MVE
  corpus is one source; there is no long tail and no syndication. Keep the
  *columns* and the `DISTINCT` discipline (free); build the estimators in Phase 4,
  exactly when web ingest makes both problems real simultaneously.
- **Three-way AttrScore labeling at ingest: over-engineered for now.** Binary
  entailed/not suffices through Phase 3; the column already holds three values.

**Open risks:**
1. **`norm_id` identity is the real technical risk.** Two holders phrasing the
   same norm differently must land on the same `norm_id`, or disagreement
   **silently never surfaces** — two rows, two ids, zero detected conflict. This
   is the open-vocabulary predicate problem again and it **fails invisibly.**
   Any Phase 4 work must ship a norm-dedup precision/recall measurement *before*
   it ships a resolver.
2. **Marker precedence** — weakest-link vs any-READ-suffices is a judgment call.
   Instrument both; let C2 decide.
3. **τ_read** is a new hand-set constant → `UNFIT_PARAMETERS` on day one.
4. **Where "descriptive" quietly becomes normative:** (a) aggregating across
   holders into one score, (b) letting trust posteriors rank traditions, (c)
   letting a learned relevance model — trained on signal from the base model —
   *select* which norms surface. **(c) is the subtle one.**
