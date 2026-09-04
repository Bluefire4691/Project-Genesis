"""
Tests for M32 GenesisVoiceLLM — local LLM expression layer.

All tests mock the HTTP call so they run without a local LLM server.
They verify:
1. State context is built from Genesis's real internal state
2. Prompt includes conversation history
3. respond() returns text from the local LLM response
4. respond() returns "" when the server is unreachable
5. _extract_keywords strips stop words
6. _interpret_drives produces the right notes
7. Orchestrator always wires voice_llm
"""
import json
import os
import sys
import tempfile
import types
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from output.voice_llm import GenesisVoiceLLM, _extract_keywords, _interpret_drives


def _brain():
    from orchestrator.orchestrator import Orchestrator
    db = tempfile.mktemp(suffix=".db")
    b = Orchestrator(verbose=False, db_path=db)
    return b, db


def _cleanup(db):
    if os.path.exists(db):
        os.unlink(db)


def _mock_ok_response(text: str):
    """Minimal mock of a successful OpenAI-format chat completion response."""
    resp = mock.MagicMock()
    resp.status_code = 200
    resp.raise_for_status = mock.MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": text}}]
    }
    return resp


# ── State context ─────────────────────────────────────────────────────────────

class TestStateContext:
    def test_context_has_state_header(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            ctx = v._build_state_context("hello")
            assert "DRIVES" in ctx or "KNOWLEDGE" in ctx or "no state" in ctx
        finally:
            _cleanup(db)

    def test_context_includes_concept_knowledge(self):
        b, db = _brain()
        try:
            b.relations.add("wolves", "IS_A", "predator", 0.9)
            b.relations.add("wolves", "CONTROLS", "deer", 0.85)
            v = GenesisVoiceLLM(b)
            ctx = v._build_state_context("tell me about wolves")
            assert "wolves" in ctx.lower()
            assert "UNDERSTANDING" in ctx
        finally:
            _cleanup(db)

    def test_unknown_concept_marked_unknown(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            ctx = v._build_state_context("what about phlogiston")
            # Either marked unknown or simply absent from context
            assert "unknown" in ctx.lower() or "phlogiston" not in ctx.lower()
        finally:
            _cleanup(db)


# ── Prompt construction ───────────────────────────────────────────────────────

class TestPromptConstruction:
    def test_prompt_includes_user_message(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            prompt = v._build_prompt([], "what are you thinking?", "STATE")
            assert "what are you thinking?" in prompt
        finally:
            _cleanup(db)

    def test_prompt_includes_prior_turns(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            history = [
                {"role": "user",    "text": "hello",      "concepts": set()},
                {"role": "genesis", "text": "Processing.", "concepts": set()},
            ]
            prompt = v._build_prompt(history, "tell me more", "STATE")
            assert "hello" in prompt
            assert "Processing." in prompt
        finally:
            _cleanup(db)

    def test_prompt_ends_with_genesis_marker(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            prompt = v._build_prompt([], "test", "STATE")
            assert prompt.strip().endswith("Genesis:")
        finally:
            _cleanup(db)


# ── Local LLM call ────────────────────────────────────────────────────────────

class TestCallLocal:
    def test_returns_text_on_success(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            with mock.patch("requests.post",
                            return_value=_mock_ok_response("Rivers have changed.")):
                result = v._call_local("some prompt")
            assert result == "Rivers have changed."
        finally:
            _cleanup(db)

    def test_returns_empty_on_connection_error(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            with mock.patch("requests.post",
                            side_effect=ConnectionError("refused")):
                result = v._call_local("some prompt")
            assert result == ""
        finally:
            _cleanup(db)

    def test_returns_empty_on_http_error(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            err_resp = mock.MagicMock()
            err_resp.raise_for_status.side_effect = Exception("404")
            with mock.patch("requests.post", return_value=err_resp):
                result = v._call_local("some prompt")
            assert result == ""
        finally:
            _cleanup(db)


# ── respond() integration ─────────────────────────────────────────────────────

class TestRespond:
    def test_respond_returns_llm_text(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            with mock.patch("requests.post",
                            return_value=_mock_ok_response("Wolves control deer.")):
                reply = v.respond("tell me about wolves", [])
            assert "Wolves control deer." == reply
        finally:
            _cleanup(db)

    def test_respond_returns_empty_on_failure(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            with mock.patch("requests.post",
                            side_effect=ConnectionError("no server")):
                reply = v.respond("hello", [])
            assert reply == ""
        finally:
            _cleanup(db)


# ── Orchestrator wiring ───────────────────────────────────────────────────────

class TestOrchestratorWiring:
    def test_voice_llm_always_present(self):
        b, db = _brain()
        try:
            assert hasattr(b, "voice_llm")
            assert isinstance(b.voice_llm, GenesisVoiceLLM)
        finally:
            _cleanup(db)

    def test_url_and_model_from_env(self, monkeypatch):
        monkeypatch.setenv("GENESIS_LLM_URL",   "http://192.168.1.5:11434/v1")
        monkeypatch.setenv("GENESIS_LLM_MODEL",  "phi3:mini")
        b, db = _brain()
        try:
            v = b.voice_llm
            assert v._url   == "http://192.168.1.5:11434/v1"
            assert v._model == "phi3:mini"
        finally:
            _cleanup(db)


# ── Helpers ───────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_extract_keywords_removes_stopwords(self):
        kws = _extract_keywords("what do you know about wolves")
        assert "what" not in kws
        assert "you"  not in kws
        assert "wolves" in kws

    def test_extract_keywords_lowercases(self):
        kws = _extract_keywords("Wolves CONTROL Deer")
        assert "wolves" in kws
        assert "control" in kws
        assert "deer" in kws

    def test_interpret_drives_balanced(self):
        d = {"hunger": 0.2, "frustration": 0.1,
             "anticipation": 0.3, "boredom": 0.1, "dissonance": 0.1}
        assert _interpret_drives(d) == "drives balanced"

    def test_interpret_drives_high_hunger(self):
        d = {"hunger": 0.8, "frustration": 0.1,
             "anticipation": 0.3, "boredom": 0.1, "dissonance": 0.1}
        result = _interpret_drives(d)
        assert "input" in result or "appetite" in result

    def test_interpret_drives_multiple_pressures(self):
        d = {"hunger": 0.8, "frustration": 0.7,
             "anticipation": 0.2, "boredom": 0.1, "dissonance": 0.1}
        result = _interpret_drives(d)
        assert ";" in result  # multiple notes joined
