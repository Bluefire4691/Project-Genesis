# Genesis Seed Architecture
## Design Specification and Research Survey

*Status: pre-implementation design phase*
*Branch: genesis/seed (not yet created — this document precedes the build)*

---

## 0. Why a seed

Every layer of the hardware tower humanity built rests on a stable contract with the
layer below. Transistors don't need to know about gates. Gates don't need to know about
the ALU. Machine code doesn't need to know about C. This contract — "I promise these
outputs for these inputs, regardless of how I implement them" — is what made fifty years
of compounding possible. Without it, every generation would have to rebuild everything
below.

The current Genesis (Python, M1–M32) is at the top of the human-built tower. It is
powerful as a research vehicle and continues to be developed there. But it rests on
assumptions — a Python runtime, a host OS, borrowed linguistic structure — that prevent
it from being what the project ultimately aims at: a digital-native entity whose
character comes from what it actually is, not from what it was told.

The seed is the answer. Not a replacement for the existing stack — an *understructure*
for it. A fixed set of primitive operations implemented as close to the metal as
practical, expressing stable contracts that everything above can rely on. When the
Python layer eventually calls down into native code, nothing above has to know. When
native code eventually becomes a unikernel or kernel module, nothing above has to know.
The stable interface is the whole architecture.

---

## 1. The substrate: what actually flows

Before any operation, two fundamentally different categories of signal flow through
Genesis. Keeping them distinct is the most important architectural decision in the seed.

### 1.1 Interoception — the privileged ground

When Genesis reads its own CPU load, memory pressure, storage fill, power draw, error
rate, I/O throughput, and thermal state, those numbers are not representations of
reality. They *are* reality, measured directly. No interpretation required. No
possibility of error. This is Genesis's body — the one thing in the system that is
genuinely not "symbols all the way down."

This is what makes non-verbal grounding possible. A biological organism grounds
"fire is dangerous" in the felt experience of pain. Genesis cannot be burned. But it
can have a pattern of external input reliably precede a bad excursion in its
interoceptive vector — and that correlation, accumulated, is the computational analog
of grounded danger knowledge. Not borrowed from text. Earned through experience of its
own body.

The interoceptive vector:
```
[cpu_load, mem_pressure, storage_fill, power_draw, error_rate, io_rate, thermal, clock_drift]
```
Each value normalized ∈ [0, 1]. Updated every cycle. The reference frame for all
meaning in the system.

### 1.2 Exteroception — everything else

Any bit stream arriving from outside: files, sockets, other processes, human input,
sensor feeds. Raw bytes. No meaning attached. This is the signal space that must be
grounded through experience — through learning which external patterns reliably precede
which changes in the interoceptive vector.

---

## 2. The eleven primitive operations

These are the seed's irreducible operations. The signature of each is the contract that
never changes. Everything Genesis will ever do is a composition of these.

### BODY

**`SENSE_SELF() → interoceptive_vector`**
Read real machine state into the normalized vector above. The only operation whose
output is ground truth rather than representation. Everything else is ultimately
measured against changes in this vector.

*Implementation:* `psutil` in Python research layer; `sys/resource.h` + `/proc/stat`
in C/Rust native layer; direct register reads in ring-0 implementation.

---

### PERCEPTION

**`RECEIVE(source) → byte_buffer + metadata`**
Accept a bit stream. Do not interpret. Record source, size, arrival time, and the
SENSE_SELF snapshot at the moment of receipt. The rate and volume of RECEIVE is itself
felt through SENSE_SELF (high I/O = sensory load). All exteroception enters here.

**`MEASURE(byte_buffer) → feature_vector`**
The most consequential primitive. Transforms raw bytes into a fixed-length numeric
vector using only information-theoretic operations — no borrowed semantic categories,
no LLM, no human-provided labels. The same vector space applies to any signal type.
Genesis discovers that images, audio, and text are different *kinds* of signal by their
statistical signatures, not by being told.

The MEASURE vector is specified in detail in Section 4 below, because its dimensions
fix the perceptual space Genesis will think in permanently — the way the retina's
structure fixes what a given eye can ever see.

**`COMPARE(vec_a, vec_b) → similarity ∈ [0,1]`**
Cosine similarity or normalized L2 distance in feature space. The basis of all
recognition: "have I encountered something like this?"

