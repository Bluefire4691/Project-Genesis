"""
WordNet Dictionary — broad-coverage offline word lookup for the knowledge feeder.

When Wikipedia fails and the hand-crafted dictionary has no entry, this module
looks up any English word or phrase in WordNet (150k+ entries) and returns a
short definition formatted to produce clean relation edges through the text
processor.

WordNet organises words into synsets (groups of synonyms). Each synset has:
  - A definition
  - Hypernyms (IS_A parents — "mammal IS_A vertebrate")
  - Domain labels ("biology", "physics", etc.)

Lookup strategy:
  1. Check _PREFER_SYNSET for words where the first sense is wrong
  2. Otherwise prefer synsets with a scientific/natural lexname category
  3. Fall back to synsets()[0] (most common sense)
  4. Return a 2-sentence string: definition + IS_A statement if hypernym exists

Requires: pip install nltk + nltk.download('wordnet')
Auto-downloads wordnet data on first use if not already present.
"""

import re

# For words where WordNet's first (most-common) sense is the wrong one for
# a natural/scientific context, specify which synset index to use instead.
# Check by running: wn.synsets("word") and picking the right index.
_PREFER_SYNSET: dict[str, int] = {
    "predator":    1,  # [0]=criminal, [1]=animal that preys
    "friction":    1,  # [0]=interpersonal conflict, [1]=physical resistance
    "entropy":     1,  # [0]=information theory, [1]=thermodynamics
    "mutation":    1,  # [0]=organism, [1]=genetic change (more useful)
    "host":        1,  # [0]=person who entertains, [1]=biological host
    "parasite":    1,  # [0]=person, [1]=organism
    "nucleus":     2,  # [0]=physics, [1]=social group, [2]=cell nucleus
    "membrane":    0,
    "evolution":   1,  # [0]=general, [1]=organic/biological
    "friction":    1,
    "conductor":   1,  # [0]=music director, [1]=electricity conductor
    "resistance":  2,  # [0]=opposition, [1]=immune, [2]=physics
    "spectrum":    1,  # [0]=broad range, [1]=visible light spectrum
    "pressure":    0,
}

# Lexname categories that signal a scientific/concrete sense —
# these are preferred over abstract/social senses when multiple synsets exist
# and the word is not in _PREFER_SYNSET.
_PREFERRED_LEXNAMES = {
    "noun.animal", "noun.plant", "noun.body", "noun.phenomenon",
    "noun.process", "noun.substance", "noun.food", "noun.artifact",
    "noun.quantity", "noun.shape",
}

# Lexnames to avoid when a better option exists
_DEPRIORITISE_LEXNAMES = {"noun.person", "noun.state", "noun.act"}


def _load_wordnet():
    """Import wordnet, downloading corpus data if needed."""
    try:
        from nltk.corpus import wordnet as wn
        wn.synsets("test")  # verify corpus is loaded
        return wn
    except LookupError:
        import nltk
        nltk.download("wordnet", quiet=True)
        nltk.download("omw-1.4", quiet=True)
        from nltk.corpus import wordnet as wn
        return wn
    except Exception:
        return None


def _best_synset(wn, word: str):
    """
    Return the most appropriate synset for the word.

    Uses _PREFER_SYNSET override first, then prefers synsets with a
    scientific/natural lexname, then falls back to synsets()[0].
    """
    query = word.lower().replace(" ", "_")
    synsets = wn.synsets(query)
    if not synsets:
        return None

    word_lower = word.lower()

    # Explicit index override for known problem words
    if word_lower in _PREFER_SYNSET:
        idx = _PREFER_SYNSET[word_lower]
        if idx < len(synsets):
            return synsets[idx]
        return synsets[0]

    # Prefer a synset with a scientific/natural lexname
    for s in synsets:
        if s.lexname() in _PREFERRED_LEXNAMES:
            return s

    # Avoid person/state/act senses if something better exists
    non_social = [s for s in synsets if s.lexname() not in _DEPRIORITISE_LEXNAMES]
    if non_social:
        return non_social[0]

    return synsets[0]


