"""
Curiosity Engine — Ingestion Pipeline.

Genesis decides what to learn next based on its own internal state.
No external topic list. No engineer-specified curriculum.

The scoring function:
    curiosity(concept) = attention_relevance × (1 / max(1, relation_count))

High attention + low relations = Genesis is thinking about this concept
but doesn't understand it well. That gap is what curiosity should fill.

This is the SOAR impasse-subgoaling mechanism applied to knowledge
acquisition: when Genesis encounters a concept it cannot place in its
existing knowledge structure, it creates a subgoal to resolve the gap.

The curiosity engine makes that subgoal concrete — it identifies the
concept and fetches Wikipedia to resolve the impasse.
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# Concepts that are too generic to fetch usefully
_SKIP_CONCEPTS = {
    "the", "and", "but", "for", "are", "was", "has", "had", "not",
    "this", "that", "with", "from", "they", "its", "can", "will",
    "fact", "neutral", "sentiment", "definition", "observation",
    "sequence", "pattern", "result", "value", "data", "item",
    "type", "kind", "form", "way", "thing", "time", "year",
    "order", "level", "rate", "size", "number", "amount",
}

# Minimum characters for a concept to be Wikipedia-searchable
_MIN_CONCEPT_LEN = 4


class CuriosityEngine:
    """
    Identifies what Genesis most needs to learn next.

    Scans working memory for high-attention, low-understanding concepts.
    Returns them as Wikipedia search terms, ordered by curiosity score.

    Usage:
        engine = CuriosityEngine(brain)
        topics = engine.top_topics(n=5)
        # ['gray wolf', 'coral reef', 'gene mutation', ...]
    """

    def __init__(self, brain: "Orchestrator"):
        self._brain = brain
        self._fetched_topics: set[str] = set()

    def top_topics(self, n: int = 5) -> list[str]:
        """
        Return the top N concepts Genesis is most curious about.

        Scores each working-memory concept by:
            attention_relevance × (1 / max(1, relation_count))

        Concepts already fetched this session are excluded.
        """
        brain = self._brain
        wm = brain.memory.memories
        if not wm:
            return self._fallback_topics(n)

        # Score all working memory concepts
        scored: list[tuple[float, str]] = []
        seen: set[str] = set()

        # Sort by relevance so we process most-attended first
        sorted_wm = sorted(wm.items(), key=lambda kv: kv[1].relevance, reverse=True)

        for key, mem in sorted_wm[:50]:
            concept = self._extract_concept(key)
            if not concept or concept in seen or concept in self._fetched_topics:
                continue
            seen.add(concept)

            # Relation density: how much does Genesis already know about this?
            rel_info = brain.relations.query_concept(concept, min_confidence=0.3)
            relation_count = (
                len(rel_info["as_subject"]) + len(rel_info["as_object"])
            )

            # Curiosity: high attention × low understanding
            score = mem.relevance * (1.0 / max(1, relation_count))
            scored.append((score, concept))

        if not scored:
            return self._fallback_topics(n)

        scored.sort(reverse=True)
        topics = [concept for _, concept in scored[:n]]

        # Mark as fetched so we don't repeat
        self._fetched_topics.update(topics)
        return topics

    def curiosity_report(self) -> list[dict]:
        """Return scored curiosity candidates for inspection."""
        brain = self._brain
        wm = brain.memory.memories
        if not wm:
            return []

        report = []
        seen: set[str] = set()
        sorted_wm = sorted(wm.items(), key=lambda kv: kv[1].relevance, reverse=True)

        for key, mem in sorted_wm[:30]:
            concept = self._extract_concept(key)
            if not concept or concept in seen:
                continue
            seen.add(concept)

            rel_info = brain.relations.query_concept(concept, min_confidence=0.3)
            relation_count = len(rel_info["as_subject"]) + len(rel_info["as_object"])
            score = mem.relevance * (1.0 / max(1, relation_count))

            report.append({
                "concept":        concept,
                "attention":      round(mem.relevance, 3),
                "relations_known": relation_count,
                "curiosity_score": round(score, 3),
                "already_fetched": concept in self._fetched_topics,
            })

        report.sort(key=lambda r: r["curiosity_score"], reverse=True)
        return report

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_concept(self, key: str) -> str:
        """
        Extract a Wikipedia-searchable concept from a memory key.

        Memory keys look like: 'text:wolves_control_deer' or
        'pattern:forest_regrowth_sequence'. We extract the meaningful
        leading words and clean them into a search phrase.
        """
        # Strip source prefix (text:, pattern:, num:)
        raw = re.sub(r"^[a-z]+:", "", key)
        # Replace underscores with spaces
        raw = raw.replace("_", " ")
        # Strip trailing digits and short suffixes
        raw = re.sub(r"\s+\d+$", "", raw).strip()
        # Take words
        words = raw.split()
        # Filter: skip generic/noise words, keep meaningful
        meaningful = [
            w for w in words
            if len(w) >= _MIN_CONCEPT_LEN and w.lower() not in _SKIP_CONCEPTS
        ]
        if not meaningful:
            return ""
        # Use first 2-3 meaningful words as the search phrase
        concept = " ".join(meaningful[:3]).strip()
        # Final length check
        if len(concept) < _MIN_CONCEPT_LEN:
            return ""
        return concept

    def _fallback_topics(self, n: int) -> list[str]:
        """
        When working memory is empty, use the most-connected relation
        graph concepts as curiosity targets — things Genesis knows
        something about but could know more.
        """
        brain = self._brain
        most_connected = brain.relations.most_connected(limit=n * 2)
        topics = []
        for entry in most_connected:
            concept = entry.get("concept", "")
            if (concept and len(concept) >= _MIN_CONCEPT_LEN
                    and concept not in _SKIP_CONCEPTS
                    and concept not in self._fetched_topics):
                topics.append(concept)
                self._fetched_topics.add(concept)
            if len(topics) >= n:
                break
        return topics
