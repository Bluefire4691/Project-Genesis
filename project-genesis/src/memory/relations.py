"""
Relation Graph — typed semantic relationships between concepts.

Goes beyond co-occurrence (things seen near each other) to typed, directed
relationships between concepts:

    (wolves,         CONTROLS,  deer_population)
    (wolves,         IS_A,      predator)
    (overgrazing,    CAUSES,    erosion)
    (erosion,        CAUSES,    river_course_change)
    (deer,           REQUIRES,  wolves)          ← inferred from "without wolves..."

This is the semantic layer. The AssociationGraph says "these things appeared
together." The RelationGraph says "this is how they relate."

Relation types:
    CAUSES    — X produces Y as a consequence
    CONTROLS  — X regulates or governs Y
    PREVENTS  — X stops Y from occurring
    ENABLES   — X makes Y possible
    REQUIRES  — X depends on Y (Y is necessary for X)
    IS_A      — X is a type/instance of Y
    PREDATES  — X eats / hunts / preys on Y
    AFFECTS   — X has some effect on Y (direction unspecified)
    CONTAINS  — X is composed of / includes Y

All relations are stored lowercase and directed (A→B ≠ B→A).
Confidence accumulates toward the max — a relation only becomes stronger.
Everything is append-only. Nothing is ever deleted.
"""

import re
import sqlite3
import time
from typing import Optional


# All recognized relation types
RELATION_TYPES = frozenset({
    "CAUSES", "CONTROLS", "PREVENTS", "ENABLES", "REQUIRES",
    "IS_A", "PREDATES", "AFFECTS", "CONTAINS",
})


