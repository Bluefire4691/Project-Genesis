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
    python src/main.py --resume          # Resume from last checkpoint
    python src/main.py --snapshot label  # Save a named snapshot at end
    python src/main.py --no-adaptive     # Use plain random shuffle instead of AdaptiveStream
"""

import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(__file__))

from orchestrator.orchestrator import Orchestrator
from curriculum.open_stage import DataStream, advance_to_open
from curriculum.adaptive_stream import AdaptiveStream
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


def run_open_stage(brain, n_cycles: int = 100, verbose: bool = True,
                   adaptive: bool = True):
    """
    Feed Genesis uncurated open-stage data and watch what develops.

    adaptive=True uses AdaptiveStream (attention-weighted selection).
    adaptive=False falls back to plain shuffled DataStream.
    """
    if adaptive:
        stream = AdaptiveStream(brain)
        stream_label = "adaptive (attention-weighted)"
    else:
        stream = DataStream(shuffle=True)
        stream_label = "random shuffle"

    pool_size = stream._pool_size if hasattr(stream, "_pool_size") else len(stream._pool)

    _header(f"OPEN STAGE — {n_cycles} cycles · {pool_size} item pool · {stream_label}")
    print(f"  No curriculum. No correct answers. No advancement criteria.")
    print(f"  Processor integration active. Observer watching.")
    if not adaptive:
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
            adaptive_info = ""
            if adaptive and hasattr(stream, "stats"):
                astats = stream.stats()
                adaptive_info = (f"| attn-sel: {astats['attention_pct']:.0f}% "
                                 f"| attn-terms: {astats['active_attention_terms']} ")
            print(f"  [{i+1}/{n_cycles}] memories: {mem_now} "
                  f"| cross-modal events: {cross_modal_total} "
                  f"{adaptive_info}| {elapsed:.1f}s elapsed")
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
    if adaptive and hasattr(stream, "stats"):
        astats = stream.stats()
        print(f"  Attention-sel pct:   {astats['attention_pct']:.1f}%")
        print(f"  Active attn terms:   {astats['active_attention_terms']}")
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
    print("    relations:<concept>  — what Genesis knows about a concept")
    print("    infer:<concept>      — what Genesis can derive (transitive chains)")
    print("    inferences           — top inferences across all concepts")
    print("    path:<A>:<B>         — relation chain from A to B")
    print("    causal               — show all causal chains")
    print("    ethics               — ethics patterns Genesis has formed")
    print("    conflicts            — show known contradictions")
    print("    conflicts:<concept>  — contradictions involving a concept")
    print("    archive              — list archive stats + snapshots")
    print("    archive:<domain>     — query archive by domain tag")
    print("    snapshot:<label>     — save named attention snapshot")
    print("    save                 — checkpoint session")
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
        elif user_input.lower().startswith("infer:"):
            concept = user_input.split(":", 1)[1].strip()
            result = brain.infer(concept)
            total = len(result["as_subject"]) + len(result["as_object"])
            print(f"  '{concept}' — {total} inference(s):")
            for r in result["as_subject"][:8]:
                chain_str = " → ".join(
                    f"{s['from']} —[{s['via']}]→ {s['to']}" for s in r["chain"]
                )
                print(f"    → {r['relation']} → {r['object']}  "
                      f"[{r['confidence']:.2f}] via: {chain_str}")
            for r in result["as_object"][:8]:
                chain_str = " → ".join(
                    f"{s['from']} —[{s['via']}]→ {s['to']}" for s in r["chain"]
                )
                print(f"    ← {r['subject']} —[{r['relation']}]→  "
                      f"[{r['confidence']:.2f}] via: {chain_str}")
        elif user_input.lower() == "inferences":
            top = brain.inference.top_inferences(limit=15)
            if not top:
                print("  No inferences yet. Process more input or run infer:<concept>.")
            else:
                print(f"  Top {len(top)} inferences:")
                for inf in top:
                    print(f"    [{inf['confidence']:.2f}] {inf['subject']} "
                          f"—[{inf['relation']}]→ {inf['object']}  "
                          f"(chain_len={inf['chain_length']})")
        elif user_input.lower().startswith("relations:"):
            concept = user_input.split(":", 1)[1].strip()
            info = brain.relations.query_concept(concept)
            print(f"  '{concept}' as subject ({len(info['as_subject'])} relations):")
            for r in info["as_subject"][:8]:
                print(f"    → {r['relation']} → {r['object']}  [{r['confidence']:.2f}]")
            print(f"  '{concept}' as object ({len(info['as_object'])} relations):")
            for r in info["as_object"][:8]:
                print(f"    {r['subject']} → {r['relation']} →   [{r['confidence']:.2f}]")
        elif user_input.lower().startswith("path:"):
            parts = user_input.split(":", 2)
            if len(parts) == 3:
                paths = brain.relations.find_path(parts[1].strip(), parts[2].strip())
                if not paths:
                    print(f"  No path found from '{parts[1]}' to '{parts[2]}'.")
                else:
                    for i, path in enumerate(paths, 1):
                        chain = " → ".join(
                            f"{s['from']} —[{s['relation']}]→ {s['to']}"
                            for s in path
                        )
                        print(f"  Path {i}: {chain}")
            else:
                print("  Usage: path:<concept_A>:<concept_B>")
        elif user_input.lower() == "ethics":
            report = brain.ethics.scan()
            print(f"\n  {brain.ethics.summary()}")
            cov = report["concept_coverage"]
            print(f"\n  Concept coverage: {cov['covered_count']}/{cov['total_concepts']} "
                  f"({cov['coverage_pct']}%)")
            if report["emergent_patterns"]:
                print(f"\n  Emergent patterns ({len(report['emergent_patterns'])}):")
                for p in report["emergent_patterns"][:5]:
                    print(f"    [{p['confidence']:.2f}] {p['chain']}")
            if report["observed_relations"]:
                print(f"\n  Observed ethics relations ({len(report['observed_relations'])}):")
                for r in report["observed_relations"][:8]:
                    print(f"    [{r['confidence']:.2f}] {r['subject']} "
                          f"—[{r['relation']}]→ {r['object']}")
            if report["inferred_chains"]:
                print(f"\n  Inferred ethics chains ({len(report['inferred_chains'])}):")
                for r in report["inferred_chains"][:5]:
                    print(f"    [{r['confidence']:.2f}] {r['subject']} "
                          f"—[{r['relation']}]→ {r['object']} "
                          f"(chain={r['chain_length']})")
        elif user_input.lower() == "conflicts":
            conflicts = brain.contradictions.query(limit=15)
            if not conflicts:
                print("  No contradictions recorded yet.")
            else:
                print(f"  {len(conflicts)} conflict(s):")
                for c in conflicts:
                    print(f"    {c['subject']} —[{c['rel_type_a']}]→ {c['object']}  "
                          f"[{c['conf_a']:.2f}]")
                    print(f"    {c['subject']} —[{c['rel_type_b']}]→ {c['object']}  "
                          f"[{c['conf_b']:.2f}]  ← CONFLICT")
        elif user_input.lower().startswith("conflicts:"):
            concept = user_input.split(":", 1)[1].strip()
            conflicts = brain.contradictions.query_concept(concept)
            if not conflicts:
                print(f"  No contradictions involving '{concept}'.")
            else:
                print(f"  {len(conflicts)} conflict(s) for '{concept}':")
                for c in conflicts:
                    print(f"    {c['subject']} —[{c['rel_type_a']}]→ {c['object']}  "
                          f"vs  —[{c['rel_type_b']}]→  [{c['conf_a']:.2f} / {c['conf_b']:.2f}]")
        elif user_input.lower() == "causal":
            chains = brain.relations.causal_chains(min_confidence=0.7)
            if not chains:
                print("  No causal chains recorded yet.")
            else:
                print(f"  {len(chains)} causal chain(s):")
                for c in chains[:15]:
                    print(f"    {c['subject']} → CAUSES → {c['object']}  [{c['confidence']:.2f}]")
        elif user_input.lower() == "save":
            brain.save_session()
            print("  Session saved.")
        elif user_input.lower() == "archive":
            stats = brain.archive.stats()
            print(f"  Archive: {stats['total_tagged']} tagged, "
                  f"{stats['total_snapshots']} snapshots, "
                  f"avg sig={stats['avg_significance']:.2f}")
            for snap in brain.archive.list_snapshots()[:5]:
                print(f"    [{snap['snapshot_id']}] '{snap['label']}' "
                      f"— {snap['key_count']} keys (session {snap['session_id']})")
        elif user_input.lower().startswith("archive:"):
            domain = user_input.split(":", 1)[1].strip()
            results = brain.archive.query(domain=domain, limit=10)
            print(f"  {len(results)} memories tagged '{domain}':")
            for r in results[:10]:
                print(f"    [{r['significance']:.2f}] {r['key']} — {r['domain_tags']}")
        elif user_input.lower().startswith("snapshot:"):
            label = user_input.split(":", 1)[1].strip()
            wm_keys = list(brain.memory.memories.keys())
            snap_id = brain.archive.snapshot(label, wm_keys, brain.session_id)
            print(f"  Snapshot '{label}' saved (id={snap_id}, {len(wm_keys)} keys).")
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
    resume = False
    adaptive = True
    snapshot_label = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--quiet":
            verbose = False
        elif arg == "--interactive":
            interactive = True
        elif arg == "--open-only":
            open_only = True
        elif arg == "--resume":
            resume = True
        elif arg == "--no-adaptive":
            adaptive = False
        elif arg.startswith("--cycles="):
            try:
                cycles = int(arg.split("=")[1])
            except ValueError:
                pass
        elif arg == "--cycles" and i + 1 < len(args):
            try:
                cycles = int(args[i + 1])
                i += 1
            except (ValueError, IndexError):
                pass
        elif arg == "--snapshot" and i + 1 < len(args):
            snapshot_label = args[i + 1]
            i += 1
        i += 1

    brain = Orchestrator(verbose=verbose, resume=resume)

    if resume and brain.curriculum.current_stage == Stage.OPEN:
        print(f"  [RESUME] Picking up from cycle {brain.cycle_count} "
              f"in OPEN stage with {len(brain.memory.memories)} warm memories.")
    elif not open_only:
        run_curriculum_pipeline(brain, verbose=verbose)
    else:
        brain.curriculum.current_stage = Stage.OPEN
        print("  Skipping curriculum — starting at OPEN stage.")

    run_open_stage(brain, n_cycles=cycles, verbose=verbose, adaptive=adaptive)

    # Optional named snapshot of the current attention state
    if snapshot_label:
        wm_keys = list(brain.memory.memories.keys())
        snap_id = brain.archive.snapshot(snapshot_label, wm_keys, brain.session_id)
        print(f"  Snapshot '{snapshot_label}' saved (id={snap_id}, {len(wm_keys)} keys).")

    # Auto-save session after every run
    brain.save_session()

    if interactive:
        run_interactive(brain)

    _divider()
    print("  Build the foundation first. Then give it the world.")
    print("  Watch what develops.")
    _divider()


if __name__ == "__main__":
    main()
