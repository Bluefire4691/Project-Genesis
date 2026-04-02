"""
Curriculum engine — Staged learning progression.

The system must demonstrate competence at each stage before advancing.
Like a child learning: simple concepts first, complexity later.
Build the reasoning machinery before giving it the world.
"""

import json
from typing import Any

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.types import Stage, ProcessorOutput


class CurriculumEngine:
    """
    Manages staged learning progression.

    Each stage has curated input and success criteria.
    The system advances when it demonstrates competence, not
    after a fixed number of examples.
    """

    def __init__(self, advancement_threshold: float = 0.6, min_items: int = 5):
        self.current_stage = Stage.FOUNDATION
        self.stage_scores: dict[Stage, float] = {s: 0.0 for s in Stage}
        self.items_processed: dict[Stage, int] = {s: 0 for s in Stage}
        self.advancement_threshold = advancement_threshold
        self.min_items_per_stage = min_items

    def get_curriculum(self) -> list[dict]:
        """Return curriculum items for the current stage."""
        curricula = {
            Stage.FOUNDATION: [
                {"type": "text", "data": "A dog is an animal. Dogs are friendly and loyal."},
                {"type": "text", "data": "The sun is a star. It gives us light and warmth."},
                {"type": "text", "data": "Water is essential for life. Humans need water to survive."},
                {"type": "numeric", "data": {"label": "water_boiling_point", "value": 100, "unit": "celsius"}},
                {"type": "numeric", "data": {"label": "days_in_week", "value": 7, "unit": "days"}},
                {"type": "text", "data": "An apple is a fruit. Fruits are food that grow on trees."},
                {"type": "text", "data": "A teacher is a person who helps children learn at school."},
                {"type": "numeric", "data": {"label": "earth_gravity", "value": 9.8, "unit": "m/s²"}},
                {"type": "pattern", "data": {"label": "seasons", "sequence": ["spring", "summer", "fall", "winter", "spring", "summer", "fall", "winter"]}},
                {"type": "text", "data": "Books contain knowledge. Reading helps you learn new things."},
            ],
            Stage.RELATIONS: [
                {"type": "text", "data": "Dogs are animals that live with people at home. Dogs need food and water to stay healthy."},
                {"type": "text", "data": "The sun heats water in the ocean. Warm water evaporates and forms clouds. Clouds bring rain."},
                {"type": "numeric", "data": {"label": "temperatures", "values": [15, 20, 25, 30, 28, 22], "unit": "celsius"}},
                {"type": "pattern", "data": {"label": "day_night", "sequence": ["light", "dark", "light", "dark", "light", "dark"]}},
                {"type": "text", "data": "When it is cold outside, animals with fur stay warm. Animals without fur must find shelter."},
                {"type": "text", "data": "A seed needs water and sunlight to grow into a plant. Plants make food from sunlight."},
                {"type": "numeric", "data": {"label": "plant_growth_cm", "values": [1, 2, 4, 7, 11, 16], "unit": "cm"}},
                {"type": "text", "data": "Fear keeps animals safe from danger. A deer runs when it sees a wolf."},
            ],
            Stage.REASONING: [
                {"type": "text", "data": "It has not rained for many days. The plants in the garden are turning brown."},
                {"type": "text", "data": "A new animal was found. It has fur and lives in a cold place."},
                {"type": "numeric", "data": {"label": "city_temps", "values": [30, 31, 33, 35, 38, 40, 42], "unit": "celsius"}},
                {"type": "text", "data": "A child is alone in a dark forest. What might the child feel?"},
                {"type": "pattern", "data": {"label": "population", "sequence": [100, 200, 400, 800, 1600]}},
                {"type": "text", "data": "The river is dry. The fish are gone. The birds that ate the fish have left."},
            ],
            Stage.OPEN: [
                {"type": "text", "data": "This stage accepts any input. The cognitive machinery is developed."},
            ],
        }
        return curricula.get(self.current_stage, [])

    def evaluate_processing(self, output: ProcessorOutput) -> float:
        """Score how well the system processed this input for the current stage."""
        score = 0.0

        if output.extracted:
            score += 0.3

        if 0.1 < output.importance < 0.95:
            score += 0.2

        if self.current_stage == Stage.FOUNDATION:
            if output.extracted.get("categories") or output.extracted.get("label"):
                score += 0.3
            if output.context and len(output.context) > 10:
                score += 0.2

        elif self.current_stage == Stage.RELATIONS:
            if output.extracted.get("trend") and output.extracted["trend"] != "flat":
                score += 0.3
            if output.extracted.get("patterns"):
                score += 0.3
            if len(output.extracted.get("keywords", [])) >= 3:
                score += 0.2

        elif self.current_stage == Stage.REASONING:
            if output.importance > 0.4:
                score += 0.3
            if output.extracted.get("trend") == "increasing":
                score += 0.2

        return min(1.0, score)

    def record_score(self, score: float):
        """Record a processing score using running average."""
        n = self.items_processed[self.current_stage]
        self.stage_scores[self.current_stage] = (
            (self.stage_scores[self.current_stage] * n + score) / (n + 1)
        )
        self.items_processed[self.current_stage] += 1

    def should_advance(self) -> bool:
        """Check if ready to advance to the next stage."""
        if self.current_stage == Stage.OPEN:
            return False
        return (
            self.stage_scores[self.current_stage] >= self.advancement_threshold
            and self.items_processed[self.current_stage] >= self.min_items_per_stage
        )

    def advance(self) -> bool:
        """Advance to the next stage if ready."""
        if self.should_advance() and self.current_stage < Stage.OPEN:
            self.current_stage = Stage(self.current_stage + 1)
            return True
        return False

    def status(self) -> dict:
        return {
            "current_stage": self.current_stage.name,
            "stage_number": int(self.current_stage),
            "score": round(self.stage_scores[self.current_stage], 3),
            "items_processed": self.items_processed[self.current_stage],
            "ready_to_advance": self.should_advance(),
        }
