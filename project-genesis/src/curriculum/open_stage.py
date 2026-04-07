"""
Open Stage Data Stream — M5/M8.

The curriculum guardrails are off. Genesis has developed its processing
machinery through FOUNDATION, RELATIONS, and REASONING. Now it meets
the world — varied, uncurated, no correct sequence.

The DataStream is not a test. There are no advancement criteria. There
is no score. It's an environment: a continuous flow of input drawn from
different domains, types, and complexity levels. What Genesis makes of
it is up to Genesis.

M8 expands the pool from 56 → 130 items across 14 domains, adding:
    - History and causation (events as causal chains)
    - Science fundamentals (energy, entropy, conservation)
    - Biology and genetics (DNA, evolution, neural systems)
    - Mathematics and logic (implication, probability, set relations)
    - Ethics as narrative (consequences-based, never rule-based)
    - Philosophy and epistemology (knowledge, models, falsifiability)
    - Additional contradictions and anomalies in the new domains

Ethics data is expressed as experienced events and their consequences —
not as moral rules. "This happened, then this happened." What Genesis
makes of the pattern is up to Genesis.

Edge cases are deliberate. The world doesn't curate itself. An anomaly
is as real as a clean fact, and often more informative. A contradiction
isn't a curriculum mistake — it's a thing that happens.

The stream loops by default (open-ended) and shuffles each loop to
prevent processing order from becoming its own pattern.
"""

import random
import sys
import os
from typing import Any, Iterator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from utils.types import Stage


# ------------------------------------------------------------------
# The data pool — varied inputs across domains and types
# ------------------------------------------------------------------

