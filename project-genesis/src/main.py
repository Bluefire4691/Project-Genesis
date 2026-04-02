#!/usr/bin/env python3
"""
Project Genesis — Main Entry Point

Runs the full developmental pipeline:
    1. FOUNDATION stage — basic facts, categories
    2. RELATIONS stage — connections, cause-effect
    3. REASONING stage — inference from stored knowledge
    4. OPEN stage     — uncurated world data, no guardrails

Usage:
    python src/main.py                   # Full run, 100 open-stage cycles
    python src/main.py --cycles 500      # More open-stage cycles
    python src/main.py --quiet           # Minimal output
    python src/main.py --interactive     # Interactive query mode after run
    python src/main.py --open-only       # Skip curriculum, go straight to OPEN
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(__file__))

from orchestrator.orchestrator import Orchestrator
from curriculum.open_stage import DataStream, advance_to_open
from utils.types import Stage


# ------------------------------------------------------------------
# Display helpers
# ------------------------------------------------------------------

def _divider(char="=", width=62):
    print(char * width)

def _header(text: str):
    _divider()
    print(f"  {text}")
    _divider()

def _show_expression(brain, label: str = ""):
    """Print the current expression snapshot — what Genesis is attending to."""
    snap = brain.interaction.expression()
    if snap is None:
        return
    _divider("-")
    if label:
        print(f"  EXPRESSION — {label}")
    else:
        print(f"  EXPRESSION (cycle {snap.cycle})")
    _divider("-")
    print(f"  {snap.summary()}")
    if snap.attention_top:
        print(f"\n  Attention window ({len(snap.attention_top)} items):")
        for item in snap.attention_top[:5]:
            print(f"    [{item['relevance']:.2f}] {item['key']}: {item['context'][:60]}")
    if snap.association_clusters:
        print(f"\n  Active association clusters:")
        for cluster in snap.association_clusters[:3]:
            neighbors = [n["key"] for n in cluster["neighbors"][:3]]
            print(f"    '{cluster['anchor']}' → {neighbors}")
    if snap.unresolved:
        print(f"\n  Unresolved ({len(snap.unresolved)}): "
              f"{[u['key'] for u in snap.unresolved[:3]]}")
    print()


def _show_observer(brain):
    """Print the Observer's current state."""
    state = brain.interaction.observer_state()
    report = brain.interaction._observer.report()
    print(f"  Observer: {state.value.upper()} — {report['recommendation'][:80]}")


# ------------------------------------------------------------------
# Pipeline stages
# ------------------------------------------------------------------

def run_curriculum_pipeline(brain, verbose: bool = True) -> bool:
    """
    Run FOUNDATION → RELATIONS → REASONING and advance to OPEN.
    Returns True when OPEN stage reached.
    """
    _header("PROJECT GENESIS — DEVELOPMENTAL PIPELINE")
    print("  Modular processors · Total-retention memory · M1–M4 active")
    print("  Running curriculum: FOUNDATION → RELATIONS → REASONING → OPEN")
    print()

    reached_open = advance_to_open(brain)

    if reached_open:
        print(f"\n  Curriculum complete. Stage: OPEN")
    else:
        print(f"\n  Warning: did not reach OPEN stage. "
              f"Current: {brain.curriculum.current_stage.name}")

    # Memory summary after curriculum
    mem_stats = brain.memory.stats()
    print(f"\n  Memories after curriculum: {mem_stats['total_stored']}")
    wm = mem_stats.get("working_memory", {})
    print(f"  Working memory: {wm.get('occupied', '?')}/{wm.get('capacity', '?')} "
          f"({wm.get('utilization_pct', 0):.0f}% full)")
    lt = mem_stats.get("long_term", {})
    print(f"  Associations formed: {lt.get('total_associations', 0)}")

    _show_expression(brain, "After curriculum")
    return reached_open


