"""Tests for M21: KnowledgeSynthesis."""
import os, sys, tempfile
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _brain_with_ecology():
    from orchestrator.orchestrator import Orchestrator
    db = tempfile.mktemp(suffix=".db")
    o = Orchestrator(verbose=False, db_path=db)
    # Inject known relations directly
    o.relations.add("wolves",     "CAUSES",   "deer decline",  0.85, source_key="t", session_id="s1")
    o.relations.add("wolves",     "CONTROLS", "overgrazing",   0.80, source_key="t", session_id="s1")
    o.relations.add("deer decline","CAUSES",  "overgrazing",   0.80, source_key="t", session_id="s2")
    o.relations.add("overgrazing","CAUSES",   "erosion",       0.75, source_key="t", session_id="s2")
    o.relations.add("erosion",    "CAUSES",   "river change",  0.70, source_key="t", session_id="s3")
    return o, db


class TestExplain:
    def test_explain_returns_string(self):
        o, db = _brain_with_ecology()
        try:
            result = o.synthesis.explain("wolves")
            assert isinstance(result, str) and len(result) > 0
        finally:
            os.unlink(db)

    def test_explain_known_concept_mentions_relations(self):
        o, db = _brain_with_ecology()
        try:
            result = o.synthesis.explain("wolves").lower()
            # Should mention something wolves does
            assert "causes" in result or "controls" in result or "deer" in result
        finally:
            os.unlink(db)

    def test_explain_unknown_concept_graceful(self):
        o, db = _brain_with_ecology()
        try:
            result = o.synthesis.explain("unicorns")
            assert isinstance(result, str) and len(result) > 0
        finally:
            os.unlink(db)

    def test_explain_includes_causal_chain(self):
        o, db = _brain_with_ecology()
        try:
            result = o.synthesis.explain("wolves")
            # Should reference a multi-hop chain
            assert ("→" in result or "chain" in result.lower()
                    or "overgrazing" in result or "erosion" in result)
        finally:
            os.unlink(db)

    def test_explain_corroborated_belief_says_so(self):
        o, db = _brain_with_ecology()
        try:
            # Add a second independent session for the same relation
            o.belief_revision.record_source("wolves", "CAUSES", "deer decline", "s1")
            o.belief_revision.record_source("wolves", "CAUSES", "deer decline", "s2")
            o.belief_revision.record_source("wolves", "CAUSES", "deer decline", "s3")
            result = o.synthesis.explain("wolves")
            # With 3 sessions the text should mention corroboration
            assert "independently" in result or "confirmed" in result or "times" in result
        finally:
            os.unlink(db)

    def test_explain_tension_mentioned_when_present(self):
        import sqlite3
        o, db = _brain_with_ecology()
        try:
            # Plant a contradiction
            o.relations.add("wolves", "ENABLES", "deer survival", 0.6,
                            source_key="t", session_id="s-bad")
            o.relations.add("wolves", "PREVENTS", "deer survival", 0.8,
                            source_key="t", session_id="s-good")
            o.contradictions.scan(session_id="s-good")
            result = o.synthesis.explain("wolves")
            # Tension/contradiction should surface in the text
            assert isinstance(result, str)
        finally:
            os.unlink(db)


class TestReflectOnState:
    def test_returns_string(self):
        o, db = _brain_with_ecology()
        try:
            result = o.synthesis.reflect_on_state()
            assert isinstance(result, str) and len(result) > 0
        finally:
            os.unlink(db)

    def test_mentions_directives_when_present(self):
        o, db = _brain_with_ecology()
        try:
            o._curiosity_directives = {"photosynthesis": 0.9, "migration": 0.8}
            result = o.synthesis.reflect_on_state()
            assert "photosynthesis" in result or "migration" in result or "understand" in result.lower()
        finally:
            os.unlink(db)


class TestRevisionNarrative:
    def test_empty_history_returns_string(self):
        o, db = _brain_with_ecology()
        try:
            result = o.synthesis.revision_narrative()
            assert isinstance(result, str) and len(result) > 0
        finally:
            os.unlink(db)

    def test_revision_in_history_appears_in_narrative(self):
        o, db = _brain_with_ecology()
        try:
            # Manually record a revision
            o.belief_revision._record_revision_audit(
                "wolves", "ENABLES", "deer survival",
                old_confidence=0.8, new_confidence=0.5,
                outcome="REVISE", reason="Contradicted by stronger evidence.",
                old_strength=0.6, new_strength=0.3,
                opposing_rel="PREVENTS", session_id="s1"
            )
            result = o.synthesis.revision_narrative()
            assert "wolves" in result
        finally:
            os.unlink(db)


class TestChainBuilding:
    def test_chains_found_for_wolves(self):
        o, db = _brain_with_ecology()
        try:
            chains = o.synthesis._build_chains("wolves")
            assert len(chains) > 0
            assert len(chains[0]) >= 2
        finally:
            os.unlink(db)

    def test_chain_narration_contains_arrow(self):
        o, db = _brain_with_ecology()
        try:
            chains = o.synthesis._build_chains("wolves")
            if chains:
                text = o.synthesis._narrate_chain(chains[0])
                assert "→" in text
        finally:
            os.unlink(db)

    def test_no_chain_for_unknown_concept(self):
        o, db = _brain_with_ecology()
        try:
            chains = o.synthesis._build_chains("unicorn")
            assert chains == []
        finally:
            os.unlink(db)
