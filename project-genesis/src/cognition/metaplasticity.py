"""
M33: Metaplasticity — adaptive learning rate from prediction-error history.

The problem with a fixed learning rate:
  - Too high: Genesis overwrites solid knowledge every time new evidence arrives
  - Too low: Genesis can't update when something it understood turns out to be wrong

Metaplasticity is the brain's solution: the plasticity of plasticity itself.
The learning rate is a function of the system's own error history.

The signal is not raw error magnitude but its time-derivative:
  learning_progress = −d(error)/dt

This table maps error history to appropriate plasticity level:

  Error    │ Trend        │ State              │ Plasticity
  ─────────┼──────────────┼────────────────────┼───────────
  High     │ Falling fast │ Actively learning  │ 0.70 — high, keep going
  High     │ Flat / stuck │ Can't make progress│ 0.90 — very high, something must change
  Low→High │ Spiking      │ Surprised          │ 0.95 — maximum, reorganize now
  Any      │ Falling slow │ Slowly improving   │ 0.55 — moderate
  Low      │ Stable       │ Mastered           │ 0.20 — low, protect solid knowledge

The plasticity score (0.0–1.0) is written to the relation graph each cycle.
When plasticity is low (<0.3), the graph uses pure MAX confidence accumulation
(existing behaviour). When plasticity is higher, contradicting evidence can
reduce confidence — not enough to destroy a belief from a single input, but
enough for the graph to genuinely update when the world has changed.

Persisted across sessions: Genesis wakes knowing how settled or unsettled its
knowledge was when it last ran.
"""

import json
import time
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator

# ── Constants ──────────────────────────────────────────────────────────────────

_WINDOW          = 30     # cycles of error history kept
_RECENT_N        = 5      # cycles that define "recent"
_SMOOTH_ALPHA    = 0.25   # smoothing factor: 0 = never change, 1 = jump immediately

# Thresholds for trend classification
_IMPROVING_FAST  = -0.06  # error falling by this much → actively learning
_WORSENING_FAST  = +0.10  # error rising by this much → something changed
_FLAT_TOLERANCE  = 0.03   # smaller than this absolute trend → "flat"
_HIGH_ERROR      = 0.55   # "stuck high" if mean error is above this
_LOW_ERROR       = 0.25   # "mastered" if mean error is below this

# Target plasticity for each regime
_P_LEARNING      = 0.70   # error falling fast — keep going
_P_STUCK         = 0.90   # error flat and high — something must change
_P_SURPRISED     = 0.95   # error spiking — reorganize
_P_SLOW_IMPROVE  = 0.55   # error slowly falling
_P_MASTERED      = 0.20   # error stable and low — protect solid knowledge
_P_DEFAULT       = 0.50   # neutral / not enough history

_DB_KEY          = "metaplasticity_state"


class MetaplasticityEngine:
    """
    Tracks Genesis's prediction-error history and computes an adaptive
    plasticity score — the learning rate modifier for the relation graph.

    Usage (called by the orchestrator each cycle):
        meta = MetaplasticityEngine(brain)
        meta.restore()
        ...
        plasticity = meta.update(pred_error)   # call once per cycle
        # brain.relations.set_plasticity() is called automatically
    """

    def __init__(self, brain: "Orchestrator"):
        self._brain  = brain
        self._conn   = brain.relations._conn
        self._history: deque[float] = deque(maxlen=_WINDOW)
        self._plasticity: float = _P_DEFAULT
        self._init_schema()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS metaplasticity_state ("
            "  key      TEXT PRIMARY KEY,"
            "  value    TEXT NOT NULL,"
            "  saved_at REAL NOT NULL"
            ")"
        )
        self._conn.commit()

    def restore(self) -> None:
        """Load persisted state — call once after construction."""
        try:
            row = self._conn.execute(
                "SELECT value FROM metaplasticity_state WHERE key = ?", (_DB_KEY,)
            ).fetchone()
            if row:
                data = json.loads(row[0])
                history = data.get("history", [])
                self._history = deque(history[-_WINDOW:], maxlen=_WINDOW)
                self._plasticity = float(data.get("plasticity", _P_DEFAULT))
                self._brain.relations.set_plasticity(self._plasticity)
        except Exception as exc:
            self._log("metaplasticity.restore", exc)

    def save(self) -> None:
        """Persist current state — called at end of session."""
        try:
            data = json.dumps({
                "history":    list(self._history),
                "plasticity": self._plasticity,
                "saved_at":   time.time(),
            })
            self._conn.execute(
                "INSERT OR REPLACE INTO metaplasticity_state (key, value, saved_at) "
                "VALUES (?, ?, ?)",
                (_DB_KEY, data, time.time())
            )
            self._conn.commit()
        except Exception as exc:
            self._log("metaplasticity.save", exc)

    # ------------------------------------------------------------------
    # Per-cycle update
    # ------------------------------------------------------------------

    def update(self, pred_error: float) -> float:
        """
        Record this cycle's prediction error and return the updated plasticity.

        Also propagates the new plasticity to the relation graph so all
        subsequent calls to relations.add() use the current value.
        """
        self._history.append(float(pred_error))
        target = self._compute_target()

        # Smooth toward target — prevents plasticity from jumping on a single
        # surprising cycle, but responds quickly to sustained shifts.
        self._plasticity = (
            _SMOOTH_ALPHA * target + (1.0 - _SMOOTH_ALPHA) * self._plasticity
        )
        self._brain.relations.set_plasticity(self._plasticity)
        return self._plasticity

    def _compute_target(self) -> float:
        h = list(self._history)
        n = len(h)
        if n < 4:
            return _P_DEFAULT

        recent  = h[-min(_RECENT_N, n):]
        older   = h[:-min(_RECENT_N, n)] or [h[0]]

        mean_r  = sum(recent) / len(recent)
        mean_o  = sum(older)  / len(older)
        trend   = mean_r - mean_o       # positive = getting worse, negative = improving

        # Regimes in priority order:
        if trend > _WORSENING_FAST:
            return _P_SURPRISED                    # sudden error spike → reorganize
        if trend < _IMPROVING_FAST:
            return _P_LEARNING                     # actively improving → keep learning
        if abs(trend) < _FLAT_TOLERANCE:
            if mean_r > _HIGH_ERROR:
                return _P_STUCK                    # stuck at high error → more plastic
            if mean_r < _LOW_ERROR:
                return _P_MASTERED                 # stable and low → protect knowledge
        if trend < 0:
            return _P_SLOW_IMPROVE                 # slowly improving → moderate
        return _P_DEFAULT

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def plasticity(self) -> float:
        """Current plasticity score 0.0 (rigid) – 1.0 (maximally plastic)."""
        return self._plasticity

    def state(self) -> dict:
        """Current state for display and diagnosis."""
        h = list(self._history)
        n = len(h)
        return {
            "plasticity":   round(self._plasticity, 3),
            "regime":       self._regime_name(),
            "error_mean":   round(sum(h) / n, 3) if n else 0.0,
            "error_recent": round(sum(h[-5:]) / min(5, n), 3) if n else 0.0,
            "history_len":  n,
        }

    def _regime_name(self) -> str:
        p = self._plasticity
        if p >= 0.88: return "surprised/stuck"
        if p >= 0.65: return "learning"
        if p >= 0.45: return "moderate"
        if p >= 0.25: return "consolidating"
        return "rigid"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _log(self, label: str, exc: Exception) -> None:
        try:
            self._brain.survival.resilience.error_log.log(label, exc)
        except Exception:
            pass
