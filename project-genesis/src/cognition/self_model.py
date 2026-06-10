"""
Self-Model — M27: Genesis Knows What It Knows.

Until now Genesis could express understanding but not introspect on it honestly.
Asked "what do you know about X?" it either echoed retained prose or said
nothing — it could not report *how well* it knows something: the confidence
behind its relations, whether its beliefs about a concept are contested,
whether it has actually read prose about it or only extracted edges in passing.

The SelfModel answers the question "how well do I understand this?" from
measurable internal state:

  - relation_count / as_subject / as_object — graph coverage
  - confidence — mean confidence over every relation the concept participates in
  - contested — contradictions Genesis currently holds about it
  - has_definition — whether an IS_A edge anchors the concept taxonomically
  - prose_count — retained sentences actually mentioning it (read vs. inferred)
  - inference_count — conclusions Genesis derived involving it
  - open_hypotheses — standing conjectures about it awaiting evidence
  - verdict — an honest tier: unknown / sparse / partial / solid

This is the architectural answer to Dunning-Kruger (CLAUDE.md Principle 5):
something in the system now explicitly represents "I don't know this."
A concept with two low-confidence edges gets verdict 'sparse', and the voice
layer says so, rather than performing fluency it doesn't have.

Everything here is read-only and computed on demand. No new tables, no writes
to any layer below — the self-model is a *view* of Genesis's state, not more
state. (Cross-layer interaction review: reads RelationGraph, ContradictionLog,
InferenceEngine, HypothesisEngine, and memory search. Writes nothing.)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator

from memory.relations import _normalise


# Verdict thresholds. Deliberately conservative: 'solid' should mean Genesis
# can genuinely stand behind what it says, not that it has seen the word a lot.
_SPARSE_MAX_RELATIONS = 2      # ≤ this many relations → at best 'sparse'
_SPARSE_MIN_CONF      = 0.50   # below this mean confidence → at best 'sparse'
_SOLID_MIN_RELATIONS  = 8      # 'solid' needs at least this much coverage
_SOLID_MIN_CONF       = 0.65   # ...at this mean confidence
# A contested concept can never be 'solid' — held contradictions cap it at
# 'partial' no matter the coverage. Knowing a lot of conflicting things is
# not the same as understanding.


class SelfModel:
    """
    Read-only introspection over Genesis's knowledge state.

    Callable so the orchestrator can expose it directly:

        brain.self_model("wolves")          # → assessment dict
        brain.self_model.overview()         # → global self-knowledge picture
        brain.self_model.weakest_concepts() # → where understanding is thinnest
    """

    def __init__(self, brain: "Orchestrator"):
        self._brain = brain

    # ------------------------------------------------------------------
    # Per-concept assessment
    # ------------------------------------------------------------------

    def assess(self, concept: str) -> dict:
        """
        How well does Genesis understand `concept`? Honest, measured answer.

        Returns a dict with coverage, confidence, contested beliefs, evidence
        sources, and a verdict tier. An unknown concept returns zeros and
        verdict 'unknown' — never a fabricated assessment.
        """
        norm = _normalise(concept or "")
        empty = {
            "concept": norm,
            "relation_count": 0,
            "as_subject": 0,
            "as_object": 0,
            "confidence": 0.0,
            "contested_count": 0,
            "contested": [],
            "has_definition": False,
            "prose_count": 0,
            "inference_count": 0,
            "open_hypotheses": 0,
            "verdict": "unknown",
        }
        if not norm:
            return empty

        rel = self._brain.relations

        # Coverage and confidence — over ALL edges, no confidence floor.
        # The self-model must see the weak edges too; that is the point.
        info = rel.query_concept(norm, min_confidence=0.0)
        as_subj = info["as_subject"]
        as_obj = info["as_object"]
        all_confs = [r["confidence"] for r in as_subj] + \
                    [r["confidence"] for r in as_obj]
        relation_count = len(all_confs)
        if relation_count == 0:
            return empty

        confidence = round(sum(all_confs) / relation_count, 3)
        has_definition = any(r["relation"] == "IS_A" for r in as_subj)

        # Contested beliefs — contradictions Genesis currently holds about it
        contested: list[dict] = []
        try:
            conflicts = self._brain.contradictions.query_concept(norm)
            contested = [
                {
                    "object": c.get("object", ""),
                    "rel_type_a": c.get("rel_type_a", ""),
                    "rel_type_b": c.get("rel_type_b", ""),
                }
                for c in conflicts[:5]
            ]
        except Exception as exc:
            self._log("self_model.contested", exc)

        # Prose evidence — has Genesis actually read sentences about this,
        # or does it only hold edges extracted in passing?
        prose_count = 0
        try:
            results = self._brain.memory.search(norm, top_k=10)
            prose_count = sum(
                1 for _k, m in results
                if norm in (m.content or "").lower()
            )
        except Exception as exc:
            self._log("self_model.prose", exc)

        # Derived understanding — conclusions Genesis worked out itself
        inference_count = 0
        try:
            inf = self._brain.inference.query(norm)
            inference_count = len(inf["as_subject"]) + len(inf["as_object"])
        except Exception as exc:
            self._log("self_model.inference", exc)

        # Open conjectures — what Genesis suspects but hasn't tested
        open_hypotheses = 0
        try:
            open_hypotheses = sum(
                1 for h in self._brain.hypotheses.open_hypotheses(limit=50)
                if h["subject"] == norm or (h["object"] or "") == norm
            )
        except Exception as exc:
            self._log("self_model.hypotheses", exc)

        verdict = self._verdict(relation_count, confidence, len(contested))

        return {
            "concept": norm,
            "relation_count": relation_count,
            "as_subject": len(as_subj),
            "as_object": len(as_obj),
            "confidence": confidence,
            "contested_count": len(contested),
            "contested": contested,
            "has_definition": has_definition,
            "prose_count": prose_count,
            "inference_count": inference_count,
            "open_hypotheses": open_hypotheses,
            "verdict": verdict,
        }

    # brain.self_model("wolves") reads naturally — the model *is* the question
    __call__ = assess

    @staticmethod
    def _verdict(relation_count: int, confidence: float, contested: int) -> str:
        if relation_count == 0:
            return "unknown"
        if relation_count <= _SPARSE_MAX_RELATIONS or confidence < _SPARSE_MIN_CONF:
            return "sparse"
        if (contested > 0
                or relation_count < _SOLID_MIN_RELATIONS
                or confidence < _SOLID_MIN_CONF):
            return "partial"
        return "solid"

    # ------------------------------------------------------------------
    # Global self-knowledge picture
    # ------------------------------------------------------------------

    def overview(self) -> dict:
        """
        The shape of Genesis's knowledge as a whole: how much it holds, how
        confident it is on average, where it is strongest and thinnest, and
        how much of what it holds is contested.
        """
        rel = self._brain.relations
        out = {
            "total_relations": 0,
            "total_concepts": 0,
            "mean_confidence": 0.0,
            "contested_total": 0,
            "strongest": [],
            "weakest": [],
        }
        try:
            out["total_relations"] = rel.stats().get("total_relations", 0)
            row = rel._conn.execute(
                "SELECT COUNT(DISTINCT c), AVG(confidence) FROM ("
                "  SELECT subject AS c, confidence FROM relations"
                "  UNION ALL"
                "  SELECT object AS c, confidence FROM relations"
                ")"
            ).fetchone()
            out["total_concepts"] = row[0] or 0
            out["mean_confidence"] = round(row[1] or 0.0, 3)
        except Exception as exc:
            self._log("self_model.overview", exc)

        try:
            out["contested_total"] = (
                self._brain.contradictions.stats().get("total_contradictions", 0)
            )
        except Exception as exc:
            self._log("self_model.overview.contested", exc)

        out["strongest"] = self.strongest_concepts(limit=3)
        out["weakest"] = self.weakest_concepts(limit=3)
        return out

    def strongest_concepts(self, limit: int = 5) -> list[dict]:
        """Concepts with the best coverage × confidence — what Genesis knows well."""
        return self._ranked_concepts(limit, ascending=False)

    def weakest_concepts(self, limit: int = 5) -> list[dict]:
        """
        Connected concepts where understanding is thinnest — the honest
        frontier. These are natural curiosity targets: Genesis has met them
        but cannot stand behind what it holds.
        """
        return self._ranked_concepts(limit, ascending=True)

    def _ranked_concepts(self, limit: int, ascending: bool) -> list[dict]:
        order = "ASC" if ascending else "DESC"
        try:
            rows = self._brain.relations._conn.execute(f"""
                SELECT c, COUNT(*) AS degree, AVG(confidence) AS conf
                FROM (
                    SELECT subject AS c, confidence FROM relations
                    UNION ALL
                    SELECT object AS c, confidence FROM relations
                )
                GROUP BY c
                HAVING LENGTH(c) >= 3
                ORDER BY (degree * conf) {order}
                LIMIT ?
            """, (limit,)).fetchall()
        except Exception as exc:
            self._log("self_model._ranked", exc)
            return []
        return [
            {"concept": r[0], "relation_count": r[1],
             "confidence": round(r[2], 3)}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _log(self, label: str, exc: Exception) -> None:
        try:
            self._brain.survival.resilience.error_log.log(label, exc)
        except Exception:
            pass
