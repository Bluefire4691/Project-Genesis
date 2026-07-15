"""
GenesisEngine — the shared headless session engine behind every frontend.

Both frontends (ui.py terminal, gui.py desktop) previously carried their own
copy of the cognition loop, fetcher loop, speed table, lock discipline, and
command handlers — and the copies diverged within one commit.  This module is
the single implementation; frontends are thin renderers over it.

Responsibilities:
  - Cognition thread: tight batch processing, never touches the network.
    Throughput tracking, spontaneous expression, periodic reflection,
    periodic autosave, explore handling.
  - Fetcher thread: web I/O only, isolated so network latency can't stall
    cognition or the frontend.  Defers while the user is active.
  - Lock discipline: one RLock serialises all brain access; access() raises
    _Busy after a timeout instead of freezing the caller.
  - Live resource controls: speed / batch / memory / fetch-topics / explore.
  - Command execution: every brain command (status, reflect, learn, …)
    returns renderable (kind, text) events; frontends decide presentation.

Frontends provide callbacks:
    on_genesis(text)   — Genesis expressed something
    on_system(text)    — quiet status note
    on_status(dict)    — ~1 Hz snapshot: cycle, drives, topic, controls,
                         cyc_per_sec, concepts
    user_active()      — True while the user is typing / a command is in
                         flight; the fetcher defers so chat stays snappy

Callbacks fire on engine threads — frontends must marshal to their own
display thread (Qt signals, queues, …).
"""

import time
import threading
from contextlib import contextmanager


class _Busy(Exception):
    """Brain lock could not be acquired in time (usually mid web-fetch)."""


# Speed 1–10 → sleep seconds BETWEEN batches
_SPEED_TABLE = {
    1: 0.500, 2: 0.200, 3: 0.100, 4: 0.050, 5: 0.020,
    6: 0.010, 7: 0.005, 8: 0.001, 9: 0.000, 10: 0.000,
}

_RESOURCE_CMDS = ("speed", "batch", "memory", "fetch")


def _fetched_topics(res: dict) -> list:
    """fetch_knowledge reports under topics_succeeded/topics_attempted."""
    return (res.get("topics_succeeded")
            or res.get("topics_attempted")
            or [])


