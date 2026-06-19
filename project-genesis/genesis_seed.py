#!/usr/bin/env python3
"""
Genesis Seed Prototype

Eleven primitives. Three drives. Real interoception.

Runs as a standalone loop or imported as a module for testing.
No LLM, no cloud, no simulated senses.  The computer IS the body.

Primitives (in dependency order):
  SENSE_SELF  — read live system state via psutil
  RECEIVE     — accept raw bytes from any channel
  MEASURE     — compute 8 information-theoretic features per byte window
  COMPARE     — signed delta between two MEASURE vectors
  ASSOCIATE   — weight edges in a concept graph from co-occurrence
  PREDICT     — project next MEASURE vector from association history
  ERROR       — L2 distance between prediction and observation
  UPDATE      — plasticity-gated adjustment of associations
  REGULATE    — homeostatic signals from drive setpoints vs actuals
  ACT         — select next action: explore / consolidate / rest / alarm
  PERSIST     — append-only log to SQLite (never discard)

Drives:
  SURVIVE     — homeostatic; terminates danger states; subsumption base
  ELABORATE   — appetitive; no terminal setpoint; spends itself reducing ignorance
  REST        — triggered when learning progress → 0; enables consolidation

Empowerment — mutual information between actions and reachable future states;
              proxy: diversity of distinct (action, sensor_bucket) pairs in
              a rolling window.

Wanting / Liking — separate signals:
  WANTING: −d(pred_error)/dt  — gradient of expected error reduction (pursuit)
  LIKING:  Δempowerment       — post-hoc; did acting increase option space?
"""

from __future__ import annotations

import math
import time
import zlib
import hashlib
import sqlite3
import statistics
import collections
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence
from pathlib import Path

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------
_MEASURE_WINDOW    = 256          # bytes fed into each MEASURE call
_SURVIVE_CPU_MAX   = 0.85         # fraction — above this is danger
_SURVIVE_MEM_MAX   = 0.90
_SURVIVE_DISK_MAX  = 0.95
_ELABORATE_BOREDOM = 0.05         # wanting below this → REST triggers
_REST_PATIENCE     = 8            # consecutive low-wanting cycles before REST
_PLASTICITY_INIT   = 0.50
_EMPOWERMENT_WIN   = 64           # rolling window for empowerment calc
_ERROR_SMOOTH      = 0.20         # EMA alpha for error smoothing
_DB_PATH           = ":memory:"   # swap for a file path to persist across runs

# ---------------------------------------------------------------------------
# DATA TYPES
# ---------------------------------------------------------------------------

@dataclass
class SensorReading:
    """Raw interoceptive snapshot from SENSE_SELF."""
    cpu:       float   # 0-1
    memory:    float   # 0-1
    disk:      float   # 0-1
    io_read:   float   # bytes/s (normalised against 1 GiB/s)
    io_write:  float   # bytes/s (normalised)
    timestamp: float   = field(default_factory=time.monotonic)


@dataclass
class MeasureVec:
    """8-dimensional information-theoretic feature vector.

    Computed from raw bytes — no semantic priors.
    """
    entropy:      float   # Shannon entropy (bits/byte, 0-8)
    compression:  float   # compressed_len / raw_len  (LZ complexity proxy)
    mean:         float   # byte mean
    std:          float   # byte std-dev
    zero_frac:    float   # fraction of zero bytes (sparsity)
    high_frac:    float   # fraction of bytes ≥ 128
    run_len:      float   # mean run-length (repetition)
    checksum:     float   # normalised CRC32 (content fingerprint)

    def as_list(self) -> list[float]:
        return [
            self.entropy, self.compression, self.mean, self.std,
            self.zero_frac, self.high_frac, self.run_len, self.checksum,
        ]

    @staticmethod
    def zero() -> "MeasureVec":
        return MeasureVec(0, 1, 0, 0, 0, 0, 0, 0)


@dataclass
class DriveState:
    survive_alarm:  bool  = False   # homeostatic danger
    elaborate_want: float = 0.0     # wanting signal (pursuit)
    elaborate_like: float = 0.0     # liking signal (post-hoc)
    rest_pending:   bool  = False   # REST triggered
    empowerment:    float = 0.0     # option-space measure
    plasticity:     float = _PLASTICITY_INIT


