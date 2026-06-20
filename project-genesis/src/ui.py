#!/usr/bin/env python3
"""
Genesis Chat UI

Clean terminal interface. Background thinking is silent.
Only Genesis's expressions and the conversation are visible.

Run:
    python ui.py
    python ui.py --resume
    python ui.py --resume --self-directed --speed 10 --batch 20

Resource commands (adjustable while running):
    speed N     — 1 (slowest) to 10 (max). Default 8.
    batch N     — items processed per tick, no sleep between them. Default 10.
    memory N    — working-memory slots (wider attention = more options).
    fetch N     — topics per web-fetch cycle. Default 3.
    explore     — break out of current topic fixation.
"""

import os
import sys
import time
import queue
import threading
import textwrap

sys.path.insert(0, os.path.dirname(__file__))

from rich.console import Console
from rich.rule import Rule

# ── Colour / style tokens ─────────────────────────────────────────────────

_C_GENESIS     = "bold cyan"
_C_USER        = "bold white"
_C_STATUS      = "dim"
_C_DIVIDER     = "bright_black"
_C_DRIVE_OK    = "green"
_C_DRIVE_ALARM = "bold red"

_WIDTH = 72

console = Console(highlight=False, soft_wrap=False)


# ── Speed table (1–10 → sleep seconds BETWEEN batches) ───────────────────
# At speed 8+, there is no sleep — the only pacing is batch size.

_SPEED_TABLE = {
    1:  0.500,
    2:  0.200,
    3:  0.100,
    4:  0.050,
    5:  0.020,
    6:  0.010,
    7:  0.005,
    8:  0.001,
    9:  0.000,
    10: 0.000,
}


# ── Helpers ───────────────────────────────────────────────────────────────

def _wrap(text: str, indent: int = 12) -> str:
    prefix = " " * indent
    lines = textwrap.wrap(text, width=_WIDTH - indent)
    if not lines:
        return ""
    return ("\n" + prefix).join(lines)


def _drive_colour(action: str) -> str:
    if action == "alarm":       return _C_DRIVE_ALARM
    if action == "explore":     return _C_DRIVE_OK
    if action == "rest":        return "blue"
    if action == "consolidate": return "cyan"
    return _C_STATUS


def _speed_bar(speed: int) -> str:
    return "█" * speed + "░" * (10 - speed)


def _print_status(cycle: int, drives: dict, topic: str,
                  controls: dict, cyc_per_sec: float) -> None:
    action  = drives.get("seed_action", "idle")
    wanting = drives.get("wanting",     0.0)
    colour  = _drive_colour(action)
    speed   = controls.get("speed",  8)
    batch   = controls.get("batch", 10)

    cps_str = f"{cyc_per_sec:.0f}/s" if cyc_per_sec > 0 else "—"

    parts = [
        f"[{_C_STATUS}]cycle {cycle:,}[/{_C_STATUS}]",
        f"[{colour}]{action}[/{colour}]",
        f"[{_C_STATUS}]want {wanting:+.2f}[/{_C_STATUS}]",
        f"[{_C_STATUS}][{_speed_bar(speed)}] spd{speed} ×{batch} {cps_str}[/{_C_STATUS}]",
    ]
    if topic:
        short = topic[:26] + "…" if len(topic) > 26 else topic
        parts.append(f"[{_C_STATUS}]reading: {short}[/{_C_STATUS}]")

    console.print("  " + "  ·  ".join(parts))


def _print_genesis(text: str) -> None:
    wrapped = _wrap(text, indent=12)
    console.print(f"\n  [bold cyan]Genesis[/bold cyan]  [dim]❯[/dim]  {wrapped}\n")


def _print_user(text: str) -> None:
    wrapped = _wrap(text, indent=12)
    console.print(f"  [bold white]You[/bold white]     [dim]❯[/dim]  {wrapped}")


def _divider() -> None:
    console.print(Rule(style=_C_DIVIDER))


def _header() -> None:
    console.print()
    _divider()
    console.print(
        "  [bold cyan]G E N E S I S[/bold cyan]"
        "  [dim]— thinking and learning continuously[/dim]"
    )
    _divider()
    console.print("  [dim]Talk normally or use a command:[/dim]")
    console.print(
        "  [dim]  [white]reflect  thoughts  curiosity  status  save  quit[/white][/dim]"
    )
    console.print(
        "  [dim]  Resources (live, type while running):[/dim]"
    )
    console.print(
        "  [dim]    [white]speed N[/white] 1–10  "
        "[white]batch N[/white] items/tick  "
        "[white]memory N[/white]  "
        "[white]fetch N[/white]  "
        "[white]explore[/white][/dim]"
    )
    _divider()
    console.print()


# ── Main UI loop ──────────────────────────────────────────────────────────

