"""
Inference Engine — M10.

Reasons from stored relations rather than just recalling them.

If Genesis has observed:
    wolves   CONTROLS  deer
    deer     CAUSES    overgrazing
    overgrazing CAUSES erosion

The InferenceEngine asserts:
    wolves CONTROLS erosion  (2-hop CONTROLS chain)
    deer   CAUSES   erosion  (1-hop already observed, but also transitively found)

Transitivity rules — same relation type propagates:
    A CAUSES B,   B CAUSES C   → A CAUSES C
    A CONTROLS B, B CONTROLS C → A CONTROLS C
    A REQUIRES B, B REQUIRES C → A REQUIRES C
    A ENABLES B,  B ENABLES C  → A ENABLES C
    A IS_A B,     B IS_A C     → A IS_A C

IS_A property inheritance — cross-type propagation:
    A IS_A B, B REL C → A REL C   (A inherits B's properties)

    If Genesis learns "cats IS_A mammal" and "mammals CONTAINS fur", it infers
    "cats CONTAINS fur" without ever having been told directly. This is the
    mechanism behind the "cats vs dogs" distinction — new facts about a
    category automatically apply to all known members.

Compound confidence per chain:
    conf = Π(hop_confidences) × HOP_DECAY^(chain_length − 1)

Inferred relations are stored in a separate table from observed relations.
They never overwrite observed data.
"""

import json
import re
import time
from typing import Optional

from memory.relations import RelationGraph


# Relation types that propagate transitively (same type)
_TRANSITIVE = frozenset({"CAUSES", "CONTROLS", "REQUIRES", "ENABLES", "IS_A"})

# Cross-type bridge rules: (first_hop, second_hop) → inferred_relation
# A first_hop B, B second_hop C → A inferred C
#
# Semantics:
#   CONTROLS + CAUSES   → CONTROLS  (A controls B which causes C → A controls C)
#   CONTROLS + ENABLES  → CONTROLS  (A controls B which enables C → A controls C)
#   CAUSES   + ENABLES  → CAUSES    (A causes B which enables C → A causes C)
#   CAUSES   + CONTROLS → AFFECTS   (A causes B which controls C → A affects C)
#   ENABLES  + REQUIRES → ENABLES   (A enables B which requires C → A enables C)
#   PREVENTS + CAUSES   → PREVENTS  (A prevents B which causes C → A prevents C)
#   PREVENTS + ENABLES  → PREVENTS  (A prevents B which enables C → A prevents C)
_BRIDGE_RULES: list[tuple[str, str, str]] = [
    ("CONTROLS", "CAUSES",   "CONTROLS"),
    ("CONTROLS", "ENABLES",  "CONTROLS"),
    ("CAUSES",   "ENABLES",  "CAUSES"),
    ("CAUSES",   "CONTROLS", "AFFECTS"),
    ("ENABLES",  "REQUIRES", "ENABLES"),
    ("PREVENTS", "CAUSES",   "PREVENTS"),
    ("PREVENTS", "ENABLES",  "PREVENTS"),
]

# Confidence multiplier per additional hop beyond the first
_HOP_DECAY: float = 0.85

# Minimum inferred confidence worth storing
_MIN_CONFIDENCE: float = 0.20

# Maximum chain length to explore (prevents combinatorial explosion)
_MAX_CHAIN: int = 4

# Minimum observed confidence to treat a relation as a valid chain edge
_MIN_EDGE_CONF: float = 0.30


def _norm(text: str) -> str:
    """Normalise concept string: lowercase, strip punctuation, collapse whitespace."""
    cleaned = re.sub(r"[^a-z0-9 ]", "", text.lower().strip())
    return " ".join(cleaned.split())


