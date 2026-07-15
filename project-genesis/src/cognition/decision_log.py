"""
DecisionLog — M28 Deliberative Integration

Persistent, append-only log of Genesis's cognitive decisions.

Each entry records what was decided, by which subsystem, and what signals
drove the choice.  Together they form an auditable trail of how Genesis has
been spending its attention — queryable by Genesis itself ("what have you
been deciding?") and by external observers.

Table lives in the main memory DB so decisions share backup, migration, and
cross-session continuity with memory, relations, and hypotheses.

Public interface:
    decision_log.record(subsystem, decision, rationale, cycle=0)
    decision_log.recent(n=5) → list[DecisionRecord]
    decision_log.count()     → int  (for tests)
"""

import time
from dataclasses import dataclass


@dataclass
class DecisionRecord:
    id: int
    timestamp: float
    subsystem: str   # "feeder" | "reflection" | "hypothesis" | "inference_programs"
    decision: str    # human-readable summary of what was decided
    rationale: str   # signals that drove the choice
    cycle_count: int

    @property
    def age_s(self) -> float:
        return time.time() - self.timestamp


class DecisionLog:
    """
    Persistent append-only log of Genesis's cognitive decisions.

    Uses the shared memory DB connection — same DB, same ACID guarantees,
    no additional files.  record() never raises, but failures are routed to
    the survival error log (errors are data, not silence).
    """

    def __init__(self, conn, error_log=None) -> None:
        self._conn = conn
        self._error_log = error_log
        self._init_schema()

    def _log_error(self, label: str, exc: Exception) -> None:
        if self._error_log is not None:
            try:
                self._error_log.log(label, exc)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS decision_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   REAL    NOT NULL,
                subsystem   TEXT    NOT NULL,
                decision    TEXT    NOT NULL,
                rationale   TEXT    NOT NULL DEFAULT '',
                cycle_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_decision_log_ts
            ON decision_log (timestamp DESC)
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, subsystem: str, decision: str,
               rationale: str = "", cycle: int = 0) -> None:
        """Append one record.  Never raises; failures go to the error log."""
        try:
            self._conn.execute(
                """INSERT INTO decision_log
                       (timestamp, subsystem, decision, rationale, cycle_count)
                   VALUES (?, ?, ?, ?, ?)""",
                (time.time(), subsystem, decision, rationale, cycle),
            )
            self._conn.commit()
        except Exception as exc:
            self._log_error("decision_log.record", exc)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def recent(self, n: int = 5) -> list[DecisionRecord]:
        """Return the n most recent decisions, newest first."""
        try:
            rows = self._conn.execute(
                """SELECT id, timestamp, subsystem, decision, rationale, cycle_count
                   FROM decision_log
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (max(1, n),),
            ).fetchall()
            return [
                DecisionRecord(
                    id=r[0], timestamp=r[1], subsystem=r[2],
                    decision=r[3], rationale=r[4], cycle_count=r[5],
                )
                for r in rows
            ]
        except Exception as exc:
            self._log_error("decision_log.recent", exc)
            return []

    def count(self) -> int:
        """Total decisions logged (used by tests)."""
        try:
            return self._conn.execute(
                "SELECT COUNT(*) FROM decision_log"
            ).fetchone()[0]
        except Exception as exc:
            self._log_error("decision_log.count", exc)
            return 0