def run(brain, self_directed: bool = False, fetch_topics: int = 3,
        initial_speed: int = 8, initial_batch: int = 10):
    """
    Run the Genesis chat UI.

    Brain processes cycles in a background thread.
    This thread owns the terminal.
    """
    brain.verbose = False

    # Build input stream
    if brain.curriculum.current_stage.value >= 4:
        from curriculum.adaptive_stream import AdaptiveStream
        stream = AdaptiveStream(brain)
    else:
        from curriculum.open_stage import DataStream
        stream = DataStream()

    # ── Shared controls ───────────────────────────────────────────────────
    try:
        _mem_cap = brain.memory._working.capacity
    except Exception:
        _mem_cap = 5000

    ctrl_lock = threading.Lock()
    controls = {
        "speed":        initial_speed,
        "batch":        initial_batch,
        "memory":       _mem_cap,
        "fetch_topics": fetch_topics,
        "explore_flag": False,
    }

    # ── Queues ────────────────────────────────────────────────────────────

    input_q:      queue.Queue = queue.Queue()
    expression_q: queue.Queue = queue.Queue()
    status_q:     queue.Queue = queue.Queue(maxsize=1)
    stop_evt = threading.Event()

    # ── Background brain thread ───────────────────────────────────────────

    def _brain_loop():
        cycles        = 0
        last_fetch    = 0
        last_reflect  = 0
        last_save     = time.time()
        current_topic = ""
        last_result   = {}

        # Throughput tracking (rolling 5s window)
        _tput_t0    = time.perf_counter()
        _tput_count = 0
        cyc_per_sec = 0.0

        _REFLECT_EVERY = 400
        _AUTOSAVE      = 120.0

        # Silence direct stdout from voice system
        try:
            from output.channel import NullChannel
            brain.voice.set_channel(NullChannel())
        except Exception:
            pass

        while not stop_evt.is_set():
            try:
                # Read controls once per batch
                with ctrl_lock:
                    speed        = controls["speed"]
                    batch_size   = max(1, controls["batch"])
                    n_fetch      = controls["fetch_topics"]
                    do_explore   = controls["explore_flag"]
                    if do_explore:
                        controls["explore_flag"] = False

                cycle_sleep = _SPEED_TABLE.get(speed, 0.001)
                # Fewer cycles between web fetches at higher speeds
                fetch_every = max(5, 100 - speed * 9)

                # Explore: clear curiosity frontier (memory is untouched)
                if do_explore:
                    try:
                        brain._curiosity_directives.clear()
                        brain._save_directives()
                    except Exception:
                        pass
                    current_topic = ""

                # ── Tight inner batch — no overhead between items ─────────
                for _ in range(batch_size):
                    if stop_evt.is_set():
                        break
                    item        = stream.next()
                    last_result = brain.process_input(item["type"], item["data"])
                    cycles     += 1
                    _tput_count += 1

                # ── Update throughput counter ─────────────────────────────
                now = time.perf_counter()
                elapsed = now - _tput_t0
                if elapsed >= 5.0:
                    cyc_per_sec = _tput_count / elapsed
                    _tput_t0    = now
                    _tput_count = 0

                # ── Spontaneous expression (check every ~40 cycles) ───────
                try:
                    if cycles % 40 < batch_size:
                        expr = brain.drives.expressive_state()
                        if expr:
                            expression_q.put(("genesis", expr))
                except Exception:
                    pass

                # ── Push latest status ────────────────────────────────────
                drives = last_result.get("drives", {})
                try:
                    status_q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    with ctrl_lock:
                        ctrl_snap = dict(controls)
                    status_q.put_nowait({
                        "cycle":      brain.cycle_count,
                        "drives":     drives,
                        "topic":      current_topic,
                        "controls":   ctrl_snap,
                        "cyc_per_sec": cyc_per_sec,
                    })
                except queue.Full:
                    pass

                # ── Periodic: self-directed web fetch ─────────────────────
                if self_directed and (cycles - last_fetch) >= fetch_every:
                    try:
                        res     = brain.fetch_knowledge(n_topics=n_fetch, verbose=False)
                        fetched = res.get("topics_fetched", [])
                        if fetched:
                            current_topic = fetched[0]
                            expression_q.put(("status", f"Reading: {current_topic}"))
                    except Exception:
                        pass
                    last_fetch = cycles

                # ── Periodic: consolidation ───────────────────────────────
                if (cycles - last_reflect) >= _REFLECT_EVERY:
                    try:
                        rep     = brain.reflect(cycle=cycles)
                        summary = rep.get("summary", "")
                        if summary:
                            expression_q.put(("genesis", summary))
                    except Exception:
                        pass
                    last_reflect = cycles

                # ── Periodic: auto-save ───────────────────────────────────
                if (time.time() - last_save) >= _AUTOSAVE:
                    try:
                        brain.save_session()
                        last_save = time.time()
                    except Exception:
                        pass

                if cycle_sleep > 0:
                    time.sleep(cycle_sleep)

            except Exception:
                time.sleep(0.1)

    brain_thread = threading.Thread(target=_brain_loop, daemon=True)
    brain_thread.start()

    # ── Stdin reader thread ───────────────────────────────────────────────

    def _read_stdin():
        while not stop_evt.is_set():
            try:
                line = input()
                input_q.put(line)
            except EOFError:
                stop_evt.set()
            except Exception:
                pass

    stdin_thread = threading.Thread(target=_read_stdin, daemon=True)
    stdin_thread.start()

    # ── Display loop (main thread) ────────────────────────────────────────

    _header()

    try:
        greeting = brain.voice.wake_greeting()
        if greeting:
            _print_genesis(greeting)
    except Exception:
        _print_genesis("I'm awake. Give me a moment to settle.")

    last_status_print = 0.0
    _STATUS_INTERVAL  = 20.0
    _last_cps         = 0.0

    try:
        while not stop_evt.is_set():

            # Drain expression queue
            while not expression_q.empty():
                try:
                    kind, text = expression_q.get_nowait()
                    if kind == "genesis":
                        _print_genesis(text)
                    else:
                        console.print(f"  [dim]{text}[/dim]")
                except queue.Empty:
                    break

            # Periodic status line
            now = time.time()
            if (now - last_status_print) >= _STATUS_INTERVAL:
                try:
                    st = status_q.get_nowait()
                    _last_cps = st.get("cyc_per_sec", _last_cps)
                    _print_status(st["cycle"], st["drives"],
                                  st.get("topic", ""),
                                  st.get("controls", controls),
                                  _last_cps)
                    last_status_print = now
                except queue.Empty:
                    pass

            # User input
            if not input_q.empty():
                raw = input_q.get_nowait().strip()
                if not raw:
                    continue

                _print_user(raw)

                if ":" in raw:
                    cmd, _, arg = raw.partition(":")
                    cmd = cmd.strip().lstrip("/").lower()
                    arg = arg.strip()
                else:
                    parts = raw.lstrip("/").split(None, 1)
                    cmd   = parts[0].lower()
                    arg   = parts[1].strip() if len(parts) > 1 else ""

                # ── Quit ──────────────────────────────────────────────────
                if cmd in ("quit", "exit", "q"):
                    console.print("\n  [dim]Saving and shutting down…[/dim]")
                    stop_evt.set()
                    break

                # ── Resource controls ──────────────────────────────────────

                elif cmd == "speed":
                    try:
                        n = max(1, min(10, int(arg)))
                        with ctrl_lock:
                            controls["speed"] = n
                        console.print(
                            f"  [dim]Speed {n}/10  [{_speed_bar(n)}]  "
                            f"({_SPEED_TABLE.get(n,0)*1000:.0f}ms between batches)[/dim]"
                        )
                    except (ValueError, TypeError):
                        console.print("  [dim]Usage: speed N  (1=slow … 10=max)[/dim]")

                elif cmd == "batch":
                    try:
                        n = max(1, min(500, int(arg)))
                        with ctrl_lock:
                            controls["batch"] = n
                        console.print(
                            f"  [dim]Batch size {n} — "
                            f"processing {n} items per tick before yielding.[/dim]"
                        )
                    except (ValueError, TypeError):
                        console.print(
                            "  [dim]Usage: batch N  (e.g. batch 50 for heavier use)[/dim]"
                        )

                elif cmd == "memory":
                    try:
                        n = max(100, int(arg))
                        with ctrl_lock:
                            controls["memory"] = n
                        try:
                            brain.memory._working.capacity = n
                        except Exception:
                            pass
                        console.print(f"  [dim]Working memory set to {n} slots.[/dim]")
                    except (ValueError, TypeError):
                        console.print("  [dim]Usage: memory N  (e.g. memory 500)[/dim]")

                elif cmd == "fetch":
                    try:
                        n = max(1, int(arg))
                        with ctrl_lock:
                            controls["fetch_topics"] = n
                        console.print(f"  [dim]Fetch depth {n} topics per cycle.[/dim]")
                    except (ValueError, TypeError):
                        console.print("  [dim]Usage: fetch N  (e.g. fetch 8)[/dim]")

                elif cmd == "explore":
                    with ctrl_lock:
                        controls["explore_flag"] = True
                    console.print(
                        "  [dim]Breaking current topic — new direction next batch.[/dim]"
                    )

                # ── Knowledge / reflection commands ────────────────────────

                elif cmd == "reflect":
                    console.print("  [dim]Reflecting…[/dim]")
                    try:
                        rep     = brain.reflect(cycle=brain.cycle_count)
                        summary = rep.get("summary", "")
                        _print_genesis(
                            summary or "I reflected but nothing crystallised yet."
                        )
                    except Exception as e:
                        console.print(f"  [dim]reflect error: {e}[/dim]")

                elif cmd == "thoughts":
                    try:
                        latest = brain.latest_reflection()
                        if latest:
                            _print_genesis(latest["summary"])
                        else:
                            _print_genesis(
                                "I haven't had time to reflect yet. "
                                "Type 'reflect' to trigger one."
                            )
                    except Exception:
                        _print_genesis("I can't retrieve my thoughts right now.")

                elif cmd == "curiosity":
                    try:
                        report = brain.curiosity_report()
                        if report:
                            topics = ", ".join(r["concept"] for r in report[:5])
                            _print_genesis(f"I most want to understand: {topics}.")
                        else:
                            _print_genesis("I haven't formed strong curiosity targets yet.")
                    except Exception:
                        _print_genesis("I can't access my curiosity targets right now.")

                elif cmd == "learn":
                    with ctrl_lock:
                        n = int(arg) if arg.isdigit() else controls["fetch_topics"]
                    console.print(f"  [dim]Fetching {n} topics…[/dim]")
                    try:
                        res     = brain.fetch_knowledge(n_topics=n, verbose=False)
                        fetched = res.get("topics_fetched", [])
                        _print_genesis(
                            f"I read about {', '.join(fetched[:3])}."
                            if fetched else "Nothing new came back from that search."
                        )
                    except Exception as e:
                        console.print(f"  [dim]learn error: {e}[/dim]")

                elif cmd == "status":
                    try:
                        s = brain.full_status()
                        d = brain.drives.summary()
                        with ctrl_lock:
                            sp = controls["speed"]
                            bt = controls["batch"]
                        _print_genesis(
                            f"Cycle {s['cycles']:,}. "
                            f"{s['memory']['total_stored']:,} memories, "
                            f"{s.get('relations',{}).get('total_relations',0):,} associations. "
                            f"Drives: {d['dominant']} {d['dominant_level']:.2f}, "
                            f"wanting {d['wanting']:+.2f}. "
                            f"Speed {sp}/10 × batch {bt} "
                            f"({_last_cps:.0f} cycles/s)."
                        )
                    except Exception as e:
                        console.print(f"  [dim]status error: {e}[/dim]")

                elif cmd == "save":
                    try:
                        brain.save_session()
                        console.print("  [dim]Session saved.[/dim]")
                    except Exception:
                        console.print("  [dim]Save failed.[/dim]")

                elif cmd in ("history", "relations", "summary"):
                    _handle_raw_command(brain, cmd, arg)

                else:
                    try:
                        reply = brain.voice.chat_respond(raw)
                        _print_genesis(
                            reply if reply else
                            "I heard you. I'm still forming a response — "
                            "try 'reflect' to help me consolidate."
                        )
                    except Exception:
                        _print_genesis(
                            "Something disrupted my response. "
                            "I'm still thinking in the background."
                        )

            time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        try:
            brain.save_session()
        except Exception:
            pass
        console.print()
        _divider()
        console.print("  [dim]Genesis is resting. Memory saved.[/dim]")
        _divider()
        console.print()


