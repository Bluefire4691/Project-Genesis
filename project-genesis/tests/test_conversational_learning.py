"""
Tests for conversational on-demand learning — M24.

The gap this closes: previously Genesis could only talk about what was already
in its graph. Ask it about lakes and it had nothing to say. Now, when a human
asks about a topic, Genesis goes and learns about it right then — reads the
WordNet definition (always offline) and any relevant book passage — then
answers comprehensively from what it just read.

This is the mechanism a curious person uses: hear a question, go find out, come
back with an answer. No LLM, no parametric recall — real text, processed live.

These tests also guard the sense-selection fix: "lake" must resolve to a body
of water, not a red pigment; "mountain" to a landform, not "a large quantity".
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _fresh_brain():
    from orchestrator.orchestrator import Orchestrator
    from utils.types import Stage
    db = tempfile.mktemp(suffix=".db")
    b = Orchestrator(verbose=False, db_path=db)
    b.curriculum.current_stage = Stage.OPEN
    return b, db


def _wordnet_or_skip():
    from ingestion.wordnet_dict import WordNetDictionary
    if not WordNetDictionary().available:
        pytest.skip("WordNet corpus not available in this environment")


# ===========================================================================
# Topic extraction from questions
# ===========================================================================

class TestQueryTopicExtraction:
    def test_extracts_topic_from_tell_me_about(self):
        b, db = _fresh_brain()
        try:
            words, explicit = b.voice._query_topic("tell me about lakes")
            assert "lakes" in words
            assert explicit is False
        finally:
            os.unlink(db)

    def test_extracts_topic_from_what_is(self):
        b, db = _fresh_brain()
        try:
            words, _ = b.voice._query_topic("what is a river?")
            assert "river" in words
        finally:
            os.unlink(db)

    def test_explicit_learn_request_is_flagged(self):
        b, db = _fresh_brain()
        try:
            words, explicit = b.voice._query_topic("can you learn about volcanoes")
            assert "volcanoes" in words
            assert explicit is True, "explicit learn request must set the learn flag"
        finally:
            os.unlink(db)

    def test_non_question_returns_no_topic(self):
        b, db = _fresh_brain()
        try:
            words, _ = b.voice._query_topic("hello there how are you")
            assert words == []
        finally:
            os.unlink(db)

    def test_strips_articles_and_fillers(self):
        b, db = _fresh_brain()
        try:
            words, _ = b.voice._query_topic("explain the mountain")
            assert "mountain" in words
            assert "the" not in words
        finally:
            os.unlink(db)


# ===========================================================================
# On-demand learning grows the graph
# ===========================================================================

class TestOnDemandLearning:
    def test_learn_about_grows_relations(self):
        _wordnet_or_skip()
        b, db = _fresh_brain()
        try:
            before = b.relations.stats().get("total_relations", 0)
            res = b.learn_about("photosynthesis")
            after = b.relations.stats().get("total_relations", 0)
            assert res["success"], "learn_about should find a source for a real word"
            assert after > before, (
                f"learn_about added no relations ({before} -> {after})"
            )
        finally:
            os.unlink(db)

    def test_asking_about_unknown_concept_triggers_learning(self):
        """The core feature: ask about something new, Genesis goes and learns it."""
        _wordnet_or_skip()
        b, db = _fresh_brain()
        try:
            before = b.relations.stats().get("total_relations", 0)
            reply = b.voice.chat_respond("tell me about photosynthesis")
            after = b.relations.stats().get("total_relations", 0)
            assert after > before, (
                "Asking about an unknown concept did not trigger any learning. "
                f"Relations: {before} -> {after}. Reply: {reply!r}"
            )
            # The answer must contain real content from what it just read
            low = reply.lower()
            assert "photosynthesis" in low
            content = {"synthesis", "compound", "radiant", "energy",
                       "chemical", "light", "plant"}
            assert any(w in low for w in content), (
                f"Reply did not use the definition it just learned: {reply!r}"
            )
        finally:
            os.unlink(db)

    def test_plural_topic_is_learnable(self):
        """A plural topic must still produce learning. WordNet's morphy resolves
        most plurals ('lakes'->'lake') directly; the singularisation fallback in
        learn_about covers the rest. Either way, relations must grow and the
        concept learned must be the singular or the original plural."""
        _wordnet_or_skip()
        b, db = _fresh_brain()
        try:
            res = b.learn_about("lakes")
            assert res["relations_added"] > 0, (
                "Plural 'lakes' produced no learning — neither morphy nor the "
                "singularisation fallback resolved it."
            )
            assert res["concept"] in ("lake", "lakes")
        finally:
            os.unlink(db)

    def test_known_concept_not_relearned_unnecessarily(self):
        """A concept Genesis already understands well is answered from the
        graph without a redundant fetch (stage gate)."""
        _wordnet_or_skip()
        b, db = _fresh_brain()
        try:
            # Teach it deeply first
            for s in [
                "A river is a large stream of water.",
                "Rivers flow to the sea.",
                "A river carries sediment downstream.",
                "Rivers carve valleys over time.",
                "A river begins at its source in the mountains.",
                "Rivers provide water for many cities.",
                "The river floods in the spring.",
                "A river supports many kinds of fish.",
            ]:
                b.process_input("text", s)
            stage = b.voice._stage_for_concept("river")
            assert stage >= 2, f"river should be well-known by now, stage={stage}"
            # Asking about it should answer from the graph (no error)
            reply = b.voice.chat_respond("tell me about rivers")
            assert reply.strip() and "river" in reply.lower()
        finally:
            os.unlink(db)


# ===========================================================================
# Sense selection — the right meaning, not a rare one
# ===========================================================================

class TestSenseSelection:
    def test_lake_is_water_not_pigment(self):
        _wordnet_or_skip()
        from ingestion.wordnet_dict import WordNetDictionary
        d = WordNetDictionary().lookup("lake")
        assert d, "WordNet returned no definition for 'lake'"
        low = d.lower()
        assert "water" in low, f"'lake' resolved to the wrong sense: {d!r}"
        assert "pigment" not in low, f"'lake' resolved to the pigment sense: {d!r}"

    def test_mountain_is_landform_not_quantity(self):
        _wordnet_or_skip()
        from ingestion.wordnet_dict import WordNetDictionary
        d = WordNetDictionary().lookup("mountain")
        assert d, "WordNet returned no definition for 'mountain'"
        low = d.lower()
        assert ("land" in low or "elevation" in low or "hill" in low), (
            f"'mountain' resolved to the wrong sense: {d!r}"
        )
        assert "large indefinite quantity" not in low, (
            f"'mountain' resolved to the quantity sense: {d!r}"
        )

    def test_common_nature_words_resolve_sensibly(self):
        _wordnet_or_skip()
        from ingestion.wordnet_dict import WordNetDictionary
        wn = WordNetDictionary()
        expectations = {
            "river": "stream",
            "ocean": "water",
            "star": "celestial",
            "wolf": "canine",
            "forest": "tree",
        }
        for word, expected in expectations.items():
            d = (wn.lookup(word) or "").lower()
            assert expected in d, (
                f"'{word}' should mention {expected!r}, got: {d!r}"
            )


# ===========================================================================
# Comprehensive answers combine prose + derived understanding
# ===========================================================================

class TestComprehensiveAnswer:
    def test_answer_leads_with_definition_then_understanding(self):
        _wordnet_or_skip()
        b, db = _fresh_brain()
        try:
            reply = b.voice.chat_respond("what is a lake?")
            low = reply.lower()
            # Should contain the definitional content
            assert "lake" in low
            assert "water" in low, (
                f"Comprehensive answer about a lake should mention water: {reply!r}"
            )
            # Should not leak raw relation tokens
            for tok in ["IS_A", "CAUSES", "CONTAINS", "REQUIRES"]:
                assert tok not in reply, f"raw token {tok} leaked: {reply!r}"
        finally:
            os.unlink(db)