Action = str   # "explore" | "consolidate" | "rest" | "alarm" | "idle"


# ---------------------------------------------------------------------------
# PRIMITIVE: SENSE_SELF
# ---------------------------------------------------------------------------

def sense_self() -> SensorReading:
    """Read live computer-native interoception."""
    if not _PSUTIL:
        return SensorReading(0.1, 0.1, 0.1, 0.0, 0.0)

    cpu  = psutil.cpu_percent(interval=None) / 100.0
    mem  = psutil.virtual_memory().percent / 100.0
    disk = psutil.disk_usage("/").percent / 100.0

    try:
        io = psutil.disk_io_counters()
        # Very rough bandwidth estimate via two samples — skip on first call
        io_r = 0.0
        io_w = 0.0
    except Exception:
        io_r, io_w = 0.0, 0.0

    return SensorReading(cpu=cpu, memory=mem, disk=disk,
                         io_read=io_r, io_write=io_w)


# ---------------------------------------------------------------------------
# PRIMITIVE: RECEIVE
# ---------------------------------------------------------------------------

def receive(channel: str, data: Any) -> bytes:
    """Accept arbitrary input; coerce to raw bytes.

    channel: a label ("stdin", "file", "sensor", …)
    Returns raw bytes — no interpretation yet.
    """
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8", errors="replace")
    if isinstance(data, (int, float)):
        import struct as _s
        return _s.pack(">d", float(data))
    return str(data).encode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# PRIMITIVE: MEASURE
# ---------------------------------------------------------------------------

def measure(raw: bytes) -> MeasureVec:
    """Compute 8 information-theoretic features from raw bytes.

    No semantic knowledge used.  Numbers come from counting and compressing.
    """
    if not raw:
        return MeasureVec.zero()

    buf = raw[:_MEASURE_WINDOW]

    # Shannon entropy
    counts = collections.Counter(buf)
    total  = len(buf)
    probs  = (c / total for c in counts.values())
    entropy = -sum(p * math.log2(p) for p in probs if p > 0)

    # LZ complexity proxy via zlib
    compressed  = zlib.compress(buf, level=1)
    compression = len(compressed) / len(buf)

    # Byte statistics
    byte_vals = list(buf)
    mean  = statistics.mean(byte_vals) / 255.0
    std   = (statistics.pstdev(byte_vals) / 255.0) if len(byte_vals) > 1 else 0.0
    zeros = sum(1 for b in byte_vals if b == 0) / total
    highs = sum(1 for b in byte_vals if b >= 128) / total

    # Mean run-length
    runs = 1
    for i in range(1, len(byte_vals)):
        if byte_vals[i] != byte_vals[i - 1]:
            runs += 1
    mean_run = total / runs / total   # normalise to [0, 1]

    # Normalised CRC32
    checksum = (zlib.crc32(buf) & 0xFFFFFFFF) / 0xFFFFFFFF

    return MeasureVec(
        entropy    = entropy / 8.0,     # normalise to [0, 1]
        compression= compression,
        mean       = mean,
        std        = std,
        zero_frac  = zeros,
        high_frac  = highs,
        run_len    = mean_run,
        checksum   = checksum,
    )


# ---------------------------------------------------------------------------
# PRIMITIVE: COMPARE
# ---------------------------------------------------------------------------

def compare(a: MeasureVec, b: MeasureVec) -> list[float]:
    """Return signed per-dimension delta b − a."""
    return [bv - av for av, bv in zip(a.as_list(), b.as_list())]


def l2(delta: list[float]) -> float:
    return math.sqrt(sum(d * d for d in delta))


# ---------------------------------------------------------------------------
# PRIMITIVE: ASSOCIATE
# ---------------------------------------------------------------------------

