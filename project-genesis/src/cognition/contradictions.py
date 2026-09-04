"""
Contradiction Detection — M11.

The world presents conflicting evidence. Intelligence handles contradiction.

If two sources assert:
    overgrazing CAUSES erosion
    overgrazing PREVENTS erosion

That conflict should be registered — not resolved by overwriting, but held
as a known uncertainty. Contradictions mark the edges of where simple models
break down. They are often the most informative signal in the data.

Contradicting relation pairs (same subject, same object, opposing type):
    CAUSES    ↔  PREVENTS   (X produces Y  vs  X stops Y)
    ENABLES   ↔  PREVENTS   (X makes Y possible  vs  X stops Y)
    REQUIRES  ↔  PREVENTS   (X needs Y  vs  X stops Y — needs but also stops?)
    CAUSES    ↔  ENABLES    (weaker: X produces Y  vs  X makes Y possible — not
                             strictly contradictory but notable divergence in strength)

Neither triple is deleted. Both are kept in the relations table with their
confidence values intact. The contradiction_log records the conflict as a
known epistemic state: "these two things have been asserted and they conflict."

Contradictions are data. They may resolve over time as Genesis encounters more
evidence — but that resolution comes from confidence accumulation in one triple,
not from the other being erased.
"""

import time
from typing import Optional


# Pairs of relation types that directly contradict each other.
# Key: rel_type_a (alphabetically first to avoid duplicate checking)
# Value: rel_type_b
# Stored once: (A, CAUSES, X) conflicts with (A, PREVENTS, X)
_OPPOSING: dict[str, str] = {
    "CAUSES":  "PREVENTS",
    "ENABLES": "PREVENTS",
    "REQUIRES": "PREVENTS",
}

# All conflict pairs as frozensets for quick membership testing
_CONFLICT_PAIRS: frozenset = frozenset(
    frozenset(pair) for pair in _OPPOSING.items()
)


def are_opposing(rel_a: str, rel_b: str) -> bool:
    """Return True if rel_a and rel_b are a contradicting pair."""
    return frozenset({rel_a, rel_b}) in _CONFLICT_PAIRS


class ContradictionLog:
    """
    Detects and records conflicting relation triples.

    Shares the sqlite3.Connection from RelationGraph — no extra file.

    Usage:
        log = ContradictionLog(conn)
        n = log.scan(session_id)       # scan all relations for conflicts
        conflicts = log.query()        # retrieve stored conflicts
        conflicts = log.query_concept("wolves")  # conflicts involving a concept
        stats = log.stats()
    """

    def __init__(self, conn):
        self._conn = conn
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS contradiction_log (
                con_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL,
                rel_type_a  TEXT NOT NULL,
                rel_type_b  TEXT NOT NULL,
                object      TEXT NOT NULL,
                conf_a      REAL NOT NULL,
                conf_b      REAL NOT NULL,
                detected_at REAL NOT NULL,
                session_id  TEXT,
                UNIQUE(subject, rel_type_a, rel_type_b, object)
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_con_subj "
            "ON contradiction_log(subject)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_con_obj "
            "ON contradiction_log(object)"
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def scan(self, session_id: str = "") -> int:
        """
        Scan all stored relations for contradicting pairs.

        For each opposing (rel_type_a, rel_type_b) pair, find all
        (subject, object) combos where both triples exist.

        Returns the count of new contradictions detected.
        """
        new_count = 0
        for rel_a, rel_b in _OPPOSING.items():
            rows = self._conn.execute("""
                SELECT r1.subject, r1.object, r1.confidence, r2.confidence
                FROM relations r1
                JOIN relations r2
                    ON r1.subject = r2.subject
                    AND r1.object  = r2.object
                WHERE r1.rel_type = ? AND r2.rel_type = ?
            """, (rel_a, rel_b)).fetchall()

            for subject, obj, conf_a, conf_b in rows:
                if self._record(subject, rel_a, rel_b, obj, conf_a, conf_b, session_id):
                    new_count += 1

        return new_count

    def _record(
        self,
        subject: str,
        rel_a: str,
        rel_b: str,
        obj: str,
        conf_a: float,
        conf_b: float,
        session_id: str,
    ) -> bool:
        """Store a contradiction. Returns True if newly inserted, False if already known."""
        exists = self._conn.execute("""
            SELECT 1 FROM contradiction_log
            WHERE subject = ? AND rel_type_a = ? AND rel_type_b = ? AND object = ?
        """, (subject, rel_a, rel_b, obj)).fetchone()

        if exists:
            # Update confidences to reflect current evidence, but it's not new
            self._conn.execute("""
                UPDATE contradiction_log
                SET conf_a = ?, conf_b = ?, detected_at = ?
                WHERE subject = ? AND rel_type_a = ? AND rel_type_b = ? AND object = ?
            """, (conf_a, conf_b, time.time(), subject, rel_a, rel_b, obj))
            self._conn.commit()
            return False

        try:
            self._conn.execute("""
                INSERT INTO contradiction_log
                    (subject, rel_type_a, rel_type_b, object,
                     conf_a, conf_b, detected_at, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (subject, rel_a, rel_b, obj, conf_a, conf_b, time.time(), session_id))
            self._conn.commit()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(self, limit: int = 50) -> list[dict]:
        """Return all recorded contradictions, most recent first."""
        rows = self._conn.execute("""
            SELECT subject, rel_type_a, rel_type_b, object,
                   conf_a, conf_b, detected_at
            FROM contradiction_log
            ORDER BY detected_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [_row_to_dict(r) for r in rows]

    def query_concept(self, concept: str) -> list[dict]:
        """Return contradictions involving a concept as subject or object."""
        rows = self._conn.execute("""
            SELECT subject, rel_type_a, rel_type_b, object,
                   conf_a, conf_b, detected_at
            FROM contradiction_log
            WHERE subject = ? OR object = ?
            ORDER BY detected_at DESC
        """, (concept, concept)).fetchall()
        return [_row_to_dict(r) for r in rows]

    def most_contested(self, limit: int = 10) -> list[dict]:
        """
        Concepts that appear in the most contradictions.

        High contest = many conflicting assertions about this concept.
        These are epistemically interesting: the world (or Genesis's sources)
        disagrees about what this concept does.
        """
        rows = self._conn.execute("""
            SELECT concept, COUNT(*) AS conflicts FROM (
                SELECT subject AS concept FROM contradiction_log
                UNION ALL
                SELECT object  AS concept FROM contradiction_log
            ) GROUP BY concept ORDER BY conflicts DESC LIMIT ?
        """, (limit,)).fetchall()
        return [{"concept": r[0], "conflicts": r[1]} for r in rows]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        total = self._conn.execute(
            "SELECT COUNT(*) FROM contradiction_log"
        ).fetchone()[0]

        by_pair_rows = self._conn.execute("""
            SELECT rel_type_a || '↔' || rel_type_b AS pair, COUNT(*) AS cnt
            FROM contradiction_log
            GROUP BY pair ORDER BY cnt DESC
        """).fetchall()

        return {
            "total_contradictions": total,
            "by_pair": {r[0]: r[1] for r in by_pair_rows},
        }

    def count(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM contradiction_log"
        ).fetchone()[0]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _row_to_dict(row) -> dict:
    return {
        "subject":    row[0],
        "rel_type_a": row[1],
        "rel_type_b": row[2],
        "object":     row[3],
        "conf_a":     row[4],
        "conf_b":     row[5],
        "detected_at": row[6],
    }
