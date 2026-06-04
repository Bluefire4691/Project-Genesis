"""
Pattern Transfer — M22.

Genesis generalizes structural patterns across domains. Two instances
that have processed different domains (ecology, economics, immunology)
should eventually recognize that the predator-prey structure in ecology
is the same structure as antigen-antibody in immunology and monopoly-
competition in economics — even though the concepts are entirely different.

Without this, Genesis accumulates facts in separate silos. With it,
understanding in one domain transfers: a known causal chain structure
primes Genesis to look for the same structure in new material, and to
predict what the next link in a chain might be before encountering it.

Approach: structural role fingerprinting.

Each concept in the relation graph has a structural fingerprint — its
pattern of incoming and outgoing relation types. Two concepts from
different domains with the same fingerprint are structural analogs.

Example:
    wolves: [CAUSES→, CONTROLS→, ←REQUIRES]
    lions:  [CAUSES→, CONTROLS→, ←REQUIRES]
    → wolves and lions are structural analogs (both play PREDATOR role)

    deer:      [←CAUSES, CAUSES→, ←CONTROLS]
    gazelles:  [←CAUSES, CAUSES→, ←CONTROLS]
    → deer and gazelles are structural analogs (both play PREY role)

This generalizes: once Genesis knows the wolves→deer ecological chain,
and recognizes that lions have the same structural fingerprint as wolves,
it can:
    1. Predict lions likely has a prey analog (CAUSES→ something)
    2. Register curiosity: what do lions cause to decline?
    3. When it learns lions→gazelles, the chain is immediately understood
       as an instance of the PREDATOR→PREY pattern it already knows.

Meta-patterns are stored in a new table (structural_patterns) and
are also exposed as curiosity directives when a partial analog is detected.

Research grounding:
    - Gentner (1983): structure-mapping theory — analogy is based on
      relational structure, not surface features. Two things are analogous
      when their relational structures are isomorphic.
    - Holyoak & Thagard (1989): multi-constraint satisfaction in analogy —
      structural consistency, semantic similarity, and pragmatic centrality
      all contribute to analogical mapping.
    - The implementation here focuses on structural consistency (Gentner's
      primary criterion): same relation-type pattern = same structural role.
"""

import json
import time
from collections import Counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.relations import RelationGraph


# Minimum confidence to include an edge in the fingerprint
_MIN_CONF = 0.45

# Minimum outgoing edges for a concept to be fingerprinted
_MIN_EDGES = 2

# Two fingerprints are considered matching if they share at least this
# fraction of their relation-type tokens
_MATCH_THRESHOLD = 0.60

# Maximum analog pairs to store per concept
_MAX_ANALOGS = 10

# Abstract role labels derived from fingerprint patterns
_ROLE_SIGNATURES: dict[str, str] = {
    # High outgoing CAUSES, is itself caused by nothing or one thing
    frozenset(["CAUSES_OUT", "CONTROLS_OUT"]): "REGULATOR",
    # Primarily caused-by others, causes downstream effects
    frozenset(["CAUSES_IN", "CAUSES_OUT"]):    "MEDIATOR",
    # End of chains — caused by many, causes little
    frozenset(["CAUSES_IN", "AFFECTS_IN"]):    "OUTCOME",
    # Prevents things from happening
    frozenset(["PREVENTS_OUT"]):               "INHIBITOR",
    # Required by many things
    frozenset(["REQUIRES_IN"]):                "DEPENDENCY",
}


