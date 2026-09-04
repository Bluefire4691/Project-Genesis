# Project Genesis

**A developmental AI architecture — building intelligence from the ground up.**

## The Thesis

Intelligence is not a program. It's an emergent property of a system under survival pressure. You don't code cognition — you code the conditions that make cognition advantageous.

Current AI development throws the entire internet at a monolithic neural network and hopes coherence emerges from statistics. That's the opposite of how biological intelligence actually developed. This project takes a different approach:

- **Start at the simplest level.** Viruses don't think. They replicate. Intelligence came last, not first.
- **Create survival pressure.** Give the system resource budgets, directives, and incentives. Make it *need* to get smarter.
- **Build modular subsystems.** Dedicated processors coordinated by a central orchestrator — like a brain, not a single giant model.
- **Use staged learning.** Simple concepts first, complexity later. Build reasoning machinery before exposing it to broad data.
- **Leverage digital strengths.** Total memory retention, fast computation, perfect storage. Don't mimic human weaknesses — adopt biological *architecture* with digital *advantages*.
- **Never crash.** Animals don't throw exceptions. The system degrades gracefully, always responds, always recovers.

## Architecture

```
Layer 4: Emergent Cognition    ← Not programmed — emerges from below
Layer 3: Memory & Learning     ← Total retention, selective attention, staged curriculum
Layer 2: Orchestrator          ← Central hypervisor: routing, prioritization, integration
Layer 1: Sensory Processors    ← Modular input handlers (text, numeric, pattern, ...)
Layer 0: Survival OS           ← Resource management, directives, never-crash resilience
```

Each layer provides the foundation for the one above it. Higher layers cannot exist without the lower ones being stable.

## Current Status

| Milestone | Status | Description |
|-----------|--------|-------------|
| M0 | ✅ Done | Proof-of-concept prototype — processors, orchestrator, memory, curriculum |
| M1 | 🔲 Next | Survival OS — resource budgets, never-crash design, basic directives |
| M2 | 🔲 | Total-retention memory with dynamic attention |
| M3 | 🔲 | Reward and incentive system |
| M4 | 🔲 | Cross-processor integration |
| M5 | 🔲 | Open-stage data ingestion |
| M6 | 🔲 | Observation, logging, and emergent behavior detection |

## Quick Start

```bash
# Run the proof-of-concept prototype
python src/main.py

# Run tests
python -m pytest tests/
```

No GPU required. No massive datasets. No million-dollar electricity bill. Pure Python, runs on anything.

## Project Structure

```
project-genesis/
├── README.md
├── ROADMAP.md                  # Detailed milestone tracking
├── SESSION_LOG.md              # Cross-session context for AI collaboration
├── docs/
│   └── architecture.docx      # Full architecture document
├── src/
│   ├── main.py                 # Entry point
│   ├── survival/               # Layer 0: Survival OS
│   │   ├── __init__.py
│   │   └── resource_manager.py
│   ├── processors/             # Layer 1: Sensory Processors
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── text.py
│   │   ├── numeric.py
│   │   └── pattern.py
│   ├── orchestrator/           # Layer 2: The Hypervisor
│   │   ├── __init__.py
│   │   └── orchestrator.py
│   ├── memory/                 # Layer 3: Memory & Learning
│   │   ├── __init__.py
│   │   └── memory.py
│   ├── curriculum/             # Layer 3: Staged Learning
│   │   ├── __init__.py
│   │   └── curriculum.py
│   └── utils/
│       ├── __init__.py
│       └── types.py
├── tests/
│   ├── __init__.py
│   ├── test_processors.py
│   ├── test_memory.py
│   ├── test_orchestrator.py
│   └── test_curriculum.py
└── skills/
    └── developmental-ai/       # Claude skill for this project
        ├── SKILL.md
        └── scripts/
            └── prototype.py
```

## Collaboration Model

This project is a collaboration between human creativity and AI architecture:

- **Human (Jacob):** Creative direction, conceptual framework, biological insight, design philosophy, and course correction.
- **AI (Claude):** Architecture design, implementation, technical tradeoff analysis, and critical pushback.

Using AI to build the next generation of AI is itself part of the thesis.

## Philosophy

> "Build the foundation first. Then give it the world."

This is not a chatbot. This is not trying to compete with GPT. This is an exploration of whether intelligence can emerge from the right architecture under the right pressures — the way it did in biology, but on digital substrate.

## License

TBD