def _handle_raw_command(brain, cmd: str, arg: str) -> None:
    try:
        if cmd == "summary":
            s = brain.full_status()
            m = s.get("memory", {})
            r = s.get("relations", {})
            _print_genesis(
                f"Cycles: {s['cycles']:,}  "
                f"Memories: {m.get('total_stored',0):,}  "
                f"Relations: {r.get('total_relations',0):,}  "
                f"Inferences: {s.get('inference',{}).get('total_inferences',0):,}"
            )

        elif cmd == "history":
            entries = brain.consolidation.history(limit=5)
            if not entries:
                _print_genesis("No reflection history yet.")
            else:
                for e in reversed(entries[-3:]):
                    salient  = e.get("salient", [])
                    concepts = ", ".join(
                        (s["concept"] if isinstance(s, dict) else str(s))
                        for s in salient[:4]
                    )
                    _print_genesis(f"Reflected on: {concepts}")

        elif cmd == "relations":
            if arg:
                try:
                    rels = brain.relations.query_subject(arg, min_confidence=0.3)
                    if rels:
                        desc = "; ".join(
                            f"{r['relation']} {r['object']} ({r['confidence']:.2f})"
                            for r in rels[:5]
                        )
                        _print_genesis(f"{arg}: {desc}")
                    else:
                        _print_genesis(f"No associations for '{arg}' yet.")
                except Exception:
                    _print_genesis(f"Can't look up '{arg}' right now.")
            else:
                _print_genesis("Use 'relations:concept' to look up a specific concept.")

        else:
            _print_genesis(
                f"Command '{cmd}' not available here. "
                "Try: status  thoughts  curiosity  reflect  history  relations"
            )
    except Exception as e:
        console.print(f"  [dim]command error: {e}[/dim]")


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Genesis Chat UI")
    ap.add_argument("--resume",        action="store_true",
                    help="Resume from last saved session")
    ap.add_argument("--self-directed", action="store_true",
                    help="Genesis autonomously fetches Wikipedia on curiosity targets")
    ap.add_argument("--fetch-topics",  type=int, default=3,
                    help="Topics to fetch per curiosity cycle (default 3)")
    ap.add_argument("--db",            default=None,
                    help="Path to memory DB (default: data/genesis_memory.db)")
    ap.add_argument("--speed",         type=int, default=8,
                    help="Cycle speed 1–10 (default 8, almost no sleep)")
    ap.add_argument("--batch",         type=int, default=10,
                    help="Items processed per inner loop tick (default 10)")
    args = ap.parse_args()

    from orchestrator.orchestrator import Orchestrator

    brain = Orchestrator(
        verbose=False,
        db_path=args.db,
        resume=args.resume,
    )

    if not args.resume:
        console.print("\n  [dim]Building foundation — this takes about a minute…[/dim]")
        from curriculum.open_stage import advance_to_open
        advance_to_open(brain)
        brain.save_session()
        console.print("  [dim]Foundation complete.[/dim]\n")
    else:
        if brain.curriculum.current_stage.value < 4:
            from curriculum.open_stage import advance_to_open
            advance_to_open(brain)

    run(
        brain,
        self_directed=args.self_directed,
        fetch_topics=args.fetch_topics,
        initial_speed=max(1, min(10, args.speed)),
        initial_batch=max(1, min(500, args.batch)),
    )