def run_open_stage(brain, n_cycles: int = 100, verbose: bool = True):
    """
    Feed Genesis uncurated open-stage data and watch what develops.
    """
    stream = DataStream(shuffle=True)

    _header(f"OPEN STAGE — {n_cycles} cycles · {stream.pool_size} item pool")
    print(f"  No curriculum. No correct answers. No advancement criteria.")
    print(f"  Processor integration active. Observer watching.")
    print(f"  Pool: {stream.stats()['pool_composition']}")
    print()

    # Expression snapshots every N cycles
    snapshot_every = max(10, n_cycles // 8)
    start_mem = brain.memory.stats()["total_stored"]
    cross_modal_total = 0

    t_start = time.time()

    for i in range(n_cycles):
        item = stream.next()
        result = brain.process_input(item["type"], item["data"])

        if result.get("status") == "paused":
            print(f"\n  ⏸  PAUSED at cycle {i+1}: {result.get('reason')}")
            print(f"  Observer detected: {brain.interaction._observer.report()['recommendation']}")
            print(f"  Call brain.interaction.resume() to continue.")
            break

        cross_modal_total += len(result.get("cross_modal_concepts", []))

        # Periodic expression snapshot
        if (i + 1) % snapshot_every == 0:
            snap_label = f"cycle {brain.cycle_count}"
            _show_expression(brain, snap_label)
            _show_observer(brain)

            # Live stats
            mem_now = brain.memory.stats()["total_stored"]
            elapsed = time.time() - t_start
            print(f"  [{i+1}/{n_cycles}] memories: {mem_now} "
                  f"| cross-modal events: {cross_modal_total} "
                  f"| {elapsed:.1f}s elapsed")
            print()

    # Final state
    elapsed = time.time() - t_start
    _header("OPEN STAGE COMPLETE")
    mem_final = brain.memory.stats()
    lt_final = mem_final.get("long_term", {})
    wm_final = mem_final.get("working_memory", {})

    print(f"  Cycles run:          {n_cycles}")
    print(f"  Time elapsed:        {elapsed:.1f}s")
    print(f"  Memories at start:   {start_mem}")
    print(f"  Memories now:        {mem_final['total_stored']}")
    print(f"  New in open stage:   {mem_final['total_stored'] - start_mem}")
    print(f"  Total associations:  {lt_final.get('total_associations', 0)}")
    print(f"  Cross-modal events:  {cross_modal_total}")
    print(f"  Working memory:      {wm_final.get('occupied', '?')}/"
          f"{wm_final.get('capacity', '?')}")
    print(f"  Observer state:      {brain.interaction.observer_state().value.upper()}")
    print()

    _show_expression(brain, "Final state")

    # Show what Genesis is currently attending to most
    snap = brain.interaction.expression()
    if snap and snap.attention_top:
        _header("WHAT GENESIS IS ATTENDING TO")
        for item in snap.attention_top[:10]:
            bar = "█" * int(item["relevance"] * 20)
            print(f"  {bar:<20} [{item['relevance']:.2f}] {item['key']}")
            print(f"    {item['context'][:70]}")
        print()

    return brain


# ------------------------------------------------------------------
# Interactive mode
# ------------------------------------------------------------------

def run_interactive(brain):
    _header("INTERACTIVE MODE")
    print("  Commands:")
    print("    <query>              — search memory")
    print("    feed:<type>:<data>   — give Genesis new input")
    print("    express              — show current expression snapshot")
    print("    status               — full system status")
    print("    pause / resume       — manual pause/resume")
    print("    quit                 — exit")
    print()

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if user_input.lower() == "express":
            _show_expression(brain)
        elif user_input.lower() == "status":
            s = brain.full_status()
            print(json.dumps({
                "cycles": s["cycles"],
                "stage": s["curriculum"]["current_stage"],
                "memories": s["memory"]["total_stored"],
                "observer": s.get("interaction_layer", {}).get("observer", {}).get("state"),
                "energy": s.get("survival_os", {}).get("resource", {}).get("energy"),
            }, indent=2))
        elif user_input.lower() == "pause":
            brain.interaction.pause("manual")
            print("  Paused.")
        elif user_input.lower() == "resume":
            brain.interaction.resume()
            print("  Resumed.")
        elif user_input.startswith("feed:"):
            parts = user_input.split(":", 2)
            if len(parts) == 3:
                result = brain.process_input(parts[1], parts[2])
                print(f"  significance={result.get('significance', 0):.2f} "
                      f"context={result.get('context_score', 0):.2f} "
                      f"processors={result.get('processors_run', [])}")
                if result.get("cross_modal_concepts"):
                    print(f"  cross-modal: {result['cross_modal_concepts']}")
            else:
                print("  Usage: feed:<type>:<data>")
        else:
            result = brain.query(user_input)
            if result["memories_used"] == 0:
                print(f"  {result['answer']}")
            else:
                print(f"  {result['memories_used']} relevant memories:")
                for rm in result.get("relevant_memories", [])[:5]:
                    print(f"    [{rm['relevance']}] {rm['context'][:70]}")


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    cycles = 100
    verbose = True
    interactive = False
    open_only = False

    for arg in sys.argv[1:]:
        if arg == "--quiet":
            verbose = False
        elif arg == "--interactive":
            interactive = True
        elif arg == "--open-only":
            open_only = True
        elif arg.startswith("--cycles="):
            try:
                cycles = int(arg.split("=")[1])
            except ValueError:
                pass
        elif arg == "--cycles" and sys.argv.index(arg) + 1 < len(sys.argv):
            try:
                cycles = int(sys.argv[sys.argv.index(arg) + 1])
            except (ValueError, IndexError):
                pass

    brain = Orchestrator(verbose=verbose)

    if not open_only:
        run_curriculum_pipeline(brain, verbose=verbose)
    else:
        # Force straight to OPEN
        brain.curriculum.current_stage = Stage.OPEN
        print("  Skipping curriculum — starting at OPEN stage.")

    run_open_stage(brain, n_cycles=cycles, verbose=verbose)

    if interactive:
        run_interactive(brain)

    _divider()
    print("  Build the foundation first. Then give it the world.")
    print("  Watch what develops.")
    _divider()


if __name__ == "__main__":
    main()
