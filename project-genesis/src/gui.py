#!/usr/bin/env python3
"""
Genesis Desktop GUI

Four-panel PyQt6 window:
  - Chat  : conversation history + text input
  - Graphs: cycles/sec rolling line chart + drive-level trends
  - Drives: live bar gauges for the five biological-analog drives
  - Controls: sliders for speed / batch / memory / fetch + active concepts

Run:
    python gui.py --resume --self-directed --speed 8 --batch 10

Same thread model as ui.py:
    - Cognition thread  : tight inner batch, never touches the network
    - Fetcher thread    : web I/O only, isolated so network latency can't
                          freeze the display or the cognition loop
    - Qt main thread    : GUI only; receives updates via pyqtSignal
"""

import collections
import os
import sys
import time
import threading
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QLineEdit, QPushButton, QSlider, QProgressBar,
    QListWidget, QGroupBox, QStatusBar,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QColor, QTextCharFormat, QTextCursor

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure


# ── Constants ─────────────────────────────────────────────────────────────────

_SPEED_TABLE = {
    1: 0.500, 2: 0.200, 3: 0.100, 4: 0.050, 5: 0.020,
    6: 0.010, 7: 0.005, 8: 0.001, 9: 0.000, 10: 0.000,
}

# Five biological-analog drives (all 0–1)
_DRIVE_NAMES  = ["hunger", "anticipation", "frustration", "boredom", "dissonance"]
_DRIVE_COLORS = {
    "hunger":       "#e74c3c",
    "anticipation": "#f1c40f",
    "frustration":  "#e67e22",
    "boredom":      "#3498db",
    "dissonance":   "#9b59b6",
}
# M34 gradient signal (−1 → +1); displayed separately
_WANTING_COLOR = "#2ecc71"

_GRAPH_LEN    = 120   # 2 min of history at 1 data-point / second
_STATUS_HZ    = 1.0   # status updates pushed to UI per second


class _Busy(Exception):
    """Brain lock could not be acquired in time."""


# ── Signal bridge (background threads → Qt main thread) ──────────────────────

class _Bridge(QObject):
    genesis_said    = pyqtSignal(str)      # Genesis expressed something
    system_note     = pyqtSignal(str)      # status / system messages
    status_update   = pyqtSignal(object)   # dict: cycle, drives, cps, topic, concepts


# ── Embedded rolling-line chart ───────────────────────────────────────────────

_DARK_BG   = "#0d0d1a"
_AXES_BG   = "#12122a"
_TICK_CLR  = "#6060a0"
_SPINE_CLR = "#2a2a4a"


class _RollingPlot(FigureCanvasQTAgg):
    """Matplotlib canvas that keeps a fixed-length rolling window per series."""

    def __init__(self, title: str, y_label: str,
                 series: list[tuple[str, str]],
                 y_range: tuple | None = None, parent=None):
        fig = Figure(figsize=(4, 2.2), tight_layout=True, facecolor=_DARK_BG)
        super().__init__(fig)
        self.setParent(parent)

        ax = fig.add_subplot(111)
        ax.set_facecolor(_AXES_BG)
        ax.set_title(title, color="#c0c0d8", fontsize=9, pad=4)
        ax.set_ylabel(y_label, color=_TICK_CLR, fontsize=8)
        ax.tick_params(colors=_TICK_CLR, labelsize=7)
        for sp in ax.spines.values():
            sp.set_edgecolor(_SPINE_CLR)
        ax.grid(color=_SPINE_CLR, linewidth=0.5, alpha=0.5)
        if y_range:
            ax.set_ylim(*y_range)

        self._ax          = ax
        self._fixed_range = y_range is not None
        self._data : dict[str, collections.deque] = {}
        self._lines: dict[str, object] = {}

        for name, color in series:
            d = collections.deque([0.0] * _GRAPH_LEN, maxlen=_GRAPH_LEN)
            (line,) = ax.plot(range(_GRAPH_LEN), list(d),
                              color=color, linewidth=1.3, label=name)
            self._data[name]  = d
            self._lines[name] = line

        if len(series) > 1:
            leg = ax.legend(fontsize=7, loc="upper left",
                            facecolor=_DARK_BG, edgecolor=_SPINE_CLR)
            for txt in leg.get_texts():
                txt.set_color("#c0c0d8")

        self._x = list(range(_GRAPH_LEN))

    def push(self, values: dict[str, float]) -> None:
        for name, val in values.items():
            if name not in self._data:
                continue
            self._data[name].append(val)
            self._lines[name].set_ydata(list(self._data[name]))
        # A fixed-range axis never needs rescaling — skip the per-push
        # relim/autoscale over every series.
        if not self._fixed_range:
            self._ax.relim()
            self._ax.autoscale_view(scalex=False)
        self.draw_idle()


