"""
Spreading Activation — M19.

ACT-R (Anderson, 1983, 1993) spreading activation: when concepts are
active in working memory, related concepts in the semantic graph receive
a retrieval activation boost proportional to their graph proximity.

Without spreading activation, retrieval is purely lexical — memory.search()
returns memories that contain the query keyword. With spreading activation,
memories about graph-neighbors of currently-attended concepts surface even
when they share no keywords with the query.

The classic example:
    Genesis is attending to ["wolves", "ecology"].
    A query for "river change" should surface the memory about wolves
    preventing overgrazing preventing erosion affecting rivers — even though
    "river" and "wolves" share no text. The path exists in the relation
    graph. Spreading activation traverses it and primes the related concepts,
    which then boost the ranking of the "river change" memory.

Algorithm:
    1. Take source concepts (current attention window) with their weights
    2. BFS through RelationGraph; activation decays _DECAY per hop
       and is modulated by each edge's confidence
    3. Activation of a concept = max over all paths that reach it
    4. Any memory whose content/context mentions an activated concept
       gets a retrieval score bonus

Research grounding:
    - Anderson (1983): ACT-R declarative memory — activation spreads
      from goal/context items through associative links, decaying with
      fan-out (fan effect). Concepts at greater remove get less activation.
    - Collins & Loftus (1975): spreading activation as cognitive model —
      activation flows through semantic links with distance-based attenuation.
    - The implementation here uses the RelationGraph instead of a
      Collins-Quillian semantic network, but the propagation mechanics
      are identical: decay per hop, max over all incoming paths.
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.relations import RelationGraph


# Activation multiplier per hop in the relation graph
_DECAY = 0.50

# Activation is modulated by edge confidence at each hop
# (a CAUSES edge at conf=0.9 spreads more than conf=0.4)
_CONF_MODULATE = True

# Maximum hops to propagate — beyond 3 the activation is negligible
_MAX_HOPS = 3

# Activations below this threshold are not propagated further
_MIN_ACTIVATION = 0.05

# How much the activation map can boost a memory's retrieval score (additive)
_MAX_BOOST = 0.35

# Minimum edge confidence to traverse (don't follow very uncertain relations)
_MIN_EDGE_CONF = 0.35


class SpreadingActivation:
    """
    Computes an activation map over the RelationGraph from a set of
    source concepts, then uses it to boost memory retrieval ranking.

    Usage:
        sa = SpreadingActivation(relations)
        activation = sa.compute({"wolves": 0.9, "ecology": 0.6})
        # {"wolves": 0.9, "deer": 0.45, "overgrazing": 0.225, ...}

        boosted = sa.boost_scores(raw_scores, activation)
    """

    def __init__(self, relations: "RelationGraph"):
        self._relations = relations

    # ------------------------------------------------------------------
    # Core activation computation
    # ------------------------------------------------------------------

    def compute(self, sources: dict[str, float]) -> dict[str, float]:
        """
        Spread activation from source concepts through the relation graph.

        Parameters
        ----------
        sources : {concept: weight}
            Concepts currently active in working memory with their weights.
            Typically the attention window terms and their relevance scores.

        Returns
        -------
        {concept: activation_score}
            All concepts reachable within _MAX_HOPS, with activation
            proportional to distance and edge confidence.
        """
        if not sources:
            return {}

        # activation[concept] = highest activation reaching this concept so far
        activation: dict[str, float] = {}

        # BFS queue: (concept, current_activation, hops_so_far)
        queue: list[tuple[str, float, int]] = []

        for concept, weight in sources.items():
            clean = _clean(concept)
            if clean and weight >= _MIN_ACTIVATION:
                queue.append((clean, weight, 0))

        visited_at: dict[str, float] = {}  # concept → best activation seen

        while queue:
            concept, act, depth = queue.pop(0)

            # Skip if we've already reached this concept with equal/greater activation
            if visited_at.get(concept, 0) >= act:
                continue
            visited_at[concept] = act
            activation[concept] = act

            if depth >= _MAX_HOPS or act < _MIN_ACTIVATION:
                continue

            # Spread to neighbors (both outgoing and incoming edges)
            for neighbor, edge_conf in self._neighbors(concept):
                if edge_conf < _MIN_EDGE_CONF:
                    continue
                modulator = edge_conf if _CONF_MODULATE else 1.0
                next_act = act * _DECAY * modulator
                if next_act >= _MIN_ACTIVATION:
                    queue.append((neighbor, next_act, depth + 1))

        # Remove source concepts themselves from the boost map — they are
        # already attended to; the boost is for *related* concepts
        for concept in sources:
            activation.pop(_clean(concept), None)

        return activation

    def _neighbors(self, concept: str) -> list[tuple[str, float]]:
        """
        All direct neighbors in the relation graph.

        Returns (neighbor_concept, edge_confidence) pairs for both
        outgoing (concept as subject) and incoming (concept as object) edges.
        """
        result = []
        try:
            for r in self._relations.query_subject(concept, min_confidence=_MIN_EDGE_CONF):
                result.append((r["object"], r["confidence"]))
            for r in self._relations.query_object(concept, min_confidence=_MIN_EDGE_CONF):
                result.append((r["subject"], r["confidence"]))
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------
    # Retrieval score boosting
    # ------------------------------------------------------------------

    def boost_scores(
        self,
        scored_memories: list[tuple[str, object, float]],
        activation: dict[str, float],
    ) -> list[tuple[str, object, float]]:
        """
        Re-rank memories by adding spreading activation bonus to base scores.

        Parameters
        ----------
        scored_memories : list of (key, Memory, base_score)
        activation : activation map from compute()

        Returns
        -------
        Same list, re-sorted by boosted score.
        """
        if not activation:
            return scored_memories

        result = []
        for key, mem, base_score in scored_memories:
            boost = self._memory_activation(mem, activation)
            boosted = min(1.0, base_score + boost * _MAX_BOOST)
            result.append((key, mem, boosted))

        result.sort(key=lambda t: t[2], reverse=True)
        return result

    def _memory_activation(self, mem: object, activation: dict[str, float]) -> float:
        """
        Maximum activation of any concept word found in a memory's content/context.
        """
        try:
            text = f"{mem.content} {mem.context}".lower()
            words = set(re.findall(r"\b[a-z]{3,}\b", text))
            if not words:
                return 0.0
            return max((activation.get(w, 0.0) for w in words), default=0.0)
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def explain(self, sources: dict[str, float], top_n: int = 10) -> list[dict]:
        """
        What concepts are primed by the current attention state?

        Returns top_n activated concepts sorted by activation score.
        Useful for debugging and for Genesis's own introspection.
        """
        activation = self.compute(sources)
        ranked = sorted(activation.items(), key=lambda kv: kv[1], reverse=True)
        return [
            {"concept": c, "activation": round(a, 4)}
            for c, a in ranked[:top_n]
        ]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Normalize a concept string to match RelationGraph's _normalise output exactly."""
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()
