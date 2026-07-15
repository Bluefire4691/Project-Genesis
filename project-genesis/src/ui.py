#!/usr/bin/env python3
"""
Genesis Chat UI

Clean terminal interface. Background thinking is silent.
Only Genesis's expressions and the conversation are visible.

Run:
    python ui.py
    python ui.py --resume --self-directed --speed 9 --batch 20

Architecture (why it's responsive):
    - Cognition runs on its own thread in tight batches. It NEVER blocks
      on the network.
    - Web fetching runs on a SEPARATE thread. It is slow (HTTP + polite
      rate-limit sleeps), so keeping it off the cognition thread is what
      lets the CPU stay busy thinking instead of waiting.
    - A single reentrant lock serialises all brain access across threads
      (the brain's SQLite conn is check_same_thread=False, safe when
      serialised).

Resource commands (adjustable while running):
    speed N     — 1 (slowest) to 10 (max). Default 8.
    batch N     — items processed per tick, no sleep between them. Default 10.
    memory N    — working-memory slots. Larger = wider attention but slower
                  per cycle (attention is re-sorted each cycle). 300–1500 is
                  a good range; very large values hurt throughput.
    fetch N     — topics pulled per web-fetch. Default 2.
    explore     — break out of current topic fixation (clears the curiosity
                  frontier; long-term memory is untouched).
"""

import os
import sys
import time
import queue
import threading
import textwrap
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(__file__))

from rich.console import Console
from rich.rule import Rule


class _Busy(Exception):
    """Raised when the brain lock can't be acquired in time (mid web-fetch)."""

# ── Colour / style tokens ─────────────────────────────────────────────────

_C_STATUS      = "dim"
_C_DIVIDER     = "bright_black"
_C_DRIVE_OK    = "green"
_C_DRIVE_ALARM = "bold red"

_WIDTH = 72

console = Console(highlight=False, soft_wrap=False)


# ── Speed table (1–10 → sleep seconds BETWEEN batches) ───────────────────

