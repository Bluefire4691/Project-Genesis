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
    python src/main.py --voice           # Enable audio output (pyttsx3) if available
    python src/main.py --listen          # Enter microphone listen loop after run
    python src/main.py --self-directed   # Genesis fetches Wikipedia on its own curiosity targets
    python src/main.py --fetch-topics 5  # How many topics to fetch per curiosity cycle (default 5)
"""

import sys
import os
import json
import time
import queue
import threading

sys.path.insert(0, os.path.dirname(__file__))

from orchestrator.orchestrator import Orchestrator
from curriculum.open_stage import DataStream, advance_to_open
from curriculum.adaptive_stream import AdaptiveStream
from output.channel import OutputChannel
from output.microphone import MicrophoneInput
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
# Live mode — Genesis runs continuously, user conversation is an overlay
# ------------------------------------------------------------------

def run_live(brain, fetch_topics: int = 3, adaptive: bool = True):
    """
    Live mode: Genesis thinks and learns continuously. The user joins the
    conversation whenever they want — Genesis responds and keeps running.

    Architecture:
        A single stdin-reader thread puts lines into a queue.
        The main thread owns all brain state: it runs cycles, drains the
        queue between each one, and expresses spontaneous thoughts on a
        time trigger. No cross-thread brain access — no SQLite issues.

    Commands (prefix with /):
        /quit  /summary  /books  /curiosity  /inferences  /status  /save

    Anything else is treated as conversation and Genesis responds from
    its current knowledge while continuing to think in the background.
    """
    brain.verbose = False

    # Build the input stream
    if adaptive and brain.curriculum.current_stage.value >= 4:
        stream = AdaptiveStream(brain)
    else:
        from curriculum.open_stage import DataStream
        stream = DataStream()

    # Stdin reader — only touches the queue, never the brain
    input_q: queue.Queue = queue.Queue()
    stop_evt = threading.Event()

    def _read_stdin():
        while not stop_evt.is_set():
            try:
                line = input()
                input_q.put(line)
            except EOFError:
                stop_evt.set()

    reader = threading.Thread(target=_read_stdin, daemon=True)
    reader.start()

    # Tuning knobs
    _FETCH_EVERY   = 50    # curiosity fetch every N cycles
    _EXPR_MIN_GAP  = 40.0  # seconds between spontaneous expressions (minimum)
    _EXPR_IDLE_GAP = 90.0  # seconds — always express if this long has passed
    _CYCLE_SLEEP   = 0.02  # seconds between cycles (≈50 cycles/sec max)

    print()
    print("  Genesis is running.")
    print("  Type to talk. Prefix / for commands: /quit /summary /books /curiosity")
    print()

    cycles     = 0
    last_fetch = 0
    last_expr  = time.time()
    last_wm    = brain.memory.stats()["working_memory"].get("occupied", 0)
    last_stmt  = ""

    try:
        while not stop_evt.is_set():

            # ── 1. Drain any user input ─────────────────────────────
            while not input_q.empty():
                raw = input_q.get_nowait().strip()
                if not raw:
                    continue

                # Slash-commands
                if raw.startswith("/"):
                    cmd = raw[1:].lower().split(":")[0]
                    arg = raw[1:].split(":", 1)[1].strip() if ":" in raw else ""

                    if cmd in ("quit", "exit", "q"):
                        stop_evt.set()
                        break
                    elif cmd == "summary":
                        print()
                        _print_summary(brain)
                    elif cmd == "books":
                        if hasattr(brain, "_feeder") and brain._feeder:
                            status = brain._feeder.reading_status()
                            if status:
                                print(f"\n  Reading {len(status)} book(s):")
                                for bid, info in status.items():
                                    print(f"    Book {bid}: {info['percent_read']}% read")
                            else:
                                print("\n  No books opened yet.")
                        else:
                            print("\n  Run a curiosity fetch first (/curiosity).")
                    elif cmd == "curiosity":
                        report = brain.curiosity_report()
                        if report:
                            print(f"\n  Genesis most wants to know about:")
                            for r in report[:6]:
                                fetched = " [read]" if r["already_fetched"] else ""
                                print(f"    [{r['curiosity_score']:.2f}] "
                                      f"{r['concept']}{fetched}")
                        else:
                            print("\n  No curiosity targets yet.")
                    elif cmd == "inferences":
                        top = brain.inference.top_inferences(limit=10)
                        if top:
                            print(f"\n  Top {len(top)} inferences:")
                            for inf in top:
                                print(f"    [{inf['confidence']:.2f}] "
                                      f"{inf['subject']} → {inf['object']}")
                        else:
                            print("\n  No inferences derived yet.")
                    elif cmd == "status":
                        s = brain.status()
                        print(f"\n  cycles={s['cycles']} "
                              f"relations={s.get('relations', {}).get('total_relations', 0)} "
                              f"inferences={s.get('inference', {}).get('total_inferences', 0)} "
                              f"memories={s['memory']['total_stored']}")
                    elif cmd == "save":
                        brain.save_session()
                        print("\n  Session saved.")
                    elif cmd == "learn":
                        n = int(arg) if arg.isdigit() else fetch_topics
                        print(f"\n  Fetching {n} topics...")
                        brain.fetch_knowledge(n_topics=n, verbose=True)
                        brain.inference.run(session_id=brain.session_id)
                        last_fetch = cycles
                    else:
                        print(f"\n  Unknown command /{cmd}. "
                              "Try /quit /summary /books /curiosity /inferences /status /save")
                    print()

                else:
                    # Conversation — Genesis responds from its own knowledge
                    response = brain.voice.chat_respond(raw)
                    print(f"\n  Genesis: {response}\n")
                    last_expr = time.time()  # reset expression timer after responding

            if stop_evt.is_set():
                break

            # ── 2. One brain cycle ──────────────────────────────────
            item = stream.next()
            brain.process_input(item["type"], item["data"])
            cycles += 1

            # ── 3. Periodic curiosity fetch ─────────────────────────
            if cycles - last_fetch >= _FETCH_EVERY:
                brain.fetch_knowledge(n_topics=fetch_topics, verbose=False)
                new_inf = brain.inference.run(session_id=brain.session_id)
                if new_inf > 0:
                    print(f"  [Genesis derived {new_inf} new connection(s)]\n")
                last_fetch = cycles

            # ── 4. Spontaneous expression ───────────────────────────
            now = time.time()
            wm_now = brain.memory.stats()["working_memory"].get("occupied", 0)
            wm_delta = wm_now - last_wm
            last_wm = wm_now

            time_since = now - last_expr
            # Express if: enough time has passed AND (something changed OR idle too long)
            if time_since >= _EXPR_MIN_GAP and (wm_delta > 0 or time_since >= _EXPR_IDLE_GAP):
                stmt = brain.voice.express(force=time_since >= _EXPR_IDLE_GAP)
                if stmt and stmt != last_stmt:
                    print(f"  Genesis: {stmt}\n")
                    last_expr = now
                    last_stmt = stmt
                elif stmt:
                    # Same statement again — reset timer but stay quiet
                    last_expr = now

            time.sleep(_CYCLE_SLEEP)

    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        brain.save_session()
        print("\n  Session saved. Genesis resting.")


# ------------------------------------------------------------------
# Interactive mode
# ------------------------------------------------------------------

def run_self_directed(brain, n_cycles: int = 100, fetch_topics: int = 5,
                      verbose: bool = True, adaptive: bool = True):
    """
    Self-directed learning mode: Genesis alternates between processing
    its built-in pool and fetching Wikipedia on its own curiosity targets.

    Rhythm: 50 cycles of pool → curiosity fetch → 50 cycles → fetch → ...
    """
    _header(f"SELF-DIRECTED MODE — {n_cycles} cycles + Wikipedia")
    print("  Genesis will identify what it needs to learn and fetch it.")
    print("  No topic list. Genesis decides.")
    print()

    batch_size = min(50, max(10, n_cycles // 10))
    batches = max(1, n_cycles // batch_size)
    remainder = n_cycles - (batches * batch_size)

    for batch_num in range(batches):
        _divider("-")
        print(f"  Batch {batch_num + 1}/{batches} — processing {batch_size} cycles")
        _divider("-")
        run_open_stage(brain, n_cycles=batch_size, verbose=verbose, adaptive=adaptive)

        # Genesis decides what to fetch
        print(f"\n  Genesis examining its own knowledge gaps...")
        brain.fetch_knowledge(n_topics=fetch_topics, verbose=True)

        # Run inference after each knowledge acquisition
        if hasattr(brain, 'inference'):
            new_inferences = brain.inference.run(session_id=brain.session_id)
            if new_inferences > 0 and verbose:
                print(f"  [Inference] {new_inferences} new chain(s) derived")

    # Remainder cycles
    if remainder > 0:
        run_open_stage(brain, n_cycles=remainder, verbose=verbose, adaptive=adaptive)

    _header("SELF-DIRECTED RUN COMPLETE")
    rel_stats = brain.relations.stats()
    inf_stats = brain.inference.stats()
    print(f"  Total relations:   {rel_stats.get('total_relations', 0)}")
    print(f"  Total inferences:  {inf_stats.get('total_inferences', 0)}")
    print(f"  Contradictions:    {brain.contradictions.count()}")
    print()


def run_listen_loop(brain):
    """
    Microphone listen loop: Genesis hears speech, processes it as text input,
    and responds from its internal state. Runs until 'goodbye genesis' is spoken
    or KeyboardInterrupt.
    """
    mic = MicrophoneInput()
    if not mic.available():
        print("  Microphone input unavailable (install SpeechRecognition + pyaudio).")
        return

    _header("LISTEN MODE — speak to Genesis")
    print("  Genesis is listening. Say 'goodbye genesis' to stop.")
    print()

    def _handle(text: str):
        print(f"\n  [You] {text}")
        result = brain.process_input("text", text)
        response = brain.voice.respond(text.split()[0].lower() if text.split() else "")
        if not response:
            response = brain.voice.compose()
        if response:
            print(f"  [Genesis] {response}")
        return True  # keep looping

    try:
        mic.listen_loop(_handle, stop_phrase="goodbye genesis")
    except KeyboardInterrupt:
        pass

    print("\n  Listen loop ended.")
    stats = mic.stats()
    print(f"  Captured: {stats['total_captures']} phrases, "
          f"failed: {stats['failed_captures']}")


def run_chat(brain):
    """
    Conversational mode — the user speaks naturally and Genesis replies
    from its own knowledge, inferences, and curiosity.

    Every message is simultaneously processed as new knowledge (Genesis
    keeps learning from the conversation) and responded to based on what
    Genesis already knows. Genesis will ask questions when it's curious.
    """
    _header("CONVERSATION")
    print("  Talk to Genesis. It will respond from its own knowledge.")
    print("  Type 'exit', 'bye', or press Ctrl+C to leave chat.")
    print()

    # Suppress cycle-by-cycle processing output during conversation
    original_verbose = brain.verbose
    brain.verbose = False

    # Show what Genesis wants to open with
    opening = brain.voice.compose(trigger="attention")
    if opening:
        print(f"  Genesis: {opening}")
        print()

    while True:
        try:
            user_text = input("  You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not user_text:
            continue
        if user_text.lower() in ("bye", "exit", "goodbye", "quit", "leave", "back"):
            print("  [returning to interactive mode]")
            break

        response = brain.voice.chat_respond(user_text)
        print(f"\n  Genesis: {response}\n")

    # Restore verbose setting
    brain.verbose = original_verbose


def _print_summary(brain):
    """
    Human-readable summary of what Genesis knows and has derived.

    Shows the three most meaningful signals of genuine learning:
      1. Knowledge base size and connectivity
      2. Inferences — things Genesis derived, not just stored
      3. What Genesis is currently focused on and curious about
    """
    _header("GENESIS KNOWLEDGE SUMMARY")

    # --- Knowledge base ---
    conn = brain.relations._conn
    rel_stats = brain.relations.stats()
    total_relations = rel_stats.get("total_relations", 0)
    by_type = rel_stats.get("by_type", {})

    # Connectivity: average relations per unique concept
    concept_rows = conn.execute(
        "SELECT subject AS c FROM relations UNION SELECT object AS c FROM relations"
    ).fetchall()
    unique_concepts = len(concept_rows)
    connectivity = round(total_relations / max(1, unique_concepts), 2)

    # Most-connected concepts (appear most as subject OR object)
    top_concepts = conn.execute("""
        SELECT concept, COUNT(*) AS degree FROM (
            SELECT subject AS concept FROM relations
            UNION ALL
            SELECT object  AS concept FROM relations
        ) GROUP BY concept ORDER BY degree DESC LIMIT 5
    """).fetchall()

    print("  Knowledge base:")
    print(f"    {total_relations} observed relations across {unique_concepts} concepts "
          f"(avg {connectivity} per concept)")
    if by_type:
        type_summary = ", ".join(f"{k}:{v}" for k, v in
                                 sorted(by_type.items(), key=lambda x: -x[1]))
        print(f"    Types: {type_summary}")
    if top_concepts:
        top_str = ", ".join(f"{r[0]} ({r[1]})" for r in top_concepts)
        print(f"    Most connected: {top_str}")
    print()

    # --- Inferences ---
    inf_stats = brain.inference.stats()
    total_inf = inf_stats.get("total_inferences", 0)
    inf_by_type = inf_stats.get("by_type", {})
    top_infs = brain.inference.top_inferences(limit=5)

    print("  Derived knowledge (inferences):")
    if total_inf == 0:
        print("    None yet — Genesis needs more interconnected relations.")
        print("    Tip: run 'learn' a few times, then 'inferences' to check.")
    else:
        print(f"    {total_inf} inferences derived from observed relations")
        if inf_by_type:
            inf_type_str = ", ".join(f"{k}:{v}" for k, v in
                                     sorted(inf_by_type.items(), key=lambda x: -x[1]))
            print(f"    Types: {inf_type_str}")
        print()
        print("    Most confident derived facts:")
        for inf in top_infs:
            chain_concepts = [inf["subject"]]
            chain_concepts.append(inf["object"])
            print(f"      [{inf['confidence']:.2f}] {inf['subject']} "
                  f"—[{inf['relation']}]→ {inf['object']}  "
                  f"(derived in {inf['chain_length']} steps)")
    print()

    # --- Attention / focus ---
    wm = brain.memory.memories
    if wm:
        top_mem = sorted(wm.items(), key=lambda kv: kv[1].relevance, reverse=True)[:5]
        print("  What Genesis is currently focused on:")
        for key, mem in top_mem:
            # Strip prefix for readability
            label = key.split(":", 1)[-1] if ":" in key else key
            label = label.replace("_", " ")[:50]
            print(f"    [{mem.relevance:.2f}] {label}")
        print()

    # --- Curiosity ---
    curiosity = brain.curiosity_report()[:5]
    if curiosity:
        unfetched = [c for c in curiosity if not c.get("already_fetched")]
        print("  What Genesis most wants to learn next:")
        for c in unfetched[:4]:
            src = "graph gap" if c["source"] == "graph_gap" else "memory"
            print(f"    [{c['curiosity_score']:.2f}] {c['concept']}  ({src})")
    print()
    _divider()


def run_interactive(brain):
    _header("INTERACTIVE MODE")
    print("  Commands:")
    print("    <query>              — search memory")
    print("    feed:<type>:<data>   — give Genesis new input")
    print("    express              — show current expression snapshot")
    print("    voice                — Genesis speaks from its current state")
    print("    voice:<concept>      — Genesis responds about a specific concept")
    print("    listen               — enter microphone listen loop")
    print("    curiosity            — show what Genesis most wants to learn")
    print("    learn                — Genesis reads from books on its curiosity targets")
    print("    learn:<N>            — fetch N topics (default 3)")
    print("    books                — show what Genesis is currently reading and how far")
    print("    chat                 — talk to Genesis; it responds from its own knowledge")
    print("    summary              — what Genesis knows and has derived (readable)")
    print("    status               — full system status (JSON)")
    print("    relations:all        — show every stored relation")
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
        elif user_input.lower() == "voice":
            stmt = brain.voice.express(force=True)
            if not stmt:
                print("  Genesis has nothing to say yet — process more input first.")
        elif user_input.lower().startswith("voice:"):
            concept = user_input.split(":", 1)[1].strip()
            stmt = brain.voice.respond(concept)
            if not stmt:
                print(f"  Genesis has not formed connections around '{concept}' yet.")
        elif user_input.lower() == "listen":
            run_listen_loop(brain)
        elif user_input.lower() == "curiosity":
            report = brain.curiosity_report()
            if not report:
                print("  Working memory empty — process more input first.")
            else:
                print(f"  Top curiosity targets ({len(report)}):")
                for r in report[:10]:
                    fetched = " [fetched]" if r["already_fetched"] else ""
                    print(f"    [{r['curiosity_score']:.2f}] {r['concept']}"
                          f"  (attention={r['attention']:.2f}, "
                          f"relations={r['relations_known']}){fetched}")
        elif user_input.lower().startswith("learn"):
            n = 3
            if ":" in user_input:
                try:
                    n = int(user_input.split(":", 1)[1].strip())
                except ValueError:
                    pass
            print(f"  Genesis choosing {n} topics to learn about...")
            report = brain.fetch_knowledge(n_topics=n, verbose=True)
            new_infs = brain.inference.run(session_id=brain.session_id)
            if new_infs > 0:
                print(f"  [Inference] {new_infs} new chain(s) derived from new knowledge")
            print(f"  Relations added: {report.get('relations_added', 0)}")
        elif user_input.lower() == "books":
            if hasattr(brain, "_feeder") and brain._feeder:
                status = brain._feeder.reading_status()
                if status:
                    print(f"  Genesis is reading {len(status)} book(s):")
                    for book_id, info in status.items():
                        print(f"    Book {book_id}: {info['percent_read']}% read "
                              f"({info['position']:,} / {info['total']:,} chars)")
                else:
                    print("  Genesis has not started reading any books yet. "
                          "Run 'learn' first.")
            else:
                print("  No reading session active. Run 'learn' first.")
        elif user_input.lower() in ("chat", "talk", "converse"):
            run_chat(brain)
        elif user_input.lower() == "summary":
            _print_summary(brain)
        elif user_input.lower() == "status":
            s = brain.full_status()
            print(json.dumps({
                "cycles":     s["cycles"],
                "stage":      s["curriculum"]["current_stage"],
                "memories":   s["memory"]["total_stored"],
                "relations":  s.get("relations", {}).get("total_relations", 0),
                "inferences": s.get("inference", {}).get("total_inferences", 0),
                "observer":   s.get("interaction_layer", {}).get("observer", {}).get("state"),
                "energy":     s.get("survival_os", {}).get("resource", {}).get("energy"),
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
        elif user_input.lower() == "relations:all":
            conn = brain.relations._conn
            rows = conn.execute(
                "SELECT subject, rel_type, object, confidence "
                "FROM relations ORDER BY confidence DESC"
            ).fetchall()
            if not rows:
                print("  No relations stored yet.")
            else:
                print(f"  All {len(rows)} stored relations:")
                for r in rows:
                    print(f"    [{r[3]:.2f}] {r[0]}  —[{r[1]}]→  {r[2]}")
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
    live = False
    open_only = False
    resume = False
    adaptive = True
    use_voice = False
    use_listen = False
    self_directed = False
    fetch_topics = 5
    snapshot_label = None
    memory_size = 500

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--quiet":
            verbose = False
        elif arg == "--live":
            live = True
        elif arg == "--interactive":
            interactive = True
        elif arg == "--open-only":
            open_only = True
        elif arg == "--resume":
            resume = True
        elif arg == "--no-adaptive":
            adaptive = False
        elif arg == "--voice":
            use_voice = True
        elif arg == "--listen":
            use_listen = True
        elif arg == "--self-directed":
            self_directed = True
        elif arg.startswith("--fetch-topics="):
            try:
                fetch_topics = int(arg.split("=")[1])
            except ValueError:
                pass
        elif arg == "--fetch-topics" and i + 1 < len(args):
            try:
                fetch_topics = int(args[i + 1])
                i += 1
            except (ValueError, IndexError):
                pass
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
        elif arg.startswith("--memory-size="):
            try:
                memory_size = int(arg.split("=")[1])
            except ValueError:
                pass
        elif arg == "--memory-size" and i + 1 < len(args):
            try:
                memory_size = int(args[i + 1])
                i += 1
            except (ValueError, IndexError):
                pass
        i += 1

    # M13: Output channel selection
    channel = OutputChannel.best_available(prefer_audio=use_voice)
    if use_voice:
        print(f"  Output channel: {channel.name}")
        if channel.name == "text":
            print("  (pyttsx3 not installed — falling back to text)")

    brain = Orchestrator(
        verbose=verbose, resume=resume, channel=channel,
        working_capacity=memory_size,
    )

    if resume and brain.curriculum.current_stage == Stage.OPEN:
        print(f"  [RESUME] Picking up from cycle {brain.cycle_count} "
              f"in OPEN stage with {len(brain.memory.memories)} warm memories.")
    elif not open_only:
        run_curriculum_pipeline(brain, verbose=verbose)
    else:
        brain.curriculum.current_stage = Stage.OPEN
        print("  Skipping curriculum — starting at OPEN stage.")

    if live:
        # Live mode takes over immediately — no batch run first.
        # Genesis enters continuous operation straight away.
        pass
    elif self_directed:
        run_self_directed(brain, n_cycles=cycles, fetch_topics=fetch_topics,
                          verbose=verbose, adaptive=adaptive)
    else:
        run_open_stage(brain, n_cycles=cycles, verbose=verbose, adaptive=adaptive)

    # Optional named snapshot of the current attention state
    if snapshot_label:
        wm_keys = list(brain.memory.memories.keys())
        snap_id = brain.archive.snapshot(snapshot_label, wm_keys, brain.session_id)
        print(f"  Snapshot '{snapshot_label}' saved (id={snap_id}, {len(wm_keys)} keys).")

    # Auto-save session after every run
    brain.save_session()

    if live:
        run_live(brain, fetch_topics=fetch_topics, adaptive=adaptive)
    elif interactive:
        run_interactive(brain)
    elif use_listen:
        run_listen_loop(brain)

    _divider()
    print("  Build the foundation first. Then give it the world.")
    print("  Watch what develops.")
    _divider()


if __name__ == "__main__":
    main()
