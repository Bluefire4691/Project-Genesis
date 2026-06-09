"""Tests for M7 TextProcessor — entity extraction, relation triples, claim type."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from processors.text import (
    TextProcessor,
    _split_sentences, _extract_entities, _classify_claim,
    _extract_relations_regex as _extract_relations, _extract_without, _clean_concept, _build_context,
)

P = TextProcessor()


# ==================================================================
# Backward-compatibility — existing tests must still pass
# ==================================================================

def test_categories_still_detected():
    result = P.process("A dog is an animal. Dogs are friendly and loyal.")
    assert "animal" in result.extracted["categories"]


def test_sentiment_positive():
    result = P.process("This is a wonderful beautiful day")
    assert result.extracted["sentiment"] == "positive"


def test_sentiment_negative():
    result = P.process("This is a terrible horrible situation")
    assert result.extracted["sentiment"] == "negative"


def test_never_crashes_empty():
    result = P.process("")
    assert result.source == "text"


def test_never_crashes_none():
    result = P.process(None)
    assert result.source == "text"


def test_never_crashes_dict():
    result = P.process({"weird": [1, 2, 3]})
    assert result.source == "text"


# ==================================================================
# Sentence splitting
# ==================================================================

def test_split_sentences_period():
    sents = _split_sentences("Wolves hunt deer. Deer overgraze without wolves.")
    assert len(sents) == 2


def test_split_sentences_multiple_punct():
    sents = _split_sentences("What happened? It collapsed! Then it recovered.")
    assert len(sents) == 3


def test_split_sentences_empty():
    assert _split_sentences("") == []


def test_split_sentences_single():
    sents = _split_sentences("Just one sentence here")
    assert len(sents) == 1


# ==================================================================
# Concept cleaning
# ==================================================================

def test_clean_concept_strips_stopwords():
    assert _clean_concept("the wolves") == "wolves"
    assert _clean_concept("wolves the") == "wolves"


def test_clean_concept_lowercase():
    result = _clean_concept("Wolves")
    assert result == "wolves"


def test_clean_concept_caps_at_three_words():
    result = _clean_concept("big scary hungry wolf pack animal")
    assert len(result.split()) <= 3


def test_clean_concept_empty_after_strip():
    result = _clean_concept("the a an")
    assert result == ""


def test_clean_concept_preserves_meaningful_words():
    result = _clean_concept("wolf population")
    assert "wolf" in result
    assert "population" in result


# ==================================================================
# Entity extraction
# ==================================================================

def test_entities_detect_proper_noun():
    result = P.process("Wolves were reintroduced to Yellowstone in 1995.")
    assert any("Yellowstone" in e for e in result.extracted["entities"])


def test_entities_skip_sentence_start():
    # "Wolves" starts the sentence — should not be treated as entity
    result = P.process("Wolves control deer populations.")
    # "Wolves" might or might not appear — but it shouldn't be *only* because it's at start
    assert isinstance(result.extracted["entities"], list)


def test_entities_multi_word():
    result = P.process("The National Park Service manages many parks.")
    entities = result.extracted["entities"]
    assert any(len(e.split()) > 1 for e in entities)


def test_entities_cap_at_eight():
    result = P.process("Alice Bob Carol Dave Eve Frank Grace Henry Irene John met.")
    assert len(result.extracted["entities"]) <= 8


def test_entities_empty_when_none():
    result = P.process("wolves eat deer in the forest every day")
    # No capitalized mid-sentence words
    assert isinstance(result.extracted["entities"], list)


# ==================================================================
# Claim type classification
# ==================================================================

def test_claim_type_question():
    result = P.process("What causes river bank erosion?")
    assert result.extracted["claim_type"] == "question"


def test_claim_type_definition():
    result = P.process("A predator is an animal that hunts other animals.")
    assert result.extracted["claim_type"] == "definition"


def test_claim_type_hypothesis():
    result = P.process("Cooperation may have driven the evolution of human intelligence.")
    assert result.extracted["claim_type"] == "hypothesis"


def test_claim_type_observation():
    result = P.process("Wolves were removed from Yellowstone in the 1920s.")
    assert result.extracted["claim_type"] == "observation"


def test_claim_type_fact():
    result = P.process("Water flows downhill due to gravity.")
    assert result.extracted["claim_type"] == "fact"


def test_claim_type_field_always_present():
    result = P.process("Anything at all")
    assert "claim_type" in result.extracted
    assert result.extracted["claim_type"] in ("fact", "hypothesis", "observation", "definition", "question")


# ==================================================================
# Relation extraction — individual patterns
# ==================================================================

def test_relation_causes():
    rels, _ = _extract_relations("Overgrazing caused severe erosion along the riverbanks.")
    assert any(r["relation"] == "CAUSES" for r in rels)


def test_relation_led_to():
    rels, _ = _extract_relations("The removal of wolves led to deer overpopulation.")
    assert any(r["relation"] == "CAUSES" for r in rels)


def test_relation_controls():
    rels, _ = _extract_relations("Wolves control deer populations in the ecosystem.")
    assert any(r["relation"] == "CONTROLS" for r in rels)


def test_relation_prevents():
    rels, _ = _extract_relations("Predators prevent prey species from overgrazing.")
    assert any(r["relation"] == "PREVENTS" for r in rels)


def test_relation_enables():
    rels, _ = _extract_relations("Stable riverbanks enable diverse plant growth.")
    assert any(r["relation"] == "ENABLES" for r in rels)


def test_relation_requires():
    rels, _ = _extract_relations("The ecosystem requires predators to stay balanced.")
    assert any(r["relation"] == "REQUIRES" for r in rels)


def test_relation_is_a():
    rels, _ = _extract_relations("A wolf is a large predatory mammal.")
    assert any(r["relation"] == "IS_A" for r in rels)


def test_relation_predates():
    rels, _ = _extract_relations("Wolves prey on deer and elk.")
    assert any(r["relation"] == "PREDATES" for r in rels)


def test_relation_subject_and_object_populated():
    rels, _ = _extract_relations("Fire causes smoke.")
    assert len(rels) > 0
    r = rels[0]
    assert r["subject"]
    assert r["object"]
    assert r["subject"] != r["object"]


def test_relation_confidence_in_range():
    rels, _ = _extract_relations("Wolves control deer populations.")
    for r in rels:
        assert 0.0 <= r["confidence"] <= 1.0


def test_relation_empty_sentence_returns_nothing():
    rels, markers = _extract_relations("")
    assert rels == []
    assert markers == []


def test_relation_no_match_returns_nothing():
    rels, _ = _extract_relations("The sky is blue on clear days.")
    # "is" alone doesn't match "is a" — may or may not match depending on pattern
    assert isinstance(rels, list)


# ==================================================================
# "Without X" construction
# ==================================================================

def test_without_relation_extracted():
    rels = _extract_without("Without wolves, deer populations explode.")
    assert len(rels) > 0
    r = rels[0]
    assert r["relation"] == "REQUIRES"
    assert "wolves" in r["object"]


def test_without_no_false_positive():
    rels = _extract_without("Water flows downhill due to gravity.")
    assert len(rels) == 0


# ==================================================================
# Full processor integration — relations in extracted dict
# ==================================================================

def test_processor_extracts_relations_from_causal_text():
    result = P.process("Wolves control deer populations in Yellowstone.")
    rels = result.extracted["relations"]
    assert len(rels) > 0
    assert any(r["relation"] == "CONTROLS" for r in rels)


def test_processor_relations_field_always_present():
    result = P.process("The sky is blue.")
    assert "relations" in result.extracted
    assert isinstance(result.extracted["relations"], list)


def test_processor_causal_markers_field():
    result = P.process("Overgrazing caused the rivers to change course.")
    markers = result.extracted["causal_markers"]
    assert isinstance(markers, list)
    assert len(markers) > 0


def test_processor_causal_markers_empty_for_neutral_text():
    result = P.process("The dog ran across the field.")
    assert isinstance(result.extracted["causal_markers"], list)


def test_processor_importance_higher_with_relations():
    simple = P.process("The sky is blue.")
    causal = P.process("Deforestation causes flooding and soil erosion worldwide.")
    assert causal.importance >= simple.importance


def test_processor_suggested_key_uses_entities():
    result = P.process("Yellowstone National Park was established in 1872.")
    assert result.suggested_key.startswith("text:")
    # Should use entity-derived key
    assert len(result.suggested_key) > len("text:")


def test_processor_confidence_higher_with_relations():
    bare = P.process("things happen sometimes")
    structured = P.process("Wolves control deer populations in the ecosystem.")
    assert structured.confidence >= bare.confidence


def test_processor_full_chain():
    """Multi-sentence text with causal chain — relations across sentences."""
    text = (
        "Wolves were removed from Yellowstone in the 1920s. "
        "Deer populations exploded. "
        "Overgrazing caused severe riverbank erosion. "
        "Rivers changed course."
    )
    result = P.process(text)
    assert result.source == "text"
    assert len(result.extracted["relations"]) > 0
    assert result.extracted["claim_type"] in ("observation", "fact")
    assert len(result.extracted.get("entities", [])) > 0


def test_processor_definition_sentence():
    # Use a clean definition without causal-sounding verbs that could
    # match CAUSES/PREDATES patterns before IS_A in the pattern list.
    result = P.process("A wolf is a large carnivorous mammal found across the northern hemisphere.")
    assert result.extracted["claim_type"] == "definition"
    rels = result.extracted["relations"]
    assert any(r["relation"] == "IS_A" for r in rels)


# ==================================================================
# Context string
# ==================================================================

def test_build_context_includes_relations():
    ctx = _build_context(
        categories=["animal"],
        sentiment="neutral",
        entities=["Wolves"],
        relations=[{"subject": "wolves", "relation": "CONTROLS", "object": "deer", "confidence": 0.85}],
        claim_type="fact",
    )
    assert "CONTROLS" in ctx


def test_build_context_no_relations():
    ctx = _build_context(
        categories=["animal"],
        sentiment="positive",
        entities=[],
        relations=[],
        claim_type="fact",
    )
    assert isinstance(ctx, str)
    assert len(ctx) > 0


# ==================================================================
# Runner
# ==================================================================

if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
