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

Thin Qt renderer over the shared GenesisEngine (engine.py), which owns the
cognition thread, the fetcher thread, the lock discipline, and every command.
Engine callbacks arrive on background threads and are marshalled to the Qt
main thread via pyqtSignal; this file only builds widgets and paints them.
"""

import collections
import os
import sys
import time
import threading

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

from engine import GenesisEngine, _SPEED_TABLE, add_common_args, boot_brain


# ── Constants ─────────────────────────────────────────────────────────────────

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


# ── Signal bridge (engine threads → Qt main thread) ───────────────────────────

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
        self._last_cps: float = 0.0
        # User-activity signals — the engine's fetcher defers while these are
        # hot so chat commands never bounce off a lock held by a web fetch.
        self._pending_cmds: int   = 0
        self._last_typing:  float = 0.0

        self._bridge = _Bridge()
        self._bridge.genesis_said.connect(self._on_genesis)
        self._bridge.system_note.connect(self._on_system)
        self._bridge.status_update.connect(self._on_status)

        # The shared engine owns the cognition thread, the fetcher thread,
        # the lock discipline, and every command — this window only renders.
        # Bridge signals are thread-safe, so engine callbacks emit directly.
        self._engine = GenesisEngine(
            brain,
            self_directed=self_directed,
            fetch_topics=fetch_topics,
            speed=initial_speed,
            batch=initial_batch,
            on_genesis=self._bridge.genesis_said.emit,
            on_system=self._bridge.system_note.emit,
            on_status=self._bridge.status_update.emit,
            user_active=self._user_active,
        )

        ctrl = self._engine.snapshot_controls()
        self._build_ui(ctrl["speed"], ctrl["batch"],
                       ctrl["memory"], ctrl["fetch_topics"])

        self._engine.start()

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
        v = self._engine.set_speed(v)
        ms = _SPEED_TABLE.get(v, 0.001) * 1000
        self._speed_lbl.setText(f"Speed  {v}/10  ({ms:.0f} ms between batches)")

    def _chg_batch(self, v):
        v = self._engine.set_batch(v)
        self._batch_lbl.setText(f"Batch  {v}")

    def _chg_mem(self, v):
        v = self._engine.set_memory(v)
        note = "  ⚠ large" if v > 3000 else ""
        self._mem_lbl.setText(f"Memory  {v:,}{note}")

    def _chg_fetch(self, v):
        v = self._engine.set_fetch_topics(v)
        self._fetch_lbl.setText(f"Fetch topics  {v}")

    def _do_explore(self):
        self._engine.explore()
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

    def _dispatch(self, raw: str):
        parsed = GenesisEngine.parse(raw)
        if parsed is None:          # input was all slashes — nothing to do
            return
        cmd, arg = parsed

        if GenesisEngine.is_quit(cmd, arg):
            self._sys("Saving and shutting down…")
            # close() triggers closeEvent, which performs the save (waits
            # up to 30s for an in-flight fetch to release the brain lock).
            QTimer.singleShot(100, self.close)
            return

        # Instant resource controls — the engine setters clamp; the sliders
        # are synced from the applied value so the display never lies.
        if GenesisEngine.is_local(cmd, arg):
            msg = self._engine.run_local(cmd, arg)
            self._sync_sliders()
            self._sys(msg)
            return

        # Brain commands — worker thread so the UI stays live.  The engine
        # turns _Busy and errors into system events, so this never raises.
        if cmd == "learn":
            self._sys("Fetching topics…")
        self._pending_cmds += 1
        threading.Thread(target=self._run_cmd,
                         args=(cmd, arg, raw), daemon=True).start()

    def _run_cmd(self, cmd: str, arg: str, raw: str):
        try:
            for kind, text in self._engine.run_command(cmd, arg, raw):
                if kind == "genesis":
                    self._bridge.genesis_said.emit(text)
                else:
                    self._bridge.system_note.emit(text)
        finally:
            self._pending_cmds = max(0, self._pending_cmds - 1)

    def _sync_sliders(self):
        """Reflect the engine's applied control values in the widgets."""
        ctrl = self._engine.snapshot_controls()
        for slider, value in ((self._speed_sl, ctrl["speed"]),
                              (self._batch_sl, min(ctrl["batch"], 500)),
                              (self._mem_sl,   min(ctrl["memory"], 5000)),
                              (self._fetch_sl, min(ctrl["fetch_topics"], 10))):
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
        # Labels are normally set by the slider callbacks; with signals
        # blocked, refresh them explicitly.
        ms = _SPEED_TABLE.get(ctrl["speed"], 0.001) * 1000
        self._speed_lbl.setText(
            f"Speed  {ctrl['speed']}/10  ({ms:.0f} ms between batches)")
        self._batch_lbl.setText(f"Batch  {ctrl['batch']}")
        note = "  ⚠ large" if ctrl["memory"] > 3000 else ""
        self._mem_lbl.setText(f"Memory  {ctrl['memory']:,}{note}")
        self._fetch_lbl.setText(f"Fetch topics  {ctrl['fetch_topics']}")

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
    # Greeting (engine owns all background threads)
    # ─────────────────────────────────────────────────────────────────────────

    def _send_greeting(self):
        def _greet():
            self._bridge.genesis_said.emit(self._engine.greeting())
        threading.Thread(target=_greet, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # Close
    # ─────────────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        # engine.stop waits up to 30s — an in-flight web fetch can hold the
        # lock for tens of seconds, and skipping the save silently would lose
        # up to 120s (the autosave interval) of memories and relations.
        if not self._engine.stop(timeout=30.0):
            print("WARNING: could not acquire brain lock — session state since "
                  "the last autosave (up to 2 minutes) was not saved.")
        event.accept()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Genesis Desktop GUI")
    add_common_args(ap)
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("Genesis")

    brain = boot_brain(args)

    win = GenesisWindow(
        brain,
        self_directed=args.self_directed,
        fetch_topics=args.fetch_topics,
        initial_speed=max(1, min(10, args.speed)),
        initial_batch=max(1, min(1000, args.batch)),
    )
    win.show()
    sys.exit(app.exec())