class GenesisEngine:
    """Headless Genesis session: cognition + fetching + commands."""

    def __init__(self, brain, *,
                 self_directed: bool = False,
                 fetch_topics: int = 2,
                 speed: int = 8,
                 batch: int = 10,
                 on_genesis=None,
                 on_system=None,
                 on_status=None,
                 user_active=None):
        self.brain = brain
        brain.verbose = False

        self._self_directed = self_directed
        self._on_genesis = on_genesis or (lambda text: None)
        self._on_system  = on_system  or (lambda text: None)
        self._on_status  = on_status  or (lambda snap: None)
        self._user_active = user_active or (lambda: False)

        # Serialises ALL brain access across cognition, fetcher, and command
        # handlers.  Brain's SQLite conn is check_same_thread=False — safe
        # while access is serialised.  Reentrant so a holder can call helpers
        # that re-acquire.
        self.lock = threading.RLock()
        self._ctrl_lock = threading.Lock()
        self._stop = threading.Event()

        try:
            mem_cap = brain.memory._working.capacity
        except Exception:
            mem_cap = 5000

        self.controls = {
            "speed":        max(1, min(10, speed)),
            "batch":        max(1, min(1000, batch)),
            "memory":       mem_cap,
            "fetch_topics": max(1, fetch_topics),
            "explore_flag": False,
        }

        self._fetch_topic = ""
        self.cyc_per_sec = 0.0

    # ------------------------------------------------------------------
    # Lock access
    # ------------------------------------------------------------------

    @contextmanager
    def access(self, timeout: float = 2.5):
        """Acquire the brain lock or raise _Busy — the frontend never
        freezes behind a slow web fetch."""
        if not self.lock.acquire(timeout=timeout):
            raise _Busy
        try:
            yield
        finally:
            self.lock.release()

    def _log_error(self, label: str, exc: Exception) -> None:
        try:
            self.brain.survival.resilience.error_log.log(label, exc)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        threading.Thread(target=self._cognition_loop, daemon=True).start()
        threading.Thread(target=self._fetcher_loop,   daemon=True).start()

    def stop(self, timeout: float = 30.0) -> bool:
        """Stop the loops and save.  Returns True if the save happened.

        The timeout is generous because an in-flight web fetch can hold the
        lock for tens of seconds; skipping the save silently would lose up
        to the autosave interval of memories and relations.
        """
        self._stop.set()
        try:
            if self.lock.acquire(timeout=timeout):
                try:
                    self.brain.save_session()
                    return True
                finally:
                    self.lock.release()
        except Exception as exc:
            self._log_error("engine.stop_save", exc)
        return False

    def greeting(self) -> str:
        try:
            with self.access(timeout=10.0):
                msg = self.brain.voice.wake_greeting()
            return msg or "I'm awake. Give me a moment to settle."
        except Exception:
            return "I'm awake. Give me a moment to settle."

    # ------------------------------------------------------------------
    # Resource controls (no brain lock — always instant)
    # ------------------------------------------------------------------

    def set_speed(self, n: int) -> int:
        n = max(1, min(10, int(n)))
        with self._ctrl_lock:
            self.controls["speed"] = n
        return n

    def set_batch(self, n: int) -> int:
        n = max(1, min(1000, int(n)))
        with self._ctrl_lock:
            self.controls["batch"] = n
        return n

    def set_memory(self, n: int) -> int:
        n = self.brain.set_working_capacity(n)
        with self._ctrl_lock:
            self.controls["memory"] = n
        return n

    def set_fetch_topics(self, n: int) -> int:
        n = max(1, int(n))
        with self._ctrl_lock:
            self.controls["fetch_topics"] = n
        return n

    def explore(self) -> None:
        """Break out of the current topic fixation (memory untouched)."""
        with self._ctrl_lock:
            self.controls["explore_flag"] = True

    def snapshot_controls(self) -> dict:
        with self._ctrl_lock:
            return dict(self.controls)

    # ------------------------------------------------------------------
    # Command layer
    # ------------------------------------------------------------------

    @staticmethod
    def parse(raw: str):
        """Parse raw input → (cmd, arg), or None for un-parseable input."""
        raw = raw.strip()
        if not raw:
            return None
        if ":" in raw:
            cmd, _, arg = raw.partition(":")
            return cmd.strip().lstrip("/").lower(), arg.strip()
        parts = raw.lstrip("/").split(None, 1)
        if not parts:          # input was all slashes
            return None
        return parts[0].lower(), (parts[1].strip() if len(parts) > 1 else "")

    @staticmethod
    def is_quit(cmd: str, arg: str) -> bool:
        return cmd in ("quit", "exit", "q") and arg == ""

    @staticmethod
    def is_local(cmd: str, arg: str) -> bool:
        """Resource keywords only act as commands with a numeric (or empty)
        argument — 'memory is fascinating' is conversation."""
        if cmd == "explore" and arg == "":
            return True
        return cmd in _RESOURCE_CMDS and (arg == "" or arg.isdigit())

    def run_local(self, cmd: str, arg: str) -> str:
        """Execute a resource command; returns a feedback message."""
        if cmd == "speed":
            if not arg.isdigit():
                return "Usage: speed N  (1=slow … 10=max)"
            n = self.set_speed(int(arg))
            ms = _SPEED_TABLE.get(n, 0.001) * 1000
            return f"Speed {n}/10  ({ms:.0f}ms between batches)"

        if cmd == "batch":
            if not arg.isdigit():
                return "Usage: batch N  (e.g. batch 50)"
            n = self.set_batch(int(arg))
            return f"Batch {n} — {n} items per tick before yielding."

        if cmd == "memory":
            if not arg.isdigit():
                return "Usage: memory N  (300–1500 recommended)"
            n = self.set_memory(int(arg))
            note = ("  (large — attention re-sorts each cycle, "
                    "may slow throughput)" if n > 3000 else "")
            return f"Working memory set to {n} slots.{note}"

        if cmd == "fetch":
            if not arg.isdigit():
                return "Usage: fetch N  (e.g. fetch 4)"
            n = self.set_fetch_topics(int(arg))
            return f"Fetch depth {n} topics per web cycle."

        if cmd == "explore":
            self.explore()
            return "Breaking current topic — new direction next batch."

        return f"Unknown command: {cmd}"

    def run_command(self, cmd: str, arg: str, raw: str) -> list:
        """
        Execute a brain command synchronously.  Returns renderable events:
        [("genesis"|"system", text), ...].  Never raises — _Busy and errors
        become system events.
        """
        brain = self.brain
        try:
            if cmd == "status":
                with self.access():
                    s = brain.full_status()
                    d = brain.drives.summary()
                ctrl = self.snapshot_controls()
                return [("genesis",
                    f"Cycle {s['cycles']:,}. "
                    f"{s['memory']['total_stored']:,} memories, "
                    f"{s.get('relations',{}).get('total_relations',0):,} associations. "
                    f"Drives: {d['dominant']} {d['dominant_level']:.2f}, "
                    f"wanting {d['wanting']:+.2f}. "
                    f"Speed {ctrl['speed']}/10 × batch {ctrl['batch']} "
                    f"({self.cyc_per_sec:.0f} cycles/s)."
                )]

            if cmd == "reflect":
                with self.access(timeout=15.0):
                    rep = brain.reflect(cycle=brain.cycle_count)
                return [("genesis", rep.get("summary")
                         or "I reflected but nothing crystallised yet.")]

            if cmd == "thoughts":
                with self.access():
                    latest = brain.latest_reflection()
                return [("genesis", latest["summary"] if latest
                         else "I haven't reflected yet. Type 'reflect'.")]

            if cmd == "curiosity":
                with self.access():
                    report = brain.curiosity_report()
                if report:
                    topics = ", ".join(r["concept"] for r in report[:5])
                    return [("genesis", f"I most want to understand: {topics}.")]
                return [("genesis", "I haven't formed strong curiosity targets yet.")]

            if cmd == "learn" and (arg == "" or arg.isdigit()):
                # "learn" / "learn 4" is a command; "learn something for me"
                # falls through to conversation below.
                n = int(arg) if arg.isdigit() else self.snapshot_controls()["fetch_topics"]
                with self.access(timeout=60.0):
                    res = brain.fetch_knowledge(n_topics=n, verbose=False)
                topics = _fetched_topics(res)
                return [("genesis",
                         f"I read about {', '.join(topics[:3])}." if topics
                         else "Nothing new came back from that search.")]

            if cmd == "save":
                with self.access(timeout=10.0):
                    brain.save_session()
                return [("system", "Session saved.")]

            if cmd == "summary":
                with self.access():
                    s = brain.full_status()
                m = s.get("memory", {})
                r = s.get("relations", {})
                return [("genesis",
                    f"Cycles: {s['cycles']:,}  "
                    f"Memories: {m.get('total_stored',0):,}  "
                    f"Relations: {r.get('total_relations',0):,}  "
                    f"Inferences: {s.get('inference',{}).get('total_inferences',0):,}"
                )]

            if cmd == "history":
                with self.access():
                    entries = brain.consolidation.history(limit=5)
                if not entries:
                    return [("genesis", "No reflection history yet.")]
                events = []
                for e in reversed(entries[-3:]):
                    salient  = e.get("salient", [])
                    concepts = ", ".join(
                        (s["concept"] if isinstance(s, dict) else str(s))
                        for s in salient[:4]
                    )
                    events.append(("genesis", f"Reflected on: {concepts}"))
                return events

            if cmd == "relations" and arg:
                with self.access():
                    rels = brain.relations.query_subject(arg, min_confidence=0.3)
                if rels:
                    desc = "; ".join(
                        f"{r['relation']} {r['object']} ({r['confidence']:.2f})"
                        for r in rels[:5]
                    )
                    return [("genesis", f"{arg}: {desc}")]
                return [("genesis", f"No associations for '{arg}' yet.")]

            # Everything else is conversation
            with self.access():
                reply = brain.voice.chat_respond(raw)
            return [("genesis", reply if reply else
                     "I heard you. I'm still forming a response — "
                     "try 'reflect' to help me consolidate.")]

        except _Busy:
            return [("system",
                     "Genesis is deep in a web read right now — give it a few "
                     "seconds and ask again. "
                     "(speed / batch / explore still work instantly.)")]
        except Exception as exc:
            self._log_error("engine.run_command", exc)
            return [("system", f"command error: {exc}")]

    # ------------------------------------------------------------------
    # Cognition thread — pure thinking, never touches the network
    # ------------------------------------------------------------------

    def _cognition_loop(self) -> None:
        brain = self.brain

        if brain.curriculum.current_stage.value >= 4:
            from curriculum.adaptive_stream import AdaptiveStream
            stream = AdaptiveStream(brain)
        else:
            from curriculum.open_stage import DataStream
            stream = DataStream()

        try:
            from output.channel import NullChannel
            brain.voice.set_channel(NullChannel())
        except Exception:
            pass

        cycles       = 0
        last_reflect = 0
        last_save    = time.time()

        _tput_t0      = time.perf_counter()
        _tput_count   = 0
        _last_status  = 0.0
        _last_err_log = 0.0
        _drives_snap: dict = {}

        _REFLECT_EVERY = 400
        _AUTOSAVE      = 120.0
        _STATUS_HZ     = 1.0

        while not self._stop.is_set():
            try:
                with self._ctrl_lock:
                    speed      = self.controls["speed"]
                    batch_size = max(1, self.controls["batch"])
                    do_explore = self.controls["explore_flag"]
                    if do_explore:
                        self.controls["explore_flag"] = False

                cycle_sleep = _SPEED_TABLE.get(speed, 0.001)

                # Explore: clear curiosity frontier (memory untouched)
                if do_explore:
                    try:
                        with self.lock:
                            brain._curiosity_directives.clear()
                            brain._save_directives()
                    except Exception as exc:
                        self._log_error("engine.explore", exc)
                    self._fetch_topic = ""

                # Tight inner batch.  Lock held per-cycle then released so
                # the fetcher and command handlers can interleave.
                for _ in range(batch_size):
                    if self._stop.is_set():
                        break
                    try:
                        with self.lock:
                            item = stream.next()
                            brain.process_input(item["type"], item["data"])
                    except Exception as exc:
                        # Errors are data — log, but at most once per second
                        # so a persistent failure can't flood from the loop.
                        if (time.monotonic() - _last_err_log) >= 1.0:
                            _last_err_log = time.monotonic()
                            self._log_error("engine.cognition_loop", exc)
                        continue
                    cycles      += 1
                    _tput_count += 1

                now = time.perf_counter()
                if (now - _tput_t0) >= 5.0:
                    self.cyc_per_sec = _tput_count / (now - _tput_t0)
                    _tput_t0    = now
                    _tput_count = 0

                # Spontaneous expression
                try:
                    if cycles % 40 < batch_size:
                        with self.lock:
                            expr = brain.drives.expressive_state()
                        if expr:
                            self._on_genesis(expr)
                except Exception as exc:
                    self._log_error("engine.expression", exc)

                # Status — drives come from drives.summary() (process_input's
                # result only carries the M34 seed drives, not the five
                # biological drives).  Throttled to _STATUS_HZ.
                wall = time.monotonic()
                if (wall - _last_status) >= (1.0 / _STATUS_HZ):
                    _last_status = wall
                    try:
                        with self.lock:
                            _drives_snap = brain.drives.summary()
                            concepts = list(
                                brain.memory._working._context_terms[:16])
                    except Exception:
                        concepts = []
                    self._on_status({
                        "cycle":       brain.cycle_count,
                        "drives":      _drives_snap,
                        "topic":       self._fetch_topic,
                        "controls":    self.snapshot_controls(),
                        "cyc_per_sec": self.cyc_per_sec,
                        "concepts":    concepts,
                    })

                # Periodic consolidation
                if (cycles - last_reflect) >= _REFLECT_EVERY:
                    try:
                        with self.lock:
                            rep = brain.reflect(cycle=cycles)
                        summary = rep.get("summary", "")
                        if summary:
                            self._on_genesis(summary)
                    except Exception as exc:
                        self._log_error("engine.reflect", exc)
                    last_reflect = cycles

                # Periodic auto-save
                if (time.time() - last_save) >= _AUTOSAVE:
                    try:
                        with self.lock:
                            brain.save_session()
                        last_save = time.time()
                    except Exception as exc:
                        self._log_error("engine.autosave", exc)

                if cycle_sleep > 0:
                    time.sleep(cycle_sleep)

            except Exception as exc:
                self._log_error("engine.cognition_outer", exc)
                time.sleep(0.1)

    # ------------------------------------------------------------------
    # Fetcher thread — slow web I/O, isolated from cognition
    # ------------------------------------------------------------------

    def _fetcher_loop(self) -> None:
        if not self._self_directed:
            return
        # First fetch after a short warm-up so cognition settles first.
        self._stop.wait(8.0)
        while not self._stop.is_set():
            # Defer while the user is typing or a command is in flight —
            # keep the brain lock free so conversation stays snappy.
            if self._user_active():
                self._stop.wait(1.5)
                continue
            n_fetch = self.snapshot_controls()["fetch_topics"]
            try:
                # Holds the brain lock for the fetch (network + ingest).
                # Cognition pauses only for this window, then resumes.
                with self.lock:
                    res = self.brain.fetch_knowledge(
                        n_topics=n_fetch, verbose=False)
                topics = _fetched_topics(res)
                added  = res.get("relations_added", 0)
                if topics:
                    self._fetch_topic = topics[0]
                    msg = f"Read about {', '.join(topics[:3])}"
                    if added:
                        msg += f"  (+{added} associations)"
                    self._on_system(msg)
            except Exception as exc:
                self._log_error("engine.fetcher_loop", exc)
            # Space fetches out so cognition gets long uninterrupted runs.
            self._stop.wait(20.0)