# ── Colour / style tokens ─────────────────────────────────────────────────

_C_GENESIS     = "bold cyan"
_C_USER        = "bold white"
_C_STATUS      = "dim"
_C_DIVIDER     = "bright_black"
_C_DRIVE_OK    = "green"
_C_DRIVE_HI    = "yellow"
_C_DRIVE_ALARM = "bold red"

_WIDTH = 72

console = Console(highlight=False, soft_wrap=False)


# ── Speed table (1–10 → sleep seconds per cycle) ─────────────────────────

_SPEED_TABLE = {
    1:  0.50,
    2:  0.25,
    3:  0.10,
    4:  0.05,
    5:  0.02,
    6:  0.01,
    7:  0.005,
    8:  0.002,
    9:  0.001,
    10: 0.000,
}


# ── Helpers ───────────────────────────────────────────────────────────────

def _wrap(text: str, indent: int = 12) -> str:
    prefix = " " * indent
    lines = textwrap.wrap(text, width=_WIDTH - indent)
    if not lines:
        return ""
    return ("\n" + prefix).join(lines)


def _drive_colour(action: str) -> str:
    if action == "alarm":       return _C_DRIVE_ALARM
    if action == "explore":     return _C_DRIVE_OK
    if action == "rest":        return "blue"
    if action == "consolidate": return "cyan"
    return _C_STATUS


