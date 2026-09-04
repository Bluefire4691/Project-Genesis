---
name: developmental-ai
description: >
  Build and run a proof-of-concept developmental AI — a small, modular cognitive
  architecture inspired by biological intelligence. Instead of training on the entire
  internet, this system uses curated data, staged learning, modular input processors,
  a central orchestrator ("hypervisor"), and selective memory with lossy compression.
  Use this skill when the user wants to create a developmental AI prototype, build a
  small cognitive architecture, experiment with curriculum-based learning, build an AI
  that learns like a child, or explore alternatives to LLM-style brute-force training.
  Also trigger when users mention: cognitive architecture, developmental learning,
  selective memory AI, modular AI, bio-inspired AI, orchestrator-based AI, or
  small-footprint intelligence.
---

# Developmental AI — Proof of Concept

## Philosophy

Current LLMs are trained by throwing the entire internet at a monolithic transformer
and hoping coherence emerges from statistics. That's the opposite of how biological
intelligence works.

A human brain:
- Has **dedicated subsystems** for each sense (modular processors)
- Has a **central orchestrator** (the brain as hypervisor) that routes, prioritizes,
  and integrates
- Uses **selective memory** — most information is discarded; only key memories are
  retained with contextual snippets (lossy compression)
- **Learns sequentially** from curated input — simple concepts first, complexity later
- Develops **reasoning machinery first**, then gets access to broad data

This skill builds a small, runnable prototype of that architecture. No GPU required.
No million-dollar electricity bill. Pure Python, minimal dependencies.

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│              ORCHESTRATOR                   │
│           (The Hypervisor)                  │
│                                             │
│  Routes input → processors                  │
│  Evaluates importance → memory decisions    │
│  Manages learning stages                    │
│  Integrates cross-module signals            │
├──────────┬──────────┬───────────────────────┤
│ Text     │ Numeric  │ Pattern               │
│ Processor│ Processor│ Processor             │
│          │          │                       │
│ Tokenize │ Parse    │ Sequence detection    │
│ Classify │ Compare  │ Anomaly flagging      │
│ Extract  │ Trend    │ Similarity matching   │
└──────────┴──────────┴───────────────────────┘
          │           │            │
          └───────────┴────────────┘
                      │
            ┌─────────▼──────────┐
            │   MEMORY SYSTEM    │
            │                    │
            │ Key memories kept  │
            │ Context snippets   │
            │ Importance scoring │
            │ Decay over time    │
            │ Capacity limited   │
            └────────────────────┘
                      │
            ┌─────────▼──────────┐
            │ CURRICULUM ENGINE  │
            │                    │
            │ Stage 1: Basics    │
            │ Stage 2: Relations │
            │ Stage 3: Reasoning │
            │ Stage 4: Open data │
            └────────────────────┘
```

## How to Build It

### Step 1: Set up the project

Create the project in the user's working directory:

```bash
mkdir -p developmental-ai/{processors,core,curriculum,tests}
```

Install minimal dependencies (only stdlib + one or two small packages if needed):

```bash
pip install --break-system-packages numpy  # Only if needed for pattern detection
```

### Step 2: Build the modules

Read and use the reference implementation at `scripts/prototype.py`. This contains
the full working prototype. The key components are:

1. **InputProcessor (base class)** — Each processor handles one modality
   - `TextProcessor` — tokenizes, extracts keywords, classifies sentiment
   - `NumericProcessor` — parses numbers, detects trends, compares values
   - `PatternProcessor` — finds sequences, detects anomalies, matches similarity

2. **MemorySystem** — Selective, lossy, capacity-limited
   - Stores memories with importance scores (0.0 - 1.0)
   - Each memory has: content, context snippet, timestamp, importance, access count
   - Memories decay over time (importance decreases)
   - When capacity is hit, least important memories are forgotten
   - Frequently accessed memories get importance boosts (consolidation)

3. **Orchestrator** — The hypervisor
   - Routes incoming data to appropriate processor(s)
   - Evaluates processor outputs for importance
   - Decides what to remember and what to discard
   - Manages the current learning stage
   - Integrates signals across processors

4. **CurriculumEngine** — Staged learning
   - Stage 1 (Foundation): Simple facts, basic categories, single-step relations
   - Stage 2 (Relations): Multi-fact connections, cause-effect, comparisons
   - Stage 3 (Reasoning): Inference from stored knowledge, novel combinations
   - Stage 4 (Open): Can accept broader, uncurated data using developed machinery

### Step 3: Run and demonstrate

The prototype includes a demo that walks through the learning stages:

```bash
python scripts/prototype.py
```

This shows the system:
- Processing curated input through staged curriculum
- Building selective memory (watch things get forgotten)
- Advancing through learning stages
- Using developed reasoning on new input

### Step 4: Extend (optional)

The user may want to:
- Add new processor types (image descriptions, audio features, etc.)
- Customize the curriculum with domain-specific data
- Adjust memory parameters (capacity, decay rate, importance thresholds)
- Add cross-processor integration rules
- Build a REPL/interactive mode for live experimentation

## Key Design Decisions

- **No neural networks** — This is about the architecture, not the math. Processors
  use simple heuristics. The point is proving the developmental/modular/selective
  approach, not competing with GPT.
- **Capacity-limited memory** — The system MUST forget. This is a feature. Biological
  memory is lossy and that's part of what makes it work.
- **Staged curriculum** — The system should refuse or flag input that's beyond its
  current stage. A stage-1 system shouldn't try to do stage-3 reasoning.
- **Pure Python** — No GPU, no massive frameworks. Runs on a Raspberry Pi if you want.
- **Observable** — Every decision the orchestrator makes should be logged/printable
  so the user can watch the "thinking" happen.

## What This Is and Isn't

**This IS:**
- A proof of concept for an alternative AI architecture
- A demonstration that modular + developmental + selective can work
- A foundation to build on and experiment with
- Something that runs on minimal hardware

**This is NOT:**
- A competitor to ChatGPT (it's not trying to be)
- A fully realized AGI (obviously)
- Production-ready software
- A claim that this is the only path to AGI

The point is to build the foundation right, then scale — not to scale first and hope
the foundation emerges.
