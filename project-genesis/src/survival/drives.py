"""
M26: Drive System — Genesis's internal biological-analog pressure signals.

Five drives track Genesis's internal state each cognitive cycle.
Unlike the resource monitor (which watches CPU/RAM), drives measure
the health of the *cognitive* experience: is it learning? is it stuck?
is it overwhelmed by contradiction? is it bored?

Each drive is a float 0.0–1.0. They decay toward a resting baseline
every cycle and are pushed by observable signals from that cycle's
outcome. High drive values influence behavior through behavioral_hints()
— topic diversity, curiosity urgency, reflection timing.

The drives are persistent: Genesis wakes from a shutdown with the same
internal state it had when it stopped.

    hunger      — urgency to fill knowledge gaps (directive backlog, sparse graph)
    frustration — blocked goal-seeking (empty cycles, stuck on same topic)
    anticipation— excitement from active learning (relations flowing in)
    boredom     — novelty collapse (revisiting already-known territory)
    dissonance  — cognitive tension from unresolved contradictions
"""
import json
import time
from dataclasses import dataclass, asdict, field


# ── Data structures ────────────────────────────────────────────────────────

@dataclass
class CycleStats:
    """Signals from one cognitive cycle, passed to DriveSystem.update()."""
    relations_added: int = 0
    new_conflicts:   int = 0
    stored_keys_count: int = 0
    directive_count: int = 0   # active curiosity directives pending
    cycle_number:    int = 0


@dataclass
class DriveState:
    hunger:       float = 0.5   # 0=sated,     1=urgent
    frustration:  float = 0.0   # 0=flowing,   1=blocked
    anticipation: float = 0.3   # 0=flat,      1=excited
    boredom:      float = 0.0   # 0=engaged,   1=disengaged
    dissonance:   float = 0.0   # 0=coherent,  1=conflicted
    updated_at:   float = field(default_factory=time.time)


# ── Constants ──────────────────────────────────────────────────────────────

# Resting baselines — drives decay toward these each cycle
_BASELINE = {
    "hunger":       0.4,
    "frustration":  0.0,
    "anticipation": 0.3,
    "boredom":      0.0,
    "dissonance":   0.0,
}

# How fast each drive decays toward its baseline (per cycle)
_DECAY = {
    "hunger":       0.05,
    "frustration":  0.12,   # frustration dissipates quickly when unblocked
    "anticipation": 0.08,
    "boredom":      0.10,
    "dissonance":   0.04,   # contradictions linger
}

# Thresholds for behavioral influence
_STRONG = 0.65   # drive is "strong" above this — starts shaping behavior
_DOMINANT = 0.80 # drive is "dominant" above this — clearly the main pressure

_DB_KEY = "drive_state"


# ── DriveSystem ────────────────────────────────────────────────────────────

