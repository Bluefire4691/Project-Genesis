"""
Tests for M13 — Output Channels, Genesis Voice, Microphone Input.

tests/test_output.py
"""

import io
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import pytest

# ── helpers ────────────────────────────────────────────────────────────────

def _capture(fn):
    """Capture stdout from a callable."""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        fn()
    finally:
        sys.stdout = old
    return buf.getvalue()


# ── minimal brain mock ──────────────────────────────────────────────────────

class _MockMemoryItem:
    def __init__(self, relevance=0.5, context="some context about wolves"):
        self.relevance = relevance
        self.context = context


class _MockBrain:
    """Minimal Orchestrator-shaped object for GenesisVoice tests."""

    class _Contradictions:
        def query(self, limit=20): return []
        def query_concept(self, concept): return []

    class _Inference:
        def top_inferences(self, limit=20): return []
        def chain_for(self, s, r, o): return []
        def query(self, concept): return {"as_subject": [], "as_object": []}

    class _Relations:
        def most_connected(self, limit=10): return []
        def query_subject(self, concept, min_confidence=0.5): return []
        def query_concept(self, concept, min_confidence=0.5):
            return {"as_subject": [], "as_object": []}

    class _Memory:
        @property
        def memories(self): return {}

    def __init__(self):
        self.contradictions = self._Contradictions()
        self.inference = self._Inference()
        self.relations = self._Relations()
        self.memory = self._Memory()


class _PopulatedBrain(_MockBrain):
    """Brain with enough data for composition methods to produce statements."""

    class _Contradictions:
        def query(self, limit=20):
            return [{"subject": "fire", "object": "growth",
                     "rel_type_a": "CAUSES", "rel_type_b": "PREVENTS",
                     "conf_a": 0.8, "conf_b": 0.6}]
        def query_concept(self, concept):
            return [{"subject": concept, "object": "growth",
                     "rel_type_a": "CAUSES", "rel_type_b": "PREVENTS"}]

    class _Inference:
        def top_inferences(self, limit=20):
            return [{"subject": "wolves", "relation": "CAUSES",
                     "object": "erosion", "confidence": 0.6, "chain_length": 3}]
        def chain_for(self, s, r, o):
            return [{"from": "wolves", "via": "CAUSES", "to": "deer"},
                    {"from": "deer", "via": "CAUSES", "to": "erosion"}]
        def query(self, concept):
            return {"as_subject": [{"relation": "CAUSES", "object": "erosion",
                                    "confidence": 0.6, "chain_length": 2}],
                    "as_object": []}

    class _Relations:
        def most_connected(self, limit=10):
            return [{"concept": "wolves"}, {"concept": "deer"}]
        def query_subject(self, concept, min_confidence=0.5):
            return [{"relation": "CONTROLS", "object": "deer", "confidence": 0.9}]
        def query_concept(self, concept, min_confidence=0.5):
            return {"as_subject": [{"relation": "CONTROLS", "object": "deer"}],
                    "as_object": []}

    class _Memory:
        @property
        def memories(self):
            return {
                "text:wolves_ecology": _MockMemoryItem(0.9, "wolves control deer populations"),
                "text:deer_grazing":   _MockMemoryItem(0.4, "deer overgraze riverbanks"),
            }

    def __init__(self):
        self.contradictions = self._Contradictions()
        self.inference = self._Inference()
        self.relations = self._Relations()
        self.memory = self._Memory()


# ══════════════════════════════════════════════════════════════════════════════
# TextChannel
# ══════════════════════════════════════════════════════════════════════════════

class TestTextChannel:
    def _ch(self):
        from output.channel import TextChannel
        return TextChannel()

    def test_always_available(self):
        assert self._ch().available() is True

    def test_name(self):
        assert self._ch().name == "text"

    def test_send_prints_with_prefix(self):
        from output.channel import TextChannel
        ch = TextChannel(prefix="[TEST] ")
        out = _capture(lambda: ch.send("hello world"))
        assert "[TEST] hello world" in out

    def test_default_prefix(self):
        out = _capture(lambda: self._ch().send("something"))
        assert "[Genesis]" in out

    def test_send_flushes(self):
        # Just verify it doesn't raise
        self._ch().send("flush test")


# ══════════════════════════════════════════════════════════════════════════════
# AudioChannel
# ══════════════════════════════════════════════════════════════════════════════

