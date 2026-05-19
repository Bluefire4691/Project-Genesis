"""
Text sensory processor — M7: Relationship Extraction.

Handles text input with full relational structure extraction:
  - Named entity detection (proper nouns, multi-word entities)
  - Causal language detection (causes, controls, prevents, enables, requires)
  - Relation triple extraction: (subject, relation_type, object)
  - Claim type classification: fact / hypothesis / observation / definition / question
  - Existing: tokenization, categories, sentiment

No external libraries. Pure Python heuristics — fast, never crashes.

Design principle: this is a sensory organ, not a reasoning engine. It extracts
signal from text; what Genesis does with that signal emerges from the rest of
the architecture. We make the lens sharper, not the mind.
"""

import re
from typing import Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.types import ProcessorOutput
from processors.base import BaseProcessor


# ==================================================================
# Knowledge bases (unchanged from M1 TextProcessor)
# ==================================================================

_CATEGORIES = {
    "animal": {"dog", "cat", "bird", "fish", "horse", "cow", "lion", "tiger",
               "elephant", "mouse", "rabbit", "bear", "wolf", "deer", "snake",
               "whale", "dolphin", "eagle", "hawk", "owl", "ant", "bee"},
    "food": {"apple", "bread", "rice", "meat", "water", "milk", "cheese",
             "fruit", "vegetable", "egg", "fish", "salt", "sugar", "butter",
             "cake", "soup", "pizza", "pasta"},
    "place": {"city", "country", "mountain", "river", "ocean", "lake", "forest",
              "desert", "island", "village", "town", "home", "school", "park"},
    "person": {"mother", "father", "child", "baby", "friend", "teacher",
               "doctor", "king", "queen", "boy", "girl", "man", "woman"},
    "object": {"book", "table", "chair", "car", "door", "window", "ball",
               "phone", "computer", "tool", "key", "box", "cup", "hat"},
    "concept": {"love", "fear", "time", "truth", "peace", "war", "life",
                "death", "freedom", "justice", "knowledge", "power", "hope"},
}

_POSITIVE = {"good", "great", "happy", "love", "beautiful", "nice", "best",
             "wonderful", "excellent", "joy", "kind", "warm", "bright", "safe"}
_NEGATIVE = {"bad", "terrible", "sad", "hate", "ugly", "worst", "awful",
             "horrible", "pain", "cruel", "cold", "dark", "danger", "fear"}

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "it", "its", "this", "that",
    "and", "but", "or", "not", "no", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "as", "into", "about", "than", "then", "so", "if",
    "when", "which", "who", "what", "where", "how", "why", "while", "after",
    "before", "between", "through", "during", "their", "they", "them", "we",
    "our", "us", "you", "your", "he", "she", "his", "her", "its", "also",
    "just", "more", "most", "other", "some", "such", "only", "both", "each",
    "very", "too", "all", "any", "same", "these", "those",
}