class AssociationGraph:
    """Weighted directed edge graph: concept_a → concept_b with confidence."""

    def __init__(self):
        self._edges: dict[tuple[str, str], float] = {}
        self._plasticity: float = _PLASTICITY_INIT

    def set_plasticity(self, p: float) -> None:
        self._plasticity = max(0.0, min(1.0, p))

    def associate(self, a: str, b: str, strength: float) -> None:
        """Plasticity-gated Hebbian update."""
        key = (a, b)
        current = self._edges.get(key, 0.0)
        if strength >= current:
            self._edges[key] = strength
        elif self._plasticity >= 0.30:
            reduction = min(0.40, (self._plasticity - 0.30) / 0.70 * 0.40)
            floor = current * 0.70
            updated = current + (strength - current) * reduction
            self._edges[key] = max(updated, floor)

    def strength(self, a: str, b: str) -> float:
        return self._edges.get((a, b), 0.0)

    def neighbours(self, a: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Return top-k neighbours of concept a by weight."""
        candidates = [(b, w) for (x, b), w in self._edges.items() if x == a]
        return sorted(candidates, key=lambda t: -t[1])[:top_k]

    def concept_count(self) -> int:
        concepts: set[str] = set()
        for a, b in self._edges:
            concepts.add(a)
            concepts.add(b)
        return len(concepts)

    def edge_count(self) -> int:
        return len(self._edges)


# ---------------------------------------------------------------------------
# PRIMITIVE: PREDICT
# ---------------------------------------------------------------------------

def predict(graph: AssociationGraph, context: str,
            history: list[MeasureVec]) -> MeasureVec:
    """Project next MeasureVec from association graph + recent history.

    Strategy: weighted average of the last 3 vectors, biased by graph
    confidence for the current context concept.  Simple but grounded.
    """
    if not history:
        return MeasureVec.zero()

    window = history[-3:]
    weights = [1.0, 2.0, 4.0][-len(window):]

    # Context-weighted blend
    ctx_conf = graph.strength(context, context)  # self-loop = stability
    stability = 0.5 + 0.5 * ctx_conf             # 0.5 – 1.0

    blended = [0.0] * 8
    total_w = sum(weights)
    for vec, w in zip(window, weights):
        for i, v in enumerate(vec.as_list()):
            blended[i] += v * w / total_w

    # Blend between full prediction and last observation based on stability
    last = window[-1].as_list()
    final = [stability * b + (1 - stability) * l
             for b, l in zip(blended, last)]

    return MeasureVec(*final)


# ---------------------------------------------------------------------------
# PRIMITIVE: ERROR
# ---------------------------------------------------------------------------

def error(predicted: MeasureVec, observed: MeasureVec) -> float:
    """L2 prediction error — the primary learning signal."""
    return l2(compare(predicted, observed))


# ---------------------------------------------------------------------------
# PRIMITIVE: UPDATE
# ---------------------------------------------------------------------------

def update(graph: AssociationGraph, context: str, observed: MeasureVec,
           pred_error: float) -> None:
    """Adjust association weights based on prediction error.

    High error → strengthen observation context.
    Low error  → slight reinforcement of existing prediction path.
    """
    # Quantise observation into a concept label (bucket by entropy band)
    e = observed.entropy
    if e < 0.25:
        obs_concept = f"low_entropy_{context}"
    elif e < 0.55:
        obs_concept = f"mid_entropy_{context}"
    else:
        obs_concept = f"high_entropy_{context}"

    # Strengthen observed transition proportionally to surprise
    strength = min(1.0, 0.3 + pred_error * 2.0)
    graph.associate(context, obs_concept, strength)

    # Self-loop (temporal auto-correlation) — context predicts itself
    self_strength = max(0.0, 1.0 - pred_error)
    graph.associate(context, context, self_strength)


# ---------------------------------------------------------------------------
# PRIMITIVE: REGULATE
# ---------------------------------------------------------------------------

def regulate(sensor: SensorReading, drive: DriveState) -> DriveState:
    """Check homeostatic setpoints; update drive state in-place."""
    danger = (
        sensor.cpu    > _SURVIVE_CPU_MAX or
        sensor.memory > _SURVIVE_MEM_MAX or
        sensor.disk   > _SURVIVE_DISK_MAX
    )
    drive.survive_alarm = danger
    return drive


# ---------------------------------------------------------------------------
# PRIMITIVE: ACT
# ---------------------------------------------------------------------------

def act(drive: DriveState) -> Action:
    """Subsumption: lower layers can override higher ones.

    Priority (highest first):
      alarm      — SURVIVE override; shed non-essential work
      rest       — REST triggered by sustained low wanting
      consolidate— moderate wanting but high empowerment gain
      explore    — high wanting; elaborate drive active
      idle       — default
    """
    if drive.survive_alarm:
        return "alarm"
    if drive.rest_pending:
        return "rest"
    if drive.elaborate_want > 0.40:
        return "explore"
    if drive.elaborate_like > 0.20:
        return "consolidate"
    return "idle"


# ---------------------------------------------------------------------------
# PRIMITIVE: PERSIST
# ---------------------------------------------------------------------------

class PersistLog:
    """Append-only SQLite log.  Genesis never discards data."""

    def __init__(self, path: str = _DB_PATH):
        self._con = sqlite3.connect(path)
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id        INTEGER PRIMARY KEY,
                cycle     INTEGER,
                ts        REAL,
                kind      TEXT,
                payload   TEXT
            )
        """)
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS measure_log (
                id          INTEGER PRIMARY KEY,
                cycle       INTEGER,
                ts          REAL,
                entropy     REAL,
                compression REAL,
                mean        REAL,
                std         REAL,
                zero_frac   REAL,
                high_frac   REAL,
                run_len     REAL,
                checksum    REAL,
                pred_error  REAL,
                action      TEXT
            )
        """)
        self._con.commit()

    def log_event(self, cycle: int, kind: str, payload: str) -> None:
        self._con.execute(
            "INSERT INTO event_log(cycle, ts, kind, payload) VALUES (?,?,?,?)",
            (cycle, time.time(), kind, payload)
        )
        self._con.commit()

    def log_measure(self, cycle: int, vec: MeasureVec,
                    pred_error: float, action: Action) -> None:
        v = vec.as_list()
        self._con.execute("""
            INSERT INTO measure_log
              (cycle, ts, entropy, compression, mean, std,
               zero_frac, high_frac, run_len, checksum, pred_error, action)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (cycle, time.time(), *v, pred_error, action))
        self._con.commit()

    def recent_errors(self, n: int = 30) -> list[float]:
        cur = self._con.execute(
            "SELECT pred_error FROM measure_log ORDER BY id DESC LIMIT ?", (n,)
        )
        rows = cur.fetchall()
        return [r[0] for r in reversed(rows)]

    def recent_actions(self, n: int = _EMPOWERMENT_WIN) -> list[str]:
        cur = self._con.execute(
            "SELECT action FROM measure_log ORDER BY id DESC LIMIT ?", (n,)
        )
        rows = cur.fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        self._con.close()


