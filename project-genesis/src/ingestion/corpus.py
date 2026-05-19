"""
Offline corpus reader — fallback when Gutenberg is unreachable.

Searches the NLTK text corpora that are already downloaded:
  - NLTK Gutenberg: 18 complete classic books (Melville, Milton, Bible, etc.)
  - NLTK Brown: 1.16M words across academic, lore, news, hobbies, government

When Genesis is curious about a topic, this finds sentences across both
corpora that are relevant to that topic and returns a coherent passage.

No network required. Degrades gracefully if NLTK corpora are not downloaded
(returns None — feeder gives up and moves to next topic).

This is not a substitute for reading whole books — it is reading fragments
from books that are already on disk. The Gutenberg fetcher (online) is
richer; this keeps Genesis learning even when offline.
"""

import re
from typing import Optional

# Brown categories most likely to contain useful knowledge for Genesis.
# Excluded: adventure, fiction, mystery, romance, science_fiction, humor
# (narrative genres produce fewer extractable relations than expository text)
_USEFUL_BROWN_CATEGORIES = [
    "learned",      # academic and scientific writing
    "lore",         # folk knowledge and natural history
    "hobbies",      # practical knowledge
    "government",   # policy and civic concepts
    "news",         # factual reporting
    "editorial",    # analytical writing
    "belles_lettres",  # essays and criticism
    "reviews",      # analytical writing about books/ideas
]

_PASSAGE_SENTENCES = 12   # sentences to return per topic
_MIN_MATCHES = 2          # minimum keyword hits to include a sentence


def _load_corpora() -> Optional[tuple]:
    """Load NLTK corpora, downloading if needed. Returns (gutenberg, brown) or None."""
    try:
        import nltk
        from nltk.corpus import gutenberg, brown
        # Trigger load to check if downloaded
        gutenberg.fileids()
        brown.fileids()
        return gutenberg, brown
    except LookupError:
        try:
            import nltk
            nltk.download("gutenberg", quiet=True)
            nltk.download("brown", quiet=True)
            from nltk.corpus import gutenberg, brown
            return gutenberg, brown
        except Exception:
            return None
    except Exception:
        return None


def _topic_keywords(topic: str) -> set[str]:
    """
    Expand a topic into a set of keywords for corpus search.

    Includes the topic words themselves plus any WordNet synonyms/hypernyms
    to widen the search without hardcoding mappings.
    """
    words = set(re.findall(r'[a-z]{3,}', topic.lower()))
    # Remove very common words that would match everything
    noise = {"the", "and", "for", "with", "that", "this", "from", "are",
             "was", "were", "has", "have", "had", "its", "not", "but"}
    words -= noise

    # Try to expand with WordNet synonyms
    try:
        from nltk.corpus import wordnet as wn
        expanded = set(words)
        for word in list(words):
            for synset in wn.synsets(word)[:2]:
                for lemma in synset.lemmas()[:3]:
                    expanded.add(lemma.name().replace("_", " ").lower())
                for hyp in synset.hypernyms()[:1]:
                    for lemma in hyp.lemmas()[:2]:
                        expanded.add(lemma.name().replace("_", " ").lower())
        return expanded
    except Exception:
        return words


def _score_sentence(sentence_words: list[str], keywords: set[str]) -> int:
    """Count how many keywords appear in the sentence."""
    sentence_lower = {w.lower() for w in sentence_words}
    return sum(1 for k in keywords if k in sentence_lower)


class OfflineCorpusFetcher:
    """
    Searches NLTK Gutenberg + Brown corpora for passages relevant to a topic.

    Used as an offline fallback when the Gutenberg HTTP fetcher cannot reach
    the network. Returns a block of real sentences from real books.
    """

    def __init__(self):
        self._corpora = None
        self._available: Optional[bool] = None
        self._brown_sents: Optional[list] = None
        self._gutenberg_sents: Optional[list] = None

    def _ensure_loaded(self) -> bool:
        if self._available is not None:
            return self._available

        result = _load_corpora()
        if result is None:
            self._available = False
            return False

        gutenberg, brown = result
        self._corpora = (gutenberg, brown)

        # Pre-load sentences from useful categories (done once)
        try:
            self._brown_sents = list(
                brown.sents(categories=_USEFUL_BROWN_CATEGORIES)
            )
        except Exception:
            self._brown_sents = []

        try:
            # All NLTK Gutenberg texts
            self._gutenberg_sents = []
            for fileid in gutenberg.fileids():
                self._gutenberg_sents.extend(gutenberg.sents(fileid))
        except Exception:
            self._gutenberg_sents = []

        self._available = (
            len(self._brown_sents) > 0 or len(self._gutenberg_sents) > 0
        )
        return self._available

    def find_passages(self, topic: str) -> Optional[str]:
        """
        Find and return sentences from the offline corpus relevant to the topic.

        Searches both Brown and Gutenberg corpora, scores each sentence by
        keyword overlap, and returns the top matches as a readable passage.
        """
        if not self._ensure_loaded():
            return None

        keywords = _topic_keywords(topic)
        if not keywords:
            return None

        # Score all sentences
        scored: list[tuple[int, list[str]]] = []

        for sent in (self._brown_sents or []):
            score = _score_sentence(sent, keywords)
            if score >= _MIN_MATCHES:
                scored.append((score, sent))

        for sent in (self._gutenberg_sents or []):
            score = _score_sentence(sent, keywords)
            if score >= _MIN_MATCHES:
                scored.append((score, sent))

        if not scored:
            # Relax to single keyword match if nothing found
            for sent in (self._brown_sents or []):
                score = _score_sentence(sent, keywords)
                if score >= 1:
                    scored.append((score, sent))

        if not scored:
            return None

        # Take top-scoring sentences, preserving some variety
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = scored[:_PASSAGE_SENTENCES]

        sentences = [" ".join(words) for _, words in selected]
        passage = " ".join(sentences)

        # Basic cleanup: collapse whitespace, fix common tokenisation artifacts
        passage = re.sub(r" +", " ", passage)
        passage = re.sub(r" ([,.;:!?])", r"\1", passage)
        passage = re.sub(r"`` ", '"', passage)
        passage = re.sub(r" ''", '"', passage)

        return passage.strip() if passage.strip() else None

    @property
    def available(self) -> bool:
        return self._ensure_loaded()