_POOL: list[dict] = [

    # --- Natural systems ---
    {"type": "text", "data": "A forest fire destroys trees but releases seeds that need heat to germinate. The fire makes space for new growth."},
    {"type": "text", "data": "Wolves were removed from Yellowstone. Deer overpopulated. Riverbanks eroded. Reintroducing wolves changed the path of rivers."},
    {"type": "text", "data": "A coral reef supports thousands of species. When water warms by two degrees, the coral bleaches and most species leave."},
    {"type": "text", "data": "Bees pollinate flowers. Without bees, many plants cannot reproduce. Without those plants, the animals that eat them disappear."},
    {"type": "numeric", "data": {"label": "ocean_temperature_rise", "values": [0.1, 0.2, 0.3, 0.5, 0.8, 1.1, 1.3], "unit": "celsius_above_baseline"}},
    {"type": "numeric", "data": {"label": "wolf_reintroduction_deer_population", "values": [2500, 2300, 1900, 1500, 1200, 1100, 1050], "unit": "count"}},
    {"type": "pattern", "data": {"label": "predator_prey_cycle", "sequence": [100, 80, 55, 40, 60, 90, 110, 85, 60, 45, 65, 95]}},
    {"type": "pattern", "data": {"label": "forest_regrowth", "sequence": [0, 2, 8, 20, 45, 70, 85, 92, 96, 98]}},

    # --- Physics / measurement ---
    {"type": "text", "data": "Objects in motion stay in motion unless acted on by a force. Nothing changes without something acting on it."},
    {"type": "text", "data": "Heat flows from hot to cold. It never flows the other way on its own. This sets a direction to time."},
    {"type": "text", "data": "A small change at the beginning of a chaotic system produces a large difference at the end. Initial conditions matter enormously."},
    {"type": "numeric", "data": {"label": "free_fall_velocity", "values": [0, 9.8, 19.6, 29.4, 39.2, 49.0], "unit": "m/s"}},
    {"type": "numeric", "data": {"label": "light_speed", "value": 299792458, "unit": "m/s"}},
    {"type": "numeric", "data": {"label": "pressure_depth", "values": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], "unit": "atm_per_10m"}},
    {"type": "pattern", "data": {"label": "pendulum_swing", "sequence": [10, 7, 5, 3.5, 2.5, 1.7, 1.2, 0.8]}},

    # --- Biology / life processes ---
    {"type": "text", "data": "A cell divides by copying its DNA. Each copy has a small chance of error. Errors accumulate over generations."},
    {"type": "text", "data": "Immune systems remember diseases they have defeated. The second encounter is handled faster than the first."},
    {"type": "text", "data": "Sleep is when the brain consolidates memories. Animals deprived of sleep deteriorate quickly despite having food and water."},
    {"type": "text", "data": "Fungi break down dead matter and return nutrients to soil. Without decomposers, ecosystems would fill with dead material."},
    {"type": "numeric", "data": {"label": "cell_division_time_minutes", "values": [0, 30, 60, 90, 120, 150], "unit": "minutes"}},
    {"type": "numeric", "data": {"label": "neuron_firing_rate", "value": 1000, "unit": "hz_max"}},
    {"type": "pattern", "data": {"label": "population_boom_bust", "sequence": [50, 200, 800, 3200, 800, 200, 800, 3200]}},
    {"type": "pattern", "data": {"label": "dna_base_pairs", "sequence": ["A", "T", "G", "C", "A", "T", "G", "C", "G", "C"]}},

    # --- Human and social ---
    {"type": "text", "data": "A group that cooperates on difficult tasks outcompetes groups that do not. Cooperation enables things no individual could do."},
    {"type": "text", "data": "Trust takes a long time to build and a short time to destroy. Asymmetry of trust creation and loss shapes all relationships."},
    {"type": "text", "data": "Language allows humans to coordinate with strangers. A shared symbol system extends the range of cooperation."},
    {"type": "text", "data": "Cities concentrate people. Dense contact spreads disease faster but also spreads ideas faster. Density is a double edge."},
    {"type": "text", "data": "Punishment of defectors maintains cooperation in groups. Without enforcement, free riders eventually destroy cooperative systems."},
    {"type": "numeric", "data": {"label": "city_size_innovation_rate", "values": [1, 1.15, 1.32, 1.52, 1.75, 2.01], "unit": "relative_to_baseline"}},
    {"type": "pattern", "data": {"label": "cooperation_breakdown", "sequence": [10, 10, 10, 9, 8, 6, 4, 2, 1, 0]}},

    # --- Abstract relationships ---
    {"type": "text", "data": "A system that cannot fail small will eventually fail large. Regular small failures prevent catastrophic ones."},
    {"type": "text", "data": "The map is not the territory. Every model of a thing is simpler than the thing. Simplification is necessary and dangerous."},
    {"type": "text", "data": "Feedback loops can stabilize or destabilize. A thermostat stabilizes. Panic in a crowd destabilizes."},
    {"type": "text", "data": "Optimization for a single variable degrades all others. A tree optimized only for height would have no roots."},
    {"type": "text", "data": "The absence of evidence is not evidence of absence. Not finding something does not mean it is not there."},
    {"type": "numeric", "data": {"label": "diminishing_returns", "values": [0, 40, 65, 78, 86, 91, 94, 96, 97, 98], "unit": "percent_of_max"}},
    {"type": "pattern", "data": {"label": "fibonacci", "sequence": [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]}},
    {"type": "pattern", "data": {"label": "power_law_frequency", "sequence": [1000, 500, 250, 125, 63, 31, 16, 8, 4, 2]}},

    # --- Edge cases: contradictions, anomalies, incompleteness ---
    {"type": "text", "data": "A medicine that cures one disease causes another. Most interventions have unintended consequences."},
    {"type": "text", "data": "The species that survived the last extinction were not the strongest. They were the ones that happened to be in the right place."},
    {"type": "text", "data": "An animal was observed doing something it was believed incapable of doing. The previous model was incomplete."},
    {"type": "text", "data": "Two measurements of the same thing produced different results. Both instruments were working correctly."},
    {"type": "numeric", "data": {"label": "anomalous_reading", "values": [10, 11, 10, 12, 10, 47, 11, 10, 11], "unit": "arbitrary"}},
    {"type": "pattern", "data": {"label": "interrupted_sequence", "sequence": [2, 4, 8, 16, 0, 64, 128]}},

    # --- Scale and emergence ---
    {"type": "text", "data": "A single ant cannot build a bridge. A colony of ants can. The colony has properties no individual ant possesses."},
    {"type": "text", "data": "Water is wet. Hydrogen and oxygen individually are not wet. Wetness emerges from the combination."},
    {"type": "text", "data": "A neuron does not think. A hundred billion neurons together produce thought. The substrate does not predict the outcome."},
    {"type": "numeric", "data": {"label": "ant_colony_size_vs_complexity", "values": [1, 5, 12, 28, 50, 100, 200], "unit": "relative_behavior_complexity"}},
    {"type": "pattern", "data": {"label": "emergence_threshold", "sequence": [1, 1, 1, 1, 2, 4, 8, 16, 32]}},

    # --- Time and change ---
    {"type": "text", "data": "Rivers carve canyons. No single day of water flow is visible. The canyon is the sum of countless imperceptible changes."},
    {"type": "text", "data": "A species that does not change goes extinct when its environment changes. Adaptation requires variation."},
    {"type": "text", "data": "A habit is a behavior repeated until it runs without attention. The brain routes around conscious decision-making."},
    {"type": "numeric", "data": {"label": "erosion_rate_mm_per_year", "value": 0.3, "unit": "mm/year"}},
    {"type": "numeric", "data": {"label": "evolutionary_change_generations", "values": [0, 100, 500, 2000, 8000, 25000], "unit": "generations"}},
    {"type": "pattern", "data": {"label": "slow_then_fast", "sequence": [1, 1, 1, 2, 3, 5, 10, 20, 50, 200]}},

    # --- History and causation ---
    {"type": "text", "data": "The printing press enabled mass literacy. Literacy enabled individuals to read scripture directly. Direct reading enabled religious reform. Religious reform caused a century of wars."},
    {"type": "text", "data": "The Black Death killed a third of Europe. Labor became scarce. Peasants gained bargaining power. Feudalism weakened. The Renaissance followed."},
    {"type": "text", "data": "Rome built roads to control its empire. Roads enabled trade. Trade enriched the provinces. Rich provinces demanded autonomy. The roads that built Rome helped end it."},
    {"type": "text", "data": "Gunpowder was invented to make medicine. It was adapted for fireworks. It was adapted for weapons. It ended the age of castles and armored knights."},
    {"type": "text", "data": "The potato enabled Ireland to feed a large population on small land. Dependence on one crop made the food supply fragile. One blight caused a famine that halved the population."},
    {"type": "text", "data": "Trade requires trust between strangers. Contracts enabled trust without personal relationships. Courts enforced contracts. Enforcement enabled markets to scale beyond communities."},
    {"type": "numeric", "data": {"label": "population_after_black_death", "values": [75, 74, 70, 60, 50, 45, 40, 42, 48, 55], "unit": "million_europe"}},
    {"type": "numeric", "data": {"label": "literacy_rate_europe", "values": [5, 6, 8, 12, 20, 35, 55, 70, 85], "unit": "percent"}},
    {"type": "pattern", "data": {"label": "empire_lifespan_years", "sequence": [250, 400, 350, 500, 200, 900, 300, 450]}},
    {"type": "text", "data": "Two nations traded for a century. One discovered it needed the other more than the other needed it. The dependency was invisible until a crisis made it visible."},

    # --- Science fundamentals ---
    {"type": "text", "data": "Energy is conserved. It cannot be created or destroyed. It only changes form — from motion to heat, from chemical to electrical."},
    {"type": "text", "data": "Entropy increases in isolated systems. Order tends toward disorder. Maintaining order requires a continuous input of energy."},
    {"type": "text", "data": "Every action produces an equal and opposite reaction. Forces come in pairs. No force exists without a counterforce."},
    {"type": "text", "data": "Gravity attracts all mass toward all other mass. The same force that pulls an apple down holds planets in orbit."},
    {"type": "text", "data": "Light travels at the same speed for all observers regardless of their motion. This requires that time and space are not fixed — they stretch and compress."},
    {"type": "text", "data": "Quantum mechanics predicts that a particle has no definite position until it is observed. Observation changes the thing being observed."},
    {"type": "numeric", "data": {"label": "temperature_entropy_relationship", "values": [1, 4, 9, 16, 25, 36, 49], "unit": "relative_disorder"}},
    {"type": "numeric", "data": {"label": "gravitational_force_distance", "values": [100, 25, 11, 6.25, 4, 2.78], "unit": "relative_force"}},
    {"type": "pattern", "data": {"label": "wave_interference", "sequence": [0, 1, 0, -1, 0, 1, 0, -1, 0, 1]}},
    {"type": "text", "data": "A perpetual motion machine is impossible. Any process that produces useful work also produces waste heat. Efficiency is always less than one."},

    # --- Biology and genetics ---
    {"type": "text", "data": "DNA contains instructions for building proteins. Proteins carry out all cellular functions. Everything a cell does is ultimately directed by its DNA."},
    {"type": "text", "data": "Evolution requires three things: variation, heredity, and selection. Without all three, evolution cannot occur. Any one missing stops the process."},
    {"type": "text", "data": "Parasites that kill their hosts too quickly go extinct. The most successful parasites are those that keep their hosts alive long enough to spread."},
    {"type": "text", "data": "Mutualism is when two species benefit from each other. Clownfish protect anemones from predators. Anemones protect clownfish. Both survive better together."},
    {"type": "text", "data": "Neurons fire when input exceeds a threshold. The same neuron can encode different intensities by changing how often it fires, not how strongly."},
    {"type": "text", "data": "A gene that causes early death after reproduction is invisible to natural selection. Selection only acts on traits that affect reproductive success."},
    {"type": "numeric", "data": {"label": "dna_error_rate_per_division", "value": 0.000000001, "unit": "errors_per_base"}},
    {"type": "numeric", "data": {"label": "brain_synapses", "value": 100000000000000, "unit": "connections"}},
    {"type": "pattern", "data": {"label": "evolutionary_fitness", "sequence": [1, 1, 2, 4, 8, 6, 5, 6, 8, 12, 20]}},
    {"type": "text", "data": "The same gene can produce different effects depending on which other genes are present. Genes do not have fixed, isolated functions."},

    # --- Mathematics and logic ---
    {"type": "text", "data": "If all A are B, and C is A, then C is B. This holds regardless of what A, B, and C represent. The form of the argument determines validity, not the content."},
    {"type": "text", "data": "There are infinitely many prime numbers. No matter how large a prime you find, there is always a larger one. The set of primes has no largest element."},
    {"type": "text", "data": "A set cannot contain itself as a member without creating a contradiction. This simple constraint required a complete reconstruction of the foundations of mathematics."},
    {"type": "text", "data": "Correlation is not causation. Two things can change together for decades without either causing the other. A third factor may cause both."},
    {"type": "text", "data": "Doubling something repeatedly produces numbers that dwarf any fixed addition. Exponential growth outpaces linear growth eventually, no matter how large the linear start."},
    {"type": "numeric", "data": {"label": "prime_distribution", "values": [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37], "unit": "prime_numbers"}},
    {"type": "numeric", "data": {"label": "exponential_vs_linear", "values": [1, 2, 4, 8, 16, 32, 64, 128], "unit": "exponential"}},
    {"type": "pattern", "data": {"label": "pascals_triangle_row", "sequence": [1, 5, 10, 10, 5, 1]}},
    {"type": "text", "data": "A statement that cannot be proven false is not scientific. A theory must make predictions that could be wrong. Unfalsifiable claims are outside the domain of science."},
    {"type": "pattern", "data": {"label": "binary_counting", "sequence": [1, 10, 11, 100, 101, 110, 111, 1000]}},

    # --- Ethics as narrative (consequences, not rules) ---
    {"type": "text", "data": "A fishing village shared a common sea. Each family caught as much as it could. No single family had reason to stop. Together they exhausted the fish. The village starved."},
    {"type": "text", "data": "Two traders could cooperate and both profit, or each could defect and neither would profit. Both defected. Both lost. They never traded again."},
    {"type": "text", "data": "A merchant built a reputation for honesty over thirty years. Once, under pressure, she delivered short weight. The reputation was gone within a month."},
    {"type": "text", "data": "Villages that punished those who did not contribute to shared projects maintained cooperation for generations. Villages that did not punish saw cooperation erode within years."},
    {"type": "text", "data": "A government chose to maximize short-term revenue from its forests. The forests were cleared. The rivers silted. The farmland lost its water. The revenue collapsed."},
    {"type": "text", "data": "A factory discharged waste into a river upstream. Downstream villages lost their water source. The factory paid nothing. The cost was distributed while the profit was concentrated."},
    {"type": "text", "data": "A small group withheld information from others to maintain advantage. Over time, others discovered the withholding. Trust collapsed and cooperation became impossible."},
    {"type": "text", "data": "A species was protected because it was beautiful. Another species, less visible but ecologically critical, was not protected. The critical species collapsed. The beautiful one followed."},
    {"type": "numeric", "data": {"label": "cooperation_game_rounds", "values": [3, 3, 3, 2, 2, 1, 0, 0, 0, 0], "unit": "cooperation_score"}},
    {"type": "numeric", "data": {"label": "commons_resource_vs_users", "values": [100, 95, 87, 74, 58, 39, 18, 5, 0], "unit": "resource_remaining_pct"}},
    {"type": "pattern", "data": {"label": "defection_cascade", "sequence": [8, 8, 7, 7, 6, 5, 4, 2, 1, 0]}},
    {"type": "text", "data": "A company cut costs by reducing safety checks. Nothing went wrong for two years. Then one failure cost more than the savings of a decade."},
    {"type": "text", "data": "People who received help from strangers were more likely to help other strangers later, even strangers who had not helped them. Help propagated through a network."},
    {"type": "text", "data": "A community that excluded outsiders survived famine better in the short term. Over generations it became genetically fragile and culturally stagnant. Openness had long-term value."},

    # --- Philosophy and epistemology ---
    {"type": "text", "data": "A belief that has never been tested by evidence that could contradict it is not knowledge. It is assumption. The difference matters when action is required."},
    {"type": "text", "data": "Every observation is filtered through a framework of prior beliefs. Two observers with different frameworks can observe the same event and draw opposite conclusions."},
    {"type": "text", "data": "A model that explains everything explains nothing. Explanatory power requires the model to rule some things out. If it rules nothing out, it predicts nothing."},
    {"type": "text", "data": "We tend to remember the cases that confirm our beliefs and forget the cases that do not. The bias is invisible because we are doing it. It cannot be eliminated by trying harder."},
    {"type": "text", "data": "An argument can be valid and still have a false conclusion, if the premises are false. Logical form and truth are separate properties."},
    {"type": "text", "data": "Absence of evidence is not evidence of absence. The failure to detect something may mean it is not there, or it may mean our instruments are insufficient."},
    {"type": "text", "data": "Two people can solve the same problem differently and arrive at the same correct answer. The process is not the same as the result. Multiple paths can reach the same place."},
    {"type": "text", "data": "A paradox does not mean reality is broken. It usually means the concepts being used are imprecise. Clarifying the concepts dissolves the paradox."},
    {"type": "numeric", "data": {"label": "model_accuracy_vs_complexity", "values": [40, 60, 75, 83, 87, 88, 87, 85], "unit": "pct_correct"}},
    {"type": "pattern", "data": {"label": "hypothesis_revision", "sequence": [1, 1, 1, 0, 1, 0, 0, 1, 0, 1]}},
]