# Relation extraction patterns: (regex, relation_type, confidence)
# Matched against lowercased sentence text.
_RELATION_PATTERNS: list[tuple[str, str, float]] = [
    # Causation
    (r"(.+?)\s+(?:caused?|causes?)\s+(.+)",                   "CAUSES",   0.88),
    (r"(.+?)\s+(?:led to|leads to)\s+(.+)",                   "CAUSES",   0.88),
    (r"(.+?)\s+(?:resulted? in|results? in)\s+(.+)",           "CAUSES",   0.85),
    (r"(.+?)\s+(?:triggered?|triggers?)\s+(.+)",               "CAUSES",   0.82),
    (r"(.+?)\s+(?:produced?|produces?)\s+(.+)",                "CAUSES",   0.75),
    # Control / regulation
    (r"(.+?)\s+(?:controls?|regulates?)\s+(.+)",               "CONTROLS", 0.85),
    (r"(.+?)\s+(?:manages?|governs?|shapes?)\s+(.+)",          "CONTROLS", 0.78),
    (r"(.+?)\s+(?:kept?|keeps?)\s+(.+?)\s+(?:in|at|under)",   "CONTROLS", 0.72),
    # Prevention
    (r"(.+?)\s+(?:prevents?|stops?|blocked?|blocks?)\s+(.+)", "PREVENTS", 0.85),
    (r"(.+?)\s+(?:suppressed?|suppresses?)\s+(.+)",            "PREVENTS", 0.80),
    # Enablement
    (r"(.+?)\s+(?:enables?|allows?|permitted?|permits?)\s+(.+)", "ENABLES", 0.82),
    (r"(.+?)\s+(?:supported?|supports?|facilitated?)\s+(.+)", "ENABLES",  0.75),
    # Dependency
    (r"(.+?)\s+(?:requires?|needs?)\s+(.+)",                   "REQUIRES", 0.82),
    (r"(.+?)\s+(?:depends? on|relies? on)\s+(.+)",             "REQUIRES", 0.85),
    # Classification
    (r"(.+?)\s+(?:is a|is an|are a|are an)\s+(.+)",            "IS_A",     0.88),
    (r"(.+?)\s+(?:refers to|means|defined as)\s+(.+)",         "IS_A",     0.82),
    # Predation / consumption
    (r"(.+?)\s+(?:eats?|feeds? on|preys? on|hunts?)\s+(.+)",   "PREDATES", 0.88),
    # Effect / impact
    (r"(.+?)\s+(?:increased?|decreased?|reduced?|elevated?)\s+(.+)", "AFFECTS", 0.72),
    (r"(.+?)\s+(?:affected?|affects?|influenced?|influences?)\s+(.+)", "AFFECTS", 0.75),
    # Composition
    (r"(.+?)\s+(?:contains?|consists? of|comprises?|made of|made up of)\s+(.+)", "CONTAINS", 0.80),
    # Involvement / participation (academic prose)
    (r"(.+?)\s+(?:is involved in|are involved in)\s+(.+)",             "AFFECTS",  0.72),
    (r"(.+?)\s+(?:plays? (?:a|an) (?:\w+ )?role in)\s+(.+)",          "AFFECTS",  0.70),
    (r"(.+?)\s+(?:is responsible for|are responsible for)\s+(.+)",     "CAUSES",   0.75),
    # Usage / purpose
    (r"(.+?)\s+(?:is used (?:for|to|in|as))\s+(.+)",                  "ENABLES",  0.72),
    (r"(.+?)\s+(?:provides?|supply|supplies)\s+(.+)",                  "ENABLES",  0.68),
    # Association
    (r"(.+?)\s+(?:is associated with|are associated with)\s+(.+)",     "AFFECTS",  0.65),
    (r"(.+?)\s+(?:is related to|are related to)\s+(.+)",               "AFFECTS",  0.62),
    # Part-whole
    (r"(.+?)\s+(?:is part of|are part of)\s+(.+)",                     "IS_A",     0.70),
    # Destruction / protection
    (r"(.+?)\s+(?:destroys?|kills?|eliminates?)\s+(.+)",               "CAUSES",   0.80),
    (r"(.+?)\s+(?:protects?|defends?)\s+(.+)",                         "PREVENTS", 0.72),
]

# Modal verbs signal hypothesis
_MODAL_VERBS = {"may", "might", "could", "perhaps", "possibly", "likely",
                "probably", "suggest", "appear", "seem", "appears", "seems"}

# Past-tense markers signal observations
_PAST_MARKERS = {"was", "were", "observed", "found", "showed", "demonstrated",
                 "resulted", "happened", "occurred", "discovered", "measured"}


# ==================================================================
# Processor
# ==================================================================

