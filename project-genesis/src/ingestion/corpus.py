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

    Uses an inverted word index so lookup is O(candidates) not O(all sentences).
    Building the index takes a few seconds on first load but pays off immediately:
    a 125k-sentence corpus scan (~3s) becomes a 500-sentence candidate scan (<5ms).
    """

    def __init__(self):
        self._available: Optional[bool] = None
        self._all_sents: list = []          # flat list of all sentences
        self._index: dict[str, list[int]] = {}  # word → [sentence indices]

    def _ensure_loaded(self) -> bool:
        if self._available is not None:
            return self._available

        result = _load_corpora()
        if result is None:
            self._available = False
            return False

        gutenberg, brown = result

        sents: list = []
        try:
            sents.extend(brown.sents(categories=_USEFUL_BROWN_CATEGORIES))
        except Exception:
            pass
        try:
            for fileid in gutenberg.fileids():
                sents.extend(gutenberg.sents(fileid))
        except Exception:
            pass

        if not sents:
            self._available = False
            return False

        self._all_sents = sents
        self._index = self._build_index(sents)
        self._available = True
        return True

    @staticmethod
    def _build_index(sents: list) -> dict[str, list[int]]:
        """Build word → [sentence_index] inverted index (built once on load)."""
        index: dict[str, list[int]] = {}
        for i, sent in enumerate(sents):
            seen_in_sent: set[str] = set()
            for word in sent:
                w = word.lower()
                if w not in seen_in_sent:
                    seen_in_sent.add(w)
                    if w not in index:
                        index[w] = []
                    index[w].append(i)
        return index

    def find_passages(self, topic: str) -> Optional[str]:
        """
        Find sentences from the offline corpus relevant to the topic.

        Uses the inverted index to find only sentences that contain at
        least one keyword — scoring a few hundred candidates instead of
        scanning the full 125k-sentence corpus every call.
        """
        if not self._ensure_loaded():
            return None

        keywords = _topic_keywords(topic)
        if not keywords:
            return None

        # Gather candidate sentence indices (any sentence with ≥1 keyword)
        candidate_ids: set[int] = set()
        for kw in keywords:
            if kw in self._index:
                candidate_ids.update(self._index[kw])

        if not candidate_ids:
            return None

        # Score candidates for multi-keyword overlap
        scored: list[tuple[int, list[str]]] = []
        for idx in candidate_ids:
            sent = self._all_sents[idx]
            score = _score_sentence(sent, keywords)
            if score >= _MIN_MATCHES:
                scored.append((score, sent))

        # Relax threshold if nothing met the bar
        if not scored:
            for idx in candidate_ids:
                sent = self._all_sents[idx]
                scored.append((1, sent))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = scored[:_PASSAGE_SENTENCES]

        sentences = [" ".join(words) for _, words in selected]
        passage = " ".join(sentences)

        passage = re.sub(r" +", " ", passage)
        passage = re.sub(r" ([,.;:!?])", r"\1", passage)
        passage = re.sub(r"`` ", '"', passage)
        passage = re.sub(r" ''", '"', passage)

        return passage.strip() if passage.strip() else None

    @property
    def available(self) -> bool:
        return self._ensure_loaded()
