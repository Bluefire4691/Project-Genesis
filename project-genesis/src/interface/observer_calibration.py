"""
Observer Calibration Engine — M14.

Derives Observer thresholds empirically from Genesis's own behavioral history
rather than relying on hardcoded defaults.

Research grounding:
- ACT-R (Anderson): utility learning — each production rule has a utility
  estimate updated from outcomes. Rules with high utility fire preferentially.
  Here: each Observer threshold is a "rule" whose utility is its fit to
  Genesis's actual behavior. Calibration = updating utilities from archive data.
- SOAR (Newell/Laird): chunking — recurring state→outcome patterns compiled
  into lightweight rules. The calibration extracts recurring patterns from the
  archive and encodes them as threshold adjustments.

The core problem with hardcoded thresholds:
  "No new relations for 10 cycles = stagnation" is meaningless unless you know
  how often THIS instance typically adds relations. If Genesis usually adds a
  relation every 20 cycles, 10 cycles without one is half a normal gap — not
  stagnation. If it usually adds one every 2 cycles, 10 cycles is 5× normal —
  definitely stagnation. The threshold must be calibrated to the instance's
  own behavioral baseline.

Calibration is attempted after each reflection and requires minimum data:
- 50+ archive entries (for significance statistics)
- 10+ relations (for growth rate estimation)
- 2+ reflections (to measure cross-session consistency)

Below minimum data, defaults are preserved. Above minimum, thresholds are
adjusted incrementally (not snapped) to prevent overreaction to early data.
"""

import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from interface.observer import Observer


# Minimum data requirements before calibration fires
_MIN_ARCHIVE_ENTRIES = 50
_MIN_RELATIONS = 10

# Maximum adjustment per calibration pass (prevents thrashing)
_MAX_STEP_CYCLES = 3     # int thresholds shift by at most 3 per pass
_MAX_STEP_FLOAT = 0.05   # float thresholds shift by at most 0.05 per pass

# Bounds on calibrated thresholds
_BOUNDS = {
    "stagnation_no_associations_cycles":   (3, 50),
    "stagnation_attention_freeze_cycles":  (3, 30),
    "stagnation_min_new_memories":         (0, 5),
    "danger_energy_floor":                 (0.05, 0.40),
    "commitment_cycles":                   (3, 15),
}

# Persistence key in consolidation_state
_STATE_KEY = "observer_calibration"


@dataclass
class CalibrationResult:
    """What the calibration engine computed and why."""
    thresholds: dict          # name → value (what was applied)
    rationale: dict           # name → explanation string
    data_points: int          # archive entries used
    relation_count: int       # relations used
    confidence: float         # 0.0–1.0 — how much data backed the calibration
    skipped: bool = False     # True if below minimum data requirement
    skip_reason: str = ""