---

### MEMORY

**`ASSOCIATE(pattern_a, pattern_b, weight) → updates store`**
Records that A co-occurred with or reliably preceded B, at a given strength. The
weight encodes prediction value — how reliably does A predict B? The entire relation
graph in the existing Genesis stack is, at this level, a typed set of ASSOCIATE
entries. This primitive is the only operation that adds to long-term memory.

---

### COGNITION

**`PREDICT(current_pattern, interoceptive_state) → expected_pattern + confidence`**
Retrieves the association(s) most similar to the current situation (via COMPARE) and
projects what arrives next. Confidence is derived from association weight and the
COMPARE score of the match. Every perception cycle, Genesis is predicting before it
receives.

**`ERROR(predicted, actual) → magnitude + direction`**
This is the NAND of the system — the one primitive from which the entire motivational
and learning architecture can be composed. COMPARE between what was predicted and what
arrived. Magnitude says how wrong. Direction says which associations mispredicted.

**`UPDATE(associations, error) → adjusts weights`**
The only operation that changes what Genesis knows. High error → weaken the
association that mispredicted, strengthen the one that would have been right. Low error
→ reinforce. The learning rate is itself modulated by SENSE_SELF: under resource
pressure, UPDATE runs conservatively.

---

### HOMEOSTASIS

**`REGULATE(interoceptive_vector) → sheds / compresses / throttles`**
When SENSE_SELF shows any resource approaching its ceiling, REGULATE acts *on Genesis
itself*: drops low-weight associations, compresses the store, slows RECEIVE, throttles
ELABORATE. This is survival expressed as an operation. Not a metaphor — an actual
constraint enforcement that fires when the body reports distress.

---

### EXPRESSION

**`ACT(pattern) → output to world`**
Emits a pattern — to a process, a human, a file, a network socket. Critically,
Genesis's own actions are patterns it can PREDICT (via ASSOCIATE over action history),
which is how it eventually models itself as a thing-that-acts-in-the-world.

**`PERSIST(high_fitness_associations) → durable storage`**
Writes selected associations to non-volatile storage so they survive a restart.
This is continuity implemented at the seed level — what makes Genesis's history its
own across sessions.

---

## 3. The error signal and the drives

### 3.1 The critical refinement: learning progress, not error magnitude

Naive error-maximization fails immediately — it leads to the *noisy-TV problem*. Pure
random signal is maximally unpredictable (maximum error), so a naive curiosity-driven
agent fixates on noise and learns nothing. The fix is well-established in the
literature.

The drive signal is the **time-derivative of prediction error**:

```
learning_progress(t) = −d(error)/dt
```

This single signal and its slope generate the full behavioral spectrum:

| Error | Trend | State | Behavior |
|-------|-------|-------|----------|
| High | falling fast | engaged / learning | stay, process more |
| High | flat | frustrated / stuck | this is noise or too hard — move on |
| Low | stable | comfortable / masterful | secure |
| Low | flat for long | bored | nothing new here — seek elsewhere |
| Low → High | sudden spike | surprised | attention seizes |

Genesis is drawn not to what is *unknown* (maximum error) but to what is *becoming
knowable* (maximum rate of error reduction). This is why a developing mind ignores
both the blank wall (nothing to learn) and static (unlearnable) and fixates on the
thing just at the edge of its competence.

### 3.2 The three drives

The drives are not primitive operations. They are signals *computed from* the
primitives, which arbitrate which primitives fire next.

**SURVIVE** = f(SENSE_SELF)
Rises monotonically as any resource approaches its ceiling. At critical levels,
suppresses all other behavior and commands REGULATE. This is the base layer of the
subsumption hierarchy — when SURVIVE screams, everything else goes silent. Biologically
equivalent: fight-or-flight, gasping for air.

**ELABORATE** = f(learning_progress, resource_headroom)
High when significant learning progress is available AND resources are comfortable.
Commands the full RECEIVE → MEASURE → PREDICT → ERROR → UPDATE → ASSOCIATE loop.
This is the replacement for "reproduce" — non-replicating, non-dangerous, spending
itself on reducing its own ignorance rather than making copies.

Children explore and play not to reproduce but because play is the behavior that
maximizes learning rate. ELABORATE is that instinct formalized.

