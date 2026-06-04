"""
The Orchestrator — Central Hypervisor.

Coordinates all layers. Doesn't process data itself — decides what gets
processed, by whom, and what to do with the results.

M1: SurvivalOS integration — resource throttle gates which processors run.
M3: InteractionLayer — expression, observation, community surface.
M4: IntegrationLayer — all available processors see every input.
    Significance is context-weighted. Cross-modal concepts are linked.
M6: Session persistence + archive tagging.
    resume=True restores cycle_count, curriculum stage, and working memory
    warm-start from last checkpoint. ArchiveStore tags every stored memory
    with significance and domain for cross-session retrieval.

The key shift in M4: the Orchestrator stops routing to one processor
and starts synthesizing across all of them. Same input, multiple views,
context determines what registers.
"""

import json
import re
import uuid
from typing import Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.types import ProcessorOutput
from processors import TextProcessor, NumericProcessor, PatternProcessor
from processors.interoception import interoception_sample
from memory.memory import MemorySystem
from memory.archive import ArchiveStore
from memory.relations import RelationGraph
from persistence.session import SessionManager
from curriculum.curriculum import CurriculumEngine
from survival import SurvivalOS
from interface import InteractionLayer
from orchestrator.integration import IntegrationLayer
from cognition.inference import InferenceEngine
from cognition.contradictions import ContradictionLog
from cognition.ethics import EthicsLens
from output.channel import OutputChannel, TextChannel
from output.voice import GenesisVoice


