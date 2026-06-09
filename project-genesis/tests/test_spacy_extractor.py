"""
Tests for the spaCy-based relation extractor (M7 upgrade).

When spaCy is not installed, SPACY_AVAILABLE is False and every function
returns empty results — those paths are always tested.

When spaCy IS installed, the grammar-aware tests run and verify:
  - IS_A from copula constructions
  - PREDATES / CONTROLS from action verbs
  - Multiple relations from a single compound sentence
  - Clean concepts (no dangling prepositions, no stopword tails)
  - Coordinated objects ("hunt deer and elk" → two PREDATES triples)
  - Conjunction verb chains ("hunt deer and prevent overgrazing")
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from processors.spacy_extractor import (
    SPACY_AVAILABLE,
    extract_relations_spacy,
    markers_for_relations,
    _clean,
)

# ── _clean() — always testable ──────────────────────────────────────────────

class TestClean:
    def test_strips_leading_stopword(self):
        assert _clean("the wolf") == "wolf"

    def test_strips_trailing_preposition_after_cap(self):
        # Bug that existed before fix: "deer populations in forested regions"
        # → cap to 3 → ["deer", "populations", "in"] → strip "in" → correct
        assert _clean("deer populations in forested regions") == "deer populations"

    def test_strips_trailing_stopword_after_punctuation_removal(self):
        # "populations, which" — after regex strip → "populations which" → strip "which"
        assert _clean("populations, which") == "populations"

    def test_cap_at_three_words(self):
        result = _clean("apex forest predator mammal canine")
        assert len(result.split()) <= 3

    def test_empty_after_all_stopwords(self):
        assert _clean("in the a") == ""

    def test_rejects_short_result(self):
        assert _clean("ab") == ""

    def test_rejects_no_real_word(self):
        assert _clean("50 6") == ""

    def test_clean_normal_concept(self):
        assert _clean("apex predators") == "apex predators"

    def test_clean_preserves_compound(self):
        assert _clean("trophic cascade") == "trophic cascade"


# ── Fallback path — always testable ─────────────────────────────────────────

class TestFallback:
    def test_returns_list(self):
        # Even without spaCy, must return a list (possibly empty)
        result = extract_relations_spacy("Wolves hunt deer.")
        assert isinstance(result, list)

    def test_markers_from_empty(self):
        assert markers_for_relations([]) == []

    def test_markers_deduplicated(self):
        rels = [
            {"subject": "a", "relation": "CAUSES", "object": "b", "confidence": 0.8},
            {"subject": "c", "relation": "CAUSES", "object": "d", "confidence": 0.8},
        ]
        markers = markers_for_relations(rels)
        assert markers.count("caused") == 1


# ── spaCy-dependent tests ───────────────────────────────────────────────────

pytestmark_spacy = pytest.mark.skipif(
    not SPACY_AVAILABLE,
    reason="spaCy + en_core_web_sm not installed",
)


@pytestmark_spacy
class TestSpacyIsA:
    def test_basic_is_a(self):
        rels = extract_relations_spacy("A wolf is an apex predator.")
        assert any(r["relation"] == "IS_A" for r in rels), f"No IS_A found: {rels}"

    def test_is_a_subject_clean(self):
        rels = extract_relations_spacy("A wolf is an apex predator.")
        is_a = [r for r in rels if r["relation"] == "IS_A"]
        subjects = [r["subject"] for r in is_a]
        assert "wolf" in subjects, f"Expected 'wolf' as subject: {subjects}"

    def test_is_a_object_no_dangling_stopword(self):
        rels = extract_relations_spacy("Wolves are social animals.")
        for r in rels:
            obj = r["object"]
            assert not obj.endswith((" in", " at", " of", " the", " a", " an")), (
                f"Object has dangling stopword: {obj!r}"
            )


@pytestmark_spacy
class TestSpacyPredates:
    def test_hunt(self):
        rels = extract_relations_spacy("Wolves hunt deer.")
        assert any(r["relation"] == "PREDATES" for r in rels), f"No PREDATES: {rels}"

    def test_subject_is_wolves(self):
        rels = extract_relations_spacy("Wolves hunt deer.")
        predates = [r for r in rels if r["relation"] == "PREDATES"]
        assert any("wolf" in r["subject"] or r["subject"] == "wolves" for r in predates), (
            f"Expected wolves as subject: {predates}"
        )

    def test_object_is_deer(self):
        rels = extract_relations_spacy("Wolves hunt deer.")
        predates = [r for r in rels if r["relation"] == "PREDATES"]
        assert any(r["object"] == "deer" for r in predates), (
            f"Expected deer as object: {predates}"
        )


@pytestmark_spacy
class TestSpacyControls:
    def test_controls(self):
        rels = extract_relations_spacy("Wolves control deer populations.")
        assert any(r["relation"] == "CONTROLS" for r in rels), f"No CONTROLS: {rels}"

    def test_controls_object_no_preposition(self):
        rels = extract_relations_spacy(
            "Wolves control deer populations in forested regions."
        )
        controls = [r for r in rels if r["relation"] == "CONTROLS"]
        for r in controls:
            assert "in" not in r["object"].split(), (
                f"Preposition leaked into object: {r['object']!r}"
            )
            assert r["object"] in ("deer populations", "populations"), (
                f"Unexpected object: {r['object']!r}"
            )


@pytestmark_spacy
class TestSpacyMultipleRelations:
    def test_compound_predicate_yields_two_relations(self):
        """'Wolves hunt deer and prevent overgrazing' → 2 relations, not 1."""
        rels = extract_relations_spacy(
            "Wolves hunt deer and prevent overgrazing."
        )
        rel_types = {r["relation"] for r in rels}
        assert len(rels) >= 2, (
            f"Expected ≥2 relations from compound predicate, got {rels}"
        )
        assert "PREDATES" in rel_types or "CONTROLS" in rel_types, (
            f"Expected PREDATES or CONTROLS in {rel_types}"
        )
        assert "PREVENTS" in rel_types, (
            f"Expected PREVENTS for 'prevent overgrazing': {rel_types}"
        )

    def test_coordinated_objects_yield_multiple_triples(self):
        """'Wolves hunt deer and elk' → PREDATES(wolves, deer) + PREDATES(wolves, elk)."""
        rels = extract_relations_spacy("Wolves hunt deer and elk.")
        predates = [r for r in rels if r["relation"] == "PREDATES"]
        objects = {r["object"] for r in predates}
        assert "deer" in objects, f"Expected 'deer' in PREDATES objects: {objects}"
        assert "elk" in objects, f"Expected 'elk' in PREDATES objects: {objects}"

    def test_photosynthesis_requires_multiple(self):
        """'Photosynthesis requires sunlight, water, and carbon dioxide' → 3 REQUIRES."""
        rels = extract_relations_spacy(
            "Photosynthesis requires sunlight, water, and carbon dioxide."
        )
        requires = [r for r in rels if r["relation"] == "REQUIRES"]
        assert len(requires) >= 2, (
            f"Expected ≥2 REQUIRES triples from 'requires sunlight, water, and CO2': {requires}"
        )


@pytestmark_spacy
class TestSpacyCleanConcepts:
    def test_no_raw_relation_tokens_in_subjects(self):
        sentences = [
            "Wolves control deer populations in forests.",
            "Photosynthesis requires sunlight and water.",
            "A neuron is a cell that transmits signals.",
        ]
        bad_tokens = {"IS_A", "CAUSES", "CONTROLS", "CONTAINS", "REQUIRES",
                      "PREVENTS", "ENABLES", "PREDATES", "AFFECTS"}
        for sent in sentences:
            for r in extract_relations_spacy(sent):
                assert r["subject"] not in bad_tokens, f"Raw token as subject: {r}"
                assert r["object"] not in bad_tokens, f"Raw token as object: {r}"

    def test_no_empty_concepts(self):
        sentences = [
            "Wolves control deer populations.",
            "Photosynthesis produces glucose.",
            "A mammal is a vertebrate.",
        ]
        for sent in sentences:
            for r in extract_relations_spacy(sent):
                assert r["subject"], f"Empty subject in relation from {sent!r}: {r}"
                assert r["object"],  f"Empty object in relation from {sent!r}: {r}"

    def test_confidence_in_range(self):
        rels = extract_relations_spacy("Wolves hunt deer.")
        for r in rels:
            assert 0.0 < r["confidence"] <= 1.0, (
                f"Confidence out of range: {r['confidence']}"
            )

    def test_no_duplicate_triples(self):
        rels = extract_relations_spacy("Wolves hunt deer and deer.")
        seen: set[tuple] = set()
        for r in rels:
            key = (r["subject"], r["relation"], r["object"])
            assert key not in seen, f"Duplicate triple: {key}"
            seen.add(key)
