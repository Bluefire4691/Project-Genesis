"""
Tests for M32 GenesisVoiceLLM — LLM expression layer.

These tests use a mocked Anthropic client so they run without a live API key.
They verify:
1. Tool definitions are well-formed
2. Tool execution calls the right brain methods
3. State context builder includes drive and knowledge data
4. respond() returns the LLM text when no tool calls needed
5. respond() handles a tool-call round correctly
6. Falls back gracefully when client unavailable
7. Orchestrator wires voice_llm (key present → object, no key → None)
"""
import json
import os
import sys
import tempfile
import types
import unittest.mock as mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from output.voice_llm import GenesisVoiceLLM, _interpret_drives


def _brain():
    from orchestrator.orchestrator import Orchestrator
    db = tempfile.mktemp(suffix=".db")
    b = Orchestrator(verbose=False, db_path=db)
    return b, db


def _cleanup(db):
    if os.path.exists(db):
        os.unlink(db)


def _make_text_block(text: str):
    """Minimal mock of an Anthropic TextBlock."""
    b = types.SimpleNamespace()
    b.type = "text"
    b.text = text
    return b


def _make_tool_use_block(name: str, args: dict, tool_id: str = "tu_1"):
    b = types.SimpleNamespace()
    b.type = "tool_use"
    b.name = name
    b.input = args
    b.id = tool_id
    return b


def _make_response(content, stop_reason="end_turn"):
    r = types.SimpleNamespace()
    r.content = content
    r.stop_reason = stop_reason
    return r


# ── Tool definitions ──────────────────────────────────────────────────────────

class TestToolDefinitions:
    def test_four_tools_defined(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            tools = v._tool_definitions()
            assert len(tools) == 4
        finally:
            _cleanup(db)

    def test_tool_names(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            names = {t["name"] for t in v._tool_definitions()}
            assert names == {"understand", "recall", "browse", "drives"}
        finally:
            _cleanup(db)

    def test_all_tools_have_input_schema(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            for t in v._tool_definitions():
                assert "input_schema" in t
                assert "type" in t["input_schema"]
        finally:
            _cleanup(db)


# ── Tool execution ────────────────────────────────────────────────────────────

class TestToolExecution:
    def test_understand_returns_dict_with_verdict(self):
        b, db = _brain()
        try:
            b.relations.add("wolves", "IS_A", "predator", 0.9)
            v = GenesisVoiceLLM(b)
            result = v._tool_understand("wolves")
            assert "verdict" in result
            assert "relation_count" in result
        finally:
            _cleanup(db)

    def test_recall_returns_passages(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            result = v._tool_recall("wolves")
            assert "passages" in result
            assert isinstance(result["passages"], list)
        finally:
            _cleanup(db)

    def test_drives_returns_dominant(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            result = v._tool_drives()
            assert "dominant" in result or "error" in result
        finally:
            _cleanup(db)

    def test_unknown_tool_returns_error(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            result = v._execute_tool("nonexistent_tool", {})
            assert "error" in result
        finally:
            _cleanup(db)


# ── State context ─────────────────────────────────────────────────────────────

class TestStateContext:
    def test_context_contains_genesis_header(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            ctx = v._build_state_context("hello")
            assert "GENESIS INTERNAL STATE" in ctx
        finally:
            _cleanup(db)

    def test_context_contains_knowledge_summary(self):
        b, db = _brain()
        try:
            b.relations.add("wolves", "CONTROLS", "deer", 0.8)
            v = GenesisVoiceLLM(b)
            ctx = v._build_state_context("tell me about wolves")
            assert "relation" in ctx.lower() or "knowledge" in ctx.lower()
        finally:
            _cleanup(db)


# ── respond() with mocked client ─────────────────────────────────────────────

class TestRespond:
    def test_respond_returns_text_on_end_turn(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            mock_client = mock.MagicMock()
            mock_client.messages.create.return_value = _make_response(
                [_make_text_block("Thinking about rivers lately.")],
                stop_reason="end_turn",
            )
            v._client = mock_client

            reply = v.respond("what are you thinking about?", [])
            assert reply == "Thinking about rivers lately."
        finally:
            _cleanup(db)

    def test_respond_handles_tool_round(self):
        """respond() executes tool call then returns text on second round."""
        b, db = _brain()
        try:
            b.relations.add("wolves", "IS_A", "predator", 0.9)
            v = GenesisVoiceLLM(b)
            mock_client = mock.MagicMock()

            tool_response = _make_response(
                [_make_tool_use_block("understand", {"concept": "wolves"})],
                stop_reason="tool_use",
            )
            final_response = _make_response(
                [_make_text_block("Wolves are predators — I have that clearly.")],
                stop_reason="end_turn",
            )
            mock_client.messages.create.side_effect = [tool_response, final_response]
            v._client = mock_client

            reply = v.respond("what do you know about wolves?", [])
            assert "wolves" in reply.lower() or "predator" in reply.lower()
            assert mock_client.messages.create.call_count == 2
        finally:
            _cleanup(db)

    def test_respond_returns_empty_when_no_client(self):
        b, db = _brain()
        try:
            v = GenesisVoiceLLM(b)
            v._client = None
            # Mock _get_client to return None
            v._get_client = lambda: None
            reply = v.respond("hello", [])
            assert reply == ""
        finally:
            _cleanup(db)


# ── Orchestrator wiring ───────────────────────────────────────────────────────

class TestOrchestratorWiring:
    def test_voice_llm_present_when_key_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
        b, db = _brain()
        try:
            assert hasattr(b, "voice_llm")
            assert b.voice_llm is not None
            assert isinstance(b.voice_llm, GenesisVoiceLLM)
        finally:
            _cleanup(db)

    def test_voice_llm_none_when_no_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        b, db = _brain()
        try:
            assert b.voice_llm is None
        finally:
            _cleanup(db)


# ── Drive interpretation ──────────────────────────────────────────────────────

class TestDriveInterpretation:
    def test_balanced_drives_no_notes(self):
        d = {"hunger": 0.2, "frustration": 0.1,
             "anticipation": 0.3, "boredom": 0.1, "dissonance": 0.1}
        assert _interpret_drives(d) == "drives balanced"

    def test_high_hunger_described(self):
        d = {"hunger": 0.8, "frustration": 0.1,
             "anticipation": 0.3, "boredom": 0.1, "dissonance": 0.1}
        result = _interpret_drives(d)
        assert "appetite" in result or "input" in result

    def test_multiple_pressures_joined(self):
        d = {"hunger": 0.8, "frustration": 0.7,
             "anticipation": 0.2, "boredom": 0.1, "dissonance": 0.1}
        result = _interpret_drives(d)
        assert "|" in result or ";" in result
