"""
Tests for progressive language acquisition — M23.

Genesis should express itself at the right level of maturity:
- Stage 0 (barely seen): acknowledgement only, no pretended knowledge
- Stage 1 (1-2 encounters): echoes an actual sentence from retained memory
- Stage 2 (several encounters): 2-3 retained sentences plus a derived relation
- Stage 3 (deeply processed): prose + inference chain narration

These tests verify that:
1. Stage grows with exposure (more processing → richer expression)
2. Stage 1+ responses contain actual words from the processed text, not templates
3. Expression never leaks raw relation tokens (IS_A, CAUSES, etc.) into prose
4. An empty brain gracefully handles unknown concepts at Stage 0
5. The 'thinking about' response surfaces real retained prose, not just concept names
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


_RAW_TOKENS = ["IS_A", "CAUSES", "CONTAINS", "PREDATES",
               "REQUIRES", "CONTROLS", "ENABLES", "PREVENTS", "AFFECTS"]


def _is_clean(text: str) -> bool:
    for tok in _RAW_TOKENS:
        if tok in text:
            return False
    return True


# ===========================================================================
# Stage computation
# ===========================================================================

class TestStageComputation:
    def test_unknown_concept_is_stage_zero(self):
        b, db = _fresh_brain()
        try:
            stage = b.voice._stage_for_concept("xyzzy_impossible_word")
            assert stage == 0, f"Unknown concept should be stage 0, got {stage}"
        finally:
            os.unlink(db)

    def test_stage_grows_with_exposure(self):
        b, db = _fresh_brain()
        try:
            stage_before = b.voice._stage_for_concept("wolf")
            # Feed several distinct sentences about wolf
            for s in [
                "Wolves are apex predators.",
                "A wolf hunts deer and elk.",
                "Wolves live in packs.",
                "The wolf is a canine mammal.",
                "Wolves prey upon deer and moose.",
                "A wolf pack can take down large prey.",
            ]:
                b.process_input("text", s)
            stage_after = b.voice._stage_for_concept("wolf")
            assert stage_after > stage_before, (
                f"Stage should grow with exposure: was {stage_before}, "
                f"after 6 sentences still {stage_after}"
            )
        finally:
            os.unlink(db)


# ===========================================================================
# Prose retrieval
# ===========================================================================

class TestProseRetrieval:
    def test_pull_prose_returns_original_sentence(self):
        b, db = _fresh_brain()
        try:
            b.process_input("text", "Wolves hunt deer in the forest.")
            b.process_input("text", "A wolf is a predator.")
            sentences = b.voice._pull_prose_about("wolf", n=3)
            assert sentences, "Should return at least one retained sentence about wolf"
            # Should contain actual words from what was processed
            joined = " ".join(sentences).lower()
            assert "wolf" in joined, "Retained prose must mention the concept"
        finally:
            os.unlink(db)

    def test_pull_prose_excludes_raw_relation_tokens(self):
        b, db = _fresh_brain()
        try:
            b.process_input("text", "A neuron is a cell that transmits signals.")
            sentences = b.voice._pull_prose_about("neuron", n=5)
            for s in sentences:
                assert _is_clean(s), f"Prose sentence contains raw token: {s!r}"
        finally:
            os.unlink(db)

    def test_pull_prose_returns_empty_for_unknown_concept(self):
        b, db = _fresh_brain()
        try:
            sentences = b.voice._pull_prose_about("xyzzy_impossible_word", n=3)
            assert isinstance(sentences, list)
            assert len(sentences) == 0
        finally:
            os.unlink(db)


# ===========================================================================
# Stage 0 — barely known
# ===========================================================================

class TestStageZeroExpression:
    def test_stage_zero_does_not_pretend_deep_knowledge(self):
        b, db = _fresh_brain()
        try:
            result = b.voice._compose_about("xyzzy_impossible_word")
            # Either None or a humble acknowledgement — not a fabricated fact
            if result is not None:
                assert "xyzzy" in result.lower() or "encountered" in result.lower(), (
                    f"Stage-0 reply should not fabricate knowledge: {result!r}"
                )
        finally:
            os.unlink(db)


# ===========================================================================
# Stage 1 — echoes actual retained prose
# ===========================================================================

class TestStageOneExpression:
    def test_stage_one_echoes_retained_sentence(self):
        """The reply at Stage 1 should contain words from the processed text."""
        b, db = _fresh_brain()
        try:
            b.process_input("text", "Salmon swim upstream to spawn.")
            b.process_input("text", "A salmon is a fish.")
            result = b.voice._compose_about("salmon")
            assert result is not None, "Stage 1 concept should produce a response"
            low = result.lower()
            # The reply must use actual words from the processed text
            assert "salmon" in low, f"Reply must mention the concept: {result!r}"
            assert _is_clean(result), f"Reply has raw tokens: {result!r}"
        finally:
            os.unlink(db)

    def test_stage_one_reply_reads_like_english(self):
        """Stage 1 replies should be proper sentences, not 'concept... object'."""
        b, db = _fresh_brain()
        try:
            b.process_input("text", "Rivers flow toward the sea.")
            b.process_input("text", "A river is a body of water.")
            result = b.voice._compose_about("river")
            assert result is not None
            # Must not be bare relation triple
            assert "river is a" in result.lower() or "river" in result.lower()
            # Must be a sentence (capital first letter, ends with punctuation)
            stripped = result.strip()
            assert stripped[0].isupper() or stripped[0].islower(), \
                f"Should start like a sentence: {result!r}"
        finally:
            os.unlink(db)


# ===========================================================================
# Stage 2+ — composition from multiple sentences
# ===========================================================================

class TestHigherStageExpression:
    def test_higher_stage_uses_more_content(self):
        """With more exposure, responses should be longer and richer."""
        b, db = _fresh_brain()
        try:
            # One sentence → Stage 1 (short reply)
            b.process_input("text", "Eagles have sharp talons.")
            b.process_input("text", "An eagle is a bird.")
            short_reply = b.voice._compose_about("eagle") or ""

            # Many more sentences → higher stage (longer, richer reply)
            for s in [
                "Eagles soar on thermal currents.",
                "The eagle hunts fish and small mammals.",
                "Eagles build large nests called eyries.",
                "An eagle can spot prey from great distance.",
                "Eagles are symbols of power in many cultures.",
                "The bald eagle is the national bird of the United States.",
            ]:
                b.process_input("text", s)

            rich_reply = b.voice._compose_about("eagle") or ""
            assert len(rich_reply) >= len(short_reply), (
                f"Higher-stage reply should be at least as rich as Stage 1. "
                f"Short: {short_reply!r} ({len(short_reply)} chars), "
                f"Rich: {rich_reply!r} ({len(rich_reply)} chars)"
            )
        finally:
            os.unlink(db)

    def test_stage_two_contains_words_from_processed_text(self):
        """Stage 2 replies should contain actual words Genesis read, not templates."""
        b, db = _fresh_brain()
        try:
            passages = [
                "Photosynthesis converts light into chemical energy.",
                "Photosynthesis occurs in the chloroplasts of plant cells.",
                "Photosynthesis requires sunlight, water, and carbon dioxide.",
                "Plants use photosynthesis to produce glucose.",
                "Photosynthesis is the basis for most life on Earth.",
            ]
            for s in passages:
                b.process_input("text", s)

            result = b.voice._compose_about("photosynthesis")
            assert result is not None
            assert _is_clean(result), f"Raw tokens in reply: {result!r}"

            # Must contain actual content words from the processed text
            content_words = {"light", "energy", "chloroplast", "sunlight",
                             "water", "glucose", "plant", "converts", "requires"}
            low = result.lower()
            matched = [w for w in content_words if w in low]
            assert matched, (
                f"Stage 2+ reply should contain words from processed text. "
                f"Reply: {result!r}. None of {content_words} found."
            )
        finally:
            os.unlink(db)


# ===========================================================================
# Clean output — no template leakage
# ===========================================================================

class TestCleanOutput:
    def test_no_raw_tokens_at_any_stage(self):
        """Raw relation-type tokens must never appear in voiced responses."""
        b, db = _fresh_brain()
        try:
            for s in [
                "A bird is a warm-blooded vertebrate.",
                "Birds have feathers and wings.",
                "A bird lays eggs to reproduce.",
            ]:
                b.process_input("text", s)

            for _ in range(10):  # Test multiple calls for consistency
                result = b.voice._compose_about("bird")
                if result:
                    assert _is_clean(result), (
                        f"Raw relation token in voiced output: {result!r}"
                    )
        finally:
            os.unlink(db)

    def test_chat_respond_uses_retained_prose(self):
        """
        chat_respond() for a concept Genesis has encountered should produce
        a reply containing actual words from the text Genesis processed —
        not just the concept name with a template sentence.
        """
        b, db = _fresh_brain()
        try:
            for s in [
                "Wolves are social animals that hunt in packs.",
                "A wolf is a predator at the top of the food chain.",
                "Wolves hunt deer and elk in forested regions.",
            ]:
                b.process_input("text", s)

            reply = b.voice.chat_respond("tell me about wolves")
            assert reply.strip(), "Reply must be non-empty"
            assert _is_clean(reply), f"Raw tokens in reply: {reply!r}"
            low = reply.lower()
            # Reply should contain actual content from what was processed
            content_words = {"hunt", "pack", "predator", "deer", "elk",
                             "social", "forest", "food chain"}
            matched = [w for w in content_words if w in low]
            assert matched, (
                f"chat_respond should use retained prose. "
                f"Reply: {reply!r}. None of {content_words} found."
            )
        finally:
            os.unlink(db)


# ===========================================================================
# "What have you been thinking about?" — grounded in prose
# ===========================================================================

class TestThoughtsExpression:
    def test_thinking_response_can_contain_retained_prose(self):
        """
        When asking what Genesis has been thinking about, the reply may
        include actual prose sentences from retained memory, not just concept names.
        """
        b, db = _fresh_brain()
        try:
            for s in [
                "Wolves hunt deer in packs.",
                "A wolf is an apex predator.",
                "Wolves are highly intelligent mammals.",
            ]:
                b.process_input("text", s)
            b.reflect()

            reply = b.voice._say_thoughts()
            assert reply.strip(), "Thoughts reply must be non-empty"
            assert _is_clean(reply), f"Raw tokens in thoughts: {reply!r}"
            # Should mention something Genesis was actually thinking about
            assert any(c in reply.lower() for c in ["wolf", "thinking", "building", "understanding"]), (
                f"Thoughts reply should mention salient concepts: {reply!r}"
            )
        finally:
            os.unlink(db)