class RelationGraph:
    """
    Typed directed relation store backed by the memory DB connection.

    Shares the sqlite3.Connection from LongTermStore — no extra file,
    no multi-connection contention.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS relations (
                rel_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                subject     TEXT NOT NULL,
                rel_type    TEXT NOT NULL,
                object      TEXT NOT NULL,
                confidence  REAL NOT NULL DEFAULT 0.75,
                source_key  TEXT,
                session_id  TEXT,
                created_at  REAL NOT NULL,
                UNIQUE(subject, rel_type, object)
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rel_subj ON relations(subject)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rel_obj  ON relations(object)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rel_type ON relations(rel_type)"
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add(
        self,
        subject: str,
        rel_type: str,
        obj: str,
        confidence: float,
        source_key: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> bool:
        """
        Record a typed relation.

        Subject and object are normalised to lowercase. If the triple already
        exists, confidence is updated to MAX(existing, new) — relations only
        become more certain, never less.

        Returns True on success, False on failure (never raises).
        """
        if rel_type not in RELATION_TYPES:
            return False

        subject = _normalise(subject)
        obj = _normalise(obj)
        if not subject or not obj or subject == obj:
            return False

        try:
            self._conn.execute("""
                INSERT INTO relations
                    (subject, rel_type, object, confidence, source_key, session_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(subject, rel_type, object) DO UPDATE SET
                    confidence = MAX(confidence, excluded.confidence),
                    source_key = excluded.source_key
            """, (
                subject, rel_type, obj,
                max(0.0, min(1.0, confidence)),
                source_key, session_id, time.time(),
            ))
            self._conn.commit()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Read — single-concept queries
    # ------------------------------------------------------------------

    def query_subject(
        self, subject: str, min_confidence: float = 0.5
    ) -> list[dict]:
        """
        What does `subject` do / is / cause / control?

        Returns list of {relation, object, confidence} sorted by confidence.
        """
        rows = self._conn.execute("""
            SELECT rel_type, object, confidence
            FROM relations
            WHERE subject = ? AND confidence >= ?
            ORDER BY confidence DESC
        """, (_normalise(subject), min_confidence)).fetchall()
        return [
            {"relation": r["rel_type"], "object": r["object"], "confidence": r["confidence"]}
            for r in rows
        ]

    def query_object(
        self, obj: str, min_confidence: float = 0.5
    ) -> list[dict]:
        """
        What causes / affects / controls `obj`?

        Returns list of {subject, relation, confidence} sorted by confidence.
        """
        rows = self._conn.execute("""
            SELECT subject, rel_type, confidence
            FROM relations
            WHERE object = ? AND confidence >= ?
            ORDER BY confidence DESC
        """, (_normalise(obj), min_confidence)).fetchall()
        return [
            {"subject": r["subject"], "relation": r["rel_type"], "confidence": r["confidence"]}
            for r in rows
        ]

    def query_concept(self, concept: str, min_confidence: float = 0.5) -> dict:
        """
        Everything known about a concept — both as subject and object.

        Returns {as_subject: [...], as_object: [...]}
        """
        return {
            "as_subject": self.query_subject(concept, min_confidence),
            "as_object":  self.query_object(concept, min_confidence),
        }

    # ------------------------------------------------------------------
    # Read — relation-type queries
    # ------------------------------------------------------------------

    def query_relation(
        self, rel_type: str, min_confidence: float = 0.5, limit: int = 50
    ) -> list[dict]:
        """
        All triples of a given relation type.

        Returns list of {subject, object, confidence}.
        """
        rows = self._conn.execute("""
            SELECT subject, object, confidence
            FROM relations
            WHERE rel_type = ? AND confidence >= ?
            ORDER BY confidence DESC
            LIMIT ?
        """, (rel_type, min_confidence, limit)).fetchall()
        return [
            {"subject": r["subject"], "object": r["object"], "confidence": r["confidence"]}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Read — path finding
    # ------------------------------------------------------------------

    def find_path(
        self, from_concept: str, to_concept: str, max_depth: int = 4
    ) -> list[list[dict]]:
        """
        Find directed relationship chains from `from_concept` to `to_concept`.

        BFS up to `max_depth` hops. Returns up to 3 shortest paths.
        Each path is a list of steps:
            [{"from": X, "relation": R, "to": Y, "confidence": C}, ...]

        Returns [] if no path found within max_depth.
        """
        from_c = _normalise(from_concept)
        to_c   = _normalise(to_concept)

        if from_c == to_c:
            return [[]]

        queue: list[tuple[str, list[dict]]] = [(from_c, [])]
        visited: set[str] = {from_c}
        paths: list[list[dict]] = []

        while queue and len(paths) < 3:
            current, path = queue.pop(0)
            if len(path) >= max_depth:
                continue

            rows = self._conn.execute("""
                SELECT rel_type, object, confidence
                FROM relations
                WHERE subject = ? AND confidence >= 0.5
                ORDER BY confidence DESC
                LIMIT 10
            """, (current,)).fetchall()

            for row in rows:
                step = {
                    "from":       current,
                    "relation":   row["rel_type"],
                    "to":         row["object"],
                    "confidence": row["confidence"],
                }
                new_path = path + [step]
                if row["object"] == to_c:
                    paths.append(new_path)
                elif row["object"] not in visited:
                    visited.add(row["object"])
                    queue.append((row["object"], new_path))

        return paths

    # ------------------------------------------------------------------
    # Read — aggregate views
    # ------------------------------------------------------------------

    def most_connected(self, limit: int = 10) -> list[dict]:
        """
        Concepts with the most relation edges (as subject or object).

        Returns list of {concept, degree} sorted by degree descending.
        """
        rows = self._conn.execute("""
            SELECT concept, COUNT(*) AS degree FROM (
                SELECT subject AS concept FROM relations
                UNION ALL
                SELECT object  AS concept FROM relations
            ) GROUP BY concept ORDER BY degree DESC LIMIT ?
        """, (limit,)).fetchall()
        return [{"concept": r["concept"], "degree": r["degree"]} for r in rows]

    def causal_chains(self, min_confidence: float = 0.7) -> list[dict]:
        """
        Return all high-confidence CAUSES triples — the causal map.

        Returns list of {subject, object, confidence}.
        """
        return self.query_relation("CAUSES", min_confidence)

    def definitions(self, min_confidence: float = 0.7) -> list[dict]:
        """Return all IS_A triples — the taxonomy."""
        return self.query_relation("IS_A", min_confidence)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        total = self._conn.execute(
            "SELECT COUNT(*) FROM relations"
        ).fetchone()[0]

        by_type_rows = self._conn.execute("""
            SELECT rel_type, COUNT(*) AS cnt
            FROM relations
            GROUP BY rel_type
            ORDER BY cnt DESC
        """).fetchall()

        return {
            "total_relations": total,
            "by_type": {r["rel_type"]: r["cnt"] for r in by_type_rows},
        }

    # ------------------------------------------------------------------
    # Prediction error (M15)
    # ------------------------------------------------------------------

    def prediction_error(self, concepts: list[str]) -> float:
        """
        Friston-grounded surprise signal: how unexpected is this input given
        Genesis's current belief state?

        For each concept, the prediction error is 1 minus the mean confidence
        of all relations it participates in (as subject or object). A concept
        Genesis knows well (many high-confidence relations) generates low error.
        A concept Genesis knows nothing about generates maximum error (1.0).

        Returns the mean prediction error across all supplied concepts,
        clamped to [0.0, 1.0]. Empty concept list → 0.5 (neutral/unknown).
        """
        if not concepts:
            return 0.5

        errors = []
        for raw in concepts:
            concept = raw.strip().lower()
            if not concept:
                continue
            try:
                rows = self._conn.execute(
                    """
                    SELECT confidence FROM relations
                    WHERE subject = ? OR object = ?
                    ORDER BY confidence DESC
                    LIMIT 20
                    """,
                    (concept, concept),
                ).fetchall()
            except Exception:
                rows = []

            if not rows:
                errors.append(1.0)  # completely unknown → maximum surprise
            else:
                mean_conf = sum(r["confidence"] for r in rows) / len(rows)
                errors.append(max(0.0, 1.0 - mean_conf))

        if not errors:
            return 0.5
        return round(sum(errors) / len(errors), 4)



# ==================================================================
# Internal helpers
# ==================================================================

def _normalise(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation from edges."""
    cleaned = re.sub(r"[^a-z0-9 ]", "", text.lower().strip())
    return " ".join(cleaned.split())