# ── Main window ───────────────────────────────────────────────────────────────

class GenesisWindow(QMainWindow):

    def __init__(self, brain, self_directed: bool,
                 fetch_topics: int, initial_speed: int, initial_batch: int):
        super().__init__()
        self._brain        = brain
        self._self_directed = self_directed

        self._brain_lock  = threading.RLock()
        self._ctrl_lock   = threading.Lock()
        self._stop_evt    = threading.Event()

        try:
            _mem = brain.memory._working.capacity
        except Exception:
            _mem = 5000

        self._controls = {
            "speed":        initial_speed,
            "batch":        initial_batch,
            "memory":       _mem,
            "fetch_topics": fetch_topics,
            "explore_flag": False,
        }

        self._fetch_topic: str = ""
        self._last_cps: float  = 0.0
        # User-activity signals — the fetcher defers while these are hot so
        # chat commands never bounce off a lock held by a web fetch.
        self._pending_cmds: int      = 0
        self._last_typing:  float    = 0.0

        self._bridge = _Bridge()
        self._bridge.genesis_said.connect(self._on_genesis)
        self._bridge.system_note.connect(self._on_system)
        self._bridge.status_update.connect(self._on_status)

        self._build_ui(initial_speed, initial_batch, _mem, fetch_topics)

        threading.Thread(target=self._cognition_loop, daemon=True).start()
        threading.Thread(target=self._fetcher_loop,   daemon=True).start()

        # Greeting after the window is shown
        QTimer.singleShot(200, self._send_greeting)

    # ─────────────────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self, speed, batch, mem, fetch):
        self.setWindowTitle("Genesis")
        self.resize(1360, 800)
        self._apply_theme()

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(6, 6, 6, 4)
        outer.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        outer.addWidget(split, stretch=1)

        split.addWidget(self._make_chat_panel())
        split.addWidget(self._make_graphs_panel())
        split.addWidget(self._make_controls_panel(speed, batch, mem, fetch))
        split.setSizes([440, 560, 320])

        sb = QStatusBar()
        self.setStatusBar(sb)
        self._sb_label = QLabel("Starting…")
        self._sb_label.setStyleSheet("color:#505070; font-size:11px;")
        sb.addWidget(self._sb_label)

    # ── Chat panel ────────────────────────────────────────────────────────

    def _make_chat_panel(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        hdr = QLabel("Genesis")
        hdr.setStyleSheet("color:#00c8f0; font-size:14px; font-weight:bold;"
                          " padding:2px 4px;")
        lay.addWidget(hdr)

        self._chat = QTextEdit()
        self._chat.setReadOnly(True)
        # Cap the document so an overnight self-directed run can't grow the
        # chat history without bound (old blocks are dropped automatically).
        self._chat.document().setMaximumBlockCount(2000)
        self._chat.setStyleSheet(
            "background:#090916; color:#c8d0e0;"
            " font-family:'Consolas','Courier New',monospace; font-size:12px;"
            " border:1px solid #232340; border-radius:5px; padding:8px;"
        )
        lay.addWidget(self._chat, stretch=1)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "Talk to Genesis — or: status  reflect  curiosity  explore  save  quit"
        )
        self._input.setStyleSheet(
            "background:#0f0f22; color:#d8d8f0;"
            " border:1px solid #353560; border-radius:5px;"
            " padding:7px 10px; font-size:12px;"
        )
        self._input.returnPressed.connect(self._send)
        self._input.textChanged.connect(self._note_typing)
        row.addWidget(self._input)

        send = QPushButton("Send")
        send.setFixedWidth(64)
        send.setStyleSheet(
            "background:#153050; color:#80b8e0;"
            " border:1px solid #206090; border-radius:5px;"
            " padding:7px; font-size:12px;"
        )
        send.clicked.connect(self._send)
        row.addWidget(send)
        lay.addLayout(row)
        return w

    # ── Graphs panel ──────────────────────────────────────────────────────

    def _make_graphs_panel(self) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(6)

        hdr = QLabel("Live Metrics")
        hdr.setStyleSheet("color:#909090; font-size:13px; font-weight:bold;"
                          " padding:2px 4px;")
        lay.addWidget(hdr)

        self._cps_plot = _RollingPlot(
            title="Cycles per second",
            y_label="c/s",
            series=[("cycles/s", "#00c8f0")],
        )
        self._cps_plot.setMinimumHeight(140)
        lay.addWidget(self._cps_plot, stretch=1)

        # Drives + wanting on the same chart.
        # Biological drives are 0–1; wanting is −1 → +1 mapped to 0–1 for display.
        drive_series = [(n, _DRIVE_COLORS[n]) for n in _DRIVE_NAMES]
        drive_series.append(("wanting ×½+½", _WANTING_COLOR))
        self._drive_plot = _RollingPlot(
            title="Drives over time  (wanting remapped 0–1)",
            y_label="level",
            series=drive_series,
            y_range=(0.0, 1.05),
        )
        self._drive_plot.setMinimumHeight(200)
        lay.addWidget(self._drive_plot, stretch=2)

        return w

    # ── Controls panel ────────────────────────────────────────────────────

    def _make_controls_panel(self, speed, batch, mem, fetch) -> QWidget:
        w = QWidget()
        w.setFixedWidth(310)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(8)

        # ── Sliders ──────────────────────────────────────────────────────

        ctrl = QGroupBox("Resource Controls")
        ctrl.setStyleSheet(self._box_style())
        cl = QVBoxLayout(ctrl)
        cl.setSpacing(6)

        self._speed_lbl = QLabel(f"Speed  {speed}/10")
        self._batch_lbl = QLabel(f"Batch  {batch}")
        self._mem_lbl   = QLabel(f"Memory  {mem:,}")
        self._fetch_lbl = QLabel(f"Fetch topics  {fetch}")
        for lbl in (self._speed_lbl, self._batch_lbl,
                    self._mem_lbl, self._fetch_lbl):
            lbl.setStyleSheet("color:#b0b0d0; font-size:11px;")

        self._speed_sl = self._slider(1,   10,   speed)
        self._batch_sl = self._slider(1,   500,  min(batch, 500))
        self._mem_sl   = self._slider(100, 5000, min(mem,   5000))
        self._fetch_sl = self._slider(1,   10,   fetch)

        self._speed_sl.valueChanged.connect(self._chg_speed)
        self._batch_sl.valueChanged.connect(self._chg_batch)
        self._mem_sl.valueChanged.connect(self._chg_mem)
        self._fetch_sl.valueChanged.connect(self._chg_fetch)

        for lbl, sl in ((self._speed_lbl, self._speed_sl),
                        (self._batch_lbl, self._batch_sl),
                        (self._mem_lbl,   self._mem_sl),
                        (self._fetch_lbl, self._fetch_sl)):
            cl.addWidget(lbl)
            cl.addWidget(sl)

        explore = QPushButton("⟳  Explore  (break topic fixation)")
        explore.setStyleSheet(
            "background:#0f2a0f; color:#70d070;"
            " border:1px solid #1a5a1a; border-radius:4px;"
            " padding:6px; font-size:11px;"
        )
        explore.clicked.connect(self._do_explore)
        cl.addWidget(explore)
        lay.addWidget(ctrl)

        # ── Drive bars ───────────────────────────────────────────────────

        drives_box = QGroupBox("Drives")
        drives_box.setStyleSheet(self._box_style())
        dl = QVBoxLayout(drives_box)
        dl.setSpacing(4)

        self._drive_bars: dict[str, QProgressBar] = {}
        self._drive_lbls: dict[str, QLabel]       = {}
        # Biological drives + wanting as a named row
        _bar_rows = list(_DRIVE_NAMES) + ["wanting"]
        _bar_colors = dict(_DRIVE_COLORS)
        _bar_colors["wanting"] = _WANTING_COLOR
        for name in _bar_rows:
            row  = QHBoxLayout()
            name_lbl = QLabel(name.capitalize()[:7])
            name_lbl.setFixedWidth(68)
            name_lbl.setStyleSheet("color:#808090; font-size:11px;")
            row.addWidget(name_lbl)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(14)
            c = _bar_colors[name]
            bar.setStyleSheet(
                f"QProgressBar {{background:#1a1a2e; border:none; border-radius:3px;}}"
                f"QProgressBar::chunk {{background:{c}; border-radius:3px;}}"
            )
            row.addWidget(bar, stretch=1)

            # wanting shows a signed value (+0.xxx)
            init_txt = "+0.000" if name == "wanting" else "0.00"
            val_lbl = QLabel(init_txt)
            val_lbl.setFixedWidth(42)
            val_lbl.setStyleSheet(f"color:{c}; font-size:10px; font-family:monospace;")
            row.addWidget(val_lbl)

            dl.addLayout(row)
            self._drive_bars[name] = bar
            self._drive_lbls[name] = val_lbl

        lay.addWidget(drives_box)

        # ── Active concepts ───────────────────────────────────────────────

        conc_box = QGroupBox("Active Concepts")
        conc_box.setStyleSheet(self._box_style())
        kl = QVBoxLayout(conc_box)
        self._concepts = QListWidget()
        self._concepts.setStyleSheet(
            "background:#08081a; color:#70d890; border:none;"
            " font-size:11px; font-family:monospace;"
        )
        self._concepts.setMaximumHeight(180)
        self._concepts.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        kl.addWidget(self._concepts)
        lay.addWidget(conc_box)

        lay.addStretch()
        return w

    # ── Helpers ───────────────────────────────────────────────────────────

    def _slider(self, lo, hi, val) -> QSlider:
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(val)
        sl.setStyleSheet(
            "QSlider::groove:horizontal {background:#252540; height:4px;"
            " border-radius:2px;}"
            "QSlider::handle:horizontal {background:#0090b8; width:14px;"
            " height:14px; margin:-5px 0; border-radius:7px;}"
            "QSlider::sub-page:horizontal {background:#005880; border-radius:2px;}"
        )
        return sl

    def _box_style(self) -> str:
        return (
            "QGroupBox {background:#0c0c1e; border:1px solid #252540;"
            " border-radius:5px; padding-top:18px; margin-top:4px;"
            " color:#8888aa; font-size:11px;}"
            "QGroupBox::title {subcontrol-origin:margin; left:8px; padding:0 4px;}"
        )

    def _apply_theme(self):
        self.setStyleSheet(
            "QMainWindow, QWidget {background:#090916; color:#c8d0e0;}"
            "QSplitter::handle {background:#1e1e38; width:2px;}"
            "QStatusBar {background:#0b0b1c; color:#505070; font-size:11px;}"
            "QScrollBar:vertical {background:#0e0e20; width:8px; border:none;}"
            "QScrollBar::handle:vertical {background:#2a2a50; border-radius:4px;}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Slider callbacks (no brain lock — instant)
    # ─────────────────────────────────────────────────────────────────────────

    def _chg_speed(self, v):
        with self._ctrl_lock:
            self._controls["speed"] = v
        ms = _SPEED_TABLE.get(v, 0.001) * 1000
        self._speed_lbl.setText(f"Speed  {v}/10  ({ms:.0f} ms between batches)")

    def _chg_batch(self, v):
        with self._ctrl_lock:
            self._controls["batch"] = v
        self._batch_lbl.setText(f"Batch  {v}")

    def _chg_mem(self, v):
        with self._ctrl_lock:
            self._controls["memory"] = v
        try:
            self._brain.memory._working.capacity = v
        except Exception:
            pass
        note = "  ⚠ large" if v > 3000 else ""
        self._mem_lbl.setText(f"Memory  {v:,}{note}")

    def _chg_fetch(self, v):
        with self._ctrl_lock:
            self._controls["fetch_topics"] = v
        self._fetch_lbl.setText(f"Fetch topics  {v}")

    def _do_explore(self):
        with self._ctrl_lock:
            self._controls["explore_flag"] = True
        self._sys("Breaking topic fixation — new direction next batch.")

    # ─────────────────────────────────────────────────────────────────────────
    # Input / command handling
    # ─────────────────────────────────────────────────────────────────────────

    def _note_typing(self):
        self._last_typing = time.monotonic()

    def _user_active(self) -> bool:
        """True if a command is in flight or the user typed recently."""
        return (self._pending_cmds > 0
                or (time.monotonic() - self._last_typing) < 5.0)

    def _send(self):
        raw = self._input.text().strip()
        if not raw:
            return
        self._input.clear()
        self._user(raw)
        self._dispatch(raw)

    @contextmanager
    def _access(self, timeout: float = 2.5):
        if not self._brain_lock.acquire(timeout=timeout):
            raise _Busy
        try:
            yield
        finally:
            self._brain_lock.release()

    def _dispatch(self, raw: str):
        if ":" in raw:
            cmd, _, arg = raw.partition(":")
            cmd, arg = cmd.strip().lstrip("/").lower(), arg.strip()
        else:
            parts = raw.lstrip("/").split(None, 1)
            if not parts:          # input was all slashes — nothing to do
                return
            cmd   = parts[0].lower()
            arg   = parts[1].strip() if len(parts) > 1 else ""

        # Resource keywords only act as commands with a numeric (or empty)
        # argument — "memory is fascinating" is conversation, "memory 800"
        # is a command.
        _numeric_arg = arg == "" or arg.isdigit()

        # Quit
        if cmd in ("quit", "exit", "q") and arg == "":
            self._sys("Saving and shutting down…")
            self._stop_evt.set()
            # close() triggers closeEvent, which performs the save (waits
            # up to 30s for an in-flight fetch to release the brain lock).
            QTimer.singleShot(100, self.close)
            return

        # Instant resource controls — no lock needed
        if cmd == "speed" and _numeric_arg:
            try:
                self._speed_sl.setValue(max(1, min(10, int(arg))))
            except ValueError:
                self._sys("Usage: speed N  (1–10)")
            return

        if cmd == "batch" and _numeric_arg:
            try:
                n = max(1, min(1000, int(arg)))
                self._batch_sl.setValue(min(n, 500))
                with self._ctrl_lock:
                    self._controls["batch"] = n
                self._batch_lbl.setText(f"Batch  {n}")
            except ValueError:
                self._sys("Usage: batch N")
            return

        if cmd == "memory" and arg.isdigit():
            n = max(100, int(arg))
            self._mem_sl.setValue(min(n, 5000))
            self._chg_mem(n)
            return

        if cmd == "fetch" and arg.isdigit():
            self._fetch_sl.setValue(max(1, min(10, int(arg))))
            return

        if cmd == "explore" and arg == "":
            self._do_explore()
            return

        # Brain commands — worker thread so the UI stays live
        self._pending_cmds += 1
        threading.Thread(target=self._run_cmd,
                         args=(cmd, arg, raw), daemon=True).start()

    def _run_cmd(self, cmd: str, arg: str, raw: str):
        try:
            if cmd == "status":
                with self._access():
                    s = self._brain.full_status()
                    d = self._brain.drives.summary()
                with self._ctrl_lock:
                    sp, bt = self._controls["speed"], self._controls["batch"]
                self._bridge.genesis_said.emit(
                    f"Cycle {s['cycles']:,}. "
                    f"{s['memory']['total_stored']:,} memories, "
                    f"{s.get('relations',{}).get('total_relations',0):,} associations. "
                    f"Drives: {d['dominant']} {d['dominant_level']:.2f}, "
                    f"wanting {d['wanting']:+.2f}. "
                    f"Speed {sp}/10 × batch {bt} ({self._last_cps:.0f} cycles/s)."
                )

            elif cmd == "reflect":
                self._bridge.system_note.emit("Reflecting…")
                with self._access(timeout=15.0):
                    rep = self._brain.reflect(cycle=self._brain.cycle_count)
                self._bridge.genesis_said.emit(
                    rep.get("summary") or "I reflected but nothing crystallised yet.")

            elif cmd == "thoughts":
                with self._access():
                    latest = self._brain.latest_reflection()
                self._bridge.genesis_said.emit(
                    latest["summary"] if latest
                    else "I haven't reflected yet. Type 'reflect'.")

            elif cmd == "curiosity":
                with self._access():
                    report = self._brain.curiosity_report()
                if report:
                    topics = ", ".join(r["concept"] for r in report[:5])
                    self._bridge.genesis_said.emit(
                        f"I most want to understand: {topics}.")
                else:
                    self._bridge.genesis_said.emit(
                        "I haven't formed strong curiosity targets yet.")

            elif cmd == "save":
                with self._access(timeout=10.0):
                    self._brain.save_session()
                self._bridge.system_note.emit("Session saved.")

            elif cmd == "learn" and (arg == "" or arg.isdigit()):
                # "learn" / "learn 4" is a command; "learn something for me"
                # is conversation and falls through to chat_respond below.
                with self._ctrl_lock:
                    n = int(arg) if arg.isdigit() else self._controls["fetch_topics"]
                self._bridge.system_note.emit(f"Fetching {n} topics…")
                with self._access(timeout=60.0):
                    res = self._brain.fetch_knowledge(n_topics=n, verbose=False)
                topics = _fetched_topics(res)
                self._bridge.genesis_said.emit(
                    f"I read about {', '.join(topics[:3])}."
                    if topics else "Nothing new came back from that search.")

            elif cmd == "relations" and arg:
                with self._access():
                    rels = self._brain.relations.query_subject(
                        arg, min_confidence=0.3)
                if rels:
                    desc = "; ".join(
                        f"{r['relation']} {r['object']} ({r['confidence']:.2f})"
                        for r in rels[:5]
                    )
                    self._bridge.genesis_said.emit(f"{arg}: {desc}")
                else:
                    self._bridge.genesis_said.emit(
                        f"No associations for '{arg}' yet.")

            else:
                with self._access():
                    reply = self._brain.voice.chat_respond(raw)
                self._bridge.genesis_said.emit(
                    reply if reply else
                    "I heard you. Still forming a response — "
                    "try 'reflect' to help me consolidate."
                )

        except _Busy:
            self._bridge.system_note.emit(
                "Genesis is mid web-read — wait a moment, or use the sliders."
            )
        except Exception as exc:
            self._bridge.system_note.emit(f"Error: {exc}")
            try:
                self._brain.survival.resilience.error_log.log("gui.run_cmd", exc)
            except Exception:
                pass
        finally:
            self._pending_cmds = max(0, self._pending_cmds - 1)

    # ─────────────────────────────────────────────────────────────────────────
    # Chat display (always on the main thread via signals)
    # ─────────────────────────────────────────────────────────────────────────

    def _insert(self, text: str, color: str, bold: bool = False, prefix: str = ""):
        cursor = self._chat.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        if prefix:
            pfmt = QTextCharFormat()
            pfmt.setForeground(QColor(color))
            pfmt.setFontWeight(700)
            cursor.insertText(prefix, pfmt)
        fmt.setForeground(QColor(color if not prefix else "#b8c8d8"))
        if bold:
            fmt.setFontWeight(700)
        cursor.insertText(text, fmt)
        self._chat.setTextCursor(cursor)
        self._chat.ensureCursorVisible()

    def _genesis(self, text: str):
        self._insert("\n", "#00c8f0")
        self._insert("  Genesis ❯  ", "#00c8f0", bold=True)
        self._insert(text + "\n", "#b8cce0")

    def _user(self, text: str):
        self._insert("  You  ❯  ", "#e0e0e0", bold=True)
        self._insert(text + "\n", "#d0d0e0")

    def _sys(self, text: str):
        self._insert(f"  {text}\n", "#505070")

    # ─────────────────────────────────────────────────────────────────────────
    # Signal slots (Qt main thread)
    # ─────────────────────────────────────────────────────────────────────────

    def _on_genesis(self, text: str):
        self._genesis(text)

    def _on_system(self, text: str):
        self._sys(text)

    def _on_status(self, st: dict):
        drives   = st.get("drives", {})
        cps      = st.get("cyc_per_sec", 0.0)
        cycle    = st.get("cycle", 0)
        topic    = st.get("topic", "")
        concepts = st.get("concepts", [])
        ctrl     = st.get("controls", {})

        if cps > 0:
            self._last_cps = cps

        # Graphs
        self._cps_plot.push({"cycles/s": cps})
        drive_push = {n: min(1.0, max(0.0, drives.get(n, 0.0)))
                      for n in _DRIVE_NAMES}
        # wanting is −1 → +1; remap to 0–1 for display on the same chart
        wanting_raw = drives.get("wanting", 0.0)
        drive_push["wanting ×½+½"] = min(1.0, max(0.0, wanting_raw * 0.5 + 0.5))
        self._drive_plot.push(drive_push)

        # Drive bars + value labels (biological drives only)
        for name in _DRIVE_NAMES:
            raw_val = drives.get(name, 0.0)
            pct     = min(100, max(0, int(raw_val * 100)))
            self._drive_bars[name].setValue(pct)
            self._drive_lbls[name].setText(f"{raw_val:.2f}")

        # Wanting bar (signed −1→+1, remapped like the trend chart:
        # empty = −1, half = 0, full = +1 — so negatives stay visible)
        want_pct = min(100, max(0, int((wanting_raw * 0.5 + 0.5) * 100)))
        self._drive_bars["wanting"].setValue(want_pct)
        self._drive_lbls["wanting"].setText(f"{wanting_raw:+.3f}")

        # Active concepts
        if concepts:
            self._concepts.clear()
            for c in concepts[:20]:
                self._concepts.addItem(f"  {c}")

        # Status bar
        action  = drives.get("seed_action", "idle")
        wanting = drives.get("wanting", 0.0)
        sp      = ctrl.get("speed", 8)
        bt      = ctrl.get("batch", 10)
        cps_str = f"{cps:.0f}/s" if cps > 0 else "—"
        reading = f"  ·  reading: {topic[:32]}" if topic else ""
        self._sb_label.setText(
            f"cycle {cycle:,}  ·  {action}  ·  "
            f"want {wanting:+.2f}  ·  spd {sp}/10 × batch {bt}  ·  {cps_str}{reading}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Background threads (identical logic to ui.py)
    # ─────────────────────────────────────────────────────────────────────────

    def _send_greeting(self):
        def _greet():
            try:
                with self._access(timeout=10.0):
                    msg = self._brain.voice.wake_greeting()
                self._bridge.genesis_said.emit(
                    msg if msg else "I'm awake. Give me a moment to settle.")
            except Exception:
                self._bridge.genesis_said.emit(
                    "I'm awake. Give me a moment to settle.")
        threading.Thread(target=_greet, daemon=True).start()

    def _cognition_loop(self):
        brain = self._brain

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
        last_result  = {}
        last_status  = 0.0

        _tput_t0      = time.perf_counter()
        _tput_count   = 0
        cyc_per_sec   = 0.0
        _last_err_log = 0.0

        _REFLECT_EVERY = 400
        _AUTOSAVE      = 120.0

        while not self._stop_evt.is_set():
            try:
                with self._ctrl_lock:
                    speed      = self._controls["speed"]
                    batch_size = max(1, self._controls["batch"])
                    do_explore = self._controls["explore_flag"]
                    if do_explore:
                        self._controls["explore_flag"] = False

                cycle_sleep = _SPEED_TABLE.get(speed, 0.001)

                if do_explore:
                    try:
                        with self._brain_lock:
                            brain._curiosity_directives.clear()
                            brain._save_directives()
                    except Exception:
                        pass
                    self._fetch_topic = ""

                for _ in range(batch_size):
                    if self._stop_evt.is_set():
                        break
                    try:
                        with self._brain_lock:
                            item        = stream.next()
                            last_result = brain.process_input(
                                item["type"], item["data"])
                    except Exception as exc:
                        # Errors are data — route to the error log, but at
                        # most once per second so a persistent failure can't
                        # flood it from a tight loop.
                        if (time.monotonic() - _last_err_log) >= 1.0:
                            _last_err_log = time.monotonic()
                            try:
                                brain.survival.resilience.error_log.log(
                                    "gui.cognition_loop", exc)
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
                        with self._brain_lock:
                            expr = brain.drives.expressive_state()
                        if expr:
                            self._bridge.genesis_said.emit(expr)
                except Exception:
                    pass

                # Status — throttled to _STATUS_HZ
                # Call drives.summary() directly: the orchestrator's process_input
                # result only carries the M34 seed drives (wanting/liking/empowerment),
                # not the five biological drives (hunger/frustration/boredom/dissonance).
                wall = time.monotonic()
                if (wall - last_status) >= (1.0 / _STATUS_HZ):
                    last_status = wall
                    try:
                        with self._brain_lock:
                            drives   = brain.drives.summary()
                            concepts = list(
                                brain.memory._working._context_terms[:16])
                    except Exception:
                        drives   = last_result.get("drives", {})
                        concepts = []
                    with self._ctrl_lock:
                        ctrl_snap = dict(self._controls)
                    self._bridge.status_update.emit({
                        "cycle":       brain.cycle_count,
                        "drives":      drives,
                        "topic":       self._fetch_topic,
                        "controls":    ctrl_snap,
                        "cyc_per_sec": cyc_per_sec,
                        "concepts":    concepts,
                    })

                # Periodic reflection
                if (cycles - last_reflect) >= _REFLECT_EVERY:
                    try:
                        with self._brain_lock:
                            rep = brain.reflect(cycle=cycles)
                        summary = rep.get("summary", "")
                        if summary:
                            self._bridge.genesis_said.emit(summary)
                    except Exception:
                        pass
                    last_reflect = cycles

                # Periodic auto-save
                if (time.time() - last_save) >= _AUTOSAVE:
                    try:
                        with self._brain_lock:
                            brain.save_session()
                        last_save = time.time()
                    except Exception:
                        pass

                if cycle_sleep > 0:
                    time.sleep(cycle_sleep)

            except Exception:
                time.sleep(0.1)

    def _fetcher_loop(self):
        if not self._self_directed:
            return
        self._stop_evt.wait(8.0)
        while not self._stop_evt.is_set():
            # Defer while the user is typing or a command is in flight —
            # keep the brain lock free so conversation stays snappy.
            if self._user_active():
                self._stop_evt.wait(1.5)
                continue
            with self._ctrl_lock:
                n_fetch = self._controls["fetch_topics"]
            try:
                with self._brain_lock:
                    res = self._brain.fetch_knowledge(
                        n_topics=n_fetch, verbose=False)
                topics = _fetched_topics(res)
                added  = res.get("relations_added", 0)
                if topics:
                    self._fetch_topic = topics[0]
                    msg = f"Read about {', '.join(topics[:3])}"
                    if added:
                        msg += f"  (+{added} associations)"
                    self._bridge.system_note.emit(msg)
            except Exception as exc:
                try:
                    self._brain.survival.resilience.error_log.log(
                        "gui.fetcher_loop", exc)
                except Exception:
                    pass
            self._stop_evt.wait(20.0)

    # ─────────────────────────────────────────────────────────────────────────
    # Close
    # ─────────────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        self._stop_evt.set()
        # Wait up to 30s — an in-flight web fetch can hold the lock for tens
        # of seconds, and skipping the save silently would lose up to 120s
        # (the autosave interval) of memories and relations.
        saved = False
        try:
            if self._brain_lock.acquire(timeout=30.0):
                try:
                    self._brain.save_session()
                    saved = True
                finally:
                    self._brain_lock.release()
        except Exception as exc:
            try:
                self._brain.survival.resilience.error_log.log("gui.close_save", exc)
            except Exception:
                pass
        if not saved:
            print("WARNING: could not acquire brain lock — session state since "
                  "the last autosave (up to 2 minutes) was not saved.")
        event.accept()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetched_topics(res: dict) -> list:
    return (res.get("topics_succeeded")
            or res.get("topics_attempted")
            or [])


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Genesis Desktop GUI")
    ap.add_argument("--resume",        action="store_true")
    ap.add_argument("--self-directed", action="store_true")
    ap.add_argument("--fetch-topics",  type=int, default=2)
    ap.add_argument("--db",            default=None)
    ap.add_argument("--speed",         type=int, default=8)
    ap.add_argument("--batch",         type=int, default=10)
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Genesis")

    from orchestrator.orchestrator import Orchestrator

    brain = Orchestrator(verbose=False, db_path=args.db, resume=args.resume)

    if not args.resume:
        print("Building foundation — about a minute…")
        from curriculum.open_stage import advance_to_open
        advance_to_open(brain)
        brain.save_session()
        print("Foundation complete.")
    else:
        if brain.curriculum.current_stage.value < 4:
            from curriculum.open_stage import advance_to_open
            advance_to_open(brain)

    win = GenesisWindow(
        brain,
        self_directed=args.self_directed,
        fetch_topics=args.fetch_topics,
        initial_speed=max(1, min(10, args.speed)),
        initial_batch=max(1, min(1000, args.batch)),
    )
    win.show()
    sys.exit(app.exec())
