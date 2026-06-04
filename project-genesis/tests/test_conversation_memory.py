"""
Tests for within-session conversational memory in GenesisVoice.

Genesis tracks the thread of a conversation — not just answering in isolation
but remembering what concepts were discussed and responding to follow-up cues.
This makes conversations feel like exchanges with an entity that's following
the discussion, rather than a stateless Q&A machine.
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
        "A neuron enables signaling.",
        "Dendrites receive signals.",
        "A mammal is a vertebrate.",
        "A mammal contains hair.",
    ]:
        b.process_input("text", s)
    b.reflect()
    return b


_RAW_TOKENS = ["IS_A", "PREDATES", "REQUIRES", "CONTROLS", "CONTAINS",
               "ENABLES", "PREVENTS", "AFFECTS", "CAUSES", "text:", "_"]


def _assert_clean(reply: str):
    assert isinstance(reply, str) and reply.strip()
    for tok in _RAW_TOKENS:
        assert tok not in reply, f"raw token {tok!r} in reply: {reply!r}"
    for word in re.findall(r"[A-Za-z]+", reply):
        assert len(word) <= 20, f"mangled token {word!r} in reply: {reply!r}"


# ==================================================================
# Conversation log tracking
# ==================================================================

def test_conversation_log_starts_empty():
    b = _brain()
    assert b.voice.conversation_log() == []


def test_conversation_log_records_turns():
    b = _taught_brain()
    b.voice.chat_respond("tell me about neuron")
    log = b.voice.conversation_log()
    # Should have at least the user turn and genesis reply
    assert len(log) >= 2
    roles = [e["role"] for e in log]
    assert "user" in roles
    assert "genesis" in roles


def test_conversation_log_grows_with_exchanges():
    b = _taught_brain()
    initial_len = len(b.voice.conversation_log())
    b.voice.chat_respond("what do you know about neurons?")
    b.voice.chat_respond("what about mammals?")
    assert len(b.voice.conversation_log()) > initial_len + 2


def test_conversation_log_is_capped():
    b = _taught_brain()
    # Many exchanges
    for msg in ["hello", "tell me about neuron", "what else", "mammals?",
                "what do you know", "curious?", "and?", "more"]:
        b.voice.chat_respond(msg)
    log = b.voice.conversation_log()
    assert len(log) <= b.voice._CONVO_MAX


# ==================================================================
# Follow-up detection
# ==================================================================

def test_followup_phrases_are_detected():
    b = _taught_brain()
    phrases = ["tell me more", "go on", "and?", "what else", "interesting",
               "more about that", "continue", "elaborate"]
    for phrase in phrases:
        assert b.voice._is_followup(phrase, []), (
            f"'{phrase}' should be detected as a follow-up"
        )


def test_non_followup_phrases_are_not_detected():
    b = _taught_brain()
    phrases = ["the sky is blue", "tell me about gravity", "what is photosynthesis"]
    for phrase in phrases:
        assert not b.voice._is_followup(phrase.lower(), []), (
            f"'{phrase}' should not be detected as a follow-up"
        )


def test_concept_overlap_triggers_followup():
    """If the user mentions a concept Genesis just discussed, it's a follow-up."""
    b = _taught_brain()
    # Have Genesis say something about neuron
    b.voice.chat_respond("tell me about neuron")
    # Genesis's reply should have logged neuron
    genesis_concepts = b.voice._recent_concepts(roles={"genesis"}, turns=2)
    if "neuron" in genesis_concepts:
        # User asks about neuron again — should be follow-up
        assert b.voice._is_followup("neuron?", ["neuron"])


# ==================================================================
# Follow-up responses
# ==================================================================

def test_followup_response_is_clean():
    b = _taught_brain()
    # Seed a prior exchange about neuron
    b.voice.chat_respond("tell me about neuron")
    # Follow up
    reply = b.voice.chat_respond("tell me more")
    _assert_clean(reply)


def test_followup_response_is_nonempty():
    b = _taught_brain()
    b.voice.chat_respond("what do you know about mammals?")
    reply = b.voice.chat_respond("go on")
    assert isinstance(reply, str) and reply.strip()


# ==================================================================
# Stats
# ==================================================================

def test_stats_include_conversation_turns():
    b = _brain()
    stats_before = b.voice.stats()
    assert "conversation_turns" in stats_before
    assert stats_before["conversation_turns"] == 0

    b2 = _taught_brain()
    b2.voice.chat_respond("hello")
    stats_after = b2.voice.stats()
    assert stats_after["conversation_turns"] > 0