def _speed_bar(speed: int) -> str:
    filled = "█" * speed
    empty  = "░" * (10 - speed)
    return filled + empty


def _print_status(cycle: int, drives: dict, topic: str, controls: dict) -> None:
    action  = drives.get("seed_action", "idle")
    wanting = drives.get("wanting",     0.0)
    emp     = drives.get("empowerment", 0.0)
    speed   = controls.get("speed",    5)
    colour  = _drive_colour(action)

    parts = [
        f"[{_C_STATUS}]cycle {cycle:,}[/{_C_STATUS}]",
        f"[{colour}]{action}[/{colour}]",
        f"[{_C_STATUS}]want {wanting:+.2f}  opt {emp:.2f}[/{_C_STATUS}]",
        f"[{_C_STATUS}]spd [{_speed_bar(speed)}][/{_C_STATUS}]",
    ]
    if topic:
        short = topic[:28] + "…" if len(topic) > 28 else topic
        parts.append(f"[{_C_STATUS}]reading: {short}[/{_C_STATUS}]")

    console.print("  " + "  ·  ".join(parts))


def _print_genesis(text: str) -> None:
    wrapped = _wrap(text, indent=12)
    console.print(f"\n  [bold cyan]Genesis[/bold cyan]  [dim]❯[/dim]  {wrapped}\n")


def _print_user(text: str) -> None:
    wrapped = _wrap(text, indent=12)
    console.print(f"  [bold white]You[/bold white]     [dim]❯[/dim]  {wrapped}")


def _divider() -> None:
    console.print(Rule(style=_C_DIVIDER))


def _header() -> None:
    console.print()
    _divider()
    console.print(
        "  [bold cyan]G E N E S I S[/bold cyan]"
        "  [dim]— thinking and learning continuously[/dim]"
    )
    _divider()
    console.print(
        "  [dim]Talk normally or use a command:[/dim]"
    )
    console.print(
        "  [dim]  [white]reflect  thoughts  curiosity  status  save  quit[/white][/dim]"
    )
    console.print(
        "  [dim]  Resources (live): "
        "[white]speed N[/white] (1–10)  "
        "[white]memory N[/white]  "
        "[white]fetch N[/white]  "
        "[white]explore[/white] (new topic)[/dim]"
    )
    _divider()
    console.print()


