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

        The relation graph itself is the memory of what has been explored:
        a concept with outgoing relations is no longer a pure gap and falls
        out of the candidate set on its own. There is NO separate "already
        fetched" exclusion here — that previously starved the engine, because
        a small frontier (a handful of gaps) would all land in the exclusion
        set and never clear, leaving Genesis with nothing to learn.

        Avoiding genuine dead-ends (concepts WordNet cannot expand) is the
        feeder's job — it tracks which topics yielded nothing and stops
        retrying them. Here we simply rank the current gaps by curiosity.

        `_fetched_topics` is still recorded, but only to drive the
        `already_fetched` flag in curiosity_report — it never filters.
        """
        candidates: list[tuple[float, str]] = []
        candidates.extend(self._graph_gap_targets())
        candidates.extend(self._reflection_targets())
        candidates.extend(self._vocabulary_targets())
        candidates.extend(self._memory_text_targets())

        seen: dict[str, float] = {}
        for score, concept in candidates:
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

        for score, concept in self._reflection_targets():
            if concept not in candidates:
                candidates[concept] = {
                    "concept": concept,
                    "source": "reflection",
                    "curiosity_score": round(score, 3),
                    "already_fetched": concept in self._fetched_topics,
                    "attention": 0.0,
                    "relations_known": 0,
                }

        for score, concept in self._vocabulary_targets():
            if concept not in candidates:
                candidates[concept] = {
                    "concept": concept,
                    "source": "vocabulary",
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

        Two tiers, in strict priority:

          Tier 1 — pure gaps (outgoing == 0): concepts Genesis has encountered
                   as the object of some relation but cannot explain at all.
                   These are the real frontier. Every WordNet lookup introduces
                   new ones (the hypernyms, parts, and causes it names), so this
                   tier is continuously replenished as Genesis learns — it does
                   not saturate as long as understanding keeps expanding.

          Tier 2 — partial gaps (outgoing > 0): concepts Genesis can explain a
                   little, scored by incoming / outgoing. Only consulted once the
                   frontier of pure gaps is exhausted.

        Pure gaps always outrank partial gaps so Genesis pushes outward into the
        unknown instead of re-reading what it already understands (which would
        only produce duplicate relations).
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
                ORDER BY
                  (CASE WHEN COALESCE(out.n, 0) = 0 THEN 1 ELSE 0 END) DESC,
                  inc.n DESC
                LIMIT 150
            """)
            rows = cur.fetchall()
        except Exception:
            return []

        scored = []
        for concept, incoming, outgoing in rows:
            clean = self._first_valid_word(concept)
            if not clean:
                continue
            if outgoing == 0:
                # Pure gap — Genesis knows OF this but cannot explain it at all.
                # Boosted so it always outranks partially-understood concepts.
                score = 1000.0 + float(incoming)
            else:
                score = float(incoming) / outgoing
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
            if not concept or concept in seen:
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
    # Tertiary signal: unexplained vocabulary from what Genesis has read
    # ------------------------------------------------------------------

    def _vocabulary_targets(self) -> list[tuple[float, str]]:
        """
        Words Genesis has *read* but cannot yet explain.

        Every text it processes — a pool item, a corpus passage, a WordNet
        definition — contains words that have never become the subject of any
        relation. A reader who meets an unfamiliar word and looks it up is how
        a mind grows; this is that, driven entirely by Genesis's own state
        (what is unknown to *it*), not an external syllabus.

        This is what keeps Genesis from going static. The relation graph alone
        eventually collapses inward — every gap reduces to a concept it already
        knows. But the text streaming through working memory carries an
        effectively unbounded vocabulary, and each definition Genesis reads
        introduces fresh words to be curious about. The frontier never closes
        as long as it keeps reading.

        Scored in a band above partial graph-gaps but below pure gaps:
        frequently-seen unknown words first.
        """
        brain = self._brain
        wm = brain.memory.memories
        if not wm:
            return []

        # Concepts Genesis can already explain (appear as a relation subject).
        # One query, then a cheap membership test — far cheaper than calling
        # query_concept per word.
        try:
            explained = {
                row[0] for row in brain.memory._long_term.conn.execute(
                    "SELECT DISTINCT LOWER(subject) FROM relations"
                ).fetchall()
            }
        except Exception:
            explained = set()

        freq: dict[str, int] = {}
        sorted_wm = sorted(wm.items(), key=lambda kv: kv[1].relevance, reverse=True)
        for key, mem in sorted_wm[:80]:
            if not key.startswith("text:"):
                continue
            # Stored content is "raw text | {json features}" — keep the raw text.
            raw = (mem.content or "").split(" | ", 1)[0].lower()
            for word in re.findall(r"[a-z]{4,}", raw):
                if word in _SKIP_CONCEPTS or word in explained:
                    continue
                freq[word] = freq.get(word, 0) + 1

        # Validate only the most frequent candidates against WordNet (the
        # expensive step), capped so this stays cheap even with a full WM.
        scored: list[tuple[float, str]] = []
        checked = 0
        for word, f in sorted(freq.items(), key=lambda kv: kv[1], reverse=True):
            if checked >= 50:
                break
            checked += 1
            if not _is_real_word(word):
                continue
            scored.append((100.0 + float(f), word))

        return scored

    # ------------------------------------------------------------------
    # Quaternary signal: this instance's reflection-salient concepts
    # ------------------------------------------------------------------

    def _reflection_targets(self) -> list[tuple[float, str]]:
        """
        Concepts Genesis judged salient in its own reflections.

        This is what makes instances diverge. Two Genesis instances started
        from the same seed will process different inputs, form different
        reflections, and therefore have different gravitational centers of
        curiosity. One instance ends up drawn toward ecology because that
        appeared in its salient concepts early; another gravitates toward
        physics. The engineer never decided this — the divergence came from
        processing history alone.

        Scored between pure graph gaps (1000+) and vocabulary targets (100+):
        reflection-salience is a real signal but doesn't override the raw
        knowledge frontier.
        """
        brain = self._brain
        try:
            salient = brain.consolidation.salient_concepts()
        except Exception:
            return []

        scored: list[tuple[float, str]] = []
        for rank, concept in enumerate(salient):
            clean = concept.strip().lower()
            if not clean or clean in _SKIP_CONCEPTS:
                continue
            # Decay by rank: first concept scores ~440, eighth scores ~200.
            score = 200.0 + max(0.0, (8 - rank) * 30.0)
            scored.append((score, clean))
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