class TextProcessor(BaseProcessor):
    name = "text"

    def _process(self, data: Any) -> ProcessorOutput:
        text = str(data)
        sentences = _split_sentences(text)

        # ── Existing features ──────────────────────────────────────
        all_words = re.findall(r"\b\w+\b", text.lower())
        word_set = set(all_words)
        keywords = sorted(
            {w for w in word_set if w not in _STOPWORDS and len(w) >= 3},
            key=len, reverse=True
        )[:12]

        categories = [
            cat for cat, cat_words in _CATEGORIES.items()
            if word_set & cat_words
        ]

        pos_count = len(word_set & _POSITIVE)
        neg_count = len(word_set & _NEGATIVE)
        if pos_count > neg_count:
            sentiment = "positive"
        elif neg_count > pos_count:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        # ── New: M7 features ───────────────────────────────────────
        entities = _extract_entities(text, sentences)
        claim_type = _classify_claim(text, word_set)
        relations: list[dict] = []
        causal_markers: list[str] = []

        for sentence in sentences:
            rels, markers = _extract_relations(sentence)
            relations.extend(rels)
            causal_markers.extend(markers)

        # Also detect "without X" constructions separately
        without_rels = _extract_without(text)
        relations.extend(without_rels)
        if without_rels:
            causal_markers.append("without")

        # Deduplicate causal markers
        causal_markers = list(dict.fromkeys(causal_markers))

        # ── Importance ────────────────────────────────────────────
        # Relations are the strongest signal — they mean we understood structure
        importance = min(1.0,
            len(keywords) * 0.04
            + len(relations) * 0.18
            + len(entities) * 0.04
            + (0.08 if sentiment != "neutral" else 0.0)
            + (0.05 if claim_type != "fact" else 0.0)
        )
        importance = max(0.15, importance)  # floor

        # ── Suggested key ─────────────────────────────────────────
        # Prefer entity-derived keys (more specific), fall back to categories
        if entities:
            raw = "_".join(e.lower().replace(" ", "_") for e in entities[:2])
        elif relations:
            raw = f"{relations[0]['subject']}_{relations[0]['object']}"[:30]
        elif categories:
            raw = "_".join(categories[:2])
        else:
            raw = "_".join(keywords[:2]) if keywords else str(abs(hash(text)) % 9999)
        suggested_key = f"text:{re.sub(r'[^a-z0-9_]', '', raw)[:40]}"

        # ── Confidence ────────────────────────────────────────────
        # Higher confidence when we extracted structured information
        confidence = 0.5
        if relations:
            confidence = max(confidence, max(r["confidence"] for r in relations))
        if entities:
            confidence = min(1.0, confidence + 0.1)

        return ProcessorOutput(
            source=self.name,
            input_data=text,
            extracted={
                "keywords": keywords[:10],
                "categories": categories,
                "sentiment": sentiment,
                "word_count": len(all_words),
                "entities": entities,
                "claim_type": claim_type,
                "relations": relations[:8],       # cap to prevent noise explosion
                "causal_markers": causal_markers,
            },
            importance=importance,
            suggested_key=suggested_key,
            context=_build_context(categories, sentiment, entities, relations, claim_type),
            confidence=confidence,
        )


# ==================================================================
# Extraction functions
# ==================================================================

def _split_sentences(text: str) -> list[str]:
    """Split text into sentences on punctuation boundaries."""
    parts = re.split(r"[.!?;]+", text)
    return [p.strip() for p in parts if p.strip()]


def _extract_entities(text: str, sentences: list[str]) -> list[str]:
    """
    Find named entities: capitalized words that aren't sentence-initial.

    Also captures multi-word capitalized sequences (e.g. "Yellowstone National Park").
    Filters out stopwords and pure determiners.
    """
    entities: list[str] = []
    seen: set[str] = set()

    for sent in sentences:
        words = sent.split()
        i = 0
        while i < len(words):
            word = words[i]
            # Skip sentence-initial word (always capitalized)
            if i == 0:
                i += 1
                continue
            clean = re.sub(r"[^a-zA-Z]", "", word)
            if not clean or not clean[0].isupper():
                i += 1
                continue
            if clean.lower() in _STOPWORDS:
                i += 1
                continue

            # Try to extend to multi-word entity
            entity_words = [clean]
            j = i + 1
            while j < len(words):
                next_clean = re.sub(r"[^a-zA-Z]", "", words[j])
                if next_clean and next_clean[0].isupper() and next_clean.lower() not in _STOPWORDS:
                    entity_words.append(next_clean)
                    j += 1
                else:
                    break

            entity = " ".join(entity_words)
            if entity not in seen:
                seen.add(entity)
                entities.append(entity)
            i = j

    return entities[:8]


