"""
Tests for LLMTextProcessor — the falsification-test extractor (board 0.3).

Every test here runs WITHOUT a live model. The HTTP path is either forced
offline or replaced by an injected `transport` callable, so the suite is
green on a machine that has never seen llama-server.

What is covered:
  1. Entity canonicalisation and the rejection rules (the crux of 0.3)
  2. The v1 garbage triples, verbatim, must be rejected
  3. RELATION_TYPES mapping — nothing outside the graph vocabulary escapes
  4. Confidence clamping
  5. The never-raises contract, including a transport that explodes
  6. Offline / unreachable degradation returns a valid ProcessorOutput
  7. ProcessorOutput shape parity with TextProcessor
  8. No regex fallback leaks relations into the LLM arm
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from memory.relations import RELATION_TYPES
from processors.text import TextProcessor
from processors.llm_text import (
    LLMTextProcessor,
    MAX_RELATIONS,
    _RELATION_ALIASES,
    _clamp_confidence,
    _load_json,
    canonicalize_entity,
    is_fragment,
    map_relation,
)
from utils.types import ProcessorOutput


# ======================================================================
# Helpers
# ======================================================================

def _transport(payload: str):
    """Return a transport callable that always answers with `payload`."""
    def _call(system_prompt: str, user_prompt: str) -> str:
        assert "JSON" in system_prompt or "json" in system_prompt.lower()
        assert user_prompt
        return payload
    return _call


def _proc(payload: str) -> LLMTextProcessor:
    return LLMTextProcessor(transport=_transport(payload))


TEXT = "Wolves hunt elk in the northern valleys, and elk browse willow."


# ======================================================================
# 1 — Canonicalisation
# ======================================================================

@pytest.mark.parametrize("raw,expected", [
    ("Wolves", "wolves"),
    ("  THE Wolves  ", "wolves"),
    ("the atmospheric carbon dioxide", "atmospheric carbon dioxide"),
    ("Soil Erosion.", "soil erosion"),
    ("a wolf's territory", "wolf territory"),
    ("river channel change", "river channel change"),
    ("overgrazing", "overgrazing"),          # -ing nominalisations are concepts
    ("global warming", "global warming"),
])
def test_canonicalize_accepts_noun_phrases(raw, expected):
    assert canonicalize_entity(raw) == expected


@pytest.mark.parametrize("raw", [
    "",
    "   ",
    None,
    123,
    "of",                                        # bare preposition
    "the",                                       # bare article
    "42 7",                                      # numerals only
    "symbol that represents",                    # clause
    "wolves that were reintroduced in 1995",     # clause, too long
    "is a large carnivore",                      # copula
    "a system for measuring the distance between",   # >4 words
    "responsible for",                           # trailing preposition
    "using smell",                               # verb phrase
    "represents",                                # finite verb
    "commonly called",                           # participle tail
    "widely used",                               # participle tail
])
def test_canonicalize_rejects_fragments(raw):
    assert canonicalize_entity(raw) == ""
    if isinstance(raw, str):
        assert is_fragment(raw)


def test_canonicalize_enforces_four_word_limit():
    assert canonicalize_entity("long term atmospheric carbon") == \
        "long term atmospheric carbon"
    assert canonicalize_entity("long term atmospheric carbon dioxide") == ""
    # leading article does not count against the limit
    assert canonicalize_entity("the long term atmospheric carbon") == \
        "long term atmospheric carbon"


def test_dangling_function_words_are_repaired_not_rejected():
    """
    A dangling preposition on an otherwise unambiguous name is stripped;
    a phrase whose head is not a noun is dropped whole. The distinction is
    deliberate — see canonicalize_entity's docstring.
    """
    assert canonicalize_entity("the deer populations in") == "deer populations"
    assert canonicalize_entity("responsible for") == ""


def test_v1_garbage_triples_are_rejected():
    """
    The actual failure cases from the live v1 database:
        dogs   PREDATES "using smell"
        number IS_A     "symbol that represents"
    Both must die at canonicalisation, or no chain can ever route through them.
    """
    payload = """{"triples": [
        {"subject": "dogs", "relation": "PREDATES",
         "object": "using smell", "confidence": 0.9},
        {"subject": "number", "relation": "IS_A",
         "object": "symbol that represents", "confidence": 0.9},
        {"subject": "deer populations in", "relation": "CAUSES",
         "object": "overgrazing", "confidence": 0.8}
    ]}"""
    p = _proc(payload)
    out = p.process(TEXT)
    rels = out.extracted["relations"]
    # Both v1 garbage triples are gone; the repairable one survives, canonical.
    assert p.rejected_entity == 2
    assert rels == [{"subject": "deer populations", "relation": "CAUSES",
                     "object": "overgrazing", "confidence": 0.8}]


# ======================================================================
# 2 — Relation vocabulary
# ======================================================================

def test_every_alias_maps_into_relation_types():
    for alias, target in _RELATION_ALIASES.items():
        assert target in RELATION_TYPES, f"{alias} → {target} is not a v1 type"


@pytest.mark.parametrize("raw,expected", [
    ("CAUSES", "CAUSES"),
    ("causes", "CAUSES"),
    ("leads to", "CAUSES"),
    ("results_in", "CAUSES"),
    ("is-a", "IS_A"),
    ("IS A", "IS_A"),
    ("part of", "IS_A"),
    ("preys on", "PREDATES"),
    ("depends on", "REQUIRES"),
    ("regulates", "CONTROLS"),
    ("inhibits", "PREVENTS"),
    ("composed of", "CONTAINS"),
    ("influences", "AFFECTS"),
])
def test_map_relation_known(raw, expected):
    assert map_relation(raw) == expected


@pytest.mark.parametrize("raw", [
    "SIMILAR_TO", "LOCATED_IN", "BORN_IN", "HAPPENED_BEFORE",
    "caused_by",           # would need the triple reversed — dropped, not flipped
    "", None, 42, "???",
])
def test_map_relation_unknown_is_dropped(raw):
    assert map_relation(raw) is None


def test_invented_relation_type_never_reaches_output():
    payload = """{"triples": [
        {"subject": "wolves", "relation": "LOCATED_IN",
         "object": "yellowstone", "confidence": 0.9},
        {"subject": "wolves", "relation": "PREDATES",
         "object": "elk", "confidence": 0.9}
    ]}"""
    p = _proc(payload)
    rels = p.process(TEXT).extracted["relations"]
    assert [r["relation"] for r in rels] == ["PREDATES"]
    assert p.rejected_relation == 1
    assert all(r["relation"] in RELATION_TYPES for r in rels)


# ======================================================================
# 3 — Confidence
# ======================================================================

@pytest.mark.parametrize("raw,expected", [
    (0.8, 0.8),
    (1.0, 0.95),        # ceiling
    (0.0, 0.10),        # floor
    (-5, 0.10),
    (2.0, 0.10),        # 2% — a model answering in percent
    (85, 0.85),
    (None, 0.70),       # default
    ("high", 0.70),
])
def test_confidence_clamping(raw, expected):
    assert _clamp_confidence(raw) == pytest.approx(expected, abs=1e-6)


def test_relation_confidences_are_in_band():
    payload = """{"triples": [
        {"subject": "wolves", "relation": "PREDATES", "object": "elk",
         "confidence": 3.0}
    ]}"""
    rels = _proc(payload).process(TEXT).extracted["relations"]
    assert 0.0 <= rels[0]["confidence"] <= 1.0


# ======================================================================
# 4 — Never raises
# ======================================================================

@pytest.mark.parametrize("data", ["", None, 42, {"weird": [1, 2, 3]}, "x" * 20000])
def test_never_raises_on_any_input(data):
    p = LLMTextProcessor(offline=True)
    out = p.process(data)
    assert isinstance(out, ProcessorOutput)
    assert out.source == "text"


def test_never_raises_when_transport_explodes():
    def boom(_system, _user):
        raise RuntimeError("model on fire")

    p = LLMTextProcessor(transport=boom)
    out = p.process(TEXT)
    assert out.source == "text"
    assert out.extracted["relations"] == []
    assert out.extracted["llm_available"] is False
    assert "model on fire" in out.extracted["error"]


@pytest.mark.parametrize("payload", [
    "not json at all",
    "",
    "{",
    '{"triples": "nonsense"}',
    '{"triples": [null, 3, "x"]}',
    '{"other_key": 1}',
])
def test_malformed_model_output_degrades_quietly(payload):
    out = _proc(payload).process(TEXT)
    assert out.extracted["relations"] == []
    assert out.source == "text"


def test_fenced_and_prefixed_json_is_recovered():
    payload = (
        "Sure! Here are the triples:\n```json\n"
        '{"triples": [{"subject": "wolves", "relation": "PREDATES", '
        '"object": "elk", "confidence": 0.9}]}\n```'
    )
    rels = _proc(payload).process(TEXT).extracted["relations"]
    assert rels == [{"subject": "wolves", "relation": "PREDATES",
                     "object": "elk", "confidence": 0.9}]


def test_load_json_returns_none_for_junk():
    assert _load_json("no json here") is None
    assert _load_json("") is None
    assert _load_json(None) is None


# ======================================================================
# 5 — Offline degradation
# ======================================================================

def test_offline_returns_degraded_but_valid_output():
    p = LLMTextProcessor(offline=True)
    out = p.process("Wolves hunt elk and control their population.")
    assert out.extracted["relations"] == []
    assert out.extracted["llm_available"] is False
    assert out.extracted["error"] == "offline"
    assert out.extracted["keywords"]          # surface features still work
    assert out.importance > 0
    assert out.confidence <= 0.3
    assert p.is_available() is False


def test_env_var_forces_offline(monkeypatch):
    monkeypatch.setenv("GENESIS_LLM_OFFLINE", "1")
    p = LLMTextProcessor()
    assert p.offline is True
    assert p.process(TEXT).extracted["relations"] == []


def test_unreachable_server_is_latched_not_retried(monkeypatch):
    """One connection failure must not cost a timeout on every later document."""
    calls = {"n": 0}

    def exploding_post(*_a, **_kw):
        calls["n"] += 1
        raise OSError("connection refused")

    import requests
    monkeypatch.setattr(requests, "post", exploding_post)

    p = LLMTextProcessor(url="http://127.0.0.1:9/v1/chat/completions")
    for _ in range(5):
        assert p.process(TEXT).extracted["relations"] == []
    assert calls["n"] == 1, "server should be probed once, then treated as down"
    assert p.diagnostics()["unreachable"] is True


def test_endpoint_normalisation():
    for given in ("http://localhost:8080",
                  "http://localhost:8080/",
                  "http://localhost:8080/v1",
                  "http://localhost:8080/v1/chat/completions"):
        assert LLMTextProcessor(url=given)._url == \
            "http://localhost:8080/v1/chat/completions"


# ======================================================================
# 6 — Shape contract vs TextProcessor
# ======================================================================

def test_processor_output_shape_matches_text_processor():
    """
    The orchestrator must not be able to tell the two apart. Same keys,
    same types; the LLM processor may only ADD diagnostic keys.
    """
    payload = """{"triples": [{"subject": "wolves", "relation": "PREDATES",
                               "object": "elk", "confidence": 0.9}]}"""
    a = TextProcessor().process(TEXT)
    b = _proc(payload).process(TEXT)

    assert a.source == b.source == "text"
    assert set(a.extracted) <= set(b.extracted)
    for key in a.extracted:
        assert type(b.extracted[key]) is type(a.extracted[key]), key

    extra = set(b.extracted) - set(a.extracted)
    assert extra == {"extractor", "llm_available", "llm_model",
                     "llm_truncated_chars", "llm_dropped_relations"}

    for out in (a, b):
        assert isinstance(out.importance, float) and 0.0 <= out.importance <= 1.0
        assert isinstance(out.confidence, float) and 0.0 <= out.confidence <= 1.0
        assert out.suggested_key.startswith("text:")
        assert isinstance(out.context, str)


def test_triple_shape_matches_orchestrator_expectations():
    """orchestrator._do_process reads exactly these four keys."""
    payload = """{"triples": [{"subject": "the Wolves", "relation": "predates",
                               "object": "Elk", "confidence": 0.88}]}"""
    rels = _proc(payload).process(TEXT).extracted["relations"]
    assert len(rels) == 1
    r = rels[0]
    assert set(r) == {"subject", "relation", "object", "confidence"}
    assert isinstance(r["subject"], str) and isinstance(r["object"], str)
    assert r["subject"] == "wolves" and r["object"] == "elk"
    assert r["relation"] in RELATION_TYPES
    assert isinstance(r["confidence"], float)


def test_name_is_text_so_the_swap_is_a_one_liner():
    assert LLMTextProcessor.name == TextProcessor.name == "text"


# ======================================================================
# 7 — Extraction behaviour
# ======================================================================

def test_no_regex_fallback_leaks_relations():
    """
    Arm B must never quietly fall back to the thing under test. A sentence
    the regex table matches happily must still yield nothing when the model
    is unavailable.
    """
    sentence = "Overgrazing causes soil erosion and wolves control deer populations."
    assert TextProcessor().process(sentence).extracted["relations"], \
        "sanity: the regex arm does extract from this sentence"
    assert LLMTextProcessor(offline=True).process(sentence).extracted["relations"] == []


def test_duplicate_triples_are_collapsed():
    payload = """{"triples": [
        {"subject": "wolves", "relation": "PREDATES", "object": "elk", "confidence": 0.9},
        {"subject": "The wolves", "relation": "preys on", "object": "Elk", "confidence": 0.7}
    ]}"""
    rels = _proc(payload).process(TEXT).extracted["relations"]
    assert len(rels) == 1


def test_self_loops_are_dropped():
    payload = """{"triples": [
        {"subject": "wolves", "relation": "IS_A", "object": "the wolves", "confidence": 0.9}
    ]}"""
    assert _proc(payload).process(TEXT).extracted["relations"] == []


def test_relations_are_capped_like_text_processor():
    triples = ",".join(
        f'{{"subject": "concept {i}", "relation": "CAUSES", '
        f'"object": "outcome {i}", "confidence": 0.8}}'
        for i in range(15)
    )
    p = _proc('{"triples": [' + triples + "]}")
    out = p.process(TEXT)
    assert len(out.extracted["relations"]) == MAX_RELATIONS
    assert out.extracted["llm_dropped_relations"] == 15 - MAX_RELATIONS


def test_bare_triple_object_is_tolerated():
    payload = ('{"subject": "wolves", "relation": "PREDATES", '
               '"object": "elk", "confidence": 0.9}')
    rels = _proc(payload).process(TEXT).extracted["relations"]
    assert len(rels) == 1


def test_empty_input_is_not_a_failure():
    out = _proc('{"triples": []}').process("")
    assert out.extracted["relations"] == []
    assert out.extracted["llm_available"] is True
    assert "error" not in out.extracted


def test_diagnostics_counters():
    payload = """{"triples": [
        {"subject": "wolves", "relation": "PREDATES", "object": "elk", "confidence": 0.9},
        {"subject": "using smell", "relation": "IS_A", "object": "sense", "confidence": 0.5},
        {"subject": "wolves", "relation": "LIVES_IN", "object": "forest", "confidence": 0.5}
    ]}"""
    p = _proc(payload)
    p.process(TEXT)
    d = p.diagnostics()
    assert d["calls"] == 1
    assert d["triples_seen"] == 3
    assert d["triples_kept"] == 1
    assert d["rejected_entity"] == 1
    assert d["rejected_relation"] == 1
    assert d["failures"] == 0


# ======================================================================
# 8 — End-to-end through the graph (still no model)
# ======================================================================

def test_extracted_triples_are_accepted_by_the_relation_graph(tmp_path):
    """
    Canonical output must survive RelationGraph.add() — which silently
    rejects unknown types, empty ends and self-loops — and then be
    chainable by the existing InferenceEngine.
    """
    import sqlite3
    from memory.relations import RelationGraph
    from cognition.inference import InferenceEngine

    conn = sqlite3.connect(str(tmp_path / "t.db"))
    conn.row_factory = sqlite3.Row
    graph = RelationGraph(conn)
    engine = InferenceEngine(graph)

    payload = """{"triples": [
        {"subject": "wolves", "relation": "CONTROLS", "object": "elk", "confidence": 0.9},
        {"subject": "elk", "relation": "CAUSES", "object": "overgrazing", "confidence": 0.9},
        {"subject": "overgrazing", "relation": "CAUSES", "object": "soil erosion", "confidence": 0.9}
    ]}"""
    for rel in _proc(payload).process(TEXT).extracted["relations"]:
        assert graph.add(rel["subject"], rel["relation"], rel["object"],
                         rel["confidence"], session_id="test")

    assert engine.run(session_id="test") > 0
    inferred = {(i["subject"], i["object"]) for i in engine.top_inferences(limit=50)}
    assert ("wolves", "overgrazing") in inferred      # 2-hop, never stated
    conn.close()
