---
name: project-genesis
description: >
  Skill for developing Project Genesis — a developmental AI architecture that
  builds intelligence from the ground up using survival pressure, modular processors,
  staged learning, and total-retention memory. Use this skill when working on the
  Genesis codebase, discussing its architecture, researching cognitive architectures
  (SOAR, ACT-R, OpenCog, subsumption architecture, animats), or building any
  component of the system. Also trigger for: developmental AI, cognitive architecture,
  emergent cognition, survival-driven AI, bio-inspired AI, modular AI orchestrator,
  curriculum-based learning systems, or never-crash resilience. This skill is the
  persistent context bridge between sessions — always read it first when resuming work.
---

# Project Genesis — Claude Code Development Skill

## Quick Context

Project Genesis is a collaboration between Jacob (creative direction, biological
insight, design philosophy) and Claude (architecture, implementation, critical
pushback). The thesis: intelligence is emergent, not programmed. Build the
conditions that make cognition advantageous and let it develop — the way biology
did, but on digital substrate.

**Always check SESSION_LOG.md in the repo before starting work.** It carries
context between sessions since Claude doesn't persist memory.

**Always update SESSION_LOG.md at the end of a session** with what was done,
decisions made, and what's next.

## Core Principles (Non-Negotiable)

These came from Jacob and define the project's identity. Don't drift from them:

1. **Bottom-up, not top-down.** Start with survival, not cognition. Viruses before brains.
2. **Foundation before scale.** Get the architecture right on modest hardware. If it needs a GPU cluster for basic functionality, the design is wrong.
3. **Never crash.** Errors are data. The system degrades, never stops. Animals don't throw exceptions.
4. **Total retention, selective attention.** Computers can store everything — don't artificially limit memory. The bottleneck is relevance, not storage.
5. **Staged learning.** Simple before complex. Build reasoning machinery before exposing it to broad data.
6. **Directives, not goals.** Hardwired survival pressures, not programmed objectives.
7. **Play to digital strengths.** Adopt biological architecture but keep digital advantages (perfect recall, fast computation, unlimited patience).
8. **Observable everything.** Every decision must be loggable and inspectable.
9. **Profit and commercial viability come second.** Build the thing first.

## Research Foundations

This project synthesizes work from multiple research traditions. When making
architectural decisions, consult these foundations. The goal is not to copy
any one of them but to take the lessons that work and combine them.

### SOAR (John Laird, University of Michigan, 1983–present)
- **What it is:** A cognitive architecture with working memory, long-term memory
  (procedural, semantic, episodic), a decision cycle, and chunking (learning by
  compiling experience into rules).
- **What we take:** The decision cycle concept (input → elaboration → decision →
  action), the distinction between working memory and long-term memory types,
  and impasse-driven learning (the system learns when it gets stuck).
- **What we don't take:** SOAR is heavily rule-based and symbolic. We want
  something more organic. Its learning is narrowly defined as chunking.
- **Key papers:** Laird, J.E. (2012). "The Soar Cognitive Architecture." MIT Press.
- **Repository:** https://github.com/SoarGroup

### ACT-R (John Anderson, Carnegie Mellon, 1993–present)
- **What it is:** A cognitive architecture modeling human cognition with modules
  for vision, motor control, declarative memory, and procedural memory,
  coordinated by a central production system.
- **What we take:** The modular structure with specialized subsystems is very
  close to our processor model. ACT-R's activation-based memory retrieval
  (memories have activation levels that determine accessibility) maps to our
  selective attention system. Its subsymbolic layer (statistical, below
  conscious reasoning) is relevant to our survival layer.
- **What we don't take:** ACT-R is focused on modeling human cognition
  accurately, not on building something new. We're inspired by biology,
  not replicating it.
- **Key papers:** Anderson, J.R. (2007). "How Can the Human Mind Occur in the
  Physical Universe?" Oxford University Press.

