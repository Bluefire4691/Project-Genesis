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
    not searchable concepts.

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


# Words too generic to be useful search terms.
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
    "does", "done", "gets", "make", "made", "take", "taken",
    "give", "given", "seem", "need", "used", "uses", "went", "come",
    "came", "gone", "seen", "kept", "keep", "call", "find", "show",
    "lead", "held", "said", "told", "mean", "work", "goes", "puts",
    # Generic nouns (not searchable on their own)
    "fact", "idea", "item", "list", "sets", "part", "case", "area",
    "role", "term", "form", "kind", "type", "way", "thing", "time",
    "year", "side", "line", "step", "base", "core", "body", "unit",
    "mode", "view", "note", "goal", "plan", "name", "word", "page",
    "link", "text", "data", "rate", "size", "order", "level",
    "number", "amount", "total", "count", "value", "result", "output",
    "change", "changes", "growth", "loss", "increase", "decrease",
    "average", "range", "scale", "measure", "degree",
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
    "versus", "across", "within",
}

_MIN_CONCEPT_LEN = 4

# WordNet lookup is cached for the session to avoid repeated imports
_wordnet_cache: dict[str, bool] = {}
_wordnet_available: bool | None = None


def _is_real_word(word: str) -> bool:
    """
    Return True if the word exists in WordNet.

    Filters out noise n-grams like 'searobber', 'adjusters', proper-noun
    fragments, and OCR artefacts that appear in memory keys but are not
    meaningful search topics.
    """
    global _wordnet_available
    if word in _wordnet_cache:
        return _wordnet_cache[word]

    if _wordnet_available is False:
        # WordNet unavailable — accept any word long enough
        return len(word) >= 5

    try:
        from nltk.corpus import wordnet
        _wordnet_available = True
        result = bool(wordnet.synsets(word))
    except Exception:
        _wordnet_available = False
        result = len(word) >= 5

    _wordnet_cache[word] = result
    return result


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
        Already-fetched topics are excluded, but the set resets once it
        grows large so Genesis can revisit concepts with fresh understanding.
        """
        # Reset fetched set once it grows too large — Genesis learns more
        # each session and re-reading the same corpus passage produces richer
        # relations the second time around.
        if len(self._fetched_topics) > 40:
            self._fetched_topics = set()

        candidates: list[tuple[float, str]] = []
        candidates.extend(self._graph_gap_targets())
        candidates.extend(self._memory_text_targets())

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
                "attention": 0.0,
                "relations_known": 0,
            }

        for score, concept in self._memory_text_targets():
            if concept not in candidates:
                candidates[concept] = {
                    "concept": concept,
                    "source": "memory",
                    "curiosity_score": round(score, 3),
                    "already_fetched": concept in self._fetched_topics,
                    "attention": 0.0,
                    "relations_known": 0,
                }

        report = sorted(candidates.values(),
                        key=lambda r: r["curiosity_score"], reverse=True)
        return report[:20]

    # ------------------------------------------------------------------
    # Primary signal: relation graph gaps
    # ------------------------------------------------------------------

    def _graph_gap_targets(self) -> list[tuple[float, str]]:
        """
        Find concepts that Genesis has heard of more than it can explain.

        Scores each relation-object by incoming_references / max(1, outgoing_relations).
        A concept mentioned by many things but able to explain little itself is the
        richest learning target. This ratio stays meaningful even after thousands of
        cycles — it never saturates to zero the way a pure "zero-outgoing" filter does.
        """
        brain = self._brain
        try:
            conn = brain.memory._long_term.conn
            cur = conn.execute("""
                WITH
                  inc AS (
                    SELECT LOWER(object) AS c, COUNT(*) AS n
                    FROM relations GROUP BY LOWER(object)
                  ),
                  out AS (
                    SELECT LOWER(subject) AS c, COUNT(*) AS n
                    FROM relations GROUP BY LOWER(subject)
                  )
                SELECT inc.c, inc.n AS incoming, COALESCE(out.n, 0) AS outgoing
                FROM inc
                LEFT JOIN out ON inc.c = out.c
                ORDER BY CAST(inc.n AS REAL) / MAX(1, COALESCE(out.n, 0)) DESC
                LIMIT 60
            """)
            rows = cur.fetchall()
        except Exception:
            return []

        scored = []
        for concept, incoming, outgoing in rows:
            clean = self._first_valid_word(concept)
            if not clean or clean in self._fetched_topics:
                continue
            # Score = how much is referenced relative to how well it's understood
            score = float(incoming) / max(1, outgoing)
            scored.append((score, clean))

        return scored

    # ------------------------------------------------------------------
    # Secondary signal: working memory text items
    # ------------------------------------------------------------------

    def _memory_text_targets(self) -> list[tuple[float, str]]:
        """
        High-attention text memories where the concept has few relations.
        Only text: keys — pattern/numeric keys are data labels.
        Only single real words — multi-word memory keys are noisy n-grams.
        """
        brain = self._brain
        wm = brain.memory.memories
        if not wm:
            return []

        scored = []
        seen: set[str] = set()

        sorted_wm = sorted(wm.items(), key=lambda kv: kv[1].relevance, reverse=True)

        for key, mem in sorted_wm[:60]:
            if not key.startswith("text:"):
                continue

            concept = self._key_to_single_word(key)
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

    def _first_valid_word(self, concept: str) -> str:
        """
        Extract the first meaningful, real word from a concept string.

        Returns a single word that is:
          - Long enough (_MIN_CONCEPT_LEN)
          - Not in the skip list
          - Present in WordNet (real word, not noise/artefact)

        Always returns a single word or empty string — never a phrase.
        Multi-word phrases from memory keys are too noisy to be reliable
        search targets for the corpus/WordNet pipeline.
        """
        clean = concept.replace("_", " ").strip().lower()
        for word in clean.split():
            if (len(word) >= _MIN_CONCEPT_LEN
                    and word not in _SKIP_CONCEPTS
                    and _is_real_word(word)):
                return word
        return ""

    def _key_to_single_word(self, key: str) -> str:
        """Extract a single valid word from a text: memory key."""
        raw = re.sub(r"^text:", "", key)
        return self._first_valid_word(raw)