def _classify_claim(text: str, word_set: set[str]) -> str:
    """
    Classify the dominant claim type.

    fact        — declarative present tense, no hedging
    hypothesis  — modal verbs, uncertainty language
    observation — past tense, empirical report
    definition  — "X is a/an Y" structure
    question    — interrogative form
    """
    text_lower = text.lower().strip()

    # Question — check punctuation and sentence starters
    if text_lower.endswith("?") or re.match(
        r"^(?:what|how|why|when|where|who|is |are |can |does |did )", text_lower
    ):
        return "question"

    # Definition
    if re.search(r"\b(?:is a|is an|are a|are an|refers to|defined as|means)\b", text_lower):
        return "definition"

    # Hypothesis — modal / uncertainty language
    if word_set & _MODAL_VERBS:
        return "hypothesis"

    # Observation — past tense or empirical markers
    if word_set & _PAST_MARKERS:
        return "observation"

    return "fact"


def _extract_relations(sentence: str) -> tuple[list[dict], list[str]]:
    """
    Extract typed relation triples from a single sentence.

    Returns: (list of relation dicts, list of marker strings found)

    Each relation dict: {subject, relation, object, confidence}
    Subjects and objects are cleaned (stopwords stripped, max 3 words, lowercase).
    """
    sent_lower = sentence.lower().strip()
    if not sent_lower:
        return [], []

    relations: list[dict] = []
    markers_found: list[str] = []

    for pattern, rel_type, confidence in _RELATION_PATTERNS:
        m = re.search(pattern, sent_lower)
        if not m:
            continue

        subject = _clean_concept(m.group(1))
        obj = _clean_concept(m.group(2))

        if not subject or not obj or subject == obj:
            continue
        if len(subject.split()) > 4 or len(obj.split()) > 4:
            continue  # too long — likely a mis-match

        relations.append({
            "subject": subject,
            "relation": rel_type,
            "object": obj,
            "confidence": confidence,
        })
        # Record the trigger word(s)
        for marker in ("caused", "led to", "resulted in", "controls", "prevents",
                       "enables", "requires", "eats", "feeds on", "preys on",
                       "is a", "is an", "depends on", "involved in", "role in",
                       "associated with", "responsible for", "is part of"):
            if marker in sent_lower:
                markers_found.append(marker)
                break

    return relations, markers_found


def _extract_without(text: str) -> list[dict]:
    """
    Handle 'without X, Y' constructions.

    Interprets as: Y REQUIRES X (the thing being described needs X to function).
    Example: "Without wolves, deer overpopulate" → (deer, REQUIRES, wolves)
    """
    relations: list[dict] = []
    text_lower = text.lower()

    for m in re.finditer(r"without\s+([\w\s]{2,25}?)(?:,\s*|\s+)([\w]+)", text_lower):
        required = _clean_concept(m.group(1))
        consequence = _clean_concept(m.group(2))
        if required and consequence and required != consequence:
            relations.append({
                "subject": consequence,
                "relation": "REQUIRES",
                "object": required,
                "confidence": 0.72,
            })
            break  # one per text block

    return relations


def _clean_concept(raw: str) -> str:
    """
    Normalize a concept: strip stopwords from edges, lowercase, max 3 words.

    Returns empty string if nothing meaningful remains.
    """
    words = raw.strip().split()
    # Strip leading stopwords
    while words and words[0].lower() in _STOPWORDS:
        words = words[1:]
    # Strip trailing stopwords
    while words and words[-1].lower() in _STOPWORDS:
        words = words[:-1]
    # Cap length
    words = words[:3]
    result = " ".join(words).lower().strip()
    # Remove non-alphanumeric except spaces
    result = re.sub(r"[^a-z0-9 ]", "", result).strip()
    return result if len(result) >= 2 else ""


def _build_context(
    categories: list[str],
    sentiment: str,
    entities: list[str],
    relations: list[dict],
    claim_type: str,
) -> str:
    """Build a rich context string for memory storage."""
    parts = []
    if relations:
        rel_strs = [f"{r['subject']} {r['relation']} {r['object']}" for r in relations[:3]]
        parts.append("; ".join(rel_strs))
    if entities:
        parts.append(f"entities: {', '.join(entities[:4])}")
    if categories:
        parts.append(f"categories: {', '.join(categories)}")
    parts.append(f"{claim_type}, {sentiment} sentiment")
    return " | ".join(parts)