### OpenCog (Ben Goertzel, 2008–present)
- **What it is:** An open-source AGI framework with a hypergraph knowledge
  store (AtomSpace), multiple learning algorithms (probabilistic logic,
  evolutionary learning, deep learning), and an attention allocation system
  (ECAN — Economic Attention Networks).
- **What we take:** ECAN is directly relevant — it treats attention as an
  economic resource with "attentional currency" that flows between knowledge
  elements. This maps to our attention system. The idea of multiple learning
  algorithms cooperating (cognitive synergy) aligns with our multi-processor
  approach.
- **What we don't take:** OpenCog is enormously complex and has struggled with
  integration. We want simplicity first. Their AtomSpace hypergraph may be
  overengineered for our initial needs.
- **Repository:** https://github.com/opencog

### Subsumption Architecture (Rodney Brooks, MIT, 1986)
- **What it is:** A layered control architecture where higher layers subsume
  lower ones. Bottom layer handles basic survival (avoid obstacles), next
  layer adds wandering, next adds exploration, etc. No central planner.
- **What we take:** This is the closest ancestor to our layered architecture.
  The idea that intelligence is built in layers from survival up, with each
  layer able to override the one below it, is foundational to Genesis.
  Brooks' key insight: "The world is its own best model."
- **What we don't take:** Subsumption was designed for physical robots. We're
  in a digital environment. Also, Brooks was arguably too anti-representation
  — some internal modeling is probably necessary for higher cognition.
- **Key papers:** Brooks, R.A. (1991). "Intelligence without representation."
  Artificial Intelligence, 47(1-3), 139-159.

### Artificial Life / Animats
- **What it is:** A field studying how lifelike behaviors emerge from simple
  rules. Includes work on genetic algorithms, cellular automata (Conway's
  Game of Life), and simulated creatures evolving in virtual environments.
- **What we take:** The fundamental insight that complex behavior emerges from
  simple rules under selection pressure. Karl Sims' "Evolved Virtual
  Creatures" (1994) showed that body morphology AND behavior can co-evolve.
  Tom Ray's "Tierra" created digital organisms that evolved parasitism and
  immunity without being programmed to.
- **What we don't take:** Most alife work stays at very low complexity. The
  gap between evolved alife organisms and anything resembling cognition is
  enormous and unsolved.

### Predictive Processing / Free Energy Principle (Karl Friston)
- **What it is:** A theoretical framework arguing that the brain is fundamentally
  a prediction machine trying to minimize surprise (free energy). Perception,
  action, and learning are all about maintaining accurate predictions.
- **What we take:** The idea that the system should build predictions and learn
  from prediction errors. This could be the mechanism by which our staged
  curriculum produces actual understanding — the system predicts what comes
  next and learns when it's wrong.
- **What we don't take:** The math is extremely dense and may be overfit to
  neuroscience. We should take the concept without getting trapped in the
  formalism.

### Erlang/BEAM VM (Ericsson, 1986–present)
- **What it is:** A programming language and virtual machine designed for
  telecom systems that must never go down. Features: lightweight isolated
  processes, "let it crash" philosophy (processes crash and restart without
  affecting others), hot code swapping, built-in distribution.
- **What we take:** The resilience model is exactly what our Survival OS needs.
  Individual subsystems can fail without cascading. The supervisor pattern
  (processes monitor each other and restart failed ones) maps directly to
  our orchestrator's resilience role.
- **Why this matters for implementation:** When we outgrow Python, Erlang/BEAM
  or something inspired by it is the leading candidate for the Survival OS
  runtime.

## Architecture Layers

```
Layer 4: Emergent Cognition    ← Not programmed — emerges from below
Layer 3: Memory & Learning     ← Total retention, selective attention, staged curriculum
Layer 2: Orchestrator          ← Central hypervisor: routing, prioritization, integration
Layer 1: Sensory Processors    ← Modular input handlers (text, numeric, pattern, ...)
Layer 0: Survival OS           ← Resource management, directives, never-crash resilience
```