_SPEED_TABLE = {
    1:  0.500, 2:  0.200, 3:  0.100, 4:  0.050, 5:  0.020,
    6:  0.010, 7:  0.005, 8:  0.001, 9:  0.000, 10: 0.000,
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
    console.print(f"\n  [bold cyan]Genesis[/bold cyan]  [dim]❯[/dim]  {_wrap(text)}\n")


def _print_user(text: str) -> None:
    console.print(f"  [bold white]You[/bold white]     [dim]❯[/dim]  {_wrap(text)}")


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
    console.print("  [dim]  Resources (live, type while running):[/dim]")
    console.print(
        "  [dim]    [white]speed N[/white] 1–10  "
        "[white]batch N[/white] items/tick  "
        "[white]memory N[/white]  "
        "[white]fetch N[/white]  "
        "[white]explore[/white][/dim]"
    )
    _divider()
    console.print()


def _fetched_topics(res: dict) -> list:
    """fetch_knowledge reports under topics_succeeded/topics_attempted."""
    return (res.get("topics_succeeded")
            or res.get("topics_attempted")
            or [])


# ── Main UI loop ──────────────────────────────────────────────────────────

def run(brain, self_directed: bool = False, fetch_topics: int = 2,
        initial_speed: int = 8, initial_batch: int = 10):
    """Run the Genesis chat UI."""
    brain.verbose = False

    if brain.curriculum.current_stage.value >= 4:
        from curriculum.adaptive_stream import AdaptiveStream
        stream = AdaptiveStream(brain)
    else:
        from curriculum.open_stage import DataStream
        stream = DataStream()

    try:
        _mem_cap = brain.memory._working.capacity
    except Exception:
        _mem_cap = 5000

    ctrl_lock  = threading.Lock()
    # Serialises ALL brain access across cognition, fetcher, and command
    # handlers. Brain's SQLite conn is check_same_thread=False — safe while
    # access is serialised. Reentrant so a holder can call helpers that
    # re-acquire.
    brain_lock = threading.RLock()

    @contextmanager
    def _access(timeout: float = 2.5):
        """Acquire the brain lock or raise _Busy. Keeps the UI from ever
        freezing behind a slow web fetch."""
        if not brain_lock.acquire(timeout=timeout):
            raise _Busy
        try:
            yield
        finally:
            brain_lock.release()

    controls = {
        "speed":        initial_speed,
        "batch":        initial_batch,
        "memory":       _mem_cap,
        "fetch_topics": fetch_topics,
        "explore_flag": False,
    }

    input_q:      queue.Queue = queue.Queue()
    expression_q: queue.Queue = queue.Queue()
    status_q:     queue.Queue = queue.Queue(maxsize=1)
    stop_evt = threading.Event()

    _fetch_state: dict = {"topic": ""}   # fetcher → status line

    # ── Cognition thread — pure thinking, never touches the network ───────

    def _brain_loop():
        cycles       = 0
        last_reflect = 0
        last_save    = time.time()
        last_result  = {}

        _tput_t0    = time.perf_counter()
        _tput_count = 0
        cyc_per_sec = 0.0
        _last_status_calc = 0.0
        _drives_snapshot: dict = {}
        _last_err_log = 0.0

        _REFLECT_EVERY = 400
        _AUTOSAVE      = 120.0

        try:
            from output.channel import NullChannel
            brain.voice.set_channel(NullChannel())
        except Exception:
            pass

        while not stop_evt.is_set():
            try:
                with ctrl_lock:
                    speed      = controls["speed"]
                    batch_size = max(1, controls["batch"])
                    do_explore = controls["explore_flag"]
                    if do_explore:
                        controls["explore_flag"] = False

                cycle_sleep = _SPEED_TABLE.get(speed, 0.001)

                # Explore: clear curiosity frontier (memory untouched)
                if do_explore:
                    try:
                        with brain_lock:
                            brain._curiosity_directives.clear()
                            brain._save_directives()
                    except Exception:
                        pass
                    _fetch_state["topic"] = ""

                # Tight inner batch. Lock held per-cycle then released so the
                # fetcher and command handlers can interleave.
                for _ in range(batch_size):
                    if stop_evt.is_set():
                        break
                    try:
                        with brain_lock:
                            item        = stream.next()
                            last_result = brain.process_input(item["type"], item["data"])
                    except Exception as exc:
                        # Errors are data — log at most once per second so a
                        # persistent failure can't flood from a tight loop.
                        if (time.monotonic() - _last_err_log) >= 1.0:
                            _last_err_log = time.monotonic()
                            try:
                                brain.survival.resilience.error_log.log(
                                    "ui.cognition_loop", exc)
                            except Exception:
                                pass
                        continue
                    cycles      += 1
                    _tput_count += 1

                now = time.perf_counter()
                if (now - _tput_t0) >= 5.0:
                    cyc_per_sec = _tput_count / (now - _tput_t0)
                    _tput_t0    = now
                    _tput_count = 0

                # Spontaneous expression
                try:
                    if cycles % 40 < batch_size:
                        with brain_lock:
                            expr = brain.drives.expressive_state()
                        if expr:
                            expression_q.put(("genesis", expr))
                except Exception:
                    pass

                # Status — drives come from drives.summary(), not from the
                # process_input result (which only carries the M34 seed
                # drives, not the five biological drives). Throttled to 1/s.
                if (time.monotonic() - _last_status_calc) >= 1.0:
                    _last_status_calc = time.monotonic()
                    try:
                        with brain_lock:
                            _drives_snapshot = brain.drives.summary()
                    except Exception:
                        _drives_snapshot = last_result.get("drives", {})
                drives = _drives_snapshot
                try:
                    status_q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    with ctrl_lock:
                        ctrl_snap = dict(controls)
                    status_q.put_nowait({
                        "cycle":       brain.cycle_count,
                        "drives":      drives,
                        "topic":       _fetch_state.get("topic", ""),
                        "controls":    ctrl_snap,
                        "cyc_per_sec": cyc_per_sec,
                    })
                except queue.Full:
                    pass

                # Periodic consolidation
                if (cycles - last_reflect) >= _REFLECT_EVERY:
                    try:
                        with brain_lock:
                            rep = brain.reflect(cycle=cycles)
                        summary = rep.get("summary", "")
                        if summary:
                            expression_q.put(("genesis", summary))
                    except Exception:
                        pass
                    last_reflect = cycles

                # Periodic auto-save
                if (time.time() - last_save) >= _AUTOSAVE:
                    try:
                        with brain_lock:
                            brain.save_session()
                        last_save = time.time()
                    except Exception:
                        pass

                if cycle_sleep > 0:
                    time.sleep(cycle_sleep)

            except Exception:
                time.sleep(0.1)

    # ── Fetcher thread — slow web I/O, isolated from cognition ────────────

    def _fetcher_loop():
        if not self_directed:
            return
        # First fetch after a short warm-up so cognition settles first.
        stop_evt.wait(8.0)
        while not stop_evt.is_set():
            # Defer if the user is mid-conversation — keep the lock free for
            # the UI so commands stay snappy.
            if not input_q.empty():
                stop_evt.wait(1.5)
                continue
            with ctrl_lock:
                n_fetch = controls["fetch_topics"]
            try:
                # Holds the brain lock for the fetch (network + ingest).
                # Cognition pauses only for this window, then resumes flat-out.
                with brain_lock:
                    res = brain.fetch_knowledge(n_topics=n_fetch, verbose=False)
                topics = _fetched_topics(res)
                added  = res.get("relations_added", 0)
                if topics:
                    _fetch_state["topic"] = topics[0]
                    msg = f"Read about {', '.join(topics[:3])}"
                    if added:
                        msg += f"  (+{added} associations)"
                    expression_q.put(("status", msg))
            except Exception as exc:
                try:
                    brain.survival.resilience.error_log.log(
                        "ui.fetcher_loop", exc)
                except Exception:
                    pass
            # Space fetches out so cognition gets long uninterrupted runs.
            stop_evt.wait(20.0)

    threading.Thread(target=_brain_loop,   daemon=True).start()
    threading.Thread(target=_fetcher_loop, daemon=True).start()

    # ── Stdin reader thread ───────────────────────────────────────────────

    def _read_stdin():
        while not stop_evt.is_set():
            try:
                input_q.put(input())
            except EOFError:
                stop_evt.set()
            except Exception:
                pass

    threading.Thread(target=_read_stdin, daemon=True).start()

    # ── Display loop (main thread) ────────────────────────────────────────

    _header()

    try:
        with _access(timeout=10.0):
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

            while not expression_q.empty():
                try:
                    kind, text = expression_q.get_nowait()
                    if kind == "genesis":
                        _print_genesis(text)
                    else:
                        console.print(f"  [dim]{text}[/dim]")
                except queue.Empty:
                    break

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

            if not input_q.empty():
                raw = input_q.get_nowait().strip()
                if not raw:
                    continue
                _print_user(raw)

                if ":" in raw:
                    cmd, _, arg = raw.partition(":")
                    cmd, arg = cmd.strip().lstrip("/").lower(), arg.strip()
                else:
                    parts = raw.lstrip("/").split(None, 1)
                    if not parts:      # input was all slashes — ignore
                        continue
                    cmd   = parts[0].lower()
                    arg   = parts[1].strip() if len(parts) > 1 else ""

                # Resource keywords only act as commands with a numeric (or
                # empty) argument — "memory is fascinating" is conversation,
                # "memory 800" is a command, bare "memory" prints usage.
                if (cmd in ("speed", "batch", "memory", "fetch", "learn")
                        and arg and not arg.isdigit()):
                    cmd = "__chat__"

                if cmd in ("quit", "exit", "q"):
                    console.print("\n  [dim]Saving and shutting down…[/dim]")
                    stop_evt.set()
                    break

                # ── Resource controls ─────────────────────────────────────
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
                        n = max(1, min(1000, int(arg)))
                        with ctrl_lock:
                            controls["batch"] = n
                        console.print(
                            f"  [dim]Batch {n} — {n} items per tick before yielding.[/dim]"
                        )
                    except (ValueError, TypeError):
                        console.print("  [dim]Usage: batch N  (e.g. batch 50)[/dim]")

                elif cmd == "memory":
                    try:
                        n = max(100, int(arg))
                        with ctrl_lock:
                            controls["memory"] = n
                        # Plain int assignment — no brain_lock needed, stays
                        # responsive even during a fetch. Cognition reads it
                        # fresh each cycle.
                        try:
                            brain.memory._working.capacity = n
                        except Exception:
                            pass
                        note = ""
                        if n > 3000:
                            note = "  (large — attention re-sorts each cycle, may slow throughput)"
                        console.print(f"  [dim]Working memory set to {n} slots.{note}[/dim]")
                    except (ValueError, TypeError):
                        console.print("  [dim]Usage: memory N  (300–1500 recommended)[/dim]")

                elif cmd == "fetch":
                    try:
                        n = max(1, int(arg))
                        with ctrl_lock:
                            controls["fetch_topics"] = n
                        console.print(f"  [dim]Fetch depth {n} topics per web cycle.[/dim]")
                    except (ValueError, TypeError):
                        console.print("  [dim]Usage: fetch N  (e.g. fetch 4)[/dim]")

                elif cmd == "explore":
                    with ctrl_lock:
                        controls["explore_flag"] = True
                    console.print(
                        "  [dim]Breaking current topic — new direction next batch.[/dim]"
                    )

                # ── Everything below needs the brain. Acquire with a short
                #    timeout so a slow web fetch can never freeze the UI.
                else:
                    # status reads can fall back to the last broadcast snapshot
                    # if the brain is busy, so it always answers something.
                    try:
                        if cmd == "status":
                            with _access():
                                s = brain.full_status()
                                d = brain.drives.summary()
                            with ctrl_lock:
                                sp, bt = controls["speed"], controls["batch"]
                            _print_genesis(
                                f"Cycle {s['cycles']:,}. "
                                f"{s['memory']['total_stored']:,} memories, "
                                f"{s.get('relations',{}).get('total_relations',0):,} associations. "
                                f"Drives: {d['dominant']} {d['dominant_level']:.2f}, "
                                f"wanting {d['wanting']:+.2f}. "
                                f"Speed {sp}/10 × batch {bt} ({_last_cps:.0f} cycles/s)."
                            )

                        elif cmd == "reflect":
                            console.print("  [dim]Reflecting…[/dim]")
                            with _access(timeout=10.0):
                                rep = brain.reflect(cycle=brain.cycle_count)
                            _print_genesis(rep.get("summary")
                                           or "I reflected but nothing crystallised yet.")

                        elif cmd == "thoughts":
                            with _access():
                                latest = brain.latest_reflection()
                            _print_genesis(latest["summary"] if latest
                                           else "I haven't reflected yet. Type 'reflect'.")

                        elif cmd == "curiosity":
                            with _access():
                                report = brain.curiosity_report()
                            if report:
                                topics = ", ".join(r["concept"] for r in report[:5])
                                _print_genesis(f"I most want to understand: {topics}.")
                            else:
                                _print_genesis("I haven't formed strong curiosity targets yet.")

                        elif cmd == "learn":
                            with ctrl_lock:
                                n = int(arg) if arg.isdigit() else controls["fetch_topics"]
                            console.print(f"  [dim]Fetching {n} topics…[/dim]")
                            with _access(timeout=60.0):
                                res = brain.fetch_knowledge(n_topics=n, verbose=False)
                            topics = _fetched_topics(res)
                            _print_genesis(
                                f"I read about {', '.join(topics[:3])}."
                                if topics else "Nothing new came back from that search."
                            )

                        elif cmd == "save":
                            with _access(timeout=10.0):
                                brain.save_session()
                            console.print("  [dim]Session saved.[/dim]")

                        elif cmd in ("history", "relations", "summary"):
                            with _access():
                                _handle_raw_command(brain, cmd, arg)

                        else:
                            with _access():
                                reply = brain.voice.chat_respond(raw)
                            _print_genesis(
                                reply if reply else
                                "I heard you. I'm still forming a response — "
                                "try 'reflect' to help me consolidate."
                            )

                    except _Busy:
                        console.print(
                            "  [dim]Genesis is deep in a web read right now — "
                            "give it a few seconds and ask again. "
                            "(speed / batch / explore still work instantly.)[/dim]"
                        )
                    except Exception as e:
                        console.print(f"  [dim]command error: {e}[/dim]")

            time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        try:
            # Best-effort save — don't hang shutdown behind an in-flight fetch.
            with _access(timeout=30.0):
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
    except Exception as e:
        console.print(f"  [dim]command error: {e}[/dim]")


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Genesis Chat UI")
    ap.add_argument("--resume",        action="store_true",
                    help="Resume from last saved session")
    ap.add_argument("--self-directed", action="store_true",
                    help="Genesis autonomously fetches the web on its curiosity targets")
    ap.add_argument("--fetch-topics",  type=int, default=2,
                    help="Topics to fetch per web cycle (default 2)")
    ap.add_argument("--db",            default=None,
                    help="Path to memory DB (default: data/genesis_memory.db)")
    ap.add_argument("--speed",         type=int, default=8,
                    help="Cycle speed 1–10 (default 8)")
    ap.add_argument("--batch",         type=int, default=10,
                    help="Items per inner loop tick (default 10)")
    args = ap.parse_args()

    from orchestrator.orchestrator import Orchestrator

    brain = Orchestrator(verbose=False, db_path=args.db, resume=args.resume)

    if not args.resume:
        console.print("\n  [dim]Building foundation — about a minute…[/dim]")
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
        initial_batch=max(1, min(1000, args.batch)),
    )