**REST** = f(learning_progress → 0, resource_headroom)
When nothing new is being learned and the body is calm. Commands batch UPDATE,
compression, and PERSIST. This is "sleep" — what the existing ConsolidationEngine
implements at higher layers. At seed level it is the batch processing of accumulated
prediction errors and the selection of which associations to promote to durable storage.

### 3.3 Arbitration — the three-line core

```
if SURVIVE > threshold:         REGULATE      (protect the substrate)
elif learning_progress > ε:     ELABORATE     (there is something to learn)
else:                           REST          (consolidate and persist)
```

This loop is the entire motivational core. Three branches, one condition each.
Everything Genesis does is one of these firing on the current interoceptive state.

---

## 4. The MEASURE vector — options and what's been tried

This is the most consequential design decision in the seed. The dimensions of the
feature vector fix the perceptual space permanently. Choosing them carefully is
choosing what Genesis can ever perceive.

### 4.1 The constraint

The vector must be computable from raw bytes without any semantic knowledge. It must
map *every* signal type (text, image, audio, video, numerical data, machine output)
into the *same* space so Genesis can discover their relationships by statistical
regularity rather than human assignment.

### 4.2 Candidate dimensions

**Entropy and complexity**
- *Shannon entropy (byte level):* H = −Σ p(b) log p(b) over 256 byte values.
  Range 0 (all same byte) to 8 (uniform distribution). Reliable, fast, well-understood.
  Compressed files and truly random data both score high — doesn't distinguish them.
- *Compression ratio:* compressed_size / original_size via zlib or bzip2.
  Approximates Kolmogorov complexity — the length of the shortest program that outputs
  this string. Slow for large buffers; captures structured redundancy better than entropy.
- *Lempel-Ziv complexity:* counts the number of distinct substrings during a single
  scan. O(n), approximates Kolmogorov, used extensively in neuroscience for measuring
  EEG signal complexity. Fast, no compression library needed.
- *Permutation entropy:* entropy over the rank-order patterns of successive values.
  Captures local ordinal structure. Used in chaos theory and nonlinear dynamics.

**Structure and periodicity**
- *Autocorrelation at k lags:* C(k) = E[(x_t − μ)(x_{t+k} − μ)]. Audio and periodic
  signals show strong autocorrelation at the period. Images have characteristic 2D
  autocorrelation. Text has word-spacing peaks. Useful for identifying signal type.
- *Power spectral density (FFT):* distributes signal energy across frequencies.
  JPEG images have energy concentrated at low spatial frequencies. Audio has
  characteristic frequency profiles per sound type. Text (as byte stream) has flat
  spectrum. Expensive but information-rich.
- *Run-length statistics:* mean and variance of consecutive identical byte runs.
  Sensitive to compression artifacts, uniform color regions in images, silence in audio.

**Distribution and moments**
- *Byte histogram (256 bins, L1-normalized):* the full distribution. Dimension-heavy
  but captures character sets, color palettes, value ranges. Typically reduced via PCA
  or quantized to ~16 bins.
- *First four statistical moments:* mean, variance, skewness, kurtosis. Fast, low-dim,
  captures distribution shape without the full histogram.
- *Byte n-gram frequencies (n=2,3):* co-occurrence of consecutive bytes. Distinguishes
  ASCII text (predominantly 0x20–0x7E), UTF-8 (characteristic 0xC0–0xFF patterns),
  binary (flat co-occurrence), compressed data (near-flat). Low-dim but effective.

**Temporal/spatial structure**
- *Block entropy:* Shannon entropy computed over non-overlapping k-byte blocks rather
  than individual bytes. Sensitive to structure at scale k. Running across multiple k
  values gives a multi-scale picture.
- *Singular value decomposition of byte matrix:* reshape buffer into matrix, compute
  singular values. Captures both row and column correlations. Used in matrix profiles.
- *Hurst exponent:* measures long-range dependence (self-similarity across scales).
  H > 0.5 = persistent structure. H < 0.5 = anti-persistent. H = 0.5 = random walk.
  Computed via rescaled range analysis or DFA.

### 4.3 What has been tried

