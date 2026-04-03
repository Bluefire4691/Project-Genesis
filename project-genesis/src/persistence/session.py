"""
Session Manager — save and restore Genesis state across process restarts.

The memory SQLite DB already persists all memories durably. This adds
state continuity for the higher-level cognitive context:

  - cycle_count   : total cycles processed (continuity of experience)
  - curriculum_stage : current learning stage (don't restart from FOUNDATION)
  - working memory warm-start : top-K memories by relevance promoted
    back into working memory so attention picks up close to where it left off

Directive satisfaction intentionally not restored — it re-converges within
a few cycles from real resource/memory stats. Trying to pickle live objects
across code changes is fragile; convergence is fast and authentic.

Usage:
    manager = SessionManager(conn)      # same conn as LongTermStore
    manager.save(brain)                 # call to checkpoint
    restored = manager.restore(brain)   # call on startup; returns True/False
"""

import json
import sqlite3
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


_WARM_START_KEYS = 30   # how many memories to promote on restore


class SessionManager:
    """
    Manages session checkpoint state in the memory DB.

    Schema: key-value pairs where value is a JSON string.
    Uses the same sqlite3.Connection as LongTermStore and ArchiveStore —
    no extra file, no multi-connection contention.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS session_state (
                state_key   TEXT PRIMARY KEY,
                value_json  TEXT NOT NULL,
                saved_at    REAL NOT NULL
            )
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, brain: "Orchestrator") -> None:
        """
        Checkpoint current brain state.

        Saves cycle count, curriculum stage, and the keys of the
        top working-memory items for warm-start on next restore().
        """
        now = time.time()

        # Top working-memory keys (by relevance) for warm-start
        wm = brain.memory.memories
        warm_keys = sorted(wm, key=lambda k: wm[k].relevance, reverse=True)[:_WARM_START_KEYS]

        state = {
            "cycle_count": brain.cycle_count,
            "curriculum_stage": int(brain.curriculum.current_stage),
            "warm_start_keys": warm_keys,
            "session_id": brain.session_id,
            "saved_at": now,
        }

        for key, value in state.items():
            self._conn.execute("""
                INSERT INTO session_state (state_key, value_json, saved_at)
                VALUES (?, ?, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    value_json = excluded.value_json,
                    saved_at   = excluded.saved_at
            """, (key, json.dumps(value), now))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore(self, brain: "Orchestrator") -> bool:
        """
        Restore brain state from last checkpoint.

        Returns True if state was found and applied, False if no checkpoint.

        Restores:
          - cycle_count (continuity of experience counter)
          - curriculum_stage (don't repeat completed stages)
          - top working-memory keys promoted from SQLite (attention warm-start)
        """
        rows = self._conn.execute(
            "SELECT state_key, value_json FROM session_state"
        ).fetchall()

        if not rows:
            return False

        state = {r["state_key"]: json.loads(r["value_json"]) for r in rows}

        # Restore cycle counter
        if "cycle_count" in state:
            brain.cycle_count = int(state["cycle_count"])

        # Restore curriculum stage
        if "curriculum_stage" in state:
            from utils.types import Stage
            try:
                brain.curriculum.current_stage = Stage(int(state["curriculum_stage"]))
            except (ValueError, KeyError):
                pass  # Unknown stage value — keep current

        # Warm-start working memory: promote top saved keys from SQLite
        for key in state.get("warm_start_keys", []):
            brain.memory.recall(key)   # triggers SQLite → working memory promotion

        return True

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def has_state(self) -> bool:
        """True if a checkpoint exists."""
        count = self._conn.execute(
            "SELECT COUNT(*) FROM session_state"
        ).fetchone()[0]
        return count > 0

    def saved_at(self) -> float | None:
        """Timestamp of the last checkpoint, or None."""
        row = self._conn.execute(
            "SELECT value_json FROM session_state WHERE state_key = 'saved_at'"
        ).fetchone()
        return float(json.loads(row["value_json"])) if row else None

    def clear(self) -> None:
        """Delete all session state (force fresh start)."""
        self._conn.execute("DELETE FROM session_state")
        self._conn.commit()