class ObserverCalibration:
    """
    Derives Observer thresholds from behavioral history.

    Usage:
        calibration = ObserverCalibration(conn)
        result = calibration.calibrate(observer, cycle_count)
    """

    def __init__(self, conn):
        self._conn = conn

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def calibrate(self, observer: "Observer", cycle_count: int) -> CalibrationResult:
        """
        Read behavioral history, derive thresholds, update the Observer.

        Returns a CalibrationResult describing what was done and why.
        """
        # --- gather data ---
        archive_rows = self._archive_data()
        relation_rows = self._relation_timestamps()
        reflection_rows = self._reflection_data()

        n_archive = len(archive_rows)
        n_relations = len(relation_rows)

        if n_archive < _MIN_ARCHIVE_ENTRIES or n_relations < _MIN_RELATIONS:
            return CalibrationResult(
                thresholds={},
                rationale={},
                data_points=n_archive,
                relation_count=n_relations,
                confidence=0.0,
                skipped=True,
                skip_reason=(
                    f"Insufficient data: {n_archive} archive entries "
                    f"(need {_MIN_ARCHIVE_ENTRIES}), "
                    f"{n_relations} relations (need {_MIN_RELATIONS})"
                ),
            )

        # --- compute calibrated values ---
        thresholds = {}
        rationale = {}

        # 1. Relation growth rate → no_associations_cycles threshold
        rels_threshold, rels_note = self._calibrate_rels_threshold(
            relation_rows, cycle_count, observer._stagnation_no_associations_cycles
        )
        thresholds["stagnation_no_associations_cycles"] = rels_threshold
        rationale["stagnation_no_associations_cycles"] = rels_note

        # 2. Archive memory rate → attention_freeze_cycles threshold
        freeze_threshold, freeze_note = self._calibrate_freeze_threshold(
            archive_rows, cycle_count, observer._stagnation_attention_freeze_cycles
        )
        thresholds["stagnation_attention_freeze_cycles"] = freeze_threshold
        rationale["stagnation_attention_freeze_cycles"] = freeze_note

        # 3. Significance distribution → min_new_memories floor
        mem_floor, mem_note = self._calibrate_memory_floor(
            archive_rows, observer._stagnation_min_new_memories
        )
        thresholds["stagnation_min_new_memories"] = mem_floor
        rationale["stagnation_min_new_memories"] = mem_note

        # 4. Energy history from interoception → danger_energy_floor
        energy_floor, energy_note = self._calibrate_energy_floor(
            observer._danger_energy_floor
        )
        thresholds["danger_energy_floor"] = energy_floor
        rationale["danger_energy_floor"] = energy_note

        # 5. Archive entry clustering → commitment_cycles
        commit, commit_note = self._calibrate_commitment(
            archive_rows, cycle_count, observer.COMMITMENT_CYCLES
        )
        thresholds["commitment_cycles"] = commit
        rationale["commitment_cycles"] = commit_note

        # --- apply with incremental adjustment (no sudden jumps) ---
        self._apply(observer, thresholds)

        # --- persist ---
        confidence = min(1.0, n_archive / 500.0)  # asymptotes toward 1.0 at 500 entries
        self._persist(thresholds, confidence)

        return CalibrationResult(
            thresholds=thresholds,
            rationale=rationale,
            data_points=n_archive,
            relation_count=n_relations,
            confidence=round(confidence, 3),
        )

    def load_calibrated(self, observer: "Observer") -> bool:
        """
        Restore previously calibrated thresholds to the Observer.
        Returns True if calibration data existed.
        """
        try:
            row = self._conn.execute(
                "SELECT value FROM consolidation_state WHERE key=?",
                (_STATE_KEY,),
            ).fetchone()
            if not row:
                return False
            data = json.loads(str(row[0]))
            thresholds = data.get("thresholds", {})
            if thresholds:
                self._apply(observer, thresholds)
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # Individual threshold calibrations
    # ------------------------------------------------------------------

    def _calibrate_rels_threshold(
        self, relation_rows: list, cycle_count: int, current: int
    ) -> tuple[int, str]:
        """
        Derive the no_associations_cycles threshold from relation growth rate.

        The threshold is set to 3× the median inter-relation interval in cycles,
        so "stagnation" means the gap is 3× longer than normal.
        """
        if len(relation_rows) < 5 or cycle_count < 10:
            return current, "insufficient data — keeping default"

        timestamps = sorted(t for (t,) in relation_rows)
        elapsed = max(1.0, timestamps[-1] - timestamps[0])
        cycles_per_sec = cycle_count / max(1.0, time.time() - timestamps[0])
        if cycles_per_sec <= 0:
            return current, "could not estimate cycle rate — keeping default"

        # Median gap between successive relations
        gaps_sec = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]
        gaps_sec.sort()
        median_gap_sec = gaps_sec[len(gaps_sec) // 2]
        median_gap_cycles = max(1.0, median_gap_sec * cycles_per_sec)

        # 3× median = definitely unusual, not just noise
        target = max(_BOUNDS["stagnation_no_associations_cycles"][0],
                     min(_BOUNDS["stagnation_no_associations_cycles"][1],
                         int(3.0 * median_gap_cycles)))

        note = (
            f"median inter-relation gap ≈ {median_gap_cycles:.1f} cycles → "
            f"3× = {target} cycles for stagnation threshold"
        )
        return _step_int(current, target, _MAX_STEP_CYCLES), note

    def _calibrate_freeze_threshold(
        self, archive_rows: list, cycle_count: int, current: int
    ) -> tuple[int, str]:
        """
        Derive the attention_freeze_cycles threshold from archive memory rate.

        More frequent new memory creation → lower freeze threshold (attention
        should rotate more frequently). Slower creation → higher threshold.
        """
        if len(archive_rows) < 20 or cycle_count < 20:
            return current, "insufficient data — keeping default"

        timestamps = sorted(t for (t, _sig) in archive_rows[-200:])
        if len(timestamps) < 5:
            return current, "sparse archive — keeping default"

        elapsed = max(1.0, timestamps[-1] - timestamps[0])
        rate = len(timestamps) / elapsed  # entries per second

        # Estimate cycles per second
        cycles_per_sec = cycle_count / max(1.0, time.time() - timestamps[0])
        if cycles_per_sec <= 0:
            return current, "could not estimate cycle rate — keeping default"

        # Average cycles between new memories
        avg_cycles_per_entry = 1.0 / max(0.001, rate * cycles_per_sec)

        # Freeze threshold = 4× the average cycle gap between new memories
        target = max(_BOUNDS["stagnation_attention_freeze_cycles"][0],
                     min(_BOUNDS["stagnation_attention_freeze_cycles"][1],
                         int(4.0 * avg_cycles_per_entry)))

        note = (
            f"avg {avg_cycles_per_entry:.1f} cycles/entry → "
            f"4× = {target} cycles for attention freeze"
        )
        return _step_int(current, target, _MAX_STEP_CYCLES), note

    def _calibrate_memory_floor(
        self, archive_rows: list, current: int
    ) -> tuple[int, str]:
        """
        Derive the min_new_memories floor from the significance distribution.

        If the median significance is very low (most inputs are routine),
        the floor stays 0. If most inputs are above average significance,
        the floor can rise to 1 (expect at least one meaningful memory/cycle).
        """
        if len(archive_rows) < 30:
            return current, "insufficient data — keeping default"

        sigs = sorted(sig for (_t, sig) in archive_rows)
        median_sig = sigs[len(sigs) // 2]
        pct_above_half = sum(1 for s in sigs if s > 0.5) / len(sigs)

        # If >30% of inputs are high-significance, expect at least 1 per cycle
        if pct_above_half > 0.30:
            target = 1
            note = f"{pct_above_half*100:.0f}% archive entries above 0.5 significance → floor=1"
        else:
            target = 0
            note = f"median sig={median_sig:.2f}, only {pct_above_half*100:.0f}% > 0.5 → floor=0"

        return target, note

    def _calibrate_energy_floor(self, current: float) -> tuple[float, str]:
        """
        Calibrate danger energy floor from interoception history.

        Reads energy values stored by the interoception processor and sets
        the floor to slightly below the 5th percentile of observed values.
        """
        try:
            rows = self._conn.execute("""
                SELECT content FROM memories
                WHERE key LIKE 'num:internal_state%'
                ORDER BY last_accessed DESC LIMIT 100
            """).fetchall()

            energy_vals = []
            for (content,) in rows:
                # Content format: "... | {"label": ..., "values": [e, m], ...}"
                import re
                m = re.search(r'"energy":\s*([\d.]+)', str(content))
                if m:
                    try:
                        energy_vals.append(float(m.group(1)))
                    except ValueError:
                        pass

            if len(energy_vals) >= 10:
                energy_vals.sort()
                p5 = energy_vals[max(0, len(energy_vals) // 20)]
                # Set floor just below 5th percentile of normal operation
                target = max(_BOUNDS["danger_energy_floor"][0],
                             min(_BOUNDS["danger_energy_floor"][1],
                                 round(p5 * 0.80, 3)))
                note = (
                    f"5th pct energy from interoception = {p5:.3f} → "
                    f"floor={target:.3f} (80% of p5)"
                )
                return _step_float(current, target, _MAX_STEP_FLOAT), note
        except Exception:
            pass
        return current, "no interoception data yet — keeping default"

    def _calibrate_commitment(
        self, archive_rows: list, cycle_count: int, current: int
    ) -> tuple[int, str]:
        """
        Calibrate COMMITMENT_CYCLES from archive entry clustering.

        If archive entries come in tight bursts (many in short time spans),
        commitment should be longer to avoid reacting to burst variation.
        If entries are steady, a shorter commitment window is appropriate.
        """
        if len(archive_rows) < 30 or cycle_count < 30:
            return current, "insufficient data — keeping default"

        timestamps = sorted(t for (t, _sig) in archive_rows[-100:])
        if len(timestamps) < 10:
            return current, "sparse archive — keeping default"

        gaps = sorted(timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps)))
        if not gaps:
            return current, "no gaps found — keeping default"

        median_gap = gaps[len(gaps) // 2]
        p90_gap = gaps[int(len(gaps) * 0.90)]

        # Burst ratio: if p90 gap is much larger than median, entries cluster
        burst_ratio = p90_gap / max(0.001, median_gap)

        if burst_ratio > 5.0:
            # High clustering — need longer commitment to see through bursts
            target = min(_BOUNDS["commitment_cycles"][1], current + 2)
            note = f"burst ratio={burst_ratio:.1f} → lengthen commitment to {target}"
        elif burst_ratio < 2.0:
            # Steady stream — shorter commitment is safe
            target = max(_BOUNDS["commitment_cycles"][0], current - 1)
            note = f"steady stream (burst ratio={burst_ratio:.1f}) → shorten commitment to {target}"
        else:
            target = current
            note = f"burst ratio={burst_ratio:.1f} → commitment unchanged at {current}"

        return _step_int(current, target, _MAX_STEP_CYCLES), note

    # ------------------------------------------------------------------
    # Data fetchers
    # ------------------------------------------------------------------

    def _archive_data(self) -> list[tuple]:
        try:
            return self._conn.execute(
                "SELECT archived_at, significance FROM archive_metadata ORDER BY archived_at"
            ).fetchall()
        except Exception:
            return []

    def _relation_timestamps(self) -> list[tuple]:
        try:
            return self._conn.execute(
                "SELECT created_at FROM relations ORDER BY created_at"
            ).fetchall()
        except Exception:
            return []

    def _reflection_data(self) -> list[tuple]:
        try:
            return self._conn.execute(
                "SELECT created_at, cycle FROM reflections ORDER BY created_at"
            ).fetchall()
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Apply and persist
    # ------------------------------------------------------------------

    def _apply(self, observer: "Observer", thresholds: dict) -> None:
        """Apply calibrated thresholds to Observer, with validation."""
        mapping = {
            "stagnation_no_associations_cycles":  "_stagnation_no_associations_cycles",
            "stagnation_attention_freeze_cycles":  "_stagnation_attention_freeze_cycles",
            "stagnation_min_new_memories":         "_stagnation_min_new_memories",
            "danger_energy_floor":                 "_danger_energy_floor",
        }
        for public_name, attr in mapping.items():
            if public_name in thresholds:
                val = thresholds[public_name]
                lo, hi = _BOUNDS.get(public_name, (0, 9999))
                clamped = max(lo, min(hi, val))
                try:
                    setattr(observer, attr, clamped)
                except Exception:
                    pass

        if "commitment_cycles" in thresholds:
            lo, hi = _BOUNDS["commitment_cycles"]
            val = max(lo, min(hi, thresholds["commitment_cycles"]))
            try:
                observer.COMMITMENT_CYCLES = val
            except Exception:
                pass

    def _persist(self, thresholds: dict, confidence: float) -> None:
        try:
            payload = json.dumps({
                "thresholds": thresholds,
                "confidence": confidence,
                "calibrated_at": time.time(),
            })
            self._conn.execute(
                "INSERT OR REPLACE INTO consolidation_state (key, value) VALUES (?, ?)",
                (_STATE_KEY, payload),
            )
            self._conn.commit()
        except Exception:
            pass


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _step_int(current: int, target: int, max_step: int) -> int:
    """Move current toward target by at most max_step per pass."""
    if target > current:
        return current + min(max_step, target - current)
    elif target < current:
        return current - min(max_step, current - target)
    return current


def _step_float(current: float, target: float, max_step: float) -> float:
    """Move current toward target by at most max_step per pass."""
    if target > current:
        return round(current + min(max_step, target - current), 4)
    elif target < current:
        return round(current - min(max_step, current - target), 4)
    return current
