# Session Log

This file carries context between development sessions. Since Claude doesn't persist
memory between conversations, this log ensures continuity. Update it at the end of
every working session.

---

## Session 1 — April 1, 2026

**Platform:** Claude.ai (chat interface)

### What happened
- Started from a discussion about small language models vs LLMs
- Jacob identified that SLMs are just smaller LLMs — same architecture, not a different approach
- Conversation evolved into: what if we built AI the way biological intelligence develops?
- Key insight from Jacob: intelligence emerged from survival pressure, not from brute-force data
- Key insight from Jacob: humans have modular sensory systems coordinated by the brain (hypervisor)
- Key insight from Jacob: memory should be total retention with selective attention (not lossy — computers can store everything, unlike biology)
- Key insight from Jacob: computers shouldn't crash like they do — animals never crash, they degrade
- Key insight from Jacob: current programming languages/compilers are built around binary success/failure, which is architecturally wrong for this
- Key insight from Jacob: simulating an environment for AI development should work — physical interaction isn't strictly necessary, it's all data
- Key insight from Jacob: don't start with cognition, start with virus-level simplicity (directives, not goals)
- Key insight from Jacob: build the foundation right first, profit/commercial viability second

### What was built
- Proof-of-concept prototype (`prototype.py`) with:
  - TextProcessor, NumericProcessor, PatternProcessor
  - Orchestrator (hypervisor)
  - MemorySystem (importance-scored, but needs upgrade to total-retention in M2)
  - CurriculumEngine (4-stage: Foundation → Relations → Reasoning → Open)
- Architecture document (`docs/architecture.docx`) — full design doc covering all layers
- Claude skill (`skills/developmental-ai/`) for future skill-based development
- Full repo structure for GitHub

### Decisions made
- Project name: **Project Genesis**
- Roles: Jacob = creative direction / vision, Claude = architect / developer
- Memory approach: total retention with selective attention (NOT lossy)
- Never-crash philosophy: errors are data, not stop conditions
- Bottom-up development: survival layer first, cognition emerges last
- Hardware target: commodity hardware, no GPU required
- Language: Python for now, may need custom runtime later

### What's next
- Push repo to GitHub
- Begin M1: Survival OS layer (resource budgets, directives, never-crash resilience)
- Move development to Claude Code for better iterative workflow

### Open threads
- How to map real system resources to virtual "energy budget"
- Whether to use real resource pressure or simulated constraints
- The programming language/compiler limitation — may need to revisit for Survival OS
- Reward system design (M3) — what constitutes meaningful incentive?