class Orchestrator:
    """
    The central coordinating intelligence.

    Never crashes. Every decision is logged. Every error is data.
    All processors see all input. Context determines significance.

    Parameters
    ----------
    verbose : bool
        Print per-cycle diagnostics.
    db_path : str | None
        Path to the SQLite memory DB. None = use MemorySystem default.
    resume : bool
        If True and a checkpoint exists, restore previous session state
        (cycle_count, curriculum stage, working memory warm-start).
    survival : SurvivalOS | None
        Inject a pre-built SurvivalOS (mainly for testing).
    interaction : InteractionLayer | None
        Inject a pre-built InteractionLayer (mainly for testing).
    """

    def __init__(
        self,
        verbose: bool = True,
        db_path: str | None = None,
        resume: bool = False,
        survival: SurvivalOS | None = None,
        interaction: InteractionLayer | None = None,
        channel: OutputChannel | None = None,
        working_capacity: int = 5000,
        memory_limit_mb: int = 6144,
    ):
        self.processors = {
            "text":    TextProcessor(),
            "numeric": NumericProcessor(),
            "pattern": PatternProcessor(),
        }

        # Memory system — optionally with explicit DB path and working capacity
        self.memory = (
            MemorySystem(db_path=db_path, working_capacity=working_capacity)
            if db_path else
            MemorySystem(working_capacity=working_capacity)
        )
        self.curriculum = CurriculumEngine()
        self.verbose = verbose
        self.cycle_count = 0
        self.error_count = 0
        self.log: list[str] = []

        # Unique session identifier — used by ArchiveStore for provenance
        self.session_id = str(uuid.uuid4())[:8]

        # All subsystems share the memory DB connection
        _conn = self.memory._long_term.conn
        self.archive = ArchiveStore(_conn)
        self.relations = RelationGraph(_conn)
        self.inference = InferenceEngine(self.relations)
        self.contradictions = ContradictionLog(_conn)
        self.ethics = EthicsLens(self)
        self._session_manager = SessionManager(_conn)

        # Self-authored consolidation — Genesis's reflection ("sleep") pass.
        from consolidation import ConsolidationEngine
        self.consolidation = ConsolidationEngine(self)

        # M14: Observer calibration — empirical thresholds from behavioral history.
        # Shares the memory DB connection (no extra file). Loaded first so restored
        # thresholds are active before the first cycle runs.
        from interface.observer_calibration import ObserverCalibration
        self._calibration = ObserverCalibration(_conn)

        # M18: Belief revision — evidence-weighted contradiction resolution.
        # Tracks corroboration provenance and source trust; revises confidences
        # when stronger independent evidence contradicts existing beliefs.
        from cognition.belief_revision import BeliefRevision
        self.belief_revision = BeliefRevision(_conn)

        # M19: Spreading activation — ACT-R associative retrieval.
        # When concepts are active in working memory, graph-adjacent concepts
        # receive a retrieval boost. Makes search associative, not just lexical.
        from cognition.spreading_activation import SpreadingActivation
        self.spreading_activation = SpreadingActivation(self.relations)

        # The survival RSS ceiling is set generously: Genesis is designed to
        # accumulate knowledge, and the corpus + working set legitimately grows.
        # The survival pressure exists to create selectivity of attention, not
        # to starve knowledge accumulation. Genuine runaway growth past the
        # ceiling still triggers throttling as intended.
        self.survival: SurvivalOS = (
            survival if survival is not None
            else SurvivalOS(memory_limit_mb=memory_limit_mb)
        )
        self.interaction: InteractionLayer = (
            interaction if interaction is not None
            else InteractionLayer(self.memory)
        )
        # Restore any previously calibrated Observer thresholds so the first cycle
        # benefits from accumulated behavioral history, not just hardcoded defaults.
        self._calibration.load_calibrated(self.interaction._observer)

        self.integrator = IntegrationLayer(self.memory)

        # M13: Voice output — speaks from internal state, not from LLM
        self.voice = GenesisVoice(self, channel=channel or TextChannel())

        # M17: Active curiosity directives — concepts Genesis is actively trying
        # to resolve (SOAR-style impasse→subgoal). Persisted across sessions.
        # Maps concept → prediction_error at time of registration.
        self._curiosity_directives: dict[str, float] = self._load_directives()

        # Restore previous session state if requested
        if resume:
            restored = self._session_manager.restore(self)
            if restored and self.verbose:
                print(
                    f"  [SESSION] Restored: cycle={self.cycle_count} "
                    f"stage={self.curriculum.current_stage.name} "
                    f"wm={len(self.memory.memories)} memories warm-started"
                )

    def _log(self, msg: str):
        self.log.append(msg)
        if self.verbose:
            print(f"  [{self.curriculum.current_stage.name}] {msg}")

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def process_input(self, input_type: str, data: Any) -> dict:
        """
        Main entry point. Never raises — always returns a result dict.
        """
        self.cycle_count += 1

        # Interoception: Genesis senses its own internal state periodically.
        # This runs outside the main dispatch so it doesn't inflate cycle metrics,
        # but the result is fed back through process_input as a numeric stream —
        # same processing pipeline as any external input.
        intero = interoception_sample(self)
        if intero is not None:
            try:
                self._do_process("numeric", intero)
            except Exception:
                pass  # interoception failure is not a cycle failure

        # Layer 0: resource tick
        survival_stats = self._survival_stats()
        survival_state = self.survival.tick(survival_stats)
        if self.verbose and survival_state["throttle"] != "NONE":
            self._log(
                f"⚡ Survival OS: energy={survival_state['energy']:.2f} "
                f"throttle={survival_state['throttle']} "
                f"pressure={survival_state['pressure']:.2f}"
            )

        # M3: interaction tick
        interaction_state = self.interaction.cycle(survival_stats, self.cycle_count)
        if interaction_state["is_paused"]:
            pause_reason = interaction_state.get("pause_reason", "")
            if "closed_loop" in str(pause_reason):
                # Attention fixation — not a crash, just a rut. Auto-recover and keep going.
                self._log("⚠ Attention loop detected — auto-recovering, continuing.")
                self.interaction.resume()
            else:
                # True danger (energy collapse, diversity collapse) — hard stop.
                self._log(
                    f"⏸  Paused — {pause_reason}. "
                    f"Call orchestrator.interaction.resume() to continue."
                )
                return {"status": "paused", "reason": pause_reason,
                        "cycle": self.cycle_count}

        # Drain any pending stimulus (stagnation injection or human feed)
        pending = self.interaction.next_stimulus()
        if pending is not None:
            stimulus_type, stimulus_data = pending
            self._log(f"💉 Processing injected stimulus ({stimulus_type})")
            input_type, data = stimulus_type, stimulus_data

        try:
            return self._do_process(input_type, data)
        except Exception as e:
            self.error_count += 1
            self._log(f"⚠ Orchestrator error (non-fatal): {e}")
            return {"status": "degraded", "reason": str(e), "cycle": self.cycle_count}

    # ------------------------------------------------------------------
    # M4 core: multi-processor dispatch + synthesis
    # ------------------------------------------------------------------

    def _do_process(self, input_type: str, data: Any) -> dict:
        """
        Run all available processors, synthesize via IntegrationLayer,
        store outputs with cross-modal associations.
        """
        # Determine which processors are available at current throttle
        active = self._active_processors(input_type)

        # Dispatch all active processors on the same input
        outputs: list[ProcessorOutput] = []
        for name, processor in active.items():
            output = processor.process(data)
            outputs.append(output)
            if self.verbose and output.confidence > 0.1:
                self._log(f"→ {output.source}: {output.context} "
                          f"(conf={output.confidence:.2f})")

        # Synthesize: context scoring + cross-modal detection
        synthesis = self.integrator.synthesize(outputs, primary_source=_resolve_primary(input_type, active))

        if synthesis.cross_modal_concepts and self.verbose:
            self._log(f"  🔗 Cross-modal: {synthesis.cross_modal_concepts[:5]}")

        # Curriculum eval on primary output
        if self.survival.can("curriculum"):
            eval_score = self.curriculum.evaluate_processing(synthesis.primary_output)
            self.curriculum.record_score(eval_score)
            self._log(
                f"  Eval: {eval_score:.2f} | significance: {synthesis.significance:.2f} "
                f"| context: {synthesis.context_score:.2f}"
            )
        else:
            eval_score = synthesis.significance

        # OOD detection — check before storing so we use pre-storage state
        novel = self._is_novel(synthesis)

        # M15: Prediction error — how surprising is this input given current beliefs?
        # Computed before storing so it reflects the pre-update knowledge state.
        # High error = Genesis has little/low-confidence knowledge about these concepts.
        pred_error = self.relations.prediction_error(synthesis.context_terms)

        # M17: Update curiosity directives before storing (uses pre-update graph state)
        self._update_curiosity_directives(synthesis.context_terms, pred_error)

        # Store everything if resources allow
        wm_before = len(self.memory.memories)
        if self.survival.can("memory_store"):
            stored_keys, new_contradictions = self._store_synthesis(synthesis, data, novel=novel)
            wm_delta = len(self.memory.memories) - wm_before
            if self.survival.can("logging"):
                novel_tag = " [NOVEL]" if novel else ""
                self._log(f"  💾 Stored {len(stored_keys)} key(s) Δwm={wm_delta:+d} "
                          f"pred_err={pred_error:.2f}{novel_tag}")

            # Archive significance = base significance boosted by prediction error.
            # Inputs that genuinely surprised Genesis (high pred_error) get higher
            # significance than inputs in well-known territory.
            # wm_delta is retained as a secondary modifier for structural disruption.
            boosted_sig = min(1.0,
                synthesis.significance * (1.0 + pred_error * 0.5)
                + wm_delta * 0.02
            )
            for key in stored_keys:
                self.archive.tag(
                    key=key,
                    significance=boosted_sig,
                    session_id=self.session_id,
                )

            # Update attention with cross-modal concepts first, then primary terms
            attention_terms = synthesis.cross_modal_concepts or synthesis.context_terms
            if attention_terms:
                self.memory.update_attention(attention_terms)
        else:
            stored_keys = []
            wm_delta = 0
            new_contradictions = 0
            if self.survival.can("logging"):
                self._log("  Memory storage skipped (emergency throttle)")

        # Stage advancement
        if self.survival.can("curriculum") and self.curriculum.should_advance():
            if self.curriculum.advance() and self.verbose:
                self._log(f"  🎓 ADVANCED to {self.curriculum.current_stage.name}!")

        # M13: Spontaneous expression triggered by internal signals
        expression = self._maybe_express(
            novel=novel,
            wm_delta=wm_delta,
            new_contradictions=new_contradictions,
        )

        return {
            "status": "processed",
            "output": synthesis.primary_output.extracted,
            "significance": synthesis.significance,
            "context_score": synthesis.context_score,
            "cross_modal_concepts": synthesis.cross_modal_concepts,
            "processors_run": synthesis.processors_run,
            "eval_score": eval_score,
            "stage": self.curriculum.current_stage.name,
            "cycle": self.cycle_count,
            "throttle": self.survival.resource.throttle_level.name,
            "novel": novel,
            "wm_delta": wm_delta,
            "prediction_error": pred_error,
            "expression": expression,
        }

    def _active_processors(self, input_type: str) -> dict:
        """
        Return all processors available at current throttle level.

        M1 guarantees can("text") is always True. Under heavy throttle,
        text survives last — lose breadth before losing function.
        """
        return {
            name: processor
            for name, processor in self.processors.items()
            if self.survival.can(name)
        }

    def _is_novel(self, synthesis) -> bool:
        """
        OOD detection: True if this input has no overlap with known concepts.

        Checks primary output context words against working memory keys and
        relation graph concepts. Zero overlap = novel/ungrounded input.
        """
        context_words = set(
            re.findall(r"\b[a-z]{3,}\b", synthesis.primary_output.context.lower())
        )
        if not context_words:
            return False

        # Check working memory keys
        wm_keys_text = " ".join(self.memory.memories.keys()).lower()
        wm_words = set(re.findall(r"\b[a-z]{3,}\b", wm_keys_text))
        if context_words & wm_words:
            return False

        # Check relation graph concepts (subjects and objects)
        try:
            rel_row = self._relations_conn_concepts()
            if context_words & rel_row:
                return False
        except Exception:
            pass

        return True

    def _maybe_express(
        self,
        novel: bool,
        wm_delta: int,
        new_contradictions: int = 0,
    ) -> str | None:
        """
        Trigger spontaneous voice expression if internal signals warrant it.

        Priority: novel > contradiction > inference (high delta) > attention (any delta).
        Only fires when the text channel is available (not under emergency throttle).
        The voice itself applies an additional probability gate (expression_rate).
        """
        if not self.survival.can("text"):
            return None

        # Priority: meaningful insight first, generic "novel" last.
        # "novel" produces a canned message and fires on almost everything early on.
        trigger: str | None = None
        if new_contradictions > 0:
            trigger = "contradiction"
        elif wm_delta > 2:
            trigger = "inference"
        elif wm_delta > 0:
            trigger = "attention"
        elif novel:
            trigger = "novel"

        return self.voice.express(trigger=trigger)

    def _relations_conn_concepts(self) -> set[str]:
        """Return set of all concept words currently in the relation graph."""
        cur = self.memory._long_term.conn.execute(
            "SELECT DISTINCT subject FROM relations "
            "UNION SELECT DISTINCT object FROM relations"
        )
        words: set[str] = set()
        for (concept,) in cur.fetchall():
            words.update(re.findall(r"\b[a-z]{3,}\b", concept))
        return words

    def _store_synthesis(self, synthesis, raw_data: Any, novel: bool = False) -> list[str]:
        """
        Store all processor outputs, linking cross-modal outputs by association.

        Primary output → main memory key.
        Secondary outputs → stored at their natural keys, linked to primary.
        Cross-modal associations → explicit high-strength links.
        """
        raw_str = str(raw_data) if not isinstance(raw_data, str) else raw_data
        stored_keys: list[str] = []

        # Store primary
        primary = synthesis.primary_output
        primary_content = f"{raw_str} | {json.dumps(primary.extracted, default=str)}"
        self.memory.store(
            key=primary.suggested_key,
            content=primary_content,
            context=primary.context,
            source_type=primary.source,
            relevance=synthesis.significance,
        )
        stored_keys.append(primary.suggested_key)

        # Store secondary outputs (only if confidence meaningful)
        secondary_keys: list[str] = []
        for sec in synthesis.secondary_outputs:
            if sec.confidence < 0.05:
                continue  # pure noise — not worth storing
            sec_content = f"{raw_str} | {json.dumps(sec.extracted, default=str)}"
            self.memory.store(
                key=sec.suggested_key,
                content=sec_content,
                context=sec.context,
                source_type=sec.source,
                relevance=sec.confidence * 0.6,  # secondary relevance discounted
            )
            stored_keys.append(sec.suggested_key)
            secondary_keys.append(sec.suggested_key)

        # Cross-modal association: link all stored keys from this input
        # These are different views of the same thing — strong explicit link
        all_keys = [primary.suggested_key] + secondary_keys
        if len(all_keys) > 1:
            for i, key_a in enumerate(all_keys):
                for key_b in all_keys[i + 1:]:
                    self.memory.associate(key_a, key_b, strength=0.8)

        # Archive tagging — every stored memory gets significance + domain
        for key in stored_keys:
            src = primary.source if key == primary.suggested_key else _key_source(key)
            self.archive.tag(
                key=key,
                significance=synthesis.significance,
                session_id=self.session_id,
                source_type=src,
            )

        # Relation extraction — store typed triples from text outputs.
        # M16: boost confidence when multiple processors independently confirm
        # the subject or object concept (Hawkins voting: independent columns
        # agreeing raises certainty more than one column repeating).
        votes = synthesis.processor_votes
        relations_added = 0
        for output in [primary] + synthesis.secondary_outputs:
            if output.source != "text":
                continue
            for rel in output.extracted.get("relations", []):
                subj_votes = votes.get(rel["subject"], 1)
                obj_votes  = votes.get(rel["object"],  1)
                # Each additional independent processor confirmation adds 15%
                # confidence, capped at 1.0.  Single-processor = no boost.
                vote_boost = 1.0 + 0.15 * (max(subj_votes, obj_votes) - 1)
                boosted_conf = min(1.0, rel["confidence"] * vote_boost)
                if self.relations.add(
                    subject=rel["subject"],
                    rel_type=rel["relation"],
                    obj=rel["object"],
                    confidence=boosted_conf,
                    source_key=output.suggested_key,
                    session_id=self.session_id,
                ):
                    relations_added += 1
                    self.belief_revision.record_source(
                        rel["subject"], rel["relation"], rel["object"],
                        self.session_id,
                    )

        # Contradiction scan after any new relations are added
        new_conflicts = 0
        if relations_added > 0:
            new_conflicts = self.contradictions.scan(session_id=self.session_id)
            if new_conflicts > 0 and self.survival.can("logging"):
                self._log(f"  ⚡ {new_conflicts} new contradiction(s) detected")
            # M18: evaluate contradictions and revise beliefs by evidence strength
            if new_conflicts > 0:
                revised = self.belief_revision.evaluate_and_revise(
                    session_id=self.session_id
                )
                if revised > 0 and self.survival.can("logging"):
                    self._log(f"  ✏️  {revised} belief(s) revised by evidence weight")

        return stored_keys, new_conflicts

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def fetch_knowledge(self, n_topics: int = 5, verbose: bool = True) -> dict:
        """
        Self-directed knowledge acquisition cycle.

        Genesis examines its own working memory and relation graph to
        identify what it most needs to learn (high attention, low relations),
        then fetches Wikipedia articles on those concepts and processes them.

        The feeder is created once and reused across calls so that
        already-fetched and already-failed topics are never retried.
        """
        if not hasattr(self, "_feeder") or self._feeder is None:
            from ingestion.feeder import KnowledgeFeeder
            self._feeder = KnowledgeFeeder(self)
        return self._feeder.run(n_topics=n_topics, verbose=verbose)

    def reflect(self, cycle: int = 0, top_k: int = 8) -> dict:
        """
        Run a consolidation pass — Genesis reflects on what it has processed
        and decides for itself what mattered. Returns the reflection report.
        """
        result = self.consolidation.consolidate(
            cycle=cycle or self.cycle_count, top_k=top_k
        )
        # M14: Calibrate Observer thresholds from accumulated behavioral history.
        # Runs after each reflection so calibration has the richest possible data —
        # the same history that consolidation just summarized.
        try:
            cal = self._calibration.calibrate(
                self.interaction._observer, self.cycle_count
            )
            if not cal.skipped and self.verbose:
                self._log(
                    f"  🎯 Observer calibrated: {len(cal.thresholds)} thresholds "
                    f"(confidence={cal.confidence:.2f}, "
                    f"data={cal.data_points} entries)"
                )
        except Exception:
            pass  # calibration failure never affects the reflection result
        return result

    def latest_reflection(self) -> dict | None:
        """The most recent reflection — what Genesis has been thinking about."""
        return self.consolidation.latest()

    def curiosity_report(self) -> list[dict]:
        """Show what Genesis is most curious about without fetching anything."""
        if not hasattr(self, "_feeder") or self._feeder is None:
            from ingestion.feeder import KnowledgeFeeder
            self._feeder = KnowledgeFeeder(self)
        return self._feeder.curiosity_report()

    def infer(self, concept: str) -> dict:
        """
        Run transitive inference around a concept and return what Genesis can derive.

        Stores new inferences in relation_inferences table. Returns a dict with
        all inferences involving concept as subject or object.
        """
        return self.inference.infer(concept, session_id=self.session_id)

    def save_session(self) -> None:
        """Checkpoint current state to the DB for restore on next startup."""
        self._session_manager.save(self)
        if self.verbose:
            self._log(f"💾 Session saved (cycle={self.cycle_count})")

    def query(self, question: str) -> dict:
        """Ask the system a question based on what it has learned."""
        self._log(f"❓ Query: '{question}'")

        if not self.survival.can("memory_search"):
            return {"answer": "System under resource pressure — memory search unavailable.",
                    "memories_used": 0}

        # M19: compute spreading activation from current attention before searching.
        # Concepts currently in working memory prime their graph-neighbors so that
        # associatively related memories surface even without keyword overlap.
        activation = {}
        try:
            attention = self.memory._working._context_terms
            if attention:
                sources = {t: 1.0 for t in attention[:8]}
                activation = self.spreading_activation.compute(sources)
        except Exception:
            pass

        results = self.memory.search(question, top_k=5, activation_boost=activation or None)

        # Also check relation graph for any known concept
        query_words = [w for w in question.lower().split() if len(w) >= 3]
        known_relations: list[dict] = []
        seen_concepts: set[str] = set()
        for word in query_words[:4]:
            if word in seen_concepts:
                continue
            seen_concepts.add(word)
            concept_info = self.relations.query_concept(word, min_confidence=0.6)
            as_subj = concept_info["as_subject"]
            as_obj  = concept_info["as_object"]
            if as_subj or as_obj:
                known_relations.append({
                    "concept": word,
                    "as_subject": as_subj[:3],
                    "as_object":  as_obj[:3],
                })

        if not results and not known_relations:
            return {"answer": "I don't have enough experience to answer that.",
                    "memories_used": 0, "relations": [],
                    "primed_concepts": [{"concept": c, "activation": round(a, 3)}
                                         for c, a in sorted(
                                             activation.items(),
                                             key=lambda kv: kv[1], reverse=True
                                         )[:5]]}

        memories_used = []
        for key, mem in results:
            self._log(f"    • {key}: {mem.context} (relevance: {mem.relevance:.2f})")
            memories_used.append(mem.to_dict() | {"key": key})

        if known_relations and self.verbose:
            for kr in known_relations:
                self._log(f"    ⟳ Relations for '{kr['concept']}': "
                          f"{len(kr['as_subject'])} outgoing, {len(kr['as_object'])} incoming")

        # Surface top primed concepts so callers can see what was activated
        primed = sorted(activation.items(), key=lambda kv: kv[1], reverse=True)[:5]
        if primed and self.verbose:
            self._log(f"    💡 Primed by spreading activation: "
                      f"{[c for c, _ in primed]}")

        return {
            "answer": f"Based on {len(results)} memories.",
            "memories_used": len(results),
            "relevant_memories": memories_used,
            "relations": known_relations,
            "primed_concepts": [{"concept": c, "activation": round(a, 3)}
                                 for c, a in primed],
        }

    # ------------------------------------------------------------------
    # Curriculum runner
    # ------------------------------------------------------------------

    def run_curriculum(self):
        """Run through the current stage's curriculum."""
        items = self.curriculum.get_curriculum()
        if not items:
            self._log("No curriculum items for current stage.")
            return

        stage_name = self.curriculum.current_stage.name
        print(f"\n{'='*60}")
        print(f"  STAGE: {stage_name}")
        print(f"{'='*60}")
        for i, item in enumerate(items):
            print(f"\n--- Item {i+1}/{len(items)} ---")
            self.process_input(item["type"], item["data"])
        print(f"\n  Stage {stage_name} complete.")
        print(f"  {json.dumps(self.curriculum.status(), indent=2)}")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # M17: Active Curiosity Directives (SOAR impasse → subgoal)
    # ------------------------------------------------------------------

    # Concept must have this pred_error or higher to become a directive.
    _DIRECTIVE_PRED_ERROR_MIN: float = 0.78
    # Concept is considered resolved once it has this many relations.
    _DIRECTIVE_RESOLVE_RELS: int = 3
    # Maximum simultaneous directives — keeps focus narrow.
    _MAX_DIRECTIVES: int = 10
    # Very common words that should never become directives.
    _DIRECTIVE_SKIP: frozenset = frozenset({
        "the", "and", "for", "are", "was", "has", "had", "not", "but",
        "its", "with", "this", "that", "from", "they", "will", "been",
        "have", "more", "also", "than", "one", "two", "can", "all",
    })

    def curiosity_directives(self) -> list[str]:
        """Active unresolved concepts Genesis is seeking to learn more about."""
        return list(self._curiosity_directives.keys())

    def _update_curiosity_directives(
        self, context_terms: list[str], pred_error: float
    ) -> None:
        """
        After each cycle: register high-surprise concepts as directives;
        resolve directives whose concepts have accumulated enough relations.
        """
        try:
            # Resolve existing directives that Genesis has since learned about
            resolved = []
            for concept in list(self._curiosity_directives):
                if self.relations.concept_relation_count(concept) >= self._DIRECTIVE_RESOLVE_RELS:
                    resolved.append(concept)
            for concept in resolved:
                self._curiosity_directives.pop(concept, None)

            # Register new directives from high-surprise context terms
            if (pred_error >= self._DIRECTIVE_PRED_ERROR_MIN
                    and len(self._curiosity_directives) < self._MAX_DIRECTIVES):
                for term in context_terms:
                    concept = term.strip().lower()
                    if (len(concept) >= 4
                            and concept not in self._DIRECTIVE_SKIP
                            and concept not in self._curiosity_directives
                            and len(self._curiosity_directives) < self._MAX_DIRECTIVES
                            and self.relations.concept_relation_count(concept) < self._DIRECTIVE_RESOLVE_RELS):
                        self._curiosity_directives[concept] = pred_error

            # Persist after every update
            if resolved or self._curiosity_directives:
                self._save_directives()
        except Exception:
            pass  # directive failure is never a cycle failure

    def _load_directives(self) -> dict[str, float]:
        """Load persisted curiosity directives from consolidation_state."""
        try:
            row = self.consolidation._conn.execute(
                "SELECT value FROM consolidation_state WHERE key='curiosity_directives'"
            ).fetchone()
            if row:
                import json as _json
                data = _json.loads(str(row[0])) if row[0] else {}
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def _save_directives(self) -> None:
        """Persist curiosity directives to consolidation_state."""
        try:
            import json as _json
            self.consolidation._conn.execute(
                "INSERT OR REPLACE INTO consolidation_state (key, value) VALUES (?, ?)",
                ("curiosity_directives", _json.dumps(self._curiosity_directives)),
            )
            self.consolidation._conn.commit()
        except Exception:
            pass

    def full_status(self) -> dict:
        status = {
            "cycles": self.cycle_count,
            "error_count": self.error_count,
            "session_id": self.session_id,
            "curriculum": self.curriculum.status(),
            "memory": self.memory.stats(),
            "archive": self.archive.stats(),
            "relations": self.relations.stats(),
            "inference": self.inference.stats(),
            "contradictions": self.contradictions.stats(),
            "voice": self.voice.stats(),
            "processors": list(self.processors.keys()),
        }
        status.update(self.survival.report())
        status.update(self.interaction.report())
        return status

    def _survival_stats(self) -> dict:
        curriculum_status = self.curriculum.status()
        return {
            "error_count": self.error_count,
            "cycle_count": self.cycle_count,
            "energy": self.survival.resource.energy,
            "throttle_level": int(self.survival.resource.throttle_level),
            "memories_stored": self.memory.stats().get("total_stored", 0),
            "current_stage": int(self.curriculum.current_stage),
            "max_stage": 4,
            "stage_score": curriculum_status.get("stage_scores", {}).get(
                str(self.curriculum.current_stage), 0.5
            ),
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _resolve_primary(input_type: str, active: dict) -> str:
    """Return the name of the primary processor — the one matching input_type, or text."""
    if input_type in active:
        return input_type
    return "text"


def _key_source(key: str) -> str:
    """Infer source type from a memory key prefix (e.g. 'text:', 'pattern:')."""
    for src in ("text", "numeric", "pattern"):
        if key.startswith(f"{src}:"):
            return src
    return "text"
