"""
spaCy-based relation extractor for Genesis (M7 upgrade).

Replaces regex matching with genuine dependency-parse extraction when
spaCy is installed.  Falls back gracefully to an empty list when spaCy
or its model is not available — the regex extractor in text.py then
takes over.

Install to activate:
    pip install spacy
    python -m spacy download en_core_web_sm
"""
import re
from typing import Optional

try:
    import spacy as _spacy_lib
    try:
        _nlp = _spacy_lib.load("en_core_web_sm")
        SPACY_AVAILABLE = True
    except OSError:
        _nlp = None
        SPACY_AVAILABLE = False
except ImportError:
    _spacy_lib = None  # type: ignore[assignment]
    _nlp = None
    SPACY_AVAILABLE = False


# ── Verb lemma → (relation_type, confidence) ──────────────────────────────
_VERB_MAP: dict[str, tuple[str, float]] = {
    # CAUSES
    "cause":     ("CAUSES", 0.88),
    "lead":      ("CAUSES", 0.88),
    "result":    ("CAUSES", 0.85),
    "trigger":   ("CAUSES", 0.82),
    "produce":   ("CAUSES", 0.75),
    "generate":  ("CAUSES", 0.75),
    "create":    ("CAUSES", 0.72),
    "destroy":   ("CAUSES", 0.80),
    "kill":      ("CAUSES", 0.80),
    "eliminate": ("CAUSES", 0.78),
    # CONTROLS
    "control":   ("CONTROLS", 0.85),
    "regulate":  ("CONTROLS", 0.85),
    "manage":    ("CONTROLS", 0.78),
    "govern":    ("CONTROLS", 0.78),
    "shape":     ("CONTROLS", 0.75),
    "maintain":  ("CONTROLS", 0.72),
    "keep":      ("CONTROLS", 0.70),
    # PREVENTS
    "prevent":   ("PREVENTS", 0.85),
    "stop":      ("PREVENTS", 0.80),
    "block":     ("PREVENTS", 0.80),
    "suppress":  ("PREVENTS", 0.80),
    "inhibit":   ("PREVENTS", 0.82),
    "protect":   ("PREVENTS", 0.72),
    "defend":    ("PREVENTS", 0.72),
    # ENABLES
    "enable":    ("ENABLES", 0.82),
    "allow":     ("ENABLES", 0.80),
    "permit":    ("ENABLES", 0.78),
    "support":   ("ENABLES", 0.75),
    "facilitate":("ENABLES", 0.75),
    "provide":   ("ENABLES", 0.68),
    # REQUIRES
    "require":   ("REQUIRES", 0.82),
    "need":      ("REQUIRES", 0.82),
    "depend":    ("REQUIRES", 0.85),
    "rely":      ("REQUIRES", 0.85),
    # PREDATES
    "eat":       ("PREDATES", 0.88),
    "feed":      ("PREDATES", 0.88),
    "prey":      ("PREDATES", 0.88),
    "hunt":      ("PREDATES", 0.88),
    "consume":   ("PREDATES", 0.85),
    "graze":     ("PREDATES", 0.80),
    # AFFECTS
    "affect":    ("AFFECTS", 0.75),
    "influence": ("AFFECTS", 0.75),
    "increase":  ("AFFECTS", 0.72),
    "decrease":  ("AFFECTS", 0.72),
    "reduce":    ("AFFECTS", 0.72),
    "impact":    ("AFFECTS", 0.72),
    "alter":     ("AFFECTS", 0.70),
    # CONTAINS
    "contain":   ("CONTAINS", 0.80),
    "include":   ("CONTAINS", 0.75),
    "comprise":  ("CONTAINS", 0.80),
    "consist":   ("CONTAINS", 0.80),
}

# Relation type → canonical causal marker string (for ProcessorOutput metadata)
_REL_TO_MARKER: dict[str, str] = {
    "IS_A":     "is a",
    "CAUSES":   "caused",
    "CONTROLS": "controls",
    "PREVENTS": "prevents",
    "ENABLES":  "enables",
    "REQUIRES": "requires",
    "PREDATES": "preys on",
    "AFFECTS":  "affected",
    "CONTAINS": "contains",
}

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "it", "its", "this", "that",
    "and", "but", "or", "not", "no", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "as", "into", "about", "than", "then", "so", "if",
    "when", "which", "who", "what", "where", "how", "why", "while", "after",
    "before", "between", "through", "during", "their", "they", "them", "we",
    "our", "us", "you", "your", "he", "she", "his", "her", "also",
    "just", "more", "most", "other", "some", "such", "only", "both", "each",
    "very", "too", "all", "any", "same", "these", "those",
}


