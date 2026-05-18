"""
Curiosity Engine — Ingestion Pipeline.

Genesis decides what to learn next based on its own internal state.
No external topic list. No engineer-specified curriculum.

Primary signal — relation graph gaps:
    Concepts that appear as objects (something affects them) but have
    zero outgoing relations (Genesis cannot explain what they do) are
    the highest-curiosity targets. Genesis knows they exist but not
    what they are.

Secondary signal — working memory text items:
    High-relevance TEXT memories where the concept has few relations.
    Pattern/numeric memory keys are excluded — they're data labels,
    not Wikipedia-searchable concepts.

Scoring:
    graph targets:  incoming_relation_count  (referenced often = important)
    memory targets: attention × (1 / max(1, relation_count))

This is the SOAR impasse-subgoaling mechanism applied to knowledge
acquisition: when Genesis encounters a concept it cannot place in its
existing knowledge structure, it creates a subgoal to resolve the gap.
"""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# Words too generic to be useful Wikipedia search terms.
# Covers: determiners, conjunctions, prepositions, common verbs (all forms),
# generic nouns, quantifiers, adjectives, and classifier tags that leak
# from the TextProcessor into relation objects.
_SKIP_CONCEPTS = {
    # Articles / determiners
    "the", "this", "that", "these", "those", "another", "other",
    # Conjunctions / prepositions
    "and", "but", "for", "nor", "yet", "both", "either", "neither",
    "with", "from", "into", "onto", "upon", "over", "under", "about",
    "since", "while", "until", "after", "before", "during", "between",
    "without", "within", "through", "against", "toward", "below",
    # Pronouns / pro-forms
    "they", "them", "their", "its", "his", "her", "our", "your",
    "ones", "each", "some", "many", "more", "most", "less", "least",
    "every", "both", "such", "same", "which", "what", "when", "where",
    # Common auxiliary / modal verbs
    "are", "was", "were", "has", "have", "had", "been", "being",
    "will", "would", "could", "should", "shall", "might", "must",
    "does", "done", "gets", "have", "make", "made", "take", "taken",
    "give", "given", "seem", "need", "used", "uses", "went", "come",
    "came", "gone", "seen", "kept", "keep", "call", "find", "show",
    "lead", "held", "said", "told", "mean", "work", "goes", "puts",
    # Generic nouns (not Wikipedia-searchable on their own)
    "fact", "idea", "item", "list", "sets", "part", "case", "area",
    "role", "term", "form", "kind", "type", "way", "thing", "time",
    "year", "side", "line", "step", "base", "core", "body", "unit",
    "mode", "view", "note", "goal", "plan", "name", "word", "page",
    "link", "text", "data", "rate", "size", "order", "level", "rate",
    "number", "amount", "total", "count", "value", "result", "output",
    # Classifier / sentiment tags that leak from TextProcessor
    "neutral", "sentiment", "definition", "observation", "sequence",
    "pattern", "concept", "concepts", "subset", "instance", "aspect",
    "example", "process", "system", "method", "approach", "model",
    # Adjective noise
    "not", "can", "will", "also", "just", "very", "well", "only",
    "then", "than", "even", "long", "high", "low", "fast", "slow",
    "large", "small", "early", "late", "first", "last", "once",
    "often", "still", "again", "thus", "like", "next", "various",
    "certain", "general", "common", "similar", "related", "specific",
    "multiple", "single", "complex", "simple", "relative", "dominant",
    "unknown", "major", "minor", "based", "known", "found", "given",
    "versus",
}

_MIN_CONCEPT_LEN = 4