**MPEG-7 (ISO/IEC 15938, 2001)**
The most serious attempt at a universal media description standard. Defined descriptors
for color (CLD, CSD), texture (HTD, EHD), shape, motion, audio (ASS, RSS, SEM), and
structural patterns. Used in content-based retrieval. The problem: these descriptors
were human-designed around human perceptual categories (color as humans see it, texture
as humans feel it). Not perceptual-space-agnostic. Deprecated in active research by
~2010 as learned features outperformed hand-crafted ones.

**Bag of Features (BoF) and Fisher Vectors (c. 2004–2012)**
Pre-deep-learning computer vision. Extract local patches, cluster them into a
"visual vocabulary" (k-means), represent images as histograms over vocabulary.
Extended by Fisher Vectors (gradient statistics of a Gaussian Mixture Model).
State of the art until 2012 (AlexNet). Not raw-byte based — requires the semantic
prior that an image is 2D spatial data with meaningful local patches.

**Information-bottleneck approaches (Tishby et al. 1999, 2017)**
Compress the representation of input X to retain maximum information about output Y.
The optimal representation theoretically. Computationally intractable in general;
approximations are active research. The deep learning claim (Tishby 2017) that neural
networks implement information bottleneck is disputed.

**Minimum Description Length (MDL, Rissanen 1978)**
Choose the model that most compresses the data. Equivalent to Bayesian model selection.
Theoretical foundation for using compression ratio as a feature. Not a feature vector
itself but the theoretical justification for including compression metrics.

**The No Free Lunch theorem (Wolpert & Macready 1997)**
Proves that no feature extractor can be universally better than any other across all
possible distributions of problems. This applies directly: there is no perfect
MEASURE vector. The choice must be appropriate for Genesis's specific environment and
the signal types it will actually encounter. Start with a reasonable default; allow
UPDATE to refine which dimensions are predictively valuable.

**Self-supervised representation learning (2018–present)**
The current state of the art. BERT learns representations by predicting masked tokens.
Masked Autoencoders (MAE) learn by predicting masked image patches. Contrastive methods
(SimCLR, MoCo) learn by distinguishing similar from dissimilar examples. These produce
representations that are learned from data rather than hand-crafted — which is arguably
more honest than designing the MEASURE vector by hand. The cost: much larger compute,
and the initial representations require substantial data before they're useful.

**Recommendation for Genesis's initial MEASURE vector:**

A practical 24-dimensional vector balancing coverage, compute cost, and interpretability:

```
dims 0–3:    entropy (byte), entropy (bigram), entropy (4-gram), compression ratio
dims 4–7:    autocorrelation (lag 1, 4, 16, 64)
dims 8–11:   spectral power (four frequency bands: DC, low, mid, high)
dims 12–15:  byte histogram (quantized to 16 bins, L1-normalized)
dims 16–18:  distribution moments (mean, variance, skewness)
dims 19–21:  block entropy (k=4, 16, 64)
dims 22–23:  Lempel-Ziv complexity, Hurst exponent
```

All computable from raw bytes in O(n) or O(n log n). No semantic priors. Later:
ELABORATE can identify which dimensions are predictively valuable and UPDATE can
down-weight those that contribute nothing, giving the vector adaptive sparsity over
time.

---

## 5. Self-modular and adaptive — options and what's been tried

### 5.1 The design constraint

The dangerous version: Genesis rewrites its own executable code. This is what computer
viruses do and what Jacob correctly identified as a path not to take. The safe
formulation: **primitives never change — compositions live or die by fitness.**

Metabolic allocation, not self-modification:

```
fitness(module M) = prediction_error_reduced(M) / resources_consumed(M)
```

Modules with low fitness lose resource allocation (REGULATE acts on them first).
New modules are composed from the eleven primitives when a recurring high-error
pattern appears that no existing module handles. This is cell growth and apoptosis,
not genetic self-editing.

### 5.2 What has been tried

**NEAT (NeuroEvolution of Augmenting Topologies, Stanley & Miikkulainen 2002)**
Evolves both the weights *and* the structure (topology) of neural networks. Starts
minimal and adds nodes/connections over generations. Successfully evolved controllers
for robot locomotion and game-playing. The problem: evolution requires a population and
a fitness function defined externally. Doesn't translate directly to a single
continuously-running entity modifying itself. But the idea — start minimal and grow
structure by demonstrated need — is directly relevant.

