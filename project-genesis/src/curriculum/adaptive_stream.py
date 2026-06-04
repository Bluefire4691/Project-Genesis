"""
Adaptive Stream — M9: Feedback Loop.

The feedback loop that was missing: Genesis's attention now shapes what
it encounters next.

Previously: DataStream serves items in shuffled order regardless of what
Genesis is attending to. Input flows in. Nothing flows back.

After M9: AdaptiveStream checks the working memory attention window each
cycle and biases item selection toward content that overlaps with current
attention terms. If Genesis is deeply engaged with "wolves/ecology/causation",
it is more likely to encounter more ecological content next — not because
we decided that, but because attention shapes perception.

This is how biological attention works. You notice what you are already
thinking about. Your current mental state makes some things more salient
than others. The AdaptiveStream models this property.

It is NOT:
  - Genesis deciding what to read
  - Us curating what Genesis gets
  - A reward signal for "good" attention

It IS:
  - A minimal feedback loop between mental state and environment
  - The first step toward consequences being real
  - Attention shaping perception, not content shaping attention

Diversity floor:
  A minimum fraction of selections are always chosen at random from the
  full pool, ignoring attention. This prevents monoculture — Genesis
  staying forever in one domain because early attention weighted toward it.
  Default: 30% random, 70% attention-weighted.
"""

import re
import random
from typing import TYPE_CHECKING

from curriculum.open_stage import DataStream, _POOL

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# Fraction of selections chosen randomly regardless of attention.
# Prevents attention monopoly on one domain.
_DIVERSITY_FLOOR: float = 0.30

# Maximum number of attention terms to use for scoring.
_MAX_ATTENTION_TERMS: int = 15

# Minimum score for an item to be considered "attention-relevant."
# Below this, items are treated as unrelated.
_MIN_RELEVANCE_SCORE: float = 0.05


class AdaptiveStream:
    """
    Attention-weighted data stream for open-stage processing.

    Wraps DataStream. After every cycle, samples working memory attention
    terms and uses them to weight item selection for the next cycle.

    Usage:
        stream = AdaptiveStream(brain)
        item = stream.next()          # attention-weighted selection
        items = stream.take(20)       # 20 attention-weighted items
    """

    def __init__(
        self,
        brain: "Orchestrator",
        diversity_floor: float = _DIVERSITY_FLOOR,
        seed: int | None = None,
    ):
        self._brain = brain
        self._diversity_floor = max(0.0, min(1.0, diversity_floor))
        self._rng = random.Random(seed)
        self._pool = list(_POOL)
        self._items_served: int = 0
        self._attention_selections: int = 0
        self._random_selections: int = 0
        self._current_attention_terms: list[str] = []

    # ------------------------------------------------------------------
    # Main interface
    # ------------------------------------------------------------------

    def next(self) -> dict:
        """
        Return the next item, weighted by current attention.

        With probability (1 - diversity_floor), selects from items whose
        content overlaps with the current attention window.
        With probability diversity_floor, selects randomly.
        """
        self._refresh_attention()

        use_random = self._rng.random() < self._diversity_floor

        if use_random or not self._current_attention_terms:
            item = self._rng.choice(self._pool)
            self._random_selections += 1
        else:
            item = self._attention_weighted_select()
            self._attention_selections += 1

        self._items_served += 1
        return item

    def take(self, n: int) -> list[dict]:
        """Return n items, each attention-weighted."""
        return [self.next() for _ in range(n)]

    # ------------------------------------------------------------------
    # Attention scoring
    # ------------------------------------------------------------------

    def _refresh_attention(self) -> None:
        """Pull current attention terms from working memory and reflection history."""
        try:
            terms: set[str] = set()

            wm = self._brain.memory.memories
            if wm:
                # Get attention window — top-K by relevance
                top = sorted(wm.items(), key=lambda kv: kv[1].relevance, reverse=True)
                top = top[:_MAX_ATTENTION_TERMS]

                for key, mem in top:
                    for part in re.split(r"[_:\s]+", key.lower()):
                        if len(part) >= 3:
                            terms.add(part)
                    for word in re.findall(r"\b[a-z]{3,}\b", mem.context.lower()[:80]):
                        terms.add(word)

            # Augment with reflection-salient concepts — this instance's longer-term
            # interests. Two instances with different histories will reflect on different
            # concepts and therefore exhibit different attention biases here, producing
            # genuinely divergent processing paths from the same underlying stream.
            try:
                salient = self._brain.consolidation.salient_concepts()
                for concept in salient[:8]:
                    for word in re.split(r"[\s_-]+", concept.lower()):
                        if len(word) >= 3:
                            terms.add(word)
            except Exception:
                pass

            self._current_attention_terms = list(terms)
        except Exception:
            self._current_attention_terms = []

    def _score_item(self, item: dict) -> float:
        """
        Score an item by overlap with current attention terms.

        Returns 0.0..1.0. Higher = more relevant to current attention.
        """
        if not self._current_attention_terms:
            return 0.0

        # Extract words from item content
        content = str(item.get("data", ""))
        if isinstance(item.get("data"), dict):
            content = " ".join(str(v) for v in item["data"].values())
        item_words = set(re.findall(r"\b[a-z]{3,}\b", content.lower()))

        if not item_words:
            return 0.0

        attention_set = set(self._current_attention_terms)
        overlap = len(attention_set & item_words)
        return min(1.0, overlap * 0.15)

    def _attention_weighted_select(self) -> dict:
        """
        Select an item weighted by attention relevance.

        Items with no relevance still have a small base probability so
        no item is permanently excluded.
        """
        scores = [
            max(_MIN_RELEVANCE_SCORE, self._score_item(item))
            for item in self._pool
        ]
        total = sum(scores)
        r = self._rng.random() * total
        cumulative = 0.0
        for item, score in zip(self._pool, scores):
            cumulative += score
            if r <= cumulative:
                return item
        return self._pool[-1]  # fallback

    # ------------------------------------------------------------------
    # Stats and introspection
    # ------------------------------------------------------------------

    @property
    def items_served(self) -> int:
        return self._items_served

    @property
    def attention_terms(self) -> list[str]:
        """Current attention terms used for scoring."""
        return list(self._current_attention_terms)

    def stats(self) -> dict:
        """Runtime statistics about selection behavior."""
        total = self._attention_selections + self._random_selections
        attn_pct = (self._attention_selections / total * 100) if total > 0 else 0.0
        return {
            "items_served": self._items_served,
            "attention_selections": self._attention_selections,
            "random_selections": self._random_selections,
            "attention_pct": round(attn_pct, 1),
            "diversity_floor": self._diversity_floor,
            "active_attention_terms": len(self._current_attention_terms),
            "pool_size": len(self._pool),
        }