class CuriosityEngine:
    """
    Identifies what Genesis most needs to learn next.

    Primary source: relation graph — concepts Genesis knows exist
    but cannot explain (referenced as objects, no outgoing relations).

    Fallback: working memory text items with high attention and low
    relation density.
    """

    def __init__(self, brain: "Orchestrator"):
        self._brain = brain
        self._fetched_topics: set[str] = set()

    def top_topics(self, n: int = 5) -> list[str]:
        """
        Return the top N concepts Genesis is most curious about.

        Prefers relation-graph gaps over memory key parsing.
        Already-fetched topics are excluded.
        """
        candidates: list[tuple[float, str]] = []

        # Primary: graph gaps — concepts referenced but unexplained
        candidates.extend(self._graph_gap_targets())

        # Secondary: high-attention text memories with low understanding
        candidates.extend(self._memory_text_targets())

        # Deduplicate, preserve highest score per concept
        seen: dict[str, float] = {}
        for score, concept in candidates:
            if concept not in self._fetched_topics:
                if concept not in seen or seen[concept] < score:
                    seen[concept] = score

        ranked = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)
        topics = [concept for concept, _ in ranked[:n]]
        self._fetched_topics.update(topics)
        return topics

    def curiosity_report(self) -> list[dict]:
        """Return scored curiosity candidates for inspection."""
        candidates: dict[str, dict] = {}

        for score, concept in self._graph_gap_targets():
            candidates[concept] = {
                "concept": concept,
                "source": "graph_gap",
                "curiosity_score": round(score, 3),
                "already_fetched": concept in self._fetched_topics,
            }

        for score, concept in self._memory_text_targets():
            if concept not in candidates:
                candidates[concept] = {
                    "concept": concept,
                    "source": "memory",
                    "curiosity_score": round(score, 3),
                    "already_fetched": concept in self._fetched_topics,
                }

        report = sorted(candidates.values(),
                        key=lambda r: r["curiosity_score"], reverse=True)
        return report[:20]

    # ------------------------------------------------------------------
    # Primary signal: relation graph gaps
    # ------------------------------------------------------------------

    def _graph_gap_targets(self) -> list[tuple[float, str]]:
        """
        Find concepts that appear as relation objects but have no
        outgoing relations of their own.

        These are concepts Genesis has 'heard of' (something causes,
        controls, or enables them) but cannot explain. Maximum gap
        between awareness and understanding.
        """
        brain = self._brain
        try:
            conn = brain.memory._long_term.conn
            cur = conn.execute("""
                SELECT object, COUNT(*) as incoming_count
                FROM relations
                WHERE LOWER(object) NOT IN (
                    SELECT DISTINCT LOWER(subject) FROM relations
                )
                GROUP BY object
                ORDER BY incoming_count DESC
                LIMIT 40
            """)
            rows = cur.fetchall()
        except Exception:
            return []

        scored = []
        for concept, incoming in rows:
            clean = self._clean_concept(concept)
            if not clean or clean in self._fetched_topics:
                continue
            # Score: how often is this concept referenced without explanation
            scored.append((float(incoming), clean))

        return scored

    # ------------------------------------------------------------------
    # Secondary signal: working memory text items
    # ------------------------------------------------------------------

    def _memory_text_targets(self) -> list[tuple[float, str]]:
        """
        High-attention text memories where the concept has few relations.
        Explicitly excludes pattern: and num: keys — those are data labels.
        """
        brain = self._brain
        wm = brain.memory.memories
        if not wm:
            return []

        scored = []
        seen: set[str] = set()

        sorted_wm = sorted(wm.items(), key=lambda kv: kv[1].relevance, reverse=True)

        for key, mem in sorted_wm[:50]:
            # Only use text memories — pattern/numeric keys are data labels
            if not key.startswith("text:"):
                continue

            concept = self._key_to_concept(key)
            if not concept or concept in seen or concept in self._fetched_topics:
                continue
            seen.add(concept)

            rel_info = brain.relations.query_concept(concept, min_confidence=0.3)
            relation_count = (
                len(rel_info["as_subject"]) + len(rel_info["as_object"])
            )

            score = mem.relevance * (1.0 / max(1, relation_count))
            scored.append((score, concept))

        return scored

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _clean_concept(self, concept: str) -> str:
        """Clean a relation graph concept into a Wikipedia search phrase."""
        clean = concept.replace("_", " ").strip().lower()
        words = clean.split()
        meaningful = [
            w for w in words
            if len(w) >= _MIN_CONCEPT_LEN and w not in _SKIP_CONCEPTS
        ]
        if not meaningful:
            return ""
        result = " ".join(meaningful[:3])
        return result if len(result) >= _MIN_CONCEPT_LEN else ""

    def _key_to_concept(self, key: str) -> str:
        """Extract a Wikipedia-searchable phrase from a text: memory key."""
        # Strip 'text:' prefix
        raw = re.sub(r"^text:", "", key)
        return self._clean_concept(raw)

