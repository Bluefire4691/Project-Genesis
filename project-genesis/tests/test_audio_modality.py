"""
M35 — audio modality + source-provenance surfacing.

A synthesized WAV (known rhythm, known loudness shape) goes through the real
pipeline: structure extracted with no pretrained knowledge, findings stored
as memories and typed relations, provenance queryable with trust scores.
"""

import math
import os
import struct
import sys
import tempfile
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from orchestrator.orchestrator import Orchestrator
from processors.audio import AudioProcessor


def _brain() -> Orchestrator:
    return Orchestrator(verbose=False, db_path=tempfile.mktemp(suffix=".db"),
                        resume=False)


def _make_wav(path: str, seconds: float = 3.0, rate: int = 8000,
              beat_hz: float = 2.0) -> None:
    """Sine bursts at beat_hz (120 bpm at 2.0) with silence between."""
    n = int(seconds * rate)
    frames = []
    for i in range(n):
        t = i / rate
        in_burst = (t * beat_hz) % 1.0 < 0.25
        v = 0.7 * math.sin(2 * math.pi * 440 * t) if in_burst else 0.0
        frames.append(struct.pack("<h", int(v * 32767)))
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"".join(frames))


def test_processor_extracts_real_structure():
    path = tempfile.mktemp(suffix=".wav")
    _make_wav(path, beat_hz=2.0)          # 120 bpm ground truth
    out = AudioProcessor().process({"path": path, "label": "test beat"})
    x = out.extracted
    assert out.source == "audio"
    assert abs(x["duration_s"] - 3.0) < 0.1
    assert x["onsets"] >= 3               # bursts were detected
    assert x["regularity"] > 0.3          # periodic signal noticed
    assert x["silence_ratio"] > 0.2       # gaps between bursts noticed
    assert x["relations"], "structural observations should become triples"
    assert "test beat" in out.context


def test_non_audio_input_quietly_skipped():
    out = AudioProcessor().process("wolves hunt deer in packs")
    assert out.importance == 0.0
    assert "skipped" in out.extracted


def test_pipeline_stores_relations_and_memory():
    brain = _brain()
    path = tempfile.mktemp(suffix=".wav")
    _make_wav(path)
    before = brain.relations.stats().get("total_relations", 0)
    result = brain.process_input("audio", {"path": path, "label": "rain rhythm"})
    assert result["status"] == "processed"
    assert brain.relations.stats().get("total_relations", 0) > before, (
        "audio structure should land in the relation graph"
    )
    rels = brain.relations.query_subject("rain rhythm", min_confidence=0.3)
    assert any(r["relation"] == "IS_A" for r in rels)


def test_corrupt_audio_is_data_not_crash():
    brain = _brain()
    bad = tempfile.mktemp(suffix=".wav")
    with open(bad, "wb") as f:
        f.write(b"not a wav at all")
    result = brain.process_input("audio", bad)     # must not raise
    assert result["status"] == "processed"


def test_audio_degrades_under_throttle():
    from survival.resource_manager import CAPABILITIES, ThrottleLevel
    assert "audio" in CAPABILITIES[ThrottleLevel.NONE]
    assert "audio" not in CAPABILITIES[ThrottleLevel.MODERATE]
    assert "text" in CAPABILITIES[ThrottleLevel.EMERGENCY]   # substrate intact


# ── Source provenance + trust surfacing ───────────────────────────────────────

def test_self_model_reports_sources_with_trust():
    brain = _brain()
    brain.process_input("text", "wolves hunt deer in packs. wolves are predators.")
    sm = brain.self_model("wolves")
    assert "sources" in sm
    if sm["relation_count"] > 0:
        assert sm["sources"], "beliefs must carry provenance"
        s = sm["sources"][0]
        assert {"source", "relations", "trust"} <= set(s)
        assert 0.0 <= s["trust"] <= 1.0


def test_chat_where_did_you_learn():
    brain = _brain()
    brain.relations.add("wolves", "IS_A", "predator", confidence=0.9,
                        source_key="web:wolf_article",
                        session_id=brain.session_id)
    reply = brain.voice.chat_respond("where did you learn about wolves?")
    assert "trust" in reply.lower() and "wolf_article" in reply


def test_chat_no_source_is_honest():
    brain = _brain()
    reply = brain.voice.chat_respond("where did you learn about quasars?")
    assert "no source" in reply.lower() or "don't hold beliefs" in reply.lower()
