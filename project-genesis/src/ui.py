#!/usr/bin/env python3
"""
Genesis Chat UI — terminal frontend.

Thin Rich renderer over the shared GenesisEngine (engine.py), which owns the
cognition thread, the fetcher thread, the lock discipline, and every command.
This file only reads stdin and paints the conversation.

Run:
    python ui.py
    python ui.py --resume --self-directed --speed 9 --batch 20

Live resource commands (type while it runs):
    speed N (1-10)   batch N   memory N   fetch N   explore
"""

import os
import sys
import time
import queue
import textwrap

sys.path.insert(0, os.path.dirname(__file__))

from rich.console import Console
from rich.rule import Rule

from engine import GenesisEngine, add_common_args, boot_brain

# ── Colour / style tokens ─────────────────────────────────────────────────

_C_STATUS      = "dim"
_C_DIVIDER     = "bright_black"
_C_DRIVE_OK    = "green"
_C_DRIVE_ALARM = "bold red"

_WIDTH = 72

console = Console(highlight=False, soft_wrap=False)


# ── Rendering helpers ─────────────────────────────────────────────────────

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


def _print_status(snap: dict) -> None:
    drives   = snap.get("drives", {})
    controls = snap.get("controls", {})
    action   = drives.get("seed_action", "idle")
    wanting  = drives.get("wanting",     0.0)
    colour   = _drive_colour(action)
    speed    = controls.get("speed",  8)
    batch    = controls.get("batch", 10)
    cps      = snap.get("cyc_per_sec", 0.0)
    topic    = snap.get("topic", "")

    cps_str = f"{cps:.0f}/s" if cps > 0 else "—"

    parts = [
        f"[{_C_STATUS}]cycle {snap.get('cycle', 0):,}[/{_C_STATUS}]",
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


def _print_system(text: str) -> None:
    console.print(f"  [dim]{text}[/dim]")


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


# ── Main UI loop ──────────────────────────────────────────────────────────

def run(brain, self_directed: bool = False, fetch_topics: int = 2,
        initial_speed: int = 8, initial_batch: int = 10):
    """Run the Genesis terminal UI over the shared engine."""

    input_q: queue.Queue = queue.Queue()   # stdin lines
    event_q: queue.Queue = queue.Queue()   # engine → display
    latest_status: dict  = {}

    engine = GenesisEngine(
        brain,
        self_directed=self_directed,
        fetch_topics=fetch_topics,
        speed=initial_speed,
        batch=initial_batch,
        on_genesis=lambda t: event_q.put(("genesis", t)),
        on_system=lambda t: event_q.put(("system", t)),
        on_status=lambda s: latest_status.update(s),
        user_active=lambda: not input_q.empty(),
    )
    engine.start()

    # Stdin reader thread
    import threading

    def _read_stdin():
        while True:
            try:
                input_q.put(input())
            except EOFError:
                input_q.put("quit")
                return
            except Exception:
                pass

    threading.Thread(target=_read_stdin, daemon=True).start()

    _header()
    _print_genesis(engine.greeting())

    last_status_print = 0.0
    _STATUS_INTERVAL  = 20.0

    try:
        while True:
            while not event_q.empty():
                try:
                    kind, text = event_q.get_nowait()
                    if kind == "genesis":
                        _print_genesis(text)
                    else:
                        _print_system(text)
                except queue.Empty:
                    break

            now = time.time()
            if latest_status and (now - last_status_print) >= _STATUS_INTERVAL:
                _print_status(latest_status)
                last_status_print = now

            if not input_q.empty():
                raw = input_q.get_nowait().strip()
                if not raw:
                    continue
                _print_user(raw)

                parsed = GenesisEngine.parse(raw)
                if parsed is None:      # input was all slashes — ignore
                    continue
                cmd, arg = parsed

                if GenesisEngine.is_quit(cmd, arg):
                    console.print("\n  [dim]Saving and shutting down…[/dim]")
                    break

                if GenesisEngine.is_local(cmd, arg):
                    _print_system(engine.run_local(cmd, arg))
                    continue

                # Brain commands run inline; the engine turns _Busy and
                # errors into system events, so this never raises.
                for kind, text in engine.run_command(cmd, arg, raw):
                    if kind == "genesis":
                        _print_genesis(text)
                    else:
                        _print_system(text)

            time.sleep(0.05)

    except KeyboardInterrupt:
        pass
    finally:
        saved = engine.stop(timeout=30.0)
        console.print()
        _divider()
        if saved:
            console.print("  [dim]Genesis is resting. Memory saved.[/dim]")
        else:
            console.print(
                "  [bold yellow]WARNING:[/bold yellow] [dim]could not save — "
                "state since the last autosave (up to 2 min) was lost.[/dim]"
            )
        _divider()
        console.print()


# ── Entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Genesis Chat UI")
    add_common_args(ap)
    args = ap.parse_args()

    brain = boot_brain(
        args, announce=lambda m: console.print(f"\n  [dim]{m}[/dim]"))

    run(
        brain,
        self_directed=args.self_directed,
        fetch_topics=args.fetch_topics,
        initial_speed=max(1, min(10, args.speed)),
        initial_batch=max(1, min(1000, args.batch)),
    )
