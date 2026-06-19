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

        # M20: Autonomous cognitive loop — Genesis runs between interactions.
        # Not started automatically; call start_autonomous() to activate.
        from cognition.autonomous_loop import AutonomousLoop
        self.autonomous = AutonomousLoop(self, verbose=verbose)

        # M21: Knowledge synthesis — express understanding as language from
        # the graph, not from templates. Traverses actual relation chains.
        from cognition.knowledge_synthesis import KnowledgeSynthesis
        self.synthesis = KnowledgeSynthesis(self)

        # M22: Pattern transfer — structural analog detection across domains.
        # Concepts with the same relation-type fingerprint play the same role
        # regardless of domain (wolves ≅ lions, deer ≅ gazelles).
        from cognition.pattern_transfer import PatternTransfer
        self.pattern_transfer = PatternTransfer(self.relations, _conn)

        # M30: Hypothesis engine — Genesis's first generative organ. Produces
        # falsifiable predictions it authored itself (structural analogy,
        # contradiction moderation, chain extension), then tests them against
        # later evidence. Conjecture, then seek the evidence that decides.
        from cognition.hypothesis import HypothesisEngine
        self.hypotheses = HypothesisEngine(self)

        # M30.2: Research proposal — assembles gaps, analogs, contradictions, and
        # open hypotheses into a first-person research direction. A document
        # Genesis authors from its own state, not retrieved from any input.
        from cognition.research_proposal import ResearchProposal
        self.research = ResearchProposal(self)
        # Drafts a proposal every Nth reflection (not every one — a research
        # direction shouldn't churn faster than understanding moves).
        self._proposal_every = 5
        self._reflection_count = 0

        # M31: Inference Programs — declarative if-then rules Genesis authors
        # by mining recurrent chain patterns in its own graph. Unlike M10's
        # hard-coded bridge rules, M31 programs are empirically discovered,
        # stored as named artifacts, and tracked for accuracy. Two instances
        # that process different texts will write different rules — this is
        # accumulated individuality expressed as program logic.
        from cognition.inference_programs import InferenceProgramEngine
        self.programs = InferenceProgramEngine(self)

        # M27: Self-model — Genesis knows what it knows. A callable, read-only
        # view over its own knowledge state: brain.self_model("wolves") returns
        # coverage, confidence, contested beliefs, and an honest verdict tier
        # (unknown/sparse/partial/solid). The architectural answer to
        # Dunning-Kruger: something now represents "I don't know this."
        from cognition.self_model import SelfModel
        self.self_model = SelfModel(self)

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

        # M32: Local LLM expression layer — a small edge model as Genesis's mouth.
        # Knowledge stays in the graph; the model turns internal state into speech.
        # Always instantiated; respond() returns "" if no local server is running,
        # and chat_respond falls back to the template voice silently.
        from output.voice_llm import GenesisVoiceLLM
        self.voice_llm = GenesisVoiceLLM(self)

        # M17: Active curiosity directives — concepts Genesis is actively trying
        # to resolve (SOAR-style impasse→subgoal). Persisted across sessions.
        # Maps concept → prediction_error at time of registration.
        self._curiosity_directives: dict[str, float] = self._load_directives()

        # M26: Drive system — internal biological-analog pressure signals.
        # Five drives (hunger/frustration/anticipation/boredom/dissonance) that
        # update each cognitive cycle and influence topic selection, diversity,
        # and reflection timing. Restored before the first cycle so Genesis
        # wakes with the same internal state it had when it stopped.
        from survival.drives import DriveSystem
        self.drives = DriveSystem(_conn)
        self.drives.restore()

        # M33: Metaplasticity — adaptive learning rate from prediction-error history.
        # The learning rate is not fixed: it rises when Genesis is stuck or surprised
        # (making it receptive to change) and falls when knowledge is stable (protecting
        # solid beliefs). Propagates to relations.set_plasticity() each cycle.
        from cognition.metaplasticity import MetaplasticityEngine
        self.metaplasticity = MetaplasticityEngine(self)
        self.metaplasticity.restore()

        # Tracks the cycle at which reflection was last triggered by drives
        # so reflect_sooner fires at most once per 20 cycles, not every cycle.
        self._last_reflect_cycle: int = 0

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
            except Exception as exc:
                self.survival.resilience.error_log.log("interoception", exc)

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
            result = self._do_process(input_type, data)
        except Exception as e:
            self.error_count += 1
            self._log(f"⚠ Orchestrator error (non-fatal): {e}")
            return {"status": "degraded", "reason": str(e), "cycle": self.cycle_count}

        # M34: Seed drive post-cycle behavior selection (subsumption).
        # seed_action() returns: alarm | rest | explore | consolidate | idle
        try:
            hints = self.drives.behavioral_hints()
            seed_act = hints.get("seed_action", "idle")

            if seed_act == "rest":
                # REST: trigger consolidation if it hasn't run recently.
                # Shorter cooldown than the M26 dissonance trigger (10 vs 20 cycles)
                # because REST means sustained low wanting — not just one bad cycle.
                if (self.cycle_count - self._last_reflect_cycle) >= 10:
                    self.reflect()
                    self._last_reflect_cycle = self.cycle_count
            elif seed_act in ("explore", "idle"):
                # EXPLORE: also honour the M26 dissonance-based reflect trigger
                # at the normal 20-cycle cadence so dissonance still resolves.
                if (self.cycle_count - self._last_reflect_cycle) >= 20:
                    if hints.get("reflect_sooner"):
                        self.reflect()
                        self._last_reflect_cycle = self.cycle_count
            # "alarm" defers to SurvivalOS throttling (already in effect).
            # "consolidate" is a soft signal — no forced reflect; the next
            # REST cycle will handle it.
        except Exception as exc:
            self.survival.resilience.error_log.log("drives.seed_action", exc)

        return result

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

        # M33: Update metaplasticity from this cycle's error signal.
        # Propagates the new plasticity to relations.set_plasticity() so all
        # subsequent add() calls this cycle use the correct learning rate.
        try:
            self.metaplasticity.update(pred_error)
        except Exception as exc:
            self.survival.resilience.error_log.log("metaplasticity.update", exc)

        # M17: Update curiosity directives before storing (uses pre-update graph state)
        self._update_curiosity_directives(synthesis.context_terms, pred_error)

        # M34: Update seed drives (SURVIVE/ELABORATE/REST + wanting/liking/empowerment).
        # Runs after curiosity directives so n_directives is current.
        try:
            self.drives.update_seed(
                pred_error    = pred_error,
                n_directives  = len(self._curiosity_directives),
                resource_energy = self.survival.resource.budget.energy,
            )
        except Exception as exc:
            self.survival.resilience.error_log.log("drives.seed", exc)

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

            # M19: spreading activation in ingestion — current attention primes
            # graph-adjacent concepts so they're included in this cycle's update,
            # making retrieval associative even for future cycles.
            activation = {}
            try:
                current_attention = self.memory._working._context_terms
                if current_attention:
                    sources = {t: 1.0 for t in current_attention[:8]}
                    activation = self.spreading_activation.compute(sources)
            except Exception as exc:
                self.survival.resilience.error_log.log("process.spreading_activation", exc)

            # Update attention: cross-modal > primary terms, augmented with primed neighbors
            attention_terms = synthesis.cross_modal_concepts or synthesis.context_terms
            if attention_terms:
                if activation:
                    primed = [c for c, _ in sorted(
                        activation.items(), key=lambda kv: kv[1], reverse=True
                    )[:4]]
                    attention_terms = list(dict.fromkeys(attention_terms + primed))
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

        # M34: Include seed drive signals in result for observability
        drive_summary = {}
        try:
            drive_summary = {
                k: v for k, v in self.drives.summary().items()
                if k in ("wanting", "liking", "empowerment", "seed_action",
                         "survive_alarm", "rest_pending")
            }
        except Exception:
            pass

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
            "drives": drive_summary,
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
        except Exception as exc:
            self.survival.resilience.error_log.log("is_novel.relations_check", exc)

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

    def _store_synthesis(self, synthesis, raw_data: Any, novel: bool = False) -> tuple[list[str], int]:
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

        # M26: Update drive states from this cycle's outcome
        from survival.drives import CycleStats
        self.drives.update(CycleStats(
            relations_added=relations_added,
            new_conflicts=new_conflicts,
            stored_keys_count=len(stored_keys),
            directive_count=len(self._curiosity_directives),
            cycle_number=self.cycle_count,
        ))

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

    def learn_about(self, concept: str, verbose: bool = False) -> dict:
        """
        On-demand learning about a single named concept.

        Unlike fetch_knowledge() — which follows Genesis's own curiosity
        frontier — this learns about a concept a human just asked about, right
        now, synchronously. It pulls the WordNet definition (always offline),
        a relevant Gutenberg passage (cache-first), and any NLTK corpus text,
        processes all of it through the normal pipeline, and reports how much
        the relation graph grew.

        This is what makes conversation generative: ask Genesis about lakes and
        it goes and reads about lakes, then answers from what it just learned —
        the same mechanism a curious person uses, not a parametric lookup.

        Returns:
            {concept, relations_before, relations_after, relations_added,
             chunks_processed, success}
        """
        if not hasattr(self, "_feeder") or self._feeder is None:
            from ingestion.feeder import KnowledgeFeeder
            self._feeder = KnowledgeFeeder(self)

        concept = (concept or "").strip().lower()

        # Try the word as given, then a singular form if it looks plural.
        # WordNet keys on lemmas — "lakes" returns nothing but "lake" does.
        variants = [concept]
        if concept.endswith("ies") and len(concept) > 4:
            variants.append(concept[:-3] + "y")   # "berries" -> "berry"
        elif concept.endswith("es") and len(concept) > 3:
            variants.append(concept[:-2])          # "volcanoes" -> "volcano"
        if concept.endswith("s") and not concept.endswith("ss") and len(concept) > 3:
            variants.append(concept[:-1])          # "lakes" -> "lake"

        before = self.relations.stats().get("total_relations", 0)
        result = {"success": False, "chunks_processed": 0}
        for variant in variants:
            try:
                result = self._feeder._fetch_and_process(variant, verbose=verbose)
            except Exception as exc:
                self.survival.resilience.error_log.log(f"learn_about._fetch:{variant}", exc)
                result = {"success": False, "chunks_processed": 0}
            if self.relations.stats().get("total_relations", 0) > before:
                concept = variant
                break
        after = self.relations.stats().get("total_relations", 0)

        # New material is worth a fresh inference pass so the answer can draw on
        # any chains the new edges complete.
        if after > before:
            try:
                self.inference.run(session_id=self.session_id)
            except Exception as exc:
                self.survival.resilience.error_log.log("learn_about.inference", exc)

        return {
            "concept": concept,
            "relations_before": before,
            "relations_after": after,
            "relations_added": after - before,
            "chunks_processed": result.get("chunks_processed", 0),
            "success": result.get("success", False),
        }

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
        except Exception as exc:
            self.survival.resilience.error_log.log("reflect.calibration", exc)

        # M22: scan for structural analogs after each reflection pass.
        # Reflection is when the relation graph is richest — best moment
        # to detect patterns that have formed across processing sessions.
        try:
            new_analogs = self.pattern_transfer.scan()
            if new_analogs > 0 and self.verbose:
                self._log(f"  🔁 {new_analogs} structural analog pair(s) detected")
            # Register curiosity directives from analogs: concepts playing the same
            # structural role as known regulators/mediators but with unexplained edges.
            analog_curiosity = self.pattern_transfer.curiosity_from_analogs()
            for concept in analog_curiosity:
                if (concept not in self._curiosity_directives
                        and len(self._curiosity_directives) < self._MAX_DIRECTIVES):
                    self._curiosity_directives[concept] = 0.82
            if analog_curiosity:
                self._save_directives()
        except Exception as exc:
            self.survival.resilience.error_log.log("reflect.pattern_transfer", exc)

        # M30: generative cognition. Reflection is when the graph is richest, so
        # it's the natural moment to (a) test standing predictions against any
        # evidence acquired since, then (b) form new conjectures. Verify first
        # so a hypothesis confirmed this pass isn't immediately re-proposed.
        try:
            resolved = self.hypotheses.verify()
            if resolved > 0 and self.verbose:
                self._log(f"  🔬 {resolved} hypothesis(es) resolved against new evidence")
            new_hyps = self.hypotheses.generate()
            if new_hyps > 0 and self.verbose:
                self._log(f"  💡 {new_hyps} new hypothesis(es) formed")
            # Open hypotheses are reasons to read: pull their subjects into the
            # curiosity frontier so Genesis goes looking for the deciding evidence.
            for concept in self.hypotheses.curiosity_targets():
                if (concept not in self._curiosity_directives
                        and len(self._curiosity_directives) < self._MAX_DIRECTIVES):
                    self._curiosity_directives[concept] = 0.80
            self._save_directives()
        except Exception as exc:
            self.survival.resilience.error_log.log("reflect.hypotheses", exc)

        # M30.2: every Nth reflection, draft a research direction from current
        # state. Spacing it out keeps the proposal a considered statement rather
        # than noise that rewrites itself each pass.
        self._reflection_count += 1
        if self._reflection_count % self._proposal_every == 0:
            try:
                doc = self.research.compose()
                if doc and self.verbose:
                    self._log("  📝 Drafted a new research direction")
            except Exception as exc:
                self.survival.resilience.error_log.log("reflect.research_proposal", exc)

        # M31: mine for new rule patterns, run existing programs to derive
        # new edges, then verify which derivations have since been confirmed.
        # Mining runs after hypothesis generation so both layers see the same
        # enriched graph state within this reflection pass.
        try:
            new_progs = self.programs.mine()
            if new_progs > 0 and self.verbose:
                self._log(f"  📐 {new_progs} inference program(s) authored")
            new_deriv = self.programs.run_all()
            if new_deriv > 0 and self.verbose:
                self._log(f"  ⚙️  {new_deriv} derivation(s) from inference programs")
            confirmed_deriv = self.programs.verify_derivations()
            if confirmed_deriv > 0 and self.verbose:
                self._log(f"  ✅ {confirmed_deriv} program derivation(s) confirmed")
        except Exception as exc:
            self.survival.resilience.error_log.log("reflect.programs", exc)

        return result

    def propose_research(self) -> str | None:
        """
        Draft (and store) a research-direction document from Genesis's current
        cognitive state: what it understands, what it can't yet explain, the
        parallels it has noticed, what it predicts, and what it intends to read.

        Returns the document text, or None if Genesis has too little to say yet.
        """
        try:
            return self.research.compose()
        except Exception as exc:
            self.survival.resilience.error_log.log("propose_research", exc)
            return None

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

    def start_autonomous(
        self,
        tick_interval: float = 60.0,
        reflect_every: int = 6,
    ) -> None:
        """
        Start the autonomous cognitive loop.

        Genesis will run between interactions: following curiosity directives,
        re-evaluating belief tensions, and periodically reflecting.
        Call stop_autonomous() to halt it.
        """
        self.autonomous._idle_interval = tick_interval
        self.autonomous._reflect_every = reflect_every
        self.autonomous.start()
        if self.verbose:
            self._log(f"🔄 Autonomous loop started "
                      f"(interval={tick_interval}s, reflect_every={reflect_every})")

    def stop_autonomous(self) -> None:
        """Stop the autonomous cognitive loop."""
        self.autonomous.stop()
        if self.verbose:
            self._log("⏹  Autonomous loop stopped")

    def save_session(self) -> None:
        """Checkpoint current state to the DB for restore on next startup."""
        self._session_manager.save(self)
        try:
            self.metaplasticity.save()
        except Exception as exc:
            self.survival.resilience.error_log.log("metaplasticity.save", exc)
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
        except Exception as exc:
            self.survival.resilience.error_log.log("query.spreading_activation", exc)

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

            # Drive-gated threshold: M26 hunger lowers it, M34 seed action modifies it.
            # explore → 20% more sensitive (ELABORATE drive active)
            # alarm   → 30% less sensitive (SURVIVE takes precedence, shed new work)
            curiosity_boost = 0.0
            seed_modifier   = 0.0
            try:
                hints = self.drives.behavioral_hints()
                curiosity_boost = hints.get("curiosity_boost", 0.0)
                seed_act = hints.get("seed_action", "idle")
                if seed_act == "explore":
                    seed_modifier = -0.10   # lower threshold → register more
                elif seed_act == "alarm":
                    seed_modifier = +0.15   # raise threshold → focus, shed breadth
            except Exception:
                pass
            effective_threshold = max(
                0.50,
                self._DIRECTIVE_PRED_ERROR_MIN - curiosity_boost * 0.15 + seed_modifier
            )

            # Register new directives from high-surprise context terms
            if (pred_error >= effective_threshold
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
        except Exception as exc:
            self.survival.resilience.error_log.log("directives.update", exc)

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
        except Exception as exc:
            self.survival.resilience.error_log.log("directives._load", exc)
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
        except Exception as exc:
            self.survival.resilience.error_log.log("directives._save", exc)

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
