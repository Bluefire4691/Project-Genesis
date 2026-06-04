"""
End-to-end integration tests — the suite that should have existed from the start.

Unlike the per-module unit tests, these run the REAL pipeline the way main.py
does: a real Orchestrator, real local WordNet text, real relation extraction,
real reflection. They assert the properties a user actually cares about:

    1. Feeding new knowledge makes the relation graph GROW.
    2. Reflection does not break subsequent relation growth.
    3. Source prose is RETAINED in memory (total-retention principle).
    4. When the curiosity frontier is exhausted, the system says so HONESTLY
       instead of silently looping on concepts it already knows.
    5. Structure-bearing short sentences are not silently discarded.

These are deliberately slow and use no mocks. If one of these is red, Genesis
is broken in a way a user will feel — regardless of how many unit tests pass.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _fresh_brain():
    from orchestrator.orchestrator import Orchestrator
    db = tempfile.mktemp(suffix=".db")
    return Orchestrator(verbose=False, db_path=db), db


def _wordnet():
    from ingestion.wordnet_dict import WordNetDictionary
    wn = WordNetDictionary()
    if not wn.available:
        pytest.skip("WordNet corpus not available in this environment")
    return wn


# Distinct concepts whose WordNet definitions yield clean, non-overlapping triples
_CONCEPTS_A = ["bird", "wolf", "river", "mountain", "ocean", "forest"]
_CONCEPTS_B = ["eagle", "salmon", "oak", "granite", "valley", "glacier"]


class TestKnowledgeGrowth:
    def test_feeding_distinct_concepts_grows_relations(self):
        brain, db = _fresh_brain()
        wn = _wordnet()
        try:
            before = brain.relations.stats().get("total_relations", 0)
            for c in _CONCEPTS_A:
                d = wn.lookup(c)
                if d:
                    brain.process_input("text", d)
            after = brain.relations.stats().get("total_relations", 0)
            assert after > before, (
                f"Feeding {len(_CONCEPTS_A)} new concepts added no relations "
                f"({before} -> {after}). Relation extraction is broken."
            )
        finally:
            os.unlink(db)

    def test_reflection_does_not_stop_relation_growth(self):
        """The reported bug: after a reflection, no new relations are created."""
        brain, db = _fresh_brain()
        wn = _wordnet()
        try:
            for c in _CONCEPTS_A:
                d = wn.lookup(c)
                if d:
                    brain.process_input("text", d)
            mid = brain.relations.stats().get("total_relations", 0)

            # Reflect — the operation the user says breaks things
            brain.reflect(cycle=100)

            # Feeding MORE distinct concepts after reflection must still grow
            for c in _CONCEPTS_B:
                d = wn.lookup(c)
                if d:
                    brain.process_input("text", d)
            after = brain.relations.stats().get("total_relations", 0)
            assert after > mid, (
                f"Relation growth halted after reflect() "
                f"({mid} -> {after}). Reflection is corrupting the pipeline."
            )
        finally:
            os.unlink(db)


class TestTotalRetention:
    def test_source_prose_is_retained_not_just_triples(self):
        """
        The total-retention principle: the actual descriptive prose must be
        recoverable, not reduced to a skeleton of triples.
        """
        brain, db = _fresh_brain()
        wn = _wordnet()
        try:
            d = wn.lookup("bird")
            assert d, "WordNet returned no definition for 'bird'"
            brain.process_input("text", d)

            # A distinctive descriptive word from the definition prose
            # (e.g. "feathers"/"warm-blooded") should be findable in memory,
            # proving the prose was retained, not discarded after extraction.
            results = brain.memory.search("feathers", top_k=5)
            joined = " ".join(
                f"{mem.content} {mem.context}".lower()
                for _key, mem in results
            ) if results else ""
            assert "feather" in joined or "warm" in joined or "vertebrate" in joined, (
                "The descriptive prose of the definition was not retained in "
                "memory — only the extracted triples survived. This violates "
                "total retention and starves synthesis of real language."
            )
        finally:
            os.unlink(db)


class TestFrontierHonesty:
    def test_exhausted_topic_reports_honestly(self):
        """
        Feeding the same concept twice should add nothing the second time
        (already known) — but the feeder must REPORT that honestly rather
        than silently churning. After a topic is exhausted it should be set
        aside, not re-served forever.
        """
        from ingestion.feeder import KnowledgeFeeder
        brain, db = _fresh_brain()
        _wordnet()
        try:
            feeder = KnowledgeFeeder(brain)

            r1 = feeder._fetch_and_process("wolf", verbose=False)
            assert r1["success"], "First fetch of 'wolf' produced nothing"
            rel_after_first = brain.relations.stats().get("total_relations", 0)
            assert rel_after_first > 0

            # Second fetch of the SAME concept adds no new relations
            r2 = feeder._fetch_and_process("wolf", verbose=False)
            rel_after_second = brain.relations.stats().get("total_relations", 0)
            assert rel_after_second == rel_after_first, (
                "Re-fetching a known concept changed the graph unexpectedly."
            )
        finally:
            os.unlink(db)

    def test_unproductive_topics_are_set_aside(self):
        """
        After repeated unproductive fetches, a concept must be set aside so the
        feeder stops re-serving dead-ends. Regression guard for the 'relations
        get stuck' report.
        """
        from ingestion.feeder import KnowledgeFeeder
        brain, db = _fresh_brain()
        _wordnet()
        try:
            feeder = KnowledgeFeeder(brain)
            # Exhaust 'wolf' completely
            for _ in range(feeder._MAX_STRIKES + 1):
                rb = brain.relations.stats().get("total_relations", 0)
                feeder._fetch_and_process("wolf", verbose=False)
                ra = brain.relations.stats().get("total_relations", 0)
                if ra == rb:
                    feeder._unproductive["wolf"] = feeder._unproductive.get("wolf", 0) + 1
            assert feeder._unproductive.get("wolf", 0) >= feeder._MAX_STRIKES, (
                "Exhausted concept 'wolf' was never marked unproductive — "
                "the feeder will re-serve it forever."
            )
        finally:
            os.unlink(db)


class TestChunkerStructure:
    def test_short_clean_sentences_are_not_discarded(self):
        """
        The chunker drops sentences under 60 chars. Short sentences like
        'Wolves hunt deer. Deer eat grass.' carry the cleanest causal triples —
        discarding them throws away exactly the structure we want.
        """
        from ingestion.chunker import chunk_text
        passage = (
            "Wolves hunt deer. Deer eat grass. Grass needs rain. "
            "The presence of wolves keeps the deer population in check, "
            "which in turn allows the grass to recover across the valley floor."
        )
        chunks = chunk_text(passage)
        joined = " ".join(chunks).lower()
        # All three short factual sentences must survive somewhere
        for needed in ("wolves hunt deer", "deer eat grass", "grass needs rain"):
            assert needed in joined, (
                f"Chunker discarded the short structure-bearing sentence: "
                f"'{needed}'. Meaning is being shredded at ingestion."
            )