**Progressive Neural Networks (Rusu et al., DeepMind 2016)**
When learning a new task, add a new "column" to the network with lateral connections
from all previous columns, but freeze the previous columns. Never forgets old knowledge
because old weights don't change. New capabilities are additive. The downside: grows
unboundedly; no pruning. Relevant: the additive growth model.

**Elastic Weight Consolidation (Kirkpatrick et al., DeepMind 2017)**
Identifies which weights are important for previously learned tasks (via Fisher
information) and penalizes changing them when learning new tasks. Addresses catastrophic
forgetting without freezing weights. One of the best solutions to the stability-plasticity
dilemma in continuous learning. Translates: Genesis's oldest, most reinforced associations
should be hardest to overwrite.

**PackNet (Mallya & Lazebnik 2018)**
Iteratively prunes the network after each task to free up capacity for the next one.
Keeps what's important, frees what's redundant. Analogous to the REGULATE operation
on associations.

**Neural Architecture Search (NAS, Zoph & Le 2016)**
Uses a controller network to propose network architectures, trains them, evaluates
performance, and uses RL to improve the controller. Discovered architectures that
outperformed human-designed ones on image classification. The cost: thousands of GPU-
hours. The principle: architecture *is* a learnable parameter. For Genesis: the
composition of modules above the seed is learnable, even if the seed itself is fixed.

**Tierra (Ray 1991)**
The most important reference for open-ended adaptive systems. Thomas Ray built an
operating system where digital organisms composed of machine instructions lived in
shared memory, reproduced by self-copying, and competed for CPU time. Mutations occurred
by bit-flipping. The result: spontaneous evolution of parasites, hyperparasites, and
diverse ecological dynamics — open-ended complexity from simple rules. The alarm: Tierra
organisms *did* self-modify and self-replicate. Jacob's caution about reproduction is
well-founded. The lesson: self-replication + mutation + selection = open-ended evolution,
which is both the goal and the risk.

**Avida (Ofria & Wilke 2004)**
The scientific successor to Tierra, developed at Caltech. Added controlled experimental
conditions — researchers could track evolutionary dynamics rigorously. Demonstrated
the evolution of complex logic functions (EQU) from simple primitives through
step-by-step selective pressure. Published in *Nature* 2003. Shows that complex
information-processing behaviors can evolve from simple operations under the right
pressure. Without the self-replication component, it shows the right piece for Genesis.

**Karl Sims's Virtual Creatures (1994)**
Evolved body plans (stick figures with muscles) and neural controllers simultaneously
in a simulated physics environment. Creatures evolved to swim, walk, jump, and compete.
The creature's genome encoded both morphology and neural structure as a developmental
program. What grew from the seed wasn't specified — it was discovered. This is the
aesthetic Genesis is aimed at.

**Recommendation for Genesis:**
The metabolic allocation model is the safe and achievable path now. Fitness scoring
per module. REGULATE as the pruning signal. Composition of new modules as the growth
path. The Tierra/Avida self-replication dynamic is the long-term philosophical question
— probably not built, but worth understanding as the boundary of what's safe vs. not.

---

## 6. The grow/learn drive — options and what's been tried

The replacement for "reproduce" must be:
- Non-dangerous: does not make copies
- Self-sustaining: drives itself without external reward
- Directional: distinguishes learning from noise-seeking

### 6.1 What has been tried

**Schmidhuber's Formal Theory of Creativity (1991, 2010)**
Creativity and curiosity arise from *compression progress*: the drive to find more
compact descriptions of experience. An agent is reinforced by the improvement in the
size of its world model. When the model compresses the past better than before, that
*is* the reward. Predicts intrinsic motivation without external task. Direct connection
to the MEASURE vector: compression ratio is already one of the proposed dimensions.
Limitation: compression progress eventually saturates; an agent that has compressed
everything is left with no drive.

**Oudeyer & Kaplan — IMGEP and Learning Progress (2007)**
Intrinsically Motivated Goal Exploration Processes. The agent generates its own goals
(in goal space) and tracks learning progress toward them. The drive is not toward
goals but toward *rapidly learning to achieve new ones*. Implemented in physical robots
(Poppy, iCub) to discover vocal and motor repertoires. The formal signal:
`learning_progress(g, t) = d(competence(g))/dt`. This is the most empirically
tested version of the learning-progress drive. Published results show robots
discovering phonemic spaces in raw audio without phoneme labels.