def _format_definition(word: str, synset) -> str:
    """
    Build a rich definition string from a WordNet synset.

    Uses WordNet's structured relations to produce sentences with explicit
    trigger language that the TextProcessor can extract as typed edges:
      IS_A   — from hypernyms ("X is a Y")
      CONTAINS — from part/substance meronyms ("X contains Y")
      REQUIRES — from verb entailments ("X requires Y")
      CAUSES   — from verb cause relation ("X causes Y")
    """
    raw_defn = synset.definition().strip().rstrip(".")
    raw_defn = re.sub(r"^\([^)]+\)\s*", "", raw_defn)
    raw_defn = re.sub(r";\s*--[A-Z].*$", "", raw_defn)
    raw_defn = re.sub(r"[\s;]+$", "", raw_defn).strip()

    display = word.capitalize()
    sentences: list[str] = []

    # Sentence 1: core definition
    if raw_defn.lower().startswith(word.lower()):
        sentences.append(raw_defn.capitalize() + ".")
    elif raw_defn[:3].lower() in ("a ", "an "):
        sentences.append(f"{display} is {raw_defn}.")
    else:
        sentences.append(f"{display} refers to {raw_defn}.")

    # IS_A from hypernym — plain "is a", not "is a type of" so the regex captures cleanly
    try:
        hypernyms = synset.hypernyms()
        if hypernyms:
            hyp_name = hypernyms[0].lemmas()[0].name().replace("_", " ")
            sentences.append(f"{display} is a {hyp_name}.")
    except Exception:
        pass

    # CONTAINS from part or substance meronyms
    try:
        meronyms = synset.part_meronyms() or synset.substance_meronyms()
        if meronyms:
            mero_name = meronyms[0].lemmas()[0].name().replace("_", " ")
            sentences.append(f"{display} contains {mero_name}.")
    except Exception:
        pass

    # REQUIRES from verb entailments (e.g. "sleep" entails "rest")
    try:
        entailments = synset.entailments()
        if entailments:
            ent_name = entailments[0].lemmas()[0].name().replace("_", " ")
            sentences.append(f"{display} requires {ent_name}.")
    except Exception:
        pass

    # CAUSES from verb cause relation (e.g. "kill" causes "die")
    try:
        causes = synset.causes()
        if causes:
            cause_name = causes[0].lemmas()[0].name().replace("_", " ")
            sentences.append(f"{display} causes {cause_name}.")
    except Exception:
        pass

    return " ".join(sentences[:5])


class WordNetDictionary:
    """
    Offline broad-coverage dictionary backed by WordNet.

    Covers 150k+ English words and phrases. Returns a short definition
    formatted to produce relation edges through the Genesis text processor.

    Auto-downloads the WordNet corpus on first use if not already present.
    Falls back gracefully (returns None) if NLTK is unavailable.
    """

    def __init__(self):
        self._wn = None
        self._available: bool | None = None

    def _ensure_loaded(self) -> bool:
        if self._available is not None:
            return self._available
        self._wn = _load_wordnet()
        self._available = self._wn is not None
        return self._available

    def lookup(self, concept: str) -> str | None:
        """
        Return a definition string for the concept, or None if not found.

        Tries the full concept first, then the first significant word of
        multi-word concepts ("immune system" → also tries "immune").
        """
        if not self._ensure_loaded():
            return None

        concept = concept.strip().lower()
        if not concept:
            return None

        synset = _best_synset(self._wn, concept)
        if synset:
            return _format_definition(concept, synset)

        # Try first significant word for multi-word concepts
        skip = {"a", "an", "the", "of", "in", "on", "at", "to", "for"}
        words = concept.split()
        significant = [w for w in words if w not in skip and len(w) >= 3]
        if significant and significant[0] != concept:
            synset = _best_synset(self._wn, significant[0])
            if synset:
                return _format_definition(significant[0], synset)

        return None

    @property
    def available(self) -> bool:
        return self._ensure_loaded()