# ---------------------------------------------------------------------------
# EMPOWERMENT SIGNAL
# ---------------------------------------------------------------------------

def compute_empowerment(log: PersistLog) -> float:
    """Proxy empowerment: diversity of (action, sensor_bucket) pairs.

    Full empowerment = mutual information between actions and future states.
    This proxy is tractable with zero extra infrastructure: more distinct
    (action, outcome_bucket) pairs → wider option space → higher empowerment.
    """
    actions = log.recent_actions(_EMPOWERMENT_WIN)
    if not actions:
        return 0.0
    unique = len(set(actions))
    max_unique = len({"explore", "consolidate", "rest", "alarm", "idle"})
    return unique / max_unique


# ---------------------------------------------------------------------------
# WANTING / LIKING SIGNALS
# ---------------------------------------------------------------------------

def compute_wanting(error_history: list[float]) -> float:
    """WANTING = −d(pred_error)/dt (smoothed).

    Positive when error is falling (learning happening → pursue more).
    Negative when error is rising (surprised → urgent).
    Bounded [-1, 1].
    """
    if len(error_history) < 2:
        return 0.0
    recent   = error_history[-3:]
    older    = error_history[-6:-3] or [error_history[0]]
    mean_r   = statistics.mean(recent)
    mean_o   = statistics.mean(older)
    gradient = mean_o - mean_r   # positive = improving = wanting to continue
    return max(-1.0, min(1.0, gradient * 5.0))  # scale to [-1,1]