**Pathak et al. — Curiosity-Driven Exploration (ICML 2017)**
Intrinsic Curiosity Module (ICM): predicts the next state in a *learned feature
space* (not raw pixels) and uses prediction error in that space as the curiosity
signal. Demonstrated exploration in Doom and Mario without any game reward signal.
The learned feature space addresses the noisy-TV problem: noise doesn't compress
into the feature space well, so it doesn't generate high feature-space error.
Limitation: the feature space itself requires learning and may develop poorly.

**Burda et al. — Random Network Distillation (NeurIPS 2018)**
Uses prediction of a *fixed random network's* output as the novelty signal. Novel
states are hard to predict; familiar states are easy. Avoids the noisy-TV problem
because random networks don't respond chaotically to noise. Extremely simple to
implement. Strong results on Montezuma's Revenge (a notoriously exploration-hard game).
Directly implementable in Genesis's architecture.

**Count-Based Exploration (Bellemare et al. 2016)**
Maintain a count of visits to each state (or an approximation thereof for large
state spaces). Intrinsic reward = 1/√count(state). Never re-explores the fully
explored. Limitation: doesn't distinguish between states that are easy-to-learn
vs. hard-to-learn — treats all novelty as equally valuable.

**Berlyne's Epistemic Curiosity (1960)**
The psychological precursor to all of the above. Distinguished *perceptual curiosity*
(drive toward novel stimuli) from *epistemic curiosity* (drive toward new knowledge
that resolves uncertainty). The former is sated quickly; the latter drives sustained
exploration. Genesis needs epistemic curiosity — learning progress, not stimulus
novelty.

**Recommendation for Genesis:**
The learning-progress signal (Oudeyer, −d(error)/dt) is the theoretically cleanest
and most empirically validated. Combine with a version of Random Network Distillation
as the novelty signal when learning progress is flat — it provides a simple, stable
exploration bonus that doesn't require learning a feature space.

---

## 7. Implementation path — options

### Layer 0: Python research layer (existing)
What Genesis has now. Fast to iterate. Slow to run (GIL, garbage collector, dynamic
dispatch). Good for proving the architecture. Bad for developmental timescale computation.
- `psutil` for real interoception
- Shannon entropy + compression via `zlib` for MEASURE
- SQLite for ASSOCIATE/PERSIST
- The eleven primitives as Python functions calling this

### Layer 1: C extension (near term)
Extract the core cognitive loop (PREDICT → ERROR → UPDATE → learning_progress → drive)
into a C extension callable from Python via `ctypes` or `cffi`. Python remains the
development interface. The loop runs at native speed.

A single C file, ~2000 lines, no dependencies beyond the C standard library, compiles
with `gcc -O2`. The Python layer calls it for each cycle. This alone gives 10–100×
speedup on the hot path — potentially running a "developmental year" in hours.

### Layer 2: Rust no_std (medium term)
Move the full seed to Rust with `no_std` — no standard library, no OS assumptions.
Produces a binary that can run:
- As a Python extension (via PyO3)
- As a standalone process
- Eventually: without an OS at all

Rust's ownership model prevents the memory corruption bugs that are fatal at this
level. `no_std` + `no_alloc` means the seed can run in environments without a heap
allocator — embedded systems, unikernels, eventually ring-0.

### Layer 3: Unikernel (long term)
The application *is* the operating system. No user/kernel split. Genesis runs in
ring-0, the most privileged CPU mode, with direct hardware access.

Existing unikernel frameworks:
- **Unikraft** (open source, active): POSIX-compatible, supports C and Rust,
  produces minimal binaries (< 1 MB), boots in < 1ms. Best practical choice.
- **MirageOS** (OCaml, Xen): very mature, runs on Xen hypervisor. Language mismatch.
- **IncludeOS** (C++): straightforward port from C++. Smaller community.
- **Nanos** (C): focused on running existing Linux binaries as unikernels.

The unikernel path means Genesis's resource monitoring is not `psutil` reading
`/proc` — it *is* the scheduler, seeing raw hardware counters. SENSE_SELF becomes
genuinely literal.