def _clean(raw: str) -> str:
    """Normalise a token span into a clean concept string."""
    words = raw.strip().lower().split()
    while words and words[0] in _STOPWORDS:
        words.pop(0)
    # Cap first, THEN strip trailing — avoids dangling prepositions after cap
    words = words[:3]
    while words and words[-1] in _STOPWORDS:
        words.pop()
    result = " ".join(words)
    result = re.sub(r"[^a-z0-9 ]", "", result).strip()
    # Final trailing strip after punctuation removal (e.g. trailing "which")
    words = result.split()
    while words and words[-1] in _STOPWORDS:
        words.pop()
    result = " ".join(words)
    if len(result) < 2:
        return ""
    if not any(len(t) >= 3 and t.isalpha() for t in result.split()):
        return ""
    return result


def _concept_for_token(token) -> str:
    """
    Build a concept string from a spaCy token: include compound and
    adjectival modifiers that precede the head, then the head itself.
    This gives "deer populations" from a token "populations" with
    compound child "deer" — without capturing the prepositional phrase
    "in forested areas" that follows.
    """
    parts = []
    for child in sorted(token.children, key=lambda t: t.i):
        if child.dep_ in ("compound", "amod") and child.i < token.i:
            # Recurse one level for compound-of-compound ("apex predators")
            for grandchild in sorted(child.children, key=lambda t: t.i):
                if grandchild.dep_ == "compound" and grandchild.i < child.i:
                    parts.append(grandchild.text)
            parts.append(child.text)
    parts.append(token.text)
    return _clean(" ".join(parts))


def _conj_tokens(token):
    """Yield token and all coordinated tokens (conj dep children)."""
    yield token
    for child in token.children:
        if child.dep_ == "conj":
            yield child


def _extract_from_verb(verb_token, inherited_subjects=None) -> list[dict]:
    """Recursively extract relations from a verb and its conjunction chain."""
    relations: list[dict] = []

    subjects = (
        inherited_subjects
        if inherited_subjects is not None
        else [t for t in verb_token.children if t.dep_ in ("nsubj", "nsubjpass")]
    )
    if not subjects:
        return relations

    is_copula = verb_token.lemma_ == "be"

    if is_copula:
        attrs = [t for t in verb_token.children if t.dep_ in ("attr", "acomp")]
        for subj_tok in subjects:
            subj = _concept_for_token(subj_tok)
            if not subj:
                continue
            for attr_tok in attrs:
                for obj_tok in _conj_tokens(attr_tok):
                    obj = _concept_for_token(obj_tok)
                    if obj and subj != obj:
                        relations.append({
                            "subject": subj,
                            "relation": "IS_A",
                            "object": obj,
                            "confidence": 0.88,
                        })
    else:
        rel_info = _VERB_MAP.get(verb_token.lemma_)
        if rel_info is not None:
            rel_type, confidence = rel_info

            direct_objs = [t for t in verb_token.children if t.dep_ in ("dobj", "oprd")]
            prep_objs: list = []
            for prep in [t for t in verb_token.children if t.dep_ == "prep"]:
                for pobj in [t for t in prep.children if t.dep_ == "pobj"]:
                    prep_objs.append(pobj)
            all_objs = direct_objs + prep_objs

            for subj_tok in subjects:
                subj = _concept_for_token(subj_tok)
                if not subj:
                    continue
                for obj_tok in all_objs:
                    for final_obj_tok in _conj_tokens(obj_tok):
                        obj = _concept_for_token(final_obj_tok)
                        if obj and subj != obj:
                            relations.append({
                                "subject": subj,
                                "relation": rel_type,
                                "object": obj,
                                "confidence": confidence,
                            })

    # Recurse into conjunct verbs (shared subject: "wolves hunt and control")
    for conj_verb in verb_token.children:
        if conj_verb.dep_ == "conj" and conj_verb.pos_ in ("VERB", "AUX"):
            relations.extend(_extract_from_verb(conj_verb, inherited_subjects=subjects))

    return relations


def extract_relations_spacy(sentence: str) -> list[dict]:
    """
    Extract typed relation triples from a sentence using spaCy dependency
    parsing.  Returns an empty list when spaCy is not installed or its
    model is not downloaded.
    """
    if not SPACY_AVAILABLE or _nlp is None:
        return []

    doc = _nlp(sentence)
    relations: list[dict] = []

    for token in doc:
        if token.dep_ == "ROOT" and token.pos_ in ("VERB", "AUX"):
            relations.extend(_extract_from_verb(token))

    # Deduplicate while preserving first-seen order
    seen: set[tuple] = set()
    unique: list[dict] = []
    for r in relations:
        key = (r["subject"], r["relation"], r["object"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def markers_for_relations(relations: list[dict]) -> list[str]:
    """Derive causal-marker strings from a list of extracted relations."""
    seen: set[str] = set()
    result: list[str] = []
    for r in relations:
        marker = _REL_TO_MARKER.get(r["relation"])
        if marker and marker not in seen:
            seen.add(marker)
            result.append(marker)
    return result