def compute_liking(prev_empowerment: float, curr_empowerment: float) -> float:
    """LIKING = Δempowerment (post-hoc hedonic signal).

    Did acting increase our option space?  Range [-1, 1].
    """
    return max(-1.0, min(1.0, (curr_empowerment - prev_empowerment) * 10.0))


# ---------------------------------------------------------------------------
# METAPLASTICITY
# ---------------------------------------------------------------------------

def update_plasticity(drive: DriveState, error_history: list[float]) -> float:
    """Adapt plasticity from error trend.

    Regime        → target plasticity
    ─────────────────────────────────
    Worsening fast→ 0.95 (surprised, open to revising beliefs)
    Improving fast→ 0.70 (learning, moderate openness)
    Flat + high   → 0.90 (stuck, try something different)
    Flat + low    → 0.20 (mastered, protect solid knowledge)
    Slow improve  → 0.55 (consolidating)
    Default       → 0.50
    """
    if len(error_history) < 4:
        return drive.plasticity

    recent = error_history[-3:]
    older  = error_history[-6:-3] or [error_history[0]]
    mean_r = statistics.mean(recent)
    mean_o = statistics.mean(older)
    trend  = mean_r - mean_o

    if   trend >  0.10: target = 0.95   # worsening fast
    elif trend < -0.10: target = 0.70   # improving fast
    elif abs(trend) < 0.02:
        target = 0.90 if mean_r > 0.50 else 0.20
    elif trend < 0:     target = 0.55   # slow improve
    else:               target = 0.50

    new_p = 0.25 * target + 0.75 * drive.plasticity
    drive.plasticity = round(new_p, 4)
    return drive.plasticity


# ---------------------------------------------------------------------------
# SEED LOOP
# ---------------------------------------------------------------------------