class InferenceEngine:
    """
    Transitive closure engine over the RelationGraph.

    Shares the sqlite3.Connection from RelationGraph — no extra file,
    no multi-connection contention.

    Usage:
        engine = InferenceEngine(brain.relations)
        n = engine.run(session_id=brain.session_id)   # infer over all concepts
        result = engine.infer("wolves")               # infer around one concept
        result = engine.query("wolves")               # query stored inferences
    """

    def __init__(self, relations: RelationGraph):
        self._relations = relations
        self._conn = relations._conn
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS relation_inferences (
                inf_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                subject      TEXT NOT NULL,
                rel_type     TEXT NOT NULL,
                object       TEXT NOT NULL,
                confidence   REAL NOT NULL,
                chain_len    INTEGER NOT NULL,
                chain_json   TEXT NOT NULL,
                inferred_at  REAL NOT NULL,
                session_id   TEXT,
                UNIQUE(subject, rel_type, object)
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inf_subj ON relation_inferences(subject)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inf_obj ON relation_inferences(object)"
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(self, session_id: str = "") -> int:
        """
        Run transitive inference, cross-type bridging, and IS_A inheritance.

        Pass 1: same-type transitive chains (CAUSES→CAUSES, CONTROLS→CONTROLS …)
        Pass 2: cross-type bridging (CONTROLS→CAUSES → CONTROLS, etc.)
        Pass 3: IS_A property inheritance (cats IS_A mammal → cats inherits mammal props)

        Returns the number of new inferences added this call.
        """
        cur = self._conn.execute(
            "SELECT DISTINCT subject AS c FROM relations "
            "UNION SELECT DISTINCT object AS c FROM relations"
        )
        concepts = [row[0] for row in cur.fetchall()]

        before = self._count()
        for concept in concepts:
            self._infer_from(concept, session_id)
        self._infer_bridges(session_id)
        self._infer_inheritance(session_id)
        return self._count() - before

    def infer(self, concept: str, session_id: str = "") -> dict:
        """
        Run inference focused on one concept, then return all inferences for it.
        """
        normed = _norm(concept)
        if normed:
            self._infer_from(normed, session_id)
            self._infer_bridges(session_id, subject_filter=normed)
            self._infer_inheritance(session_id, subject_filter=normed)
        return self.query(normed)

    # ------------------------------------------------------------------
    # Core BFS
    # ------------------------------------------------------------------

    def _infer_from(self, start: str, session_id: str) -> None:
        """
        BFS outward from `start`, building transitive chains.

        Only same-type relation chains propagate: CAUSES→CAUSES,
        CONTROLS→CONTROLS, etc.
        """
        # Queue: (current_concept, steps_list, running_product_of_hop_confs)
        # steps_list: list of (from, rel_type, to, hop_conf)
        queue: list[tuple] = [(start, [], 1.0)]
        # Track (start, endpoint, rel_type) tuples we've already stored
        stored_pairs: set[tuple] = set()

        while queue:
            current, steps, path_prod = queue.pop(0)
            if len(steps) >= _MAX_CHAIN:
                continue

            for rel_type, obj, hop_conf in self._outgoing(current):
                # Cycle check: don't revisit start or any concept in current path
                path_concepts = {s[2] for s in steps} | {start}
                if obj in path_concepts:
                    continue

                new_steps = steps + [(current, rel_type, obj, hop_conf)]
                new_prod = path_prod * hop_conf

                # Only store inferences that are non-trivial (≥2 hops)
                if len(new_steps) >= 2:
                    first_rel = new_steps[0][1]  # rel_type at start of chain
                    # Only propagate if all steps share the same rel_type
                    if rel_type == first_rel:
                        pair = (start, obj, first_rel)
                        if pair not in stored_pairs:
                            stored_pairs.add(pair)
                            decay = _HOP_DECAY ** (len(new_steps) - 1)
                            inferred_conf = new_prod * decay
                            if inferred_conf >= _MIN_CONFIDENCE:
                                self._store(
                                    start, first_rel, obj,
                                    inferred_conf, new_steps, session_id,
                                )

                queue.append((obj, new_steps, new_prod))

    def _infer_bridges(
        self, session_id: str, subject_filter: Optional[str] = None
    ) -> None:
        """
        Cross-type bridge inference: A type1 B, B type2 C → A result C.

        Uses a single SQL JOIN so the middle concept is matched exactly as stored.
        This is the primary path to inferences when the knowledge graph is sparse
        and same-type transitive chains don't yet exist.

        Examples:
            wolves CONTROLS deer, deer CAUSES overgrazing → wolves CONTROLS overgrazing
            drought CAUSES fire,  fire  ENABLES erosion   → drought CAUSES erosion
        """
        for type1, type2, result_type in _BRIDGE_RULES:
            filter_clause = "AND r1.subject = ?" if subject_filter else ""
            params = [type1, type2, _MIN_EDGE_CONF, _MIN_EDGE_CONF]
            if subject_filter:
                params.append(subject_filter)

            rows = self._conn.execute(f"""
                SELECT r1.subject, r1.object, r1.confidence,
                       r2.object,  r2.confidence
                FROM relations r1
                JOIN relations r2 ON LOWER(r1.object) = LOWER(r2.subject)
                WHERE r1.rel_type = ? AND r2.rel_type = ?
                  AND r1.confidence >= ? AND r2.confidence >= ?
                  AND r1.subject != r2.object
                  {filter_clause}
                LIMIT 200
            """, params).fetchall()

            for subj, mid, conf1, obj, conf2 in rows:
                inferred_conf = conf1 * conf2 * _HOP_DECAY
                if inferred_conf >= _MIN_CONFIDENCE:
                    steps = [
                        (subj, type1,  mid, conf1),
                        (mid,  type2,  obj, conf2),
                    ]
                    self._store(subj, result_type, obj, inferred_conf, steps, session_id)

    def _infer_inheritance(
        self, session_id: str, subject_filter: Optional[str] = None
    ) -> None:
        """
        IS_A property inheritance: X IS_A Y, Y REL Z → infer X REL Z.

        Checks both observed relations and previously inferred IS_A chains so
        that multi-hop IS_A paths (cats→felines→mammals→animals) propagate
        properties in a single call once the IS_A transitive closure is built.

        subject_filter: if set, only inherit for that specific child concept.
        """
        # Collect IS_A edges from observed relations
        q_obs = "SELECT subject, object, confidence FROM relations WHERE rel_type = 'IS_A' AND confidence >= ?"
        params_obs: tuple = (_MIN_EDGE_CONF,)
        if subject_filter:
            q_obs += " AND subject = ?"
            params_obs = (_MIN_EDGE_CONF, subject_filter)
        is_a_pairs = self._conn.execute(q_obs, params_obs).fetchall()

        # Also collect IS_A edges from inferred table (covers transitive IS_A chains)
        q_inf = "SELECT subject, object, confidence FROM relation_inferences WHERE rel_type = 'IS_A' AND confidence >= ?"
        params_inf: tuple = (_MIN_EDGE_CONF,)
        if subject_filter:
            q_inf += " AND subject = ?"
            params_inf = (_MIN_EDGE_CONF, subject_filter)
        is_a_pairs += self._conn.execute(q_inf, params_inf).fetchall()

        for child, parent, is_a_conf in is_a_pairs:
            if child == parent:
                continue
            # Find all non-IS_A properties of the parent
            parent_props = self._conn.execute(
                "SELECT rel_type, object, confidence FROM relations "
                "WHERE subject = ? AND rel_type != 'IS_A' AND confidence >= ?",
                (parent, _MIN_EDGE_CONF),
            ).fetchall()

            for rel_type, obj, prop_conf in parent_props:
                if obj == child:
                    continue
                inferred_conf = is_a_conf * prop_conf * _HOP_DECAY
                if inferred_conf >= _MIN_CONFIDENCE:
                    steps = [
                        (child, "IS_A", parent, is_a_conf),
                        (parent, rel_type, obj, prop_conf),
                    ]
                    self._store(child, rel_type, obj, inferred_conf, steps, session_id)

    def _outgoing(self, concept: str) -> list[tuple]:
        """Return (rel_type, object, confidence) for transitive edges from concept."""
        placeholders = ",".join("?" * len(_TRANSITIVE))
        rows = self._conn.execute(
            f"SELECT rel_type, object, confidence FROM relations "
            f"WHERE subject = ? AND confidence >= ? AND rel_type IN ({placeholders}) "
            f"ORDER BY confidence DESC LIMIT 20",
            (concept, _MIN_EDGE_CONF, *_TRANSITIVE),
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def _store(
        self,
        subject: str,
        rel_type: str,
        obj: str,
        confidence: float,
        steps: list,
        session_id: str,
    ) -> None:
        chain = [
            {"from": s[0], "via": s[1], "to": s[2], "conf": round(s[3], 4)}
            for s in steps
        ]
        try:
            self._conn.execute("""
                INSERT INTO relation_inferences
                    (subject, rel_type, object, confidence, chain_len, chain_json,
                     inferred_at, session_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(subject, rel_type, object) DO UPDATE SET
                    confidence  = MAX(confidence, excluded.confidence),
                    chain_len   = CASE
                                    WHEN excluded.confidence > confidence
                                    THEN excluded.chain_len ELSE chain_len
                                  END,
                    chain_json  = CASE
                                    WHEN excluded.confidence > confidence
                                    THEN excluded.chain_json ELSE chain_json
                                  END,
                    inferred_at = excluded.inferred_at
            """, (
                subject, rel_type, obj,
                round(confidence, 4),
                len(steps),
                json.dumps(chain),
                time.time(),
                session_id,
            ))
            self._conn.commit()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(self, concept: str, min_confidence: float = _MIN_CONFIDENCE) -> dict:
        """
        Return all inferences involving `concept`.

        Returns {concept, as_subject: [...], as_object: [...]}
        Each entry: {subject, relation, object, confidence, chain_length, chain}
        """
        normed = _norm(concept)
        rows = self._conn.execute("""
            SELECT subject, rel_type, object, confidence, chain_len, chain_json
            FROM relation_inferences
            WHERE (subject = ? OR object = ?) AND confidence >= ?
            ORDER BY confidence DESC
        """, (normed, normed, min_confidence)).fetchall()

        as_subject, as_object = [], []
        for row in rows:
            entry = {
                "subject":      row[0],
                "relation":     row[1],
                "object":       row[2],
                "confidence":   row[3],
                "chain_length": row[4],
                "chain":        json.loads(row[5]),
            }
            (as_subject if row[0] == normed else as_object).append(entry)

        return {"concept": normed, "as_subject": as_subject, "as_object": as_object}

    def top_inferences(self, limit: int = 20, min_confidence: float = _MIN_CONFIDENCE) -> list[dict]:
        """Highest-confidence inferences across all concepts."""
        rows = self._conn.execute("""
            SELECT subject, rel_type, object, confidence, chain_len
            FROM relation_inferences
            WHERE confidence >= ?
            ORDER BY confidence DESC
            LIMIT ?
        """, (min_confidence, limit)).fetchall()
        return [
            {"subject": r[0], "relation": r[1], "object": r[2],
             "confidence": r[3], "chain_length": r[4]}
            for r in rows
        ]

    def chain_for(self, subject: str, rel_type: str, obj: str) -> Optional[list[dict]]:
        """Return the stored chain for a specific inferred triple, or None."""
        row = self._conn.execute("""
            SELECT chain_json FROM relation_inferences
            WHERE subject = ? AND rel_type = ? AND object = ?
        """, (_norm(subject), rel_type, _norm(obj))).fetchone()
        return json.loads(row[0]) if row else None

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        row = self._conn.execute("""
            SELECT COUNT(*), AVG(confidence), MIN(chain_len), MAX(chain_len)
            FROM relation_inferences
        """).fetchone()
        total, avg_conf, min_chain, max_chain = row
        by_type_rows = self._conn.execute("""
            SELECT rel_type, COUNT(*) FROM relation_inferences GROUP BY rel_type
        """).fetchall()
        return {
            "total_inferences": total or 0,
            "avg_confidence":   round(avg_conf or 0.0, 3),
            "min_chain_length": min_chain or 0,
            "max_chain_length": max_chain or 0,
            "by_type":          {r[0]: r[1] for r in by_type_rows},
        }

    def _count(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM relation_inferences"
        ).fetchone()[0]
