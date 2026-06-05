"""
Regression tests for DEF-001 — survival throttle must not disable learning.

The bug (see docs/STATE_OF_PROJECT.md): loading a knowledge corpus burns several
seconds of CPU, which the ResourceManager charged to the next cognitive tick as
`cpu_pressure = 1.0`, collapsing energy to 0 and forcing EMERGENCY throttle. Under
EMERGENCY, `can("memory_store")` is False, so relation extraction silently
stopped — Genesis could not learn what the user asked about.

These tests assert the user-observable property directly: a transient CPU spike
must not stop learning, and a whole session of on-demand learning must keep
growing the graph. They run the real pipeline with no mocks — exactly the layer
that was missing and let DEF-001 through a green suite.
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


class TestThrottleDoesNotKillLearning:
    def test_single_cpu_spike_does_not_force_emergency(self):
        """A one-tick CPU spike must not, by itself, drive EMERGENCY throttle.
        This is the unit-level guard for DEF-001's root cause."""
        from survival.resource_manager import ResourceManager, ThrottleLevel
        rm = ResourceManager()
        # Warm up to a rested state: at rest the per-tick CPU delta is tiny, so
        # EMA energy climbs back up. Reset the CPU baseline each tick so we model
        # genuine rest rather than the process's own startup cost.
        import resource as _r
        for _ in range(12):
            rm._last_cpu_s = (_r.getrusage(_r.RUSAGE_SELF).ru_utime
                              + _r.getrusage(_r.RUSAGE_SELF).ru_stime)
            rm.tick()
        rested = rm.throttle_level
        assert rested <= ThrottleLevel.LIGHT, (
            f"Could not reach a rested state at all (throttle={rested.name})."
        )

        # Inject a single massive one-off CPU spike (a corpus load) by rewinding
        # the CPU accounting so the next tick sees a ~5000 ms delta.
        rm._last_cpu_s -= 5.0
        rm.tick()
        assert rm.throttle_level != ThrottleLevel.EMERGENCY, (
            "A single transient CPU spike collapsed the system to EMERGENCY — "
            "the DEF-001 failure mode. Energy smoothing is not working."
        )

        # And it must recover after the spike passes.
        for _ in range(12):
            rm._last_cpu_s = (_r.getrusage(_r.RUSAGE_SELF).ru_utime
                              + _r.getrusage(_r.RUSAGE_SELF).ru_stime)
            rm.tick()
        assert rm.throttle_level <= ThrottleLevel.LIGHT, (
            "Throttle did not recover after a transient spike passed."
        )

    def test_memory_store_stays_available_through_a_learning_session(self):
        """The behaviour the user cares about: ask about several new topics in
        one session and every one must actually be learned (relations grow)."""
        _wordnet_or_skip()
        b, db = _fresh_brain()
        try:
            topics = ["photosynthesis", "lake", "gravity", "volcano",
                      "glacier", "river", "mountain"]
            learned = 0
            for t in topics:
                before = b.relations.stats().get("total_relations", 0)
                res = b.learn_about(t)
                after = b.relations.stats().get("total_relations", 0)
                if after > before and res["success"]:
                    learned += 1
            # Allow one or two topics to legitimately add nothing new (overlap),
            # but the session as a whole must clearly keep learning.
            assert learned >= len(topics) - 1, (
                f"Only {learned}/{len(topics)} topics were learned in one "
                f"session. The survival throttle is still suppressing learning "
                f"(DEF-001 regression)."
            )
            # The system must never be stuck in EMERGENCY at the end.
            assert b.survival.resource.throttle_level.name != "EMERGENCY"
        finally:
            os.unlink(db)

    def test_asking_about_new_topics_in_conversation_keeps_learning(self):
        """End-to-end through the conversation layer, the way a user hits it."""
        _wordnet_or_skip()
        b, db = _fresh_brain()
        try:
            questions = [
                "tell me about photosynthesis",
                "what is a lake?",
                "explain gravity",
                "tell me about volcanoes",
            ]
            grew_count = 0
            for q in questions:
                before = b.relations.stats().get("total_relations", 0)
                reply = b.voice.chat_respond(q)
                after = b.relations.stats().get("total_relations", 0)
                assert "couldn't find a source" not in reply.lower(), (
                    f"Genesis claimed it couldn't find a source for {q!r} while "
                    f"throttled — DEF-001 regression. Reply: {reply!r}"
                )
                if after > before:
                    grew_count += 1
            assert grew_count >= len(questions) - 1, (
                f"Conversational learning stalled: only {grew_count}/"
                f"{len(questions)} questions grew the graph."
            )
        finally:
            os.unlink(db)