class GenesisSeed:
    """Minimal cognitive loop running all eleven primitives."""

    def __init__(self, db_path: str = _DB_PATH, verbose: bool = True):
        self.graph    = AssociationGraph()
        self.log      = PersistLog(db_path)
        self.drive    = DriveState()
        self.history:  list[MeasureVec] = []
        self.verbose  = verbose
        self.cycle    = 0
        self._rest_streak = 0
        self._prev_emp    = 0.0
        self._smooth_err  = 0.0

    # ── public API ──────────────────────────────────────────────────────────

    def tick(self, channel: str, data: Any) -> dict[str, Any]:
        """Run one full cognitive cycle.

        1. SENSE_SELF   — interoception
        2. RECEIVE      — coerce input to bytes
        3. MEASURE      — feature vector
        4. COMPARE      — delta from last observation
        5. PREDICT      — next-state estimate
        6. ERROR        — surprise magnitude
        7. UPDATE       — plasticity-gated learning
        8. REGULATE     — homeostatic check
        9. ACT          — action selection
        10. PERSIST     — append-only log
        11. Drive update — wanting / liking / empowerment / plasticity
        """
        self.cycle += 1
        c = self.cycle

        # 1. SENSE_SELF
        sensor = sense_self()

        # 2. RECEIVE
        raw = receive(channel, data)

        # 3. MEASURE
        vec = measure(raw)

        # 4. COMPARE (vs last observation)
        delta = compare(self.history[-1], vec) if self.history else [0.0] * 8

        # 5. PREDICT
        predicted = predict(self.graph, channel, self.history)

        # 6. ERROR
        pred_err = error(predicted, vec)
        self._smooth_err = (
            _ERROR_SMOOTH * pred_err + (1 - _ERROR_SMOOTH) * self._smooth_err
        )

        # 7. UPDATE (plasticity-gated learning)
        update(self.graph, channel, vec, pred_err)
        self.graph.set_plasticity(self.drive.plasticity)

        # Append to in-memory history
        self.history.append(vec)
        if len(self.history) > 128:
            self.history = self.history[-128:]

        # 8. REGULATE
        self.drive = regulate(sensor, self.drive)

        # Drive signals
        err_hist = self.log.recent_errors(30) + [pred_err]
        curr_emp = compute_empowerment(self.log)
        wanting  = compute_wanting(err_hist)
        liking   = compute_liking(self._prev_emp, curr_emp)

        # Metaplasticity
        update_plasticity(self.drive, err_hist)

        # REST trigger
        if wanting < _ELABORATE_BOREDOM:
            self._rest_streak += 1
        else:
            self._rest_streak = 0
        self.drive.rest_pending = self._rest_streak >= _REST_PATIENCE

        self.drive.elaborate_want = wanting
        self.drive.elaborate_like = liking
        self.drive.empowerment    = curr_emp
        self._prev_emp            = curr_emp

        # 9. ACT
        action = act(self.drive)

        # 10. PERSIST
        self.log.log_measure(c, vec, pred_err, action)
        if c == 1 or action == "alarm":
            self.log.log_event(c, action,
                f"cpu={sensor.cpu:.2f} mem={sensor.memory:.2f} "
                f"err={pred_err:.4f} want={wanting:.3f} p={self.drive.plasticity:.3f}"
            )

        result = {
            "cycle":        c,
            "channel":      channel,
            "pred_error":   round(pred_err,  4),
            "smooth_error": round(self._smooth_err, 4),
            "action":       action,
            "wanting":      round(wanting, 3),
            "liking":       round(liking,  3),
            "empowerment":  round(curr_emp, 3),
            "plasticity":   self.drive.plasticity,
            "survive_alarm":self.drive.survive_alarm,
            "rest_pending": self.drive.rest_pending,
            "concepts":     self.graph.concept_count(),
            "edges":        self.graph.edge_count(),
            "sensor":       {
                "cpu": round(sensor.cpu,    3),
                "mem": round(sensor.memory, 3),
                "disk":round(sensor.disk,   3),
            },
        }

        if self.verbose:
            self._print(result)

        return result

    def close(self) -> None:
        self.log.close()

    # ── internals ───────────────────────────────────────────────────────────

    def _print(self, r: dict) -> None:
        flags = ""
        if r["survive_alarm"]: flags += " [ALARM]"
        if r["rest_pending"]:  flags += " [REST]"
        print(
            f"C{r['cycle']:04d} | {r['channel']:<12} | "
            f"err={r['pred_error']:.4f} want={r['wanting']:+.3f} "
            f"like={r['liking']:+.3f} emp={r['empowerment']:.3f} "
            f"p={r['plasticity']:.3f} → {r['action']}{flags}"
        )


# ---------------------------------------------------------------------------
# DEMO
# ---------------------------------------------------------------------------

def _demo():
    """Run a short demo to show the seed loop in action."""
    import os
    import struct

    print("=" * 70)
    print("Genesis Seed — Python Prototype")
    print("=" * 70)
    print("Eleven primitives. Three drives. Real interoception.")
    print("No LLM. No cloud. No simulated senses.\n")

    seed = GenesisSeed(verbose=True)

    channels = [
        # (channel_name, data_generator)
        ("sensor",  lambda i: struct.pack(">ff", time.monotonic(), i * 0.01)),
        ("stdin",   lambda i: f"hello world cycle {i}"),
        ("file",    lambda i: os.urandom(128) if i % 3 == 0 else b"\x00" * 64),
        ("sensor",  lambda i: struct.pack(">ff", time.monotonic(), math.sin(i / 5))),
    ]

    try:
        for i in range(1, 33):
            ch_name, gen = channels[i % len(channels)]
            seed.tick(ch_name, gen(i))
            time.sleep(0.05)

        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)
        last = seed.log.recent_errors(10)
        if last:
            print(f"  Mean pred error (last 10): {statistics.mean(last):.4f}")
        print(f"  Concepts learned : {seed.graph.concept_count()}")
        print(f"  Association edges: {seed.graph.edge_count()}")
        print(f"  Final plasticity : {seed.drive.plasticity}")
        print(f"  Final empowerment: {seed.drive.empowerment:.3f}")
        print(f"  Wanting          : {seed.drive.elaborate_want:+.3f}")
        print(f"  Liking           : {seed.drive.elaborate_like:+.3f}")
    finally:
        seed.close()


if __name__ == "__main__":
    _demo()
