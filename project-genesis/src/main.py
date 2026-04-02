#!/usr/bin/env python3
"""
Project Genesis — Main Entry Point

Run the developmental AI proof-of-concept demonstration.

Usage:
    python src/main.py              # Full demo
    python src/main.py --quiet      # Minimal output
    python src/main.py --interactive # Interactive query mode after learning
"""

import sys
import os
import json

# Ensure src is on the path
sys.path.insert(0, os.path.dirname(__file__))

from orchestrator.orchestrator import Orchestrator
from utils.types import Stage


def run_demo(verbose: bool = True, interactive: bool = False):
    print("╔════════════════════════════════════════════════════╗")
    print("║           PROJECT GENESIS — v0.1                  ║")
    print("║                                                    ║")
    print("║  Modular processors • Total-retention memory       ║")
    print("║  Staged learning • No GPU • No massive datasets    ║")
    print("╚════════════════════════════════════════════════════╝")

    brain = Orchestrator(verbose=verbose)

    # Run through curriculum stages
    brain.run_curriculum()

    while brain.curriculum.current_stage > Stage.FOUNDATION:
        if brain.curriculum.current_stage <= Stage.OPEN:
            brain.run_curriculum()
        if not brain.curriculum.should_advance():
            break

    # Status report
    print(f"\n{'='*60}")
    print("  SYSTEM STATUS AFTER LEARNING")
    print(f"{'='*60}")
    status = brain.full_status()
    print(f"  Total cycles: {status['cycles']}")
    print(f"  Current stage: {status['curriculum']['current_stage']}")
    print(f"  Memories stored: {status['memory']['total_stored']}")
    print(f"  Avg relevance: {status['memory']['avg_relevance']}")

    # Show stored memories
    print(f"\n  All memories (total retention):")
    for key, mem in sorted(brain.memory.memories.items(),
                           key=lambda x: x[1].relevance, reverse=True):
        print(f"    [{mem.relevance:.2f}] {key}: {mem.context}")

    # Demo queries
    print(f"\n{'='*60}")
    print("  QUERYING THE SYSTEM")
    print(f"{'='*60}")

    queries = [
        "dog animal",
        "water",
        "patterns",
        "seasons spring summer",
        "plant growth",
    ]

    for q in queries:
        print(f"\n--- Query: '{q}' ---")
        result = brain.query(q)
        print(f"  Memories used: {result['memories_used']}")
        if "relevant_memories" in result:
            for rm in result["relevant_memories"]:
                print(f"    • [{rm['relevance']}] {rm['context']}")

    # Interactive mode
    if interactive:
        print(f"\n{'='*60}")
        print("  INTERACTIVE MODE")
        print("  Type queries to search memory. Type 'quit' to exit.")
        print("  Type 'feed:text:your input here' to feed new data.")
        print(f"{'='*60}")

        while True:
            try:
                user_input = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if user_input.lower() in ('quit', 'exit', 'q'):
                break

            if user_input.startswith("feed:"):
                parts = user_input.split(":", 2)
                if len(parts) == 3:
                    result = brain.process_input(parts[1], parts[2])
                    print(f"  → {json.dumps(result, indent=2)}")
                else:
                    print("  Usage: feed:type:data (e.g., feed:text:The sky is blue)")
            elif user_input.startswith("status"):
                print(json.dumps(brain.full_status(), indent=2))
            else:
                result = brain.query(user_input)
                if "relevant_memories" in result:
                    for rm in result["relevant_memories"]:
                        print(f"  [{rm['relevance']}] {rm['context']}")
                else:
                    print(f"  {result['answer']}")

    print(f"\n{'='*60}")
    print("  SESSION COMPLETE")
    print(f"{'='*60}")
    print("\n  Build the foundation first. Then give it the world.\n")


if __name__ == "__main__":
    verbose = "--quiet" not in sys.argv
    interactive = "--interactive" in sys.argv
    run_demo(verbose=verbose, interactive=interactive)