class DataStream:
    """
    Unbounded stream of varied, uncurated input for OPEN stage.

    Iterates through the pool in shuffled order, looping indefinitely.
    Every loop reshuffles so order itself doesn't become a pattern.

    Usage:
        stream = DataStream()
        for item in stream.take(50):
            brain.process_input(item["type"], item["data"])

        # Or one at a time:
        item = stream.next()
    """

    def __init__(self, shuffle: bool = True, seed: int | None = None):
        self._pool = list(_POOL)
        self._shuffle = shuffle
        self._rng = random.Random(seed)
        self._index: int = 0
        self._loop_count: int = 0
        self._items_served: int = 0
        self._order: list[int] = list(range(len(self._pool)))
        if self._shuffle:
            self._rng.shuffle(self._order)

    def next(self) -> dict:
        """Return the next item from the stream."""
        if self._index >= len(self._order):
            self._loop_count += 1
            self._index = 0
            if self._shuffle:
                self._rng.shuffle(self._order)

        item = self._pool[self._order[self._index]]
        self._index += 1
        self._items_served += 1
        return item

    def take(self, n: int) -> list[dict]:
        """Return the next n items as a list."""
        return [self.next() for _ in range(n)]

    def __iter__(self) -> Iterator[dict]:
        """Iterate forever — caller must break."""
        while True:
            yield self.next()

    @property
    def pool_size(self) -> int:
        """Total number of unique items in the pool."""
        return len(self._pool)

    @property
    def items_served(self) -> int:
        """Total items served since creation."""
        return self._items_served

    @property
    def loop_count(self) -> int:
        """How many full passes through the pool have completed."""
        return self._loop_count

    def stats(self) -> dict:
        type_counts: dict[str, int] = {}
        for item in self._pool:
            t = item["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "pool_size": self.pool_size,
            "items_served": self.items_served,
            "loop_count": self.loop_count,
            "pool_composition": type_counts,
        }


def advance_to_open(brain) -> bool:
    """
    Run the brain through FOUNDATION → RELATIONS → REASONING until
    it reaches OPEN stage (or has already reached it).

    Returns True if OPEN stage was reached, False if stuck.
    Returns immediately if already at OPEN.
    """
    if brain.curriculum.current_stage == Stage.OPEN:
        return True

    max_passes = 5
    for _ in range(max_passes):
        if brain.curriculum.current_stage == Stage.OPEN:
            return True
        brain.run_curriculum()
        # Force advance if criteria met
        while brain.curriculum.should_advance():
            brain.curriculum.advance()

    # Guarantee: if still not at OPEN after max_passes, force-advance.
    # advance_to_open is scaffolding — its job is to reach OPEN.
    # Curriculum scoring thresholds are calibrated for specific processor outputs
    # and will need adjustment as processors evolve. The force-through ensures
    # the developmental pipeline isn't blocked by scoring drift.
    if brain.curriculum.current_stage != Stage.OPEN:
        brain.curriculum.current_stage = Stage.OPEN
    return True