class PatternTransfer:
    """
    Structural analog detection and pattern transfer across domains.

    Usage:
        pt = PatternTransfer(relations, conn)
        pt.scan()                            # find and store analogs
        analogs = pt.analogs_for("wolves")   # who plays the same role?
        role = pt.role_of("wolves")          # "REGULATOR" etc.
        directives = pt.curiosity_from_analogs()  # what to look up next
    """

    def __init__(self, relations: "RelationGraph", conn):
        self._relations = relations
        self._conn = conn
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS structural_patterns (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_a    TEXT NOT NULL,
                concept_b    TEXT NOT NULL,
                role         TEXT,
                match_score  REAL NOT NULL,
                fingerprint  TEXT NOT NULL,
                detected_at  REAL NOT NULL,
                UNIQUE(concept_a, concept_b)
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_roles (
                concept      TEXT PRIMARY KEY,
                role         TEXT NOT NULL,
                fingerprint  TEXT NOT NULL,
                updated_at   REAL NOT NULL
            )
        """)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Fingerprinting
    # ------------------------------------------------------------------

    def fingerprint(self, concept: str) -> list[str]:
        """
        Structural fingerprint for a concept: sorted list of
        RELATION_DIRECTION tokens representing its graph neighbourhood.

        e.g. ["CAUSES_IN", "CAUSES_OUT", "CONTROLS_OUT", "REQUIRES_IN"]
        """
        tokens: list[str] = []
        try:
            for r in self._relations.query_subject(concept, min_confidence=_MIN_CONF):
                tokens.append(f"{r['relation']}_OUT")
            for r in self._relations.query_object(concept, min_confidence=_MIN_CONF):
                tokens.append(f"{r['relation']}_IN")
        except Exception:
            pass
        return sorted(set(tokens))

    def role_of(self, concept: str) -> str:
        """
        Map a concept's fingerprint to an abstract structural role label.
        Returns "UNKNOWN" if no known role matches.
        """
        fp = set(self.fingerprint(concept))
        best_role = "UNKNOWN"
        best_overlap = 0
        for signature, role in _ROLE_SIGNATURES.items():
            overlap = len(fp & signature)
            if overlap > best_overlap:
                best_overlap = overlap
                best_role = role
        return best_role

    def match_score(self, fp_a: list[str], fp_b: list[str]) -> float:
        """
        Jaccard similarity between two fingerprints.
        1.0 = identical structural role, 0.0 = no overlap at all.
        """
        if not fp_a or not fp_b:
            return 0.0
        sa, sb = set(fp_a), set(fp_b)
        return len(sa & sb) / len(sa | sb)

    # ------------------------------------------------------------------
    # Analog detection
    # ------------------------------------------------------------------

    def scan(self, min_edges: int = _MIN_EDGES) -> int:
        """
        Scan all concepts in the relation graph for structural analogs.
        Stores analog pairs in the DB.
        Returns number of new analog pairs found.
        """
        # Fetch all concepts with enough edges
        try:
            rows = self._conn.execute("""
                SELECT concept FROM (
                    SELECT subject AS concept FROM relations
                    WHERE confidence >= ?
                    UNION
                    SELECT object AS concept FROM relations
                    WHERE confidence >= ?
                ) GROUP BY concept
            """, (_MIN_CONF, _MIN_CONF)).fetchall()
        except Exception:
            return 0

        concepts = [r[0] for r in rows]

        # Build fingerprints
        fps: dict[str, list[str]] = {}
        for c in concepts:
            fp = self.fingerprint(c)
            if len(fp) >= min_edges:
                fps[c] = fp

        # Compare all pairs
        found = 0
        concept_list = list(fps.keys())
        now = time.time()

        for i, ca in enumerate(concept_list):
            for cb in concept_list[i + 1:]:
                score = self.match_score(fps[ca], fps[cb])
                if score < _MATCH_THRESHOLD:
                    continue
                role = self.role_of(ca)
                fp_json = json.dumps(fps[ca])
                try:
                    self._conn.execute("""
                        INSERT OR REPLACE INTO structural_patterns
                            (concept_a, concept_b, role, match_score,
                             fingerprint, detected_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (ca, cb, role, round(score, 4), fp_json, now))
                    found += 1
                except Exception:
                    pass

        # Update concept roles
        for concept, fp in fps.items():
            role = self.role_of(concept)
            try:
                self._conn.execute("""
                    INSERT OR REPLACE INTO concept_roles
                        (concept, role, fingerprint, updated_at)
                    VALUES (?, ?, ?, ?)
                """, (concept, role, json.dumps(fp), now))
            except Exception:
                pass

        if found:
            self._conn.commit()

        return found

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def analogs_for(self, concept: str, limit: int = _MAX_ANALOGS) -> list[dict]:
        """
        What other concepts play the same structural role as this one?
        """
        try:
            rows = self._conn.execute("""
                SELECT concept_b AS analog, role, match_score
                FROM structural_patterns
                WHERE concept_a = ?
                UNION
                SELECT concept_a AS analog, role, match_score
                FROM structural_patterns
                WHERE concept_b = ?
                ORDER BY match_score DESC
                LIMIT ?
            """, (concept, concept, limit)).fetchall()
        except Exception:
            return []
        return [
            {"analog": r[0], "role": r[1], "match_score": round(r[2], 3)}
            for r in rows
        ]

    def concepts_by_role(self, role: str, limit: int = 20) -> list[str]:
        """All concepts Genesis has identified as playing a given role."""
        try:
            rows = self._conn.execute("""
                SELECT concept FROM concept_roles
                WHERE role = ?
                ORDER BY updated_at DESC
                LIMIT ?
            """, (role, limit)).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def curiosity_from_analogs(self) -> list[str]:
        """
        Concepts that Genesis should seek to understand next, derived from
        structural analogy: if wolves has a CAUSES→ edge (deer decline) and
        lions has the same structural role as wolves but no CAUSES→ edge yet,
        then 'lions' is a curiosity target — what does lions cause?

        Returns concept names Genesis should add to curiosity directives.
        """
        targets: list[str] = []
        try:
            # Find all concepts with REGULATOR role that have CAUSES_OUT
            regulators_with_cause = set(
                r[0] for r in self._conn.execute("""
                    SELECT DISTINCT concept_a FROM structural_patterns
                    WHERE role = 'REGULATOR'
                    UNION
                    SELECT DISTINCT concept_b FROM structural_patterns
                    WHERE role = 'REGULATOR'
                """).fetchall()
            )
            # Find regulators that lack any CAUSES outgoing edge
            for concept in regulators_with_cause:
                outgoing = self._relations.query_subject(concept, min_confidence=_MIN_CONF)
                has_causes = any(r["relation"] == "CAUSES" for r in outgoing)
                if not has_causes:
                    targets.append(concept)
        except Exception:
            pass
        return targets[:5]

    def pattern_report(self) -> dict:
        """Summary of detected structural patterns."""
        try:
            n_pairs = self._conn.execute(
                "SELECT COUNT(*) FROM structural_patterns"
            ).fetchone()[0]
            n_roles = self._conn.execute(
                "SELECT COUNT(DISTINCT role) FROM concept_roles"
            ).fetchone()[0]
            role_counts = dict(
                self._conn.execute(
                    "SELECT role, COUNT(*) FROM concept_roles GROUP BY role"
                ).fetchall()
            )
        except Exception:
            n_pairs = n_roles = 0
            role_counts = {}
        return {
            "analog_pairs":  n_pairs,
            "distinct_roles": n_roles,
            "role_counts":    role_counts,
        }

    def stats(self) -> dict:
        return self.pattern_report()
