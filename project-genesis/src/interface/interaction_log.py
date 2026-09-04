"""
Interaction Log — symmetric record of everything that crosses the boundary.

Both sides of the interaction are recorded with equal weight:
    - What we gave Genesis (input, stimuli, queries)
    - What Genesis surfaced (expression snapshots, attention state)
    - What interventions occurred (stimulus injections, pauses)
    - What the Observer reported (state changes, signals)

"Symmetric" means neither side is privileged in the log. Our inputs
don't get a special "important" flag. Genesis's expressions don't get
filtered. The log is a factual record, not an editorial.

This matters because over time the log becomes evidence — the raw
material for understanding what actually happened in a session and
whether anything interesting emerged. Selective logging would corrupt
that record before we even know what we're looking for.

Total retention applies here too: nothing is ever deleted from the log.
The log is append-only. Old sessions can be loaded for inspection.

Storage: SQLite (consistent with the memory system) in data/interaction_log.db.
"""

import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class EventKind(Enum):
    """Every event in the log has a kind."""
    HUMAN_INPUT     = "human_input"      # we gave Genesis something
    GENESIS_EXPR    = "genesis_expr"     # Genesis surfaced its state
    OBSERVER_REPORT = "observer_report"  # Observer issued a state assessment
    INTERVENTION    = "intervention"     # a stimulus or pause/resume occurred
    SYSTEM_EVENT    = "system_event"     # startup, shutdown, error


@dataclass
class LogEntry:
    """A single entry in the interaction log."""
    event_id: int
    timestamp: float
    kind: str          # EventKind value
    cycle: int
    source: str        # "human", "genesis", "observer", "system"
    summary: str       # brief plain-text description
    payload: dict      # full structured data


class InteractionLog:
    """
    Append-only interaction log backed by SQLite.

    All reads return copies — the log itself is immutable once written.
    """

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        self._event_counter: int = self._load_event_count()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS interaction_log (
                event_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                kind      TEXT NOT NULL,
                cycle     INTEGER NOT NULL,
                source    TEXT NOT NULL,
                summary   TEXT NOT NULL,
                payload   TEXT NOT NULL   -- JSON
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_log_timestamp ON interaction_log(timestamp)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_log_kind ON interaction_log(kind)"
        )
        self._conn.commit()

    def _load_event_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM interaction_log").fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Write side
    # ------------------------------------------------------------------

    def log_human_input(self, cycle: int, input_type: str, data: Any, summary: str = "") -> LogEntry:
        """Record something we gave Genesis."""
        return self._append(
            kind=EventKind.HUMAN_INPUT,
            cycle=cycle,
            source="human",
            summary=summary or f"Human gave '{input_type}' input",
            payload={"input_type": input_type, "data": str(data)[:500]},
        )

    def log_genesis_expression(self, cycle: int, snapshot_dict: dict) -> LogEntry:
        """Record what Genesis surfaced."""
        top_key = ""
        if snapshot_dict.get("attention_top"):
            top_key = snapshot_dict["attention_top"][0].get("key", "")
        return self._append(
            kind=EventKind.GENESIS_EXPR,
            cycle=cycle,
            source="genesis",
            summary=f"Genesis surfaced state — top attention: '{top_key}'",
            payload=snapshot_dict,
        )

    def log_observer_report(self, cycle: int, report_dict: dict) -> LogEntry:
        """Record the Observer's assessment."""
        state = report_dict.get("state", "unknown")
        return self._append(
            kind=EventKind.OBSERVER_REPORT,
            cycle=cycle,
            source="observer",
            summary=f"Observer: state={state} — {report_dict.get('recommendation', '')[:80]}",
            payload=report_dict,
        )

    def log_intervention(self, cycle: int, kind: str, details: str, payload: dict | None = None) -> LogEntry:
        """Record that an intervention occurred."""
        return self._append(
            kind=EventKind.INTERVENTION,
            cycle=cycle,
            source="system",
            summary=f"Intervention: {kind} — {details}",
            payload=payload or {"kind": kind, "details": details},
        )

    def log_system_event(self, cycle: int, event: str, details: dict | None = None) -> LogEntry:
        """Record a system event (start, stop, error)."""
        return self._append(
            kind=EventKind.SYSTEM_EVENT,
            cycle=cycle,
            source="system",
            summary=event,
            payload=details or {},
        )

    # ------------------------------------------------------------------
    # Read side
    # ------------------------------------------------------------------

    def recent(self, n: int = 20) -> list[LogEntry]:
        """Return the n most recent log entries."""
        rows = self._conn.execute(
            "SELECT * FROM interaction_log ORDER BY event_id DESC LIMIT ?", (n,)
        ).fetchall()
        return [self._row_to_entry(r) for r in reversed(rows)]

    def since_cycle(self, cycle: int) -> list[LogEntry]:
        """Return all entries from a given cycle onward."""
        rows = self._conn.execute(
            "SELECT * FROM interaction_log WHERE cycle >= ? ORDER BY event_id", (cycle,)
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def by_kind(self, kind: EventKind, limit: int = 50) -> list[LogEntry]:
        """Return recent entries of a specific kind."""
        rows = self._conn.execute(
            "SELECT * FROM interaction_log WHERE kind = ? ORDER BY event_id DESC LIMIT ?",
            (kind.value, limit),
        ).fetchall()
        return [self._row_to_entry(r) for r in reversed(rows)]

    def total(self) -> int:
        """Total number of log entries ever written."""
        row = self._conn.execute("SELECT COUNT(*) FROM interaction_log").fetchone()
        return row[0] if row else 0

    def stats(self) -> dict:
        rows = self._conn.execute(
            "SELECT kind, COUNT(*) AS cnt FROM interaction_log GROUP BY kind"
        ).fetchall()
        return {
            "total_entries": self.total(),
            "by_kind": {r["kind"]: r["cnt"] for r in rows},
        }

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _append(
        self,
        kind: EventKind,
        cycle: int,
        source: str,
        summary: str,
        payload: dict,
    ) -> LogEntry:
        now = time.time()
        payload_json = json.dumps(payload, default=str)
        cursor = self._conn.execute(
            """INSERT INTO interaction_log (timestamp, kind, cycle, source, summary, payload)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (now, kind.value, cycle, source, summary[:255], payload_json),
        )
        self._conn.commit()
        self._event_counter += 1
        return LogEntry(
            event_id=cursor.lastrowid,
            timestamp=now,
            kind=kind.value,
            cycle=cycle,
            source=source,
            summary=summary,
            payload=payload,
        )

    @staticmethod
    def _row_to_entry(row) -> LogEntry:
        return LogEntry(
            event_id=row["event_id"],
            timestamp=row["timestamp"],
            kind=row["kind"],
            cycle=row["cycle"],
            source=row["source"],
            summary=row["summary"],
            payload=json.loads(row["payload"]),
        )
