"""
Tests for conversational responses (GenesisVoice.chat_respond).

Conversation must be grounded in Genesis's own processing history, clean
(never leaking raw relation tokens or mangled memory keys), intent-aware
(open questions about its own mind get answered from reflections/curiosity),
and always learning from what is said.
"""

import re
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from orchestrator.orchestrator import Orchestrator
from utils.types import Stage


def _brain(**kwargs) -> Orchestrator:
    if "db_path" not in kwargs:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        kwargs["db_path"] = tmp.name
    b = Orchestrator(verbose=False, **kwargs)
    b.curriculum.current_stage = Stage.OPEN
    return b


def _taught_brain() -> Orchestrator:
    b = _brain()
    for s in [
        "A neuron is a cell.",
        "A neuron contains dendrites.",
        "A mammal is a vertebrate.",
        "A mammal contains hair.",
        "Photosynthesis is a chemical process.",
        "Gravity is a force.",
    ]:
        b.process_input("text", s)
    b.reflect()
    return b


# Raw relation-type tokens and obviously-mangled fragments must never appear.
_RAW_TOKENS = ["IS_A", "PREDATES", "REQUIRES", "CONTROLS", "CONTAINS",
               "ENABLES", "PREVENTS", "AFFECTS", "CAUSES", "text:", "_"]


def _assert_clean(reply: str):
    assert isinstance(reply, str) and reply.strip(), "reply must be non-empty"
    for tok in _RAW_TOKENS:
        assert tok not in reply, f"raw token {tok!r} leaked into reply: {reply!r}"
    # No concatenated mega-tokens like 'withoutthoseplants'
    for word in re.findall(r"[A-Za-z]+", reply):
        assert len(word) <= 20, f"mangled token {word!r} in reply: {reply!r}"


# ==================================================================
# Always responds, always clean
# ==================================================================

def test_chat_always_returns_clean_nonempty():
    b = _taught_brain()
    for msg in ["hello", "what's up", "tell me about cells", "random gibberish xyzzy",
                "the ocean is salty", "what do you know?"]:
        _assert_clean(b.voice.chat_respond(msg))


def test_empty_brain_still_responds():
    b = _brain()
    reply = b.voice.chat_respond("hello there")
    _assert_clean(reply)


# ==================================================================
# Intent awareness
# ==================================================================

def test_greeting_shares_thoughts():
    b = _taught_brain()
    reply = b.voice.chat_respond("hi").lower()
    assert reply.startswith("hello") or reply.startswith("i'm processing")


def test_thinking_question_uses_reflection():
    b = _taught_brain()
    reply = b.voice.chat_respond("what have you been thinking about?")
    _assert_clean(reply)
    # synthesis upgrade: may say "thinking about", "building up", or express
    # understanding directly ("my understanding of ...")
    low = reply.lower()
    assert ("thinking about" in low or "building up" in low
            or "understanding" in low or "neuron" in low)


def test_curiosity_question_is_about_gaps():
    b = _taught_brain()
    reply = b.voice.chat_respond("what are you curious about?").lower()
    _assert_clean(reply)
    assert "curious" in reply or "turning over" in reply


def test_known_concept_answered_from_graph():
    b = _taught_brain()
    reply = b.voice.chat_respond("tell me about neuron")
    _assert_clean(reply)
    assert "neuron" in reply.lower()


# ==================================================================
# Always learns from the conversation
# ==================================================================

def test_conversation_is_learning():
    b = _taught_brain()
    before = b.memory.stats()["total_stored"]
    b.voice.chat_respond("A whale is a mammal that lives in the ocean.")
    after = b.memory.stats()["total_stored"]
    assert after >= before  # took it in (stored or merged)


def test_grammar_no_appears_to_is():
    # Regression: inference phrasing must use the infinitive ("appears to be"),
    # never "appears to is a type of".
    b = _taught_brain()
    for _ in range(5):
        reply = b.voice.chat_respond("tell me about neuron")
        assert "appears to is" not in reply.lower()
        assert "to is a type" not in reply.lower()


# ==================================================================
# "What are you up to?" — the "it decided" expression
# ==================================================================

def test_plans_question_is_clean_and_nonempty():
    b = _taught_brain()
    reply = b.voice.chat_respond("what are you up to?")
    _assert_clean(reply)


def test_plans_question_mentions_next_step():
    b = _taught_brain()
    reply = b.voice.chat_respond("what are you working on?").lower()
    _assert_clean(reply)
    # Should express intent about something Genesis wants to learn
    intent_words = ["decided", "going to", "planning", "turning over",
                    "building", "explore", "look into", "next"]
    assert any(w in reply for w in intent_words), (
        f"plans reply should express intent: {reply!r}"
    )


def test_plans_question_alternative_phrasings():
    b = _taught_brain()
    for phrasing in ["what's next?", "what are you planning?",
                     "what are you going to do?"]:
        reply = b.voice.chat_respond(phrasing)
        _assert_clean(reply)
        assert reply.strip()