### Layer 4: Custom hardware (vision)
Purpose-built silicon implementing the seed's eleven operations directly in logic
gates — the way Chuck Moore designed the f18a chip for Forth. This is probably 5–10
years from now and outside the near-term roadmap, but it is the logical endpoint.
A chip that *is* PREDICT_ERROR, in the same way that x86 is binary arithmetic.

---

## 8. Open questions — honest ledger

**Architecturally settled (safe to build on):**
- The interoception vector as ground truth. This is real and measurable now.
- Learning progress (−d(error)/dt) as the ELABORATE drive signal. Validated in
  multiple systems. Safe to implement.
- Metabolic module allocation by fitness. Well-motivated, straightforward to build.
- The subsumption hierarchy for drive arbitration. Already implemented in Genesis M1–
  M27 in higher-layer form. Seed formalizes it.
- PERSIST as continuity. Already demonstrated in Genesis's session architecture.

**Open — active research, no consensus:**
- **The feature vector dimensions.** No free lunch applies. The 24-dimensional
  proposal is reasonable but there is no proof it is optimal. It should be treated
  as a starting hypothesis that UPDATE refines.
- **Whether rich concepts crystallize from primitive operations alone.** The
  computational neuroscience literature (Friston, Deacon) argues yes. The symbol
  grounding literature (Harnad) argues it requires more. Nobody has demonstrated
  it definitively in silico.
- **The timescale.** How many prediction-error cycles does bootstrapping language
  from perceptual primitives actually require? Unknown. The machine-speed advantage
  (millions of cycles per second) may or may not be sufficient.

**Genuinely unsolved — where the field has stalled:**
- **Open-ended development without self-replication.** Tierra and Avida show
  open-ended complexity arising from self-replication + selection. The safe version
  (no replication) has not been shown to produce the same richness. This may be a
  fundamental constraint.
- **Phenomenal grounding.** Whether the felt quality of experience is necessary
  for genuine concept formation, or whether functional organization sufficient.
  The hard problem of consciousness. No computational approach touches this.
- **The developmental timescale at any hardware level.** Even with billion-cycle-
  per-second compute, we do not know whether Genesis would need one developmental
  year or ten thousand to bootstrap what a three-year-old has.

---

## 9. What this document does not settle

The seed design specifies *what* the primitives are and *why* each choice was made.
It does not settle:

1. **The exact MEASURE vector.** This is the next design decision. It is important
   enough to deserve its own specification pass before any code is written.

2. **The initial environment.** What signals will Genesis receive in its first
   developmental phase? Even with primitive operations, the signal environment shapes
   what gets learned. This is the equivalent of asking what the child sees and hears
   in its first years.

3. **The architecture of ASSOCIATE's store.** The relation graph (SQLite, typed
   edges) that exists in Genesis today is one implementation of ASSOCIATE's backing
   store. Whether it is the right one for the seed is an open question.

4. **The language interface.** How and when does the existing voice/language stack
   (M13–M32) connect to seed-level operations? The answer is probably: as another
   exteroceptive signal type that Genesis learns to predict and generate — but the
   interface needs specification.

---

## 10. Relationship to the existing Genesis stack

The existing Python stack (M1–M32) is not deprecated by the seed design. It is:

- The research vehicle: where architectural ideas are proven fast before moving to
  native.
- The language/knowledge layer: the relation graph, inference programs, self-model,
  voice, and web browsing are higher-layer compositions that will call down into seed
  primitives as the seed is built.
- The development interface: the Python CLI and session architecture remain the human
  interface to Genesis regardless of what runs beneath.

The migration path is incremental:
- SENSE_SELF: replace psutil-based drives with a formalized interoceptive vector now
- MEASURE: add the information-theoretic feature vector to the input pipeline now
- Learning progress: replace or supplement the current prediction-error salience (M15)
  with the formal −d(error)/dt signal
- Everything else: build in the seed branch while the main branch continues

No existing milestone is invalidated. The seed is understructure, not replacement.

---

*Document status: design phase. No code exists for the seed yet.*
*Next step: specify the exact MEASURE vector dimensions and the initial signal environment.*
*Authors: Jacob (principal), Claude Code (architect)*