# ── Main UI loop ──────────────────────────────────────────────────────────

def run(brain, self_directed: bool = False, fetch_topics: int = 3,
        initial_speed: int = 5):
    """
    Run the Genesis chat UI.

    Brain processes cycles in a background thread.
    This thread owns the terminal.
    """
    brain.verbose = False

    # Build input stream
    if brain.curriculum.current_stage.value >= 4:
        from curriculum.adaptive_stream import AdaptiveStream
        stream = AdaptiveStream(brain)
    else:
        from curriculum.open_stage import DataStream
        stream = DataStream()

    # ── Shared controls (adjusted by user commands at runtime) ────────────
    # Background thread reads these; main thread writes them under lock.

    try:
        _mem_cap = brain.memory._working.capacity
    except Exception:
        _mem_cap = 5000

    ctrl_lock = threading.Lock()
    controls = {
        "speed":         initial_speed,
        "memory":        _mem_cap,
        "fetch_topics":  fetch_topics,
        "explore_flag":  False,   # set True to force topic reset
    }

    # ── Queues ────────────────────────────────────────────────────────────

    input_q:      queue.Queue = queue.Queue()
    expression_q: queue.Queue = queue.Queue()
    status_q:     queue.Queue = queue.Queue(maxsize=1)
    stop_evt = threading.Event()

    # ── Background brain thread ───────────────────────────────────────────

    def _brain_loop():
        cycles       = 0
        last_fetch   = 0
        last_reflect = 0
        last_save    = time.time()
        current_topic = ""

        _REFLECT_EVERY = 400
        _AUTOSAVE      = 120.0

        # Silence direct stdout output from voice system
        try:
            from output.channel import NullChannel
            brain.voice.set_channel(NullChannel())
        except Exception:
            pass

        while not stop_evt.is_set():
            try:
                with ctrl_lock:
                    speed        = controls["speed"]
                    n_fetch      = controls["fetch_topics"]
                    do_explore   = controls["explore_flag"]
                    if do_explore:
                        controls["explore_flag"] = False

                cycle_sleep  = _SPEED_TABLE.get(speed, 0.02)
                fetch_every  = max(10, 80 - speed * 7)  # 73→10 cycles between fetches

                # Force new curiosity topic when user asked for it.
                # Fixation lives in the curiosity-directive frontier; clearing
                # it lets fresh input repopulate the targets (memory is untouched
                # — long-term store keeps everything).
                if do_explore:
                    try:
                        brain._curiosity_directives.clear()
                        brain._save_directives()
                    except Exception:
                        pass
                    current_topic = ""

                item   = stream.next()
                result = brain.process_input(item["type"], item["data"])
                cycles += 1

                # Collect spontaneous expressions
                try:
                    expr = brain.drives.expressive_state()
                    if expr and cycles % 40 == 0:
                        expression_q.put(("genesis", expr))
                except Exception:
                    pass

                # Push status
                drives = result.get("drives", {})
                try:
                    status_q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    with ctrl_lock:
                        ctrl_snap = dict(controls)
                    status_q.put_nowait({
                        "cycle":    brain.cycle_count,
                        "drives":   drives,
                        "topic":    current_topic,
                        "controls": ctrl_snap,
                    })
                except queue.Full:
                    pass

                # Periodic: self-directed web fetch
                if self_directed and (cycles - last_fetch) >= fetch_every:
                    try:
                        res = brain.fetch_knowledge(n_topics=n_fetch, verbose=False)
                        fetched = res.get("topics_fetched", [])
                        if fetched:
                            current_topic = fetched[0]
                            expression_q.put(("status", f"Reading: {current_topic}"))
                    except Exception:
                        pass
                    last_fetch = cycles

                # Periodic: consolidation
                if (cycles - last_reflect) >= _REFLECT_EVERY:
                    try:
                        rep = brain.reflect(cycle=cycles)
                        summary = rep.get("summary", "")
                        if summary:
                            expression_q.put(("genesis", summary))
                    except Exception:
                        pass
                    last_reflect = cycles

                # Periodic: auto-save
                if (time.time() - last_save) >= _AUTOSAVE:
                    try:
                        brain.save_session()
                        last_save = time.time()
                    except Exception:
                        pass

                if cycle_sleep > 0:
                    time.sleep(cycle_sleep)

            except Exception:
                time.sleep(0.1)

    brain_thread = threading.Thread(target=_brain_loop, daemon=True)
    brain_thread.start()

    # ── Stdin reader thread ───────────────────────────────────────────────

    def _read_stdin():
        while not stop_evt.is_set():
            try:
                line = input()
                input_q.put(line)
            except EOFError:
                stop_evt.set()
            except Exception:
                pass

    stdin_thread = threading.Thread(target=_read_stdin, daemon=True)
    stdin_thread.start()

    # ── Display loop (main thread) ────────────────────────────────────────

    _header()

    try:
        greeting = brain.voice.wake_greeting()
        if greeting:
            _print_genesis(greeting)
    except Exception:
        _print_genesis("I'm awake. Give me a moment to settle.")

    last_status_print = 0.0
    _STATUS_INTERVAL  = 30.0
    _last_controls    = dict(controls)

    try:
        while not stop_evt.is_set():

            # Drain expressions
            while not expression_q.empty():
                try:
                    kind, text = expression_q.get_nowait()
                    if kind == "genesis":
                        _print_genesis(text)
                    else:
                        console.print(f"  [dim]{text}[/dim]")
                except queue.Empty:
                    break

            # Periodic status
            now = time.time()
            if (now - last_status_print) >= _STATUS_INTERVAL:
                try:
                    st = status_q.get_nowait()
                    _print_status(st["cycle"], st["drives"],
                                  st.get("topic", ""), st.get("controls", controls))
                    last_status_print = now
                except queue.Empty:
                    pass

            # User input
            if not input_q.empty():
                raw = input_q.get_nowait().strip()
                if not raw:
                    continue

                _print_user(raw)

                # Parse "command arg" or "command:arg"
                if ":" in raw:
                    cmd, _, arg = raw.partition(":")
                    cmd = cmd.strip().lstrip("/").lower()
                    arg = arg.strip()
                else:
                    parts = raw.lstrip("/").split(None, 1)
                    cmd = parts[0].lower()
                    arg = parts[1].strip() if len(parts) > 1 else ""

                # ── Quit ─────────────────────────────────────────────────
                if cmd in ("quit", "exit", "q"):
                    console.print("\n  [dim]Saving and shutting down…[/dim]")
                    stop_evt.set()
                    break

                # ── Resource controls ─────────────────────────────────────

                elif cmd == "speed":
                    try:
                        n = int(arg)
                        n = max(1, min(10, n))
                        with ctrl_lock:
                            controls["speed"] = n
                        bar = _speed_bar(n)
                        console.print(
                            f"  [dim]Speed set to {n}/10  [{bar}][/dim]"
                        )
                    except (ValueError, TypeError):
                        console.print(
                            "  [dim]Usage: speed N  where N is 1 (slow) to 10 (max)[/dim]"
                        )

                elif cmd == "memory":
                    try:
                        n = max(10, int(arg))
                        with ctrl_lock:
                            controls["memory"] = n
                        try:
                            brain.memory._working.capacity = n
                        except Exception:
                            pass
                        console.print(f"  [dim]Working memory set to {n} slots.[/dim]")
                    except (ValueError, TypeError):
                        console.print("  [dim]Usage: memory N  (e.g. memory 50)[/dim]")

                elif cmd == "fetch":
                    try:
                        n = max(1, int(arg))
                        with ctrl_lock:
                            controls["fetch_topics"] = n
                        console.print(f"  [dim]Fetch depth set to {n} topics per cycle.[/dim]")
                    except (ValueError, TypeError):
                        console.print("  [dim]Usage: fetch N  (e.g. fetch 5)[/dim]")

                elif cmd == "explore":
                    with ctrl_lock:
                        controls["explore_flag"] = True
                    console.print(
                        "  [dim]Breaking out of current topic — new direction next cycle.[/dim]"
                    )

                # ── Knowledge / reflection commands ───────────────────────

                elif cmd == "reflect":
                    console.print("  [dim]Reflecting…[/dim]")
                    try:
                        rep     = brain.reflect(cycle=brain.cycle_count)
                        summary = rep.get("summary", "")
                        _print_genesis(summary or "I reflected but nothing crystallised yet.")
                    except Exception as e:
                        console.print(f"  [dim]reflect error: {e}[/dim]")

                elif cmd == "thoughts":
                    try:
                        latest = brain.latest_reflection()
                        if latest:
                            _print_genesis(latest["summary"])
                        else:
                            _print_genesis(
                                "I haven't had time to reflect yet. "
                                "Type 'reflect' to trigger one."
                            )
                    except Exception:
                        _print_genesis("I can't retrieve my thoughts right now.")

                elif cmd == "curiosity":
                    try:
                        report = brain.curiosity_report()
                        if report:
                            topics = ", ".join(r["concept"] for r in report[:5])
                            _print_genesis(f"I most want to understand: {topics}.")
                        else:
                            _print_genesis("I haven't formed strong curiosity targets yet.")
                    except Exception:
                        _print_genesis("I can't access my curiosity targets right now.")

                elif cmd == "learn":
                    with ctrl_lock:
                        n = int(arg) if arg.isdigit() else controls["fetch_topics"]
                    console.print(f"  [dim]Fetching {n} topics…[/dim]")
                    try:
                        res = brain.fetch_knowledge(n_topics=n, verbose=False)
                        fetched = res.get("topics_fetched", [])
                        _print_genesis(
                            f"I read about {', '.join(fetched[:3])}."
                            if fetched else "Nothing new came back from that search."
                        )
                    except Exception as e:
                        console.print(f"  [dim]learn error: {e}[/dim]")

                elif cmd == "status":
                    try:
                        s = brain.full_status()
                        d = brain.drives.summary()
                        with ctrl_lock:
                            sp = controls["speed"]
                        _print_genesis(
                            f"Cycle {s['cycles']:,}. "
                            f"{s['memory']['total_stored']:,} memories, "
                            f"{s.get('relations', {}).get('total_relations', 0):,} associations. "
                            f"Drives: {d['dominant']} at {d['dominant_level']:.2f}, "
                            f"wanting {d['wanting']:+.2f}. "
                            f"Speed {sp}/10."
                        )
                    except Exception as e:
                        console.print(f"  [dim]status error: {e}[/dim]")

                elif cmd == "save":
                    try:
                        brain.save_session()
                        console.print("  [dim]Session saved.[/dim]")
                    except Exception:
                        console.print("  [dim]Save failed.[/dim]")

                elif cmd in ("history", "relations", "summary"):
                    _handle_raw_command(brain, cmd, arg)

                else:
                    # Conversation
                    try:
                        reply = brain.voice.chat_respond(raw)
                        _print_genesis(
                            reply if reply else
                            "I heard you. I'm still forming a response — "
                            "try 'reflect' to help me consolidate."
                        )
                    except Exception:
                        _print_genesis(
                            "Something disrupted my response. "
                            "I'm still thinking in the background."
                        )

            time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        try:
            brain.save_session()
        except Exception:
            pass
        console.print()
        _divider()
        console.print("  [dim]Genesis is resting. Memory saved.[/dim]")
        _divider()
        console.print()