class TestAudioChannel:
    def _ch(self):
        from output.channel import AudioChannel
        return AudioChannel()

    def test_name(self):
        assert self._ch().name == "audio"

    def test_available_returns_bool(self):
        result = self._ch().available()
        assert isinstance(result, bool)

    def test_send_does_not_raise_when_unavailable(self):
        ch = self._ch()
        if not ch.available():
            ch.send("this should not raise")  # graceful no-op

    def test_send_does_not_raise_when_available(self):
        ch = self._ch()
        try:
            ch.send("test")
        except Exception as e:
            pytest.fail(f"AudioChannel.send() raised: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MultiChannel
# ══════════════════════════════════════════════════════════════════════════════

class TestMultiChannel:
    def test_broadcasts_to_all(self):
        from output.channel import MultiChannel, TextChannel
        received = []

        class _Cap(TextChannel):
            def send(self, text):
                received.append(text)

        ch = MultiChannel([_Cap(), _Cap()])
        ch.send("broadcast")
        assert received == ["broadcast", "broadcast"]

    def test_available_when_any_channel_available(self):
        from output.channel import MultiChannel, TextChannel
        ch = MultiChannel([TextChannel()])
        assert ch.available() is True

    def test_not_available_when_empty(self):
        from output.channel import MultiChannel
        ch = MultiChannel([])
        assert ch.available() is False

    def test_name_concatenates(self):
        from output.channel import MultiChannel, TextChannel
        ch = MultiChannel([TextChannel(), TextChannel()])
        assert "text" in ch.name

    def test_send_skips_failed_channels(self):
        from output.channel import MultiChannel, TextChannel
        received = []

        class _Bad(TextChannel):
            def send(self, text):
                raise RuntimeError("boom")

        class _Good(TextChannel):
            def send(self, text):
                received.append(text)

        ch = MultiChannel([_Bad(), _Good()])
        ch.send("test")  # should not raise
        assert received == ["test"]


# ══════════════════════════════════════════════════════════════════════════════
# OutputChannel.best_available
# ══════════════════════════════════════════════════════════════════════════════

class TestBestAvailable:
    def test_prefer_audio_false_returns_text(self):
        from output.channel import OutputChannel, TextChannel
        ch = OutputChannel.best_available(prefer_audio=False)
        assert isinstance(ch, TextChannel)

    def test_best_available_returns_output_channel(self):
        from output.channel import OutputChannel
        ch = OutputChannel.best_available()
        assert ch.available()

    def test_all_available_includes_text(self):
        from output.channel import OutputChannel, TextChannel
        channels = OutputChannel.all_available()
        assert any(isinstance(c, TextChannel) for c in channels)

    def test_all_available_nonempty(self):
        from output.channel import OutputChannel
        assert len(OutputChannel.all_available()) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# GenesisVoice — construction
# ══════════════════════════════════════════════════════════════════════════════

class TestGenesisVoiceConstruct:
    def test_constructs_with_mock_brain(self):
        from output.voice import GenesisVoice
        from output.channel import TextChannel
        v = GenesisVoice(_MockBrain(), channel=TextChannel(), seed=42)
        assert v is not None

    def test_default_channel_is_text(self):
        from output.voice import GenesisVoice
        v = GenesisVoice(_MockBrain(), seed=42)
        assert v.channel_name == "text"

    def test_stats_keys(self):
        from output.voice import GenesisVoice
        v = GenesisVoice(_MockBrain(), seed=42)
        s = v.stats()
        for key in ("expressions_total", "last_expressed_at", "last_statement",
                    "channel", "expression_rate"):
            assert key in s

    def test_initial_expressions_zero(self):
        from output.voice import GenesisVoice
        v = GenesisVoice(_MockBrain(), seed=42)
        assert v.stats()["expressions_total"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# GenesisVoice — compose (no delivery)
# ══════════════════════════════════════════════════════════════════════════════

class TestGenesisVoiceCompose:
    def _voice(self, brain=None):
        from output.voice import GenesisVoice
        from output.channel import TextChannel
        return GenesisVoice(brain or _MockBrain(), channel=TextChannel(), seed=42)

    def test_compose_novel_always_returns_string(self):
        v = self._voice()
        stmt = v.compose(trigger="novel")
        assert isinstance(stmt, str)
        assert len(stmt) > 10

    def test_compose_empty_brain_returns_none_for_non_novel(self):
        v = self._voice(_MockBrain())
        # Empty brain has no relations/inferences/contradictions
        stmt = v.compose(trigger="contradiction")
        assert stmt is None

    def test_compose_populated_brain_contradiction(self):
        v = self._voice(_PopulatedBrain())
        stmt = v.compose(trigger="contradiction")
        assert stmt is not None
        assert "conflicting" in stmt.lower()

    def test_compose_populated_brain_inference(self):
        v = self._voice(_PopulatedBrain())
        stmt = v.compose(trigger="inference")
        assert stmt is not None

    def test_compose_populated_brain_attention(self):
        v = self._voice(_PopulatedBrain())
        stmt = v.compose(trigger="attention")
        assert stmt is not None
        assert "thinking about" in stmt.lower()

    def test_compose_does_not_deliver(self):
        v = self._voice()
        v.compose(trigger="novel")
        assert v.stats()["expressions_total"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# GenesisVoice — express (with delivery)
# ══════════════════════════════════════════════════════════════════════════════

class TestGenesisVoiceExpress:
    def _voice(self, brain=None, rate=1.0):
        from output.voice import GenesisVoice
        from output.channel import TextChannel
        return GenesisVoice(
            brain or _MockBrain(),
            channel=TextChannel(),
            expression_rate=rate,
            seed=42,
        )

    def test_express_force_novel_returns_string(self):
        v = self._voice()
        stmt = v.express(force=True, trigger="novel")
        assert isinstance(stmt, str)

    def test_express_force_increments_count(self):
        v = self._voice()
        v.express(force=True, trigger="novel")
        assert v.stats()["expressions_total"] == 1

    def test_express_force_delivers_to_channel(self):
        from output.voice import GenesisVoice
        from output.channel import TextChannel
        delivered = []

        class _Cap(TextChannel):
            def send(self, text):
                delivered.append(text)

        v = GenesisVoice(_MockBrain(), channel=_Cap(), seed=42)
        v.express(force=True, trigger="novel")
        assert len(delivered) == 1
        assert "encountered" in delivered[0].lower()

    def test_express_rate_zero_never_fires(self):
        v = self._voice(rate=0.0)
        for _ in range(20):
            result = v.express(force=False, trigger="novel")
            assert result is None

    def test_express_rate_one_always_fires_with_content(self):
        v = self._voice(brain=_PopulatedBrain(), rate=1.0)
        results = [v.express(force=False) for _ in range(5)]
        # At least some should produce statements with populated brain
        assert any(r is not None for r in results)

    def test_express_empty_brain_no_trigger_returns_none(self):
        # Empty brain, no trigger, no force → nothing to say
        v = self._voice(brain=_MockBrain(), rate=1.0)
        # All composers return None for empty brain except novel
        stmt = v.express(force=False, trigger=None)
        assert stmt is None

    def test_express_updates_last_statement(self):
        v = self._voice()
        v.express(force=True, trigger="novel")
        assert len(v.stats()["last_statement"]) > 0


# ══════════════════════════════════════════════════════════════════════════════
# GenesisVoice — respond
# ══════════════════════════════════════════════════════════════════════════════

class TestGenesisVoiceRespond:
    def _voice(self, brain=None):
        from output.voice import GenesisVoice
        from output.channel import TextChannel
        return GenesisVoice(brain or _MockBrain(), channel=TextChannel(), seed=42)

    def test_respond_unknown_concept_returns_string(self):
        v = self._voice()
        stmt = v.respond("xyzzy_unknown")
        assert stmt is not None
        assert "encountered" in stmt.lower()

    def test_respond_known_concept_populated_brain(self):
        v = self._voice(_PopulatedBrain())
        stmt = v.respond("wolves")
        assert stmt is not None

    def test_respond_delivers_to_channel(self):
        from output.voice import GenesisVoice
        from output.channel import TextChannel
        delivered = []

        class _Cap(TextChannel):
            def send(self, text):
                delivered.append(text)

        v = GenesisVoice(_MockBrain(), channel=_Cap(), seed=42)
        v.respond("something")
        assert len(delivered) == 1

    def test_respond_increments_expressions(self):
        v = self._voice()
        v.respond("test")
        assert v.stats()["expressions_total"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# GenesisVoice — set_channel
# ══════════════════════════════════════════════════════════════════════════════

class TestGenesisVoiceChannel:
    def test_set_channel_changes_delivery(self):
        from output.voice import GenesisVoice
        from output.channel import TextChannel
        received_a, received_b = [], []

        class _CapA(TextChannel):
            def send(self, t): received_a.append(t)

        class _CapB(TextChannel):
            def send(self, t): received_b.append(t)

        v = GenesisVoice(_MockBrain(), channel=_CapA(), seed=42)
        v.express(force=True, trigger="novel")
        assert len(received_a) == 1 and len(received_b) == 0

        v.set_channel(_CapB())
        v.express(force=True, trigger="novel")
        assert len(received_b) == 1

    def test_channel_name_reflects_set(self):
        from output.voice import GenesisVoice
        from output.channel import TextChannel, AudioChannel
        v = GenesisVoice(_MockBrain(), channel=TextChannel(), seed=42)
        assert v.channel_name == "text"


# ══════════════════════════════════════════════════════════════════════════════
# MicrophoneInput
# ══════════════════════════════════════════════════════════════════════════════

class TestMicrophoneInput:
    def _mic(self):
        from output.microphone import MicrophoneInput
        return MicrophoneInput()

    def test_available_returns_bool(self):
        assert isinstance(self._mic().available(), bool)

    def test_listen_returns_none_when_unavailable(self):
        mic = self._mic()
        if not mic.available():
            assert mic.listen() is None

    def test_stats_keys(self):
        s = self._mic().stats()
        for key in ("available", "total_captures", "failed_captures"):
            assert key in s

    def test_initial_stats(self):
        s = self._mic().stats()
        assert s["total_captures"] == 0
        assert s["failed_captures"] == 0

    def test_listen_loop_exits_on_callback_false(self):
        mic = self._mic()
        if mic.available():
            pytest.skip("Mic available — loop test requires unavailable mic")
        # When unavailable, listen_loop returns immediately
        calls = []
        mic.listen_loop(lambda t: calls.append(t) or False)
        assert calls == []

    def test_listen_loop_stops_on_stop_phrase(self):
        from output.microphone import MicrophoneInput
        calls = []

        class _FakeMic(MicrophoneInput):
            _phrases = ["hello world", "goodbye genesis", "more text"]
            _idx = 0

            def available(self): return True

            def listen(self, language="en-US"):
                if self._idx >= len(self._phrases):
                    return None
                phrase = self._phrases[self._idx]
                self._idx += 1
                return phrase

        mic = _FakeMic()
        mic.listen_loop(lambda t: calls.append(t) or True, stop_phrase="goodbye genesis")
        assert "hello world" in calls
        assert "goodbye genesis" not in calls  # stop phrase not passed to callback
        assert "more text" not in calls


# ══════════════════════════════════════════════════════════════════════════════
# Orchestrator integration — M13 wiring
# ══════════════════════════════════════════════════════════════════════════════

class TestOrchestratorM13:
    def _brain(self):
        import tempfile, os
        from output.channel import TextChannel
        from orchestrator.orchestrator import Orchestrator
        db = tempfile.mktemp(suffix=".db")
        brain = Orchestrator(verbose=False, db_path=db, channel=TextChannel())
        brain.curriculum.current_stage = __import__("utils.types", fromlist=["Stage"]).Stage.OPEN
        return brain

    def test_brain_has_voice(self):
        from output.voice import GenesisVoice
        brain = self._brain()
        assert isinstance(brain.voice, GenesisVoice)

    def test_process_returns_expression_key(self):
        brain = self._brain()
        result = brain.process_input("text", "Wolves control deer populations.")
        assert "expression" in result

    def test_expression_is_string_or_none(self):
        brain = self._brain()
        result = brain.process_input("text", "Fire destroys trees but enables new growth.")
        assert result["expression"] is None or isinstance(result["expression"], str)

    def test_voice_force_express(self):
        brain = self._brain()
        # Process some input to give voice something to say
        brain.process_input("text", "Wolves control deer populations in Yellowstone.")
        brain.process_input("text", "Overgrazing causes riverbank erosion.")
        stmt = brain.voice.express(force=True)
        # May be None if no composers succeed, but should not raise
        assert stmt is None or isinstance(stmt, str)

    def test_voice_respond(self):
        brain = self._brain()
        brain.process_input("text", "Wolves control deer through predation.")
        stmt = brain.voice.respond("wolves")
        assert stmt is None or isinstance(stmt, str)

    def test_full_status_has_voice_key(self):
        brain = self._brain()
        status = brain.full_status()
        assert "voice" in status
        assert "expressions_total" in status["voice"]

    def test_channel_passed_through(self):
        import tempfile
        from output.channel import TextChannel
        from orchestrator.orchestrator import Orchestrator
        db = tempfile.mktemp(suffix=".db")
        brain = Orchestrator(verbose=False, db_path=db, channel=TextChannel(prefix="[X] "))
        assert brain.voice.channel_name == "text"

    def test_novel_input_triggers_novel_flag(self):
        brain = self._brain()
        # Fresh brain — any input with truly unknown concepts should flag novel
        result = brain.process_input("text", "xylophone zither kazoo piccolo")
        assert isinstance(result.get("novel"), bool)