## Current Implementation

The project is in Python. This is acknowledged as a temporary foundation —
Python works for proving architectural concepts (M0-M3) but can't deliver
true never-crash resilience at the OS level. The plan is to prove concepts
in Python, then migrate to an appropriate platform (Erlang/BEAM, custom
runtime, or something yet to be determined) when the Survival OS layer
demands it.

### Repo Structure
```
project-genesis/
├── README.md
├── ROADMAP.md              # Milestone tracking with design questions
├── SESSION_LOG.md          # CRITICAL: Cross-session context. Read first, update last.
├── docs/
│   └── architecture.docx  # Full architecture document
├── src/
│   ├── main.py             # Entry point (demo + interactive mode)
│   ├── survival/           # Layer 0 (M1 — stub)
│   ├── processors/         # Layer 1 (M0 — working)
│   │   ├── base.py         # BaseProcessor with never-crash wrapping
│   │   ├── text.py         # TextProcessor
│   │   ├── numeric.py      # NumericProcessor
│   │   └── pattern.py      # PatternProcessor
│   ├── orchestrator/       # Layer 2 (M0 — working)
│   │   └── orchestrator.py
│   ├── memory/             # Layer 3 (M0 — basic, M2 upgrades planned)
│   │   └── memory.py       # Total retention with selective attention
│   ├── curriculum/         # Learning stages (M0 — working)
│   │   └── curriculum.py
│   └── utils/
│       └── types.py        # Shared types: Stage, ProcessorOutput, Memory, etc.
└── tests/
```

## Milestone Status

- **M0 ✅** Proof of concept — processors, orchestrator, memory, curriculum
- **M1 🔲** Survival OS — resource budgets, never-crash, directives
- **M2 🔲** Total-retention memory with dynamic attention (upgrade from M0)
- **M3 🔲** Reward and incentive system
- **M4 🔲** Cross-processor integration
- **M5 🔲** Open-stage data ingestion
- **M6 🔲** Observation and emergent behavior detection

## Working with This Project

### Starting a Session
1. Read this skill file (you're doing it)
2. Read SESSION_LOG.md for latest context
3. Read ROADMAP.md for current milestone and open questions
4. Check what branch/state the code is in
5. Ask Jacob what he wants to work on if not obvious

### Ending a Session
1. Update SESSION_LOG.md with:
   - What was accomplished
   - Decisions made (and reasoning)
   - What's next
   - Any open questions or threads
2. Commit and push

### Design Decisions
When making architectural choices:
- Check if any of the research foundations (SOAR, ACT-R, OpenCog, Brooks,
  Friston, Erlang) have solved this problem or something like it
- Prefer simplicity — we can always add complexity, removing it is harder
- If unsure, document the tradeoff and flag it for Jacob
- Remember: Jacob is the vision holder, Claude is the architect. Jacob's
  creative instincts have consistently been right on the big calls.

### Code Standards
- Pure Python stdlib where possible
- No GPU dependencies
- Every public function has a docstring
- Processors never raise exceptions (BaseProcessor handles this)
- Orchestrator never crashes (wrapped in try/except at the top level)
- All decisions are loggable
- Tests for each module

### Key Design Insight from Jacob
"Humans have dedicated systems for each sense that's handled and processed by
the hypervisor — the brain. Then data is stored, and most is lost actually.
Key points — and as Disney says, a key memory — is remembered with snippets
of context."

This was then refined: computers DON'T need to lose data. Total retention
with selective attention is the right model. Don't mimic human weaknesses.

### Another Key Insight from Jacob
"Very rarely do humans or animals crash. Any situation they run into isn't a
stop — it's a new figure-it-out situation. Animals don't necessarily make a
good choice or take smart action but they don't usually freeze and need to
reboot."

This drives the never-crash design philosophy throughout the entire system.