class DriveSystem:
    """
    Tracks and updates Genesis's five internal drive states.

    Usage:
        drives = DriveSystem(conn)
        drives.restore()           # call once after construction

        # at end of each cognitive cycle:
        stats = CycleStats(relations_added=n, new_conflicts=k, ...)
        drives.update(stats)

        # query current state:
        hints = drives.behavioral_hints()
        summary = drives.summary()
    """

    def __init__(self, conn):
        self._conn = conn
        self._state = DriveState()
        self._cycle_since_last_relations = 0  # consecutive empty cycles
        self._init_schema()

    # ── Schema ──────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS drive_state ("
            "  state_key  TEXT PRIMARY KEY,"
            "  value_json TEXT NOT NULL,"
            "  saved_at   REAL NOT NULL"
            ")"
        )
        self._conn.commit()

    # ── Core update ─────────────────────────────────────────────────────

    def update(self, stats: CycleStats) -> None:
        """
        Update all drives based on the outcome of one cognitive cycle.
        Called once per cycle by the orchestrator.
        """
        s = self._state

        # Track consecutive cycles with no learning
        if stats.relations_added == 0:
            self._cycle_since_last_relations += 1
        else:
            self._cycle_since_last_relations = 0

        empty_streak = self._cycle_since_last_relations

        # ── Hunger ──────────────────────────────────────────────────────
        # Rises with unresolved curiosity gaps; satisfied by new relations.
        # Push magnitudes are kept small (≤0.06) so hunger can't saturate
        # at 1.0 on a fresh brain where directive_count spikes immediately.
        hunger_signal = 0.0
        if stats.directive_count > 5:
            hunger_signal += 0.06
        elif stats.directive_count > 2:
            hunger_signal += 0.03
        if stats.relations_added >= 3:
            hunger_signal -= 0.12   # fed
        elif stats.relations_added == 0:
            hunger_signal += 0.02   # still hungry
        s.hunger = _decay_toward(s.hunger, _BASELINE["hunger"], _DECAY["hunger"], hunger_signal)

        # ── Frustration ─────────────────────────────────────────────────
        # Spikes when learning is blocked; resets quickly when it flows
        if stats.relations_added == 0:
            frustration_push = 0.10 + min(0.20, empty_streak * 0.03)
        elif stats.relations_added >= 4:
            frustration_push = -0.25   # strong flow clears frustration fast
        else:
            frustration_push = -0.08
        s.frustration = _decay_toward(s.frustration, _BASELINE["frustration"], _DECAY["frustration"], frustration_push)

        # ── Anticipation ────────────────────────────────────────────────
        # Rises when learning is active; conflicts add interesting complexity
        if stats.relations_added >= 5:
            anticipation_push = 0.18
        elif stats.relations_added >= 2:
            anticipation_push = 0.08
        elif stats.relations_added == 0:
            anticipation_push = -0.05
        else:
            anticipation_push = 0.02
        if stats.new_conflicts > 0:
            anticipation_push += 0.05  # finding contradictions = interesting
        s.anticipation = _decay_toward(s.anticipation, _BASELINE["anticipation"], _DECAY["anticipation"], anticipation_push)

        # ── Boredom ─────────────────────────────────────────────────────
        # Rises when nothing new is happening; any real learning resets it
        if stats.relations_added == 0 and stats.new_conflicts == 0:
            boredom_push = 0.08 + min(0.15, empty_streak * 0.02)
        elif stats.relations_added >= 3:
            boredom_push = -0.20   # genuinely learning = not bored
        else:
            boredom_push = -0.04
        s.boredom = _decay_toward(s.boredom, _BASELINE["boredom"], _DECAY["boredom"], boredom_push)

        # ── Dissonance ──────────────────────────────────────────────────
        # Set from contradiction signals; dissipates slowly
        if stats.new_conflicts > 0:
            dissonance_push = 0.12 * min(stats.new_conflicts, 3)
        else:
            dissonance_push = -0.02   # slight relief when no new conflicts
        s.dissonance = _decay_toward(s.dissonance, _BASELINE["dissonance"], _DECAY["dissonance"], dissonance_push)

        s.updated_at = time.time()
        self._persist()

    # ── Behavioral influence ─────────────────────────────────────────────

    def behavioral_hints(self) -> dict:
        """
        Returns modifiers for other subsystems to optionally apply.

        Keys:
          diversity_boost   float 0-1: increase topic/source diversity
                            (high boredom or frustration → seek new territory)
          curiosity_boost   float 0-1: lower the threshold for forming directives
                            (high hunger → become more curious about gaps)
          reflect_sooner    bool: trigger consolidation reflection now
                            (high dissonance → resolve tensions actively)
          dominant_drive    str: name of the currently strongest drive
          dominant_level    float: strength of the dominant drive
        """
        s = self._state
        dominant, level = self._dominant()

        diversity_boost = max(s.boredom, s.frustration) if max(s.boredom, s.frustration) > _STRONG else 0.0
        curiosity_boost = (s.hunger - _BASELINE["hunger"]) if s.hunger > _STRONG else 0.0
        reflect_sooner  = s.dissonance > _STRONG

        return {
            "diversity_boost":  round(diversity_boost, 3),
            "curiosity_boost":  round(curiosity_boost, 3),
            "reflect_sooner":   reflect_sooner,
            "dominant_drive":   dominant,
            "dominant_level":   round(level, 3),
        }

    # ── Expression support ───────────────────────────────────────────────

    def expressive_state(self) -> str | None:
        """
        Returns a short phrase describing the dominant drive if it is strong
        enough to be worth mentioning, or None if the system is in a neutral
        state.  Used by GenesisVoice to colour its self-expression.
        """
        dominant, level = self._dominant()
        if level < _STRONG:
            return None
        phrases = {
            "hunger":       "I feel like I'm still missing pieces.",
            "frustration":  "I keep hitting dead ends — something isn't connecting.",
            "anticipation": "Things are coming together right now.",
            "boredom":      "I need to find something new to think about.",
            "dissonance":   "I'm holding some ideas that don't fit together yet.",
        }
        return phrases.get(dominant)

    def summary(self) -> dict:
        """Full drive state snapshot for logging and self-model queries."""
        s = self._state
        dominant, level = self._dominant()
        return {
            "hunger":       round(s.hunger, 3),
            "frustration":  round(s.frustration, 3),
            "anticipation": round(s.anticipation, 3),
            "boredom":      round(s.boredom, 3),
            "dissonance":   round(s.dissonance, 3),
            "dominant":     dominant,
            "dominant_level": round(level, 3),
            "empty_streak": self._cycle_since_last_relations,
        }

    # ── Persistence ──────────────────────────────────────────────────────

    def save(self) -> None:
        """Checkpoint drive state to SQLite (called by SessionManager.save)."""
        self._persist()

    def restore(self) -> bool:
        """Load persisted drive state. Returns True if state was found."""
        row = self._conn.execute(
            "SELECT value_json FROM drive_state WHERE state_key = ?",
            (_DB_KEY,)
        ).fetchone()
        if not row:
            return False
        try:
            data = json.loads(row[0])
            s = self._state
            s.hunger       = float(data.get("hunger",       s.hunger))
            s.frustration  = float(data.get("frustration",  s.frustration))
            s.anticipation = float(data.get("anticipation", s.anticipation))
            s.boredom      = float(data.get("boredom",      s.boredom))
            s.dissonance   = float(data.get("dissonance",   s.dissonance))
            self._cycle_since_last_relations = int(
                data.get("empty_streak", self._cycle_since_last_relations)
            )
        except Exception:
            return False
        return True

    # ── Internal ─────────────────────────────────────────────────────────

    def _dominant(self) -> tuple[str, float]:
        """Return (drive_name, level) for the drive furthest above its baseline."""
        s = self._state
        deltas = {
            "hunger":       s.hunger       - _BASELINE["hunger"],
            "frustration":  s.frustration  - _BASELINE["frustration"],
            "anticipation": s.anticipation - _BASELINE["anticipation"],
            "boredom":      s.boredom      - _BASELINE["boredom"],
            "dissonance":   s.dissonance   - _BASELINE["dissonance"],
        }
        dominant = max(deltas, key=deltas.get)
        return dominant, getattr(s, dominant)

    def _persist(self) -> None:
        s = self._state
        payload = {
            "hunger":       s.hunger,
            "frustration":  s.frustration,
            "anticipation": s.anticipation,
            "boredom":      s.boredom,
            "dissonance":   s.dissonance,
            "empty_streak": self._cycle_since_last_relations,
        }
        self._conn.execute(
            "INSERT INTO drive_state (state_key, value_json, saved_at)"
            " VALUES (?, ?, ?)"
            " ON CONFLICT(state_key) DO UPDATE SET"
            "   value_json = excluded.value_json,"
            "   saved_at   = excluded.saved_at",
            (_DB_KEY, json.dumps(payload), time.time())
        )
        self._conn.commit()


# ── Helper ────────────────────────────────────────────────────────────────

def _decay_toward(value: float, baseline: float, decay: float, push: float) -> float:
    """Move value toward baseline by decay, then apply push signal, clamp to [0,1]."""
    value += (baseline - value) * decay
    value += push
    return max(0.0, min(1.0, value))
