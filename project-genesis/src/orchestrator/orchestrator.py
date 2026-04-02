"""
The Orchestrator — Central Hypervisor.

Routes input to processors, evaluates outputs, manages memory decisions,
and controls learning progression. It doesn't process data itself — it
decides what gets processed, by whom, and what to do with the results.

Like the brain's executive function: coordination, not computation.

M1 addition: SurvivalOS integration. The Orchestrator now consults
Layer 0 at the start of each cycle. Throttle level determines which
processors and memory operations are available. Resource-constrained
cycles degrade gracefully rather than failing.
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


class Orchestrator:
    """
    The central coordinating intelligence.

    Never crashes. Every decision is logged. Every error is data.

    With a SurvivalOS attached (default), each cycle begins with a
    resource tick. The orchestrator checks which capabilities are
    available before dispatching to processors and memory.
    """

    def __init__(
        self,
        verbose: bool = True,
        survival: SurvivalOS | None = None,
        interaction: InteractionLayer | None = None,
    ):
        self.processors = {
            "text": TextProcessor(),
            "numeric": NumericProcessor(),
            "pattern": PatternProcessor(),
        }
        self.memory = MemorySystem()
        self.curriculum = CurriculumEngine()
        self.verbose = verbose
        self.cycle_count = 0
        self.error_count = 0
        self.log: list[str] = []

        # Layer 0 — Survival OS.
        self.survival: SurvivalOS = survival if survival is not None else SurvivalOS()

        # M3 — Interaction Layer (community surface + observer + interventions).
        self.interaction: InteractionLayer = (
            interaction if interaction is not None
            else InteractionLayer(self.memory)
        )

    def _log(self, msg: str):
        self.log.append(msg)
        if self.verbose:
            print(f"  [{self.curriculum.current_stage.name}] {msg}")

    def process_input(self, input_type: str, data: Any) -> dict:
        """
        Main entry point. Routes input, evaluates results, manages memory.
        Never raises an exception — always returns a result dict.
        """
        self.cycle_count += 1

        # Layer 0 tick — update resource state and directives
        survival_stats = self._survival_stats()
        survival_state = self.survival.tick(survival_stats)

        if self.verbose and survival_state["throttle"] != "NONE":
            self._log(
                f"⚡ Survival OS: energy={survival_state['energy']:.2f} "
                f"throttle={survival_state['throttle']} "
                f"pressure={survival_state['pressure']:.2f}"
            )

        # M3 — Interaction layer tick
        interaction_state = self.interaction.cycle(survival_stats, self.cycle_count)

        # If paused by the Observer, hold without processing
        if interaction_state["is_paused"]:
            self._log(
                f"⏸  Paused — {interaction_state['pause_reason']}. "
                f"Call orchestrator.interaction.resume() to continue."
            )
            return {
                "status": "paused",
                "reason": interaction_state["pause_reason"],
                "cycle": self.cycle_count,
            }

        # Check for pending stimulus (from stagnation intervention or human feed)
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
            return {
                "status": "degraded",
                "reason": str(e),
                "cycle": self.cycle_count,
            }

    def _do_process(self, input_type: str, data: Any) -> dict:
        """Internal processing — the actual work."""
        # Resolve processor, respecting current throttle level
        processor = self._select_processor(input_type, data)
        processor_type = processor.name

        # Process
        output = processor.process(data if processor_type != "text" or input_type == "text" else str(data))
        self._log(f"→ {output.source} processor: {output.context}")

        # Evaluate against curriculum (only if curriculum capability is available)
        if self.survival.can("curriculum"):
            eval_score = self.curriculum.evaluate_processing(output)
            self.curriculum.record_score(eval_score)
            self._log(
                f"  Eval: {eval_score:.2f} | "
                f"Stage avg: {self.curriculum.stage_scores[self.curriculum.current_stage]:.2f}"
            )
        else:
            eval_score = output.importance
            self._log("  Curriculum eval skipped (resource pressure)")

        # Store in memory — conditionally on throttle level
        if self.survival.can("memory_store"):
            raw = str(data) if not isinstance(data, str) else data
            memory_content = f"{raw} | {json.dumps(output.extracted, default=str)}"
            self.memory.store(
                key=output.suggested_key,
                content=memory_content,
                context=output.context,
                source_type=output.source,
                relevance=output.importance,
            )
            if self.survival.can("logging"):
                self._log(f"  💾 Stored '{output.suggested_key}' (relevance: {output.importance:.2f})")

            # Update attention context
            attention_terms = output.extracted.get("keywords", [])
            if output.extracted.get("categories"):
                attention_terms.extend(output.extracted["categories"])
            if output.extracted.get("label"):
                attention_terms.append(output.extracted["label"])
            if attention_terms:
                self.memory.update_attention(attention_terms)
        else:
            if self.survival.can("logging"):
                self._log("  Memory storage skipped (emergency throttle)")

        # Check for stage advancement (only when not in survival mode)
        if self.survival.can("curriculum") and self.curriculum.should_advance():
            advanced = self.curriculum.advance()
            if advanced:
                self._log(f"  🎓 ADVANCED to stage {self.curriculum.current_stage.name}!")

        return {
            "status": "processed",
            "output": output.extracted,
            "importance": output.importance,
            "eval_score": eval_score,
            "stage": self.curriculum.current_stage.name,
            "cycle": self.cycle_count,
            "throttle": self.survival.resource.throttle_level.name,
        }

    def _select_processor(self, input_type: str, data: Any):
        """
        Select a processor, degrading gracefully under resource pressure.

        If the requested processor is unavailable (throttled), fall back
        to the next available one. Text is always the final fallback.
        """
        requested = self.processors.get(input_type)

        # Check if the requested processor type is available
        if requested and self.survival.can(input_type):
            return requested

        # Fallback chain: numeric → text, pattern → text
        if not self.survival.can(input_type) and input_type != "text":
            self._log(
                f"⚠ Processor '{input_type}' unavailable (throttle: "
                f"{self.survival.resource.throttle_level.name}) — falling back to text"
            )
            return self.processors["text"]

        # Unknown type or no processor found
        if not requested:
            self._log(f"⚠ No processor for '{input_type}' — routing to text as fallback")
        return self.processors["text"]

    def query(self, question: str) -> dict:
        """Ask the system a question based on what it has learned."""
        self._log(f"❓ Query: '{question}'")

        # Memory search respects throttle level
        if not self.survival.can("memory_search"):
            self._log("  Memory search unavailable (resource pressure)")
            return {"answer": "System under resource pressure — memory search unavailable.", "memories_used": 0}

        results = self.memory.search(question, top_k=5)

        if not results:
            self._log("  No relevant memories found.")
            return {"answer": "I don't have enough experience to answer that.", "memories_used": 0}

        self._log(f"  Found {len(results)} relevant memories:")
        memories_used = []
        for key, mem in results:
            self._log(f"    • {key}: {mem.context} (relevance: {mem.relevance:.2f})")
            memories_used.append(mem.to_dict() | {"key": key})

        return {
            "answer": f"Based on {len(results)} memories.",
            "memories_used": len(results),
            "relevant_memories": memories_used,
        }

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
        """Build the stats dict for DirectiveEngine.update()."""
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