def _handle_raw_command(brain, cmd: str, arg: str) -> None:
    try:
        if cmd == "summary":
            s = brain.full_status()
            m = s.get("memory", {})
            r = s.get("relations", {})
            _print_genesis(
                f"Cycles: {s['cycles']:,}  "
                f"Memories: {m.get('total_stored', 0):,}  "
                f"Relations: {r.get('total_relations', 0):,}  "
                f"Inferences: {s.get('inference', {}).get('total_inferences', 0):,}"
            )

        elif cmd == "history":
            entries = brain.consolidation.history(limit=5)
            if not entries:
                _print_genesis("No reflection history yet.")
            else:
                for e in reversed(entries[-3:]):
                    salient  = e.get("salient", [])
                    concepts = ", ".join(
                        (s["concept"] if isinstance(s, dict) else str(s))
                        for s in salient[:4]
                    )
                    _print_genesis(f"Reflected on: {concepts}")

        elif cmd == "relations":
            if arg:
                try:
                    rels = brain.relations.query_subject(arg, min_confidence=0.3)
                    if rels:
                        desc = "; ".join(
                            f"{r['relation']} {r['object']} ({r['confidence']:.2f})"
                            for r in rels[:5]
                        )
                        _print_genesis(f"{arg}: {desc}")
                    else:
                        _print_genesis(f"No associations for '{arg}' yet.")
                except Exception:
                    _print_genesis(f"Can't look up '{arg}' right now.")
            else:
                _print_genesis("Use 'relations:concept' to look up a specific concept.")

        else:
            _print_genesis(
                f"Command '{cmd}' not available here. "
                "Try: status  thoughts  curiosity  reflect  history  relations"
            )
    except Exception as e:
        console.print(f"  [dim]command error: {e}[/dim]")


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Genesis Chat UI")
    ap.add_argument("--resume",        action="store_true",
                    help="Resume from last saved session")
    ap.add_argument("--self-directed", action="store_true",
                    help="Genesis autonomously fetches Wikipedia on curiosity targets")
    ap.add_argument("--fetch-topics",  type=int, default=3,
                    help="Topics to fetch per curiosity cycle (default 3)")
    ap.add_argument("--db",            default=None,
                    help="Path to memory DB (default: genesis.db in src/)")
    ap.add_argument("--speed",         type=int, default=5,
                    help="Initial cycle speed 1–10 (default 5)")
    args = ap.parse_args()

    from orchestrator.orchestrator import Orchestrator

    brain = Orchestrator(
        verbose=False,
        db_path=args.db,
        resume=args.resume,
    )

    if not args.resume:
        console.print("\n  [dim]Building foundation — this takes about a minute…[/dim]")
        from curriculum.open_stage import advance_to_open
        advance_to_open(brain)
        brain.save_session()
        console.print("  [dim]Foundation complete.[/dim]\n")
    else:
        if brain.curriculum.current_stage.value < 4:
            from curriculum.open_stage import advance_to_open
            advance_to_open(brain)

    run(
        brain,
        self_directed=args.self_directed,
        fetch_topics=args.fetch_topics,
        initial_speed=max(1, min(10, args.speed)),
    )
