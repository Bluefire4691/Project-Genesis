"""
The Orchestrator — Central Hypervisor.

Coordinates all layers. Doesn't process data itself — decides what gets
processed, by whom, and what to do with the results.

M1: SurvivalOS integration — resource throttle gates which processors run.
M3: InteractionLayer — expression, observation, community surface.
M4: IntegrationLayer — all available processors see every input.
    Significance is context-weighted. Cross-modal concepts are linked.

The key shift in M4: the Orchestrator stops routing to one processor
and starts synthesizing across all of them. Same input, multiple views,
context determines what registers.
"""

import json
from typing import Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.types import ProcessorOutput
from processors import TextProcessor, NumericProcessor, PatternProcessor
from memory.memory import MemorySystem
from curriculum.curriculum import CurriculumEngine
from survival import SurvivalOS
from interface import InteractionLayer
from orchestrator.integration import IntegrationLayer


class Orchestrator:
    """
    The central coordinating intelligence.

    Never crashes. Every decision is logged. Every error is data.
    All processors see all input. Context determines significance.
    """

    def __init__(
        self,
        verbose: bool = True,
        survival: SurvivalOS | None = None,
        interaction: InteractionLayer | None = None,
    ):
        self.processors = {
            "text":    TextProcessor(),
            "numeric": NumericProcessor(),
            "pattern": PatternProcessor(),
        }
        self.memory = MemorySystem()
        self.curriculum = CurriculumEngine()
        self.verbose = verbose
        self.cycle_count = 0
        self.error_count = 0
        self.log: list[str] = []

        self.survival: SurvivalOS = survival if survival is not None else SurvivalOS()
        self.interaction: InteractionLayer = (
            interaction if interaction is not None
            else InteractionLayer(self.memory)
        )
        self.integrator = IntegrationLayer(self.memory)

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
            self._log(
                f"⏸  Paused — {interaction_state['pause_reason']}. "
                f"Call orchestrator.interaction.resume() to continue."
            )
            return {"status": "paused", "reason": interaction_state["pause_reason"],
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

        # Store everything if resources allow
        if self.survival.can("memory_store"):
            stored_keys = self._store_synthesis(synthesis, data)
            if self.survival.can("logging"):
                self._log(f"  💾 Stored {len(stored_keys)} memory key(s)")

            # Update attention with cross-modal concepts first, then primary terms
            attention_terms = synthesis.cross_modal_concepts or synthesis.context_terms
            if attention_terms:
                self.memory.update_attention(attention_terms)
        else:
            stored_keys = []
            if self.survival.can("logging"):
                self._log("  Memory storage skipped (emergency throttle)")

        # Stage advancement
        if self.survival.can("curriculum") and self.curriculum.should_advance():
            if self.curriculum.advance() and self.verbose:
                self._log(f"  🎓 ADVANCED to {self.curriculum.current_stage.name}!")

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
        }

    def _active_processors(self, input_type: str) -> dict:
        """
        Return all processors available at current throttle level.

        The primary (input_type) is always included if text is available.
        Under heavy throttle, only text survives — that's the correct
        degradation: lose breadth before losing function.
        """
        active = {}
        for name, processor in self.processors.items():
            if self.survival.can(name):
                active[name] = processor

        if not active:
            # Ultimate fallback — text always available unless something is broken
            active["text"] = self.processors["text"]

        return active

    def _store_synthesis(self, synthesis, raw_data: Any) -> list[str]:
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

        return stored_keys

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(self, question: str) -> dict:
        """Ask the system a question based on what it has learned."""
        self._log(f"❓ Query: '{question}'")

        if not self.survival.can("memory_search"):
            return {"answer": "System under resource pressure — memory search unavailable.",
                    "memories_used": 0}

        results = self.memory.search(question, top_k=5)
        if not results:
            return {"answer": "I don't have enough experience to answer that.",
                    "memories_used": 0}

        memories_used = []
        for key, mem in results:
            self._log(f"    • {key}: {mem.context} (relevance: {mem.relevance:.2f})")
            memories_used.append(mem.to_dict() | {"key": key})

        return {
            "answer": f"Based on {len(results)} memories.",
            "memories_used": len(results),
            "relevant_memories": memories_used,
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

    def full_status(self) -> dict:
        status = {
            "cycles": self.cycle_count,
            "error_count": self.error_count,
            "curriculum": self.curriculum.status(),
            "memory": self.memory.stats(),
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