# ---------------------------------------------------------------------------
# Shared bootstrap for frontends
# ---------------------------------------------------------------------------

def add_common_args(parser) -> None:
    """The CLI flags every frontend shares."""
    parser.add_argument("--resume",        action="store_true",
                        help="Resume from last saved session")
    parser.add_argument("--self-directed", action="store_true",
                        help="Autonomously fetch the web on curiosity targets")
    parser.add_argument("--fetch-topics",  type=int, default=2,
                        help="Topics to fetch per web cycle (default 2)")
    parser.add_argument("--db",            default=None,
                        help="Path to memory DB (default: data/genesis_memory.db)")
    parser.add_argument("--speed",         type=int, default=8,
                        help="Cycle speed 1–10 (default 8)")
    parser.add_argument("--batch",         type=int, default=10,
                        help="Items per inner loop tick (default 10)")


def boot_brain(args, announce=print):
    """Create the Orchestrator and ensure the foundation curriculum ran."""
    from orchestrator.orchestrator import Orchestrator

    brain = Orchestrator(verbose=False, db_path=args.db, resume=args.resume)

    if not args.resume:
        announce("Building foundation — about a minute…")
        from curriculum.open_stage import advance_to_open
        advance_to_open(brain)
        brain.save_session()
        announce("Foundation complete.")
    elif brain.curriculum.current_stage.value < 4:
        from curriculum.open_stage import advance_to_open
        advance_to_open(brain)

    return brain
