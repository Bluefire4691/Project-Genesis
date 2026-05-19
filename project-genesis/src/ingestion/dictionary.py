"""
Local Dictionary — offline fallback for the knowledge feeder.

When Wikipedia is unavailable or returns no result for a concept,
the feeder consults this dictionary before giving up.

Entries are written to produce clean relation edges through the text
processor — sentences use the causal/relational verbs the processor
recognises (causes, requires, enables, controls, prevents, is a,
contains, eats/preys on, affects). Two to four sentences each.

Coverage: foundational concepts in math, logic, physics, biology,
language, and social life — the concepts most likely to surface as
curiosity targets in early Genesis sessions.
"""

ENTRIES: dict[str, str] = {

    # ---- Mathematics ----
    "number": (
        "A number is a symbol that represents a quantity. "
        "Numbers enable comparison between quantities. "
        "Larger numbers represent greater quantity than smaller numbers."
    ),
    "addition": (
        "Addition is an operation that combines two quantities into a larger quantity. "
        "Addition requires two or more numbers. "
        "Addition is the inverse of subtraction."
    ),
    "subtraction": (
        "Subtraction is an operation that removes one quantity from another. "
        "Subtraction requires a starting quantity and an amount to remove. "
        "Subtraction is the inverse of addition."
    ),
    "multiplication": (
        "Multiplication combines a number with itself a given number of times. "
        "Multiplication requires two numbers called factors. "
        "Multiplication is the inverse of division."
    ),
    "division": (
        "Division splits a quantity into equal parts. "
        "Division requires a dividend and a divisor. "
        "Division is the inverse of multiplication."
    ),
    "fraction": (
        "A fraction is a number that represents part of a whole. "
        "A fraction contains a numerator and a denominator. "
        "Fractions enable description of quantities smaller than one."
    ),
    "zero": (
        "Zero is a number that represents the absence of quantity. "
        "Adding zero to any number does not affect that number. "
        "Multiplying any number by zero produces zero."
    ),
    "prime": (
        "A prime number is a number that only divides evenly by one and itself. "
        "Two, three, five, and seven are prime numbers. "
        "There are infinitely many prime numbers — no largest prime exists."
    ),
    "infinity": (
        "Infinity is a concept that represents a quantity without limit. "
        "Adding one to any number produces a larger number, so counting never ends. "
        "Infinity is not a number but a property of certain sets and processes."
    ),
    "probability": (
        "Probability is a measure of how likely an event is to occur. "
        "A probability of one means the event is certain. "
        "A probability of zero means the event cannot occur."
    ),
    "equation": (
        "An equation is a statement that two expressions are equal. "
        "Solving an equation requires finding the value that makes both sides equal. "
        "Equations enable description of relationships between quantities."
    ),
    "geometry": (
        "Geometry is a branch of mathematics that studies shapes and their properties. "
        "A triangle contains three sides and three angles. "
        "A circle is a shape where all points on its boundary are equally distant from its center."
    ),
    "sequence": (
        "A sequence is an ordered list of numbers or items. "
        "Each item in a sequence occupies a specific position. "
        "Recognising a pattern in a sequence enables prediction of the next item."
    ),
    "symmetry": (
        "Symmetry is a property of a shape that looks the same after a transformation. "
        "A square contains four axes of symmetry. "
        "Symmetry enables identification of patterns in shapes and structures."
    ),

    # ---- Logic ----
    "logic": (
        "Logic is the study of valid reasoning. "
        "A valid argument requires premises that support its conclusion. "
        "Logic enables evaluation of arguments regardless of their subject matter."
    ),
    "implication": (
        "An implication is a logical relationship of the form if A then B. "
        "If A is true, an implication requires that B is also true. "
        "If B is false, an implication requires that A is also false."
    ),
    "contradiction": (
        "A contradiction is a statement that cannot be true. "
        "A contradiction contains two claims that cannot both be true at the same time. "
        "Finding a contradiction in a set of beliefs requires revising at least one belief."
    ),
    "category": (
        "A category is a group of things that share a common property. "
        "A mammal is a category that contains all warm-blooded animals that feed their young with milk. "
        "Belonging to a category enables inference of properties shared by all members."
    ),
    "evidence": (
        "Evidence is information that supports or weakens a conclusion. "
        "More evidence increases confidence in a conclusion. "
        "Evidence that contradicts a conclusion requires revision of the conclusion or the evidence."
    ),
    "inference": (
        "An inference is a conclusion reached from available information. "
        "Valid inference requires that the conclusion follows from the premises. "
        "Inference enables derivation of new knowledge from existing knowledge."
    ),
    "argument": (
        "An argument is a set of premises combined with a conclusion. "
        "A valid argument requires that the conclusion follows from the premises. "
        "An argument can be valid even if its premises are false."
    ),

    # ---- Physics ----
    "gravity": (
        "Gravity is a force that attracts objects with mass toward each other. "
        "Gravity causes objects to fall toward Earth when released. "
        "Gravity controls the orbits of planets around the sun."
    ),
    "energy": (
        "Energy is the capacity to do work. "
        "Energy is conserved — it changes form but is never created or destroyed. "
        "Energy enables all physical processes including motion, heat, and chemical reactions."
    ),
    "force": (
        "A force is a push or pull that acts on an object. "
        "Force causes objects to accelerate, decelerate, or change direction. "
        "Every force requires an equal and opposite reaction force."
    ),
    "mass": (
        "Mass is the amount of matter contained in an object. "
        "Greater mass requires greater force to produce the same acceleration. "
        "Mass affects the strength of gravitational attraction between objects."
    ),
    "temperature": (
        "Temperature is a measure of the average energy of particles in a substance. "
        "Higher temperature causes particles to move faster. "
        "Heat flows from high-temperature regions to low-temperature regions."
    ),
    "pressure": (
        "Pressure is force distributed over an area. "
        "Higher pressure affects objects by pushing harder per unit of area. "
        "Pressure in a fluid affects all surfaces it touches equally in all directions."
    ),
    "velocity": (
        "Velocity is a measure of the speed and direction of an object's motion. "
        "Changing velocity requires a force. "
        "Constant velocity means an object is not accelerating."
    ),
    "entropy": (
        "Entropy is a measure of disorder in a system. "
        "Entropy increases in isolated systems — order tends toward disorder. "
        "Maintaining order requires a continuous input of energy."
    ),
    "wave": (
        "A wave is a disturbance that transfers energy through a medium. "
        "Sound is a wave that requires air or another medium to travel. "
        "Light is a wave that enables vision and does not require a medium."
    ),
    "atom": (
        "An atom is the smallest unit of a chemical element. "
        "An atom contains a nucleus surrounded by electrons. "
        "Atoms combine to form molecules."
    ),
    "molecule": (
        "A molecule is two or more atoms bonded together. "
        "Water is a molecule that contains two hydrogen atoms and one oxygen atom. "
        "The properties of a molecule differ from the properties of its individual atoms."
    ),
    "electricity": (
        "Electricity is the flow of electric charge through a conductor. "
        "Electricity enables machines to operate by transferring energy to them. "
        "Electricity requires a closed circuit to flow continuously."
    ),
    "magnetism": (
        "Magnetism is a force that acts between magnetic materials. "
        "Opposite magnetic poles attract each other. "
        "Magnetism and electricity are related — each can produce the other."
    ),
    "light": (
        "Light is electromagnetic radiation that is visible to the eye. "
        "Light enables vision by carrying information from objects to eyes. "
        "Light travels faster than any other known thing."
    ),
    "sound": (
        "Sound is a vibration that travels through air or another medium. "
        "Sound requires a medium — it cannot travel through a vacuum. "
        "Higher frequency sound produces higher pitch."
    ),
    "friction": (
        "Friction is a force that opposes motion between two surfaces in contact. "
        "Friction converts kinetic energy into heat. "
        "Reducing friction enables smoother and faster movement."
    ),
    "momentum": (
        "Momentum is a property of a moving object determined by its mass and velocity. "
        "Greater mass or greater speed increases momentum. "
        "Momentum is conserved — the total momentum of a closed system does not change."
    ),
    "orbit": (
        "An orbit is a curved path that one object follows around another. "
        "Gravity causes planets to follow orbits around the sun. "
        "An orbit requires a balance between inward gravity and outward inertia."
    ),
    "oxygen": (
        "Oxygen is a gas that most living things require to produce energy. "
        "Photosynthesis produces oxygen as a byproduct. "
        "Burning fuel requires oxygen and releases energy."
    ),
    "carbon": (
        "Carbon is an element that forms the basis of all known living things. "
        "Carbon dioxide is produced when carbon-based fuels burn. "
        "Carbon atoms bond in many combinations, enabling a vast variety of molecules."
    ),
    "water": (
        "Water is a molecule that contains hydrogen and oxygen. "
        "All known living things require water to survive. "
        "Water enables chemical reactions inside cells."
    ),
    "matter": (
        "Matter is anything that contains mass and occupies space. "
        "Matter exists as solid, liquid, or gas depending on temperature and pressure. "
        "Energy is required to change matter from one state to another."
    ),

    # ---- Living things / Biology ----
    "cell": (
        "A cell is the smallest unit of life. "
        "Every living organism contains cells. "
        "A cell contains DNA, which controls all cellular functions."
    ),
    "dna": (
        "DNA is a molecule that contains the genetic instructions for building a living organism. "
        "DNA controls the production of proteins inside cells. "
        "DNA is copied when a cell divides, enabling inheritance."
    ),
    "protein": (
        "A protein is a molecule that carries out functions inside cells. "
        "Proteins are produced using instructions from DNA. "
        "Proteins enable digestion, movement, immune defence, and many other processes."
    ),
    "gene": (
        "A gene is a section of DNA that controls production of a specific protein. "
        "Genes are inherited — offspring receive genes from their parents. "
        "Genes affect the traits and characteristics of an organism."
    ),
    "evolution": (
        "Evolution is the change in inherited traits of a population over generations. "
        "Evolution requires variation, inheritance, and selection. "
        "Natural selection causes traits that improve survival to spread through a population."
    ),
    "mutation": (
        "A mutation is a change in the sequence of DNA. "
        "Most mutations are neutral or harmful. "
        "Occasionally a mutation enables improved survival and spreads through a population."
    ),
    "species": (
        "A species is a group of organisms that can reproduce with each other. "
        "Different species cannot produce fertile offspring together. "
        "Natural selection causes species to change over generations."
    ),
    "mammal": (
        "A mammal is a warm-blooded animal that feeds its young with milk. "
        "Mammals contain hair or fur. "
        "Dogs, cats, whales, and humans are all mammals."
    ),
    "photosynthesis": (
        "Photosynthesis is the process plants use to make food from sunlight, water, and carbon dioxide. "
        "Photosynthesis requires sunlight to operate. "
        "Photosynthesis produces oxygen as a byproduct."
    ),
    "predator": (
        "A predator is an animal that hunts and eats other animals. "
        "Predators control the population of their prey. "
        "Removing a predator from an ecosystem causes prey populations to increase rapidly."
    ),
    "prey": (
        "Prey is an animal that is hunted and eaten by a predator. "
        "Predators feed on prey to obtain energy. "
        "Prey populations affect predator populations — fewer prey causes fewer predators."
    ),
    "ecosystem": (
        "An ecosystem is a community of living organisms interacting with their environment. "
        "Every species in an ecosystem affects the other species. "
        "Removing a species from an ecosystem affects all organisms that depend on it."
    ),
    "habitat": (
        "A habitat is the environment where an organism naturally lives. "
        "Each species requires a specific habitat to survive. "
        "Destroying a habitat causes the species that depend on it to decline."
    ),
    "nutrient": (
        "A nutrient is a substance that living things require to grow and function. "
        "Plants absorb nutrients from soil through their roots. "
        "Animals obtain nutrients by eating plants or other animals."
    ),
    "reproduction": (
        "Reproduction is the process by which living things produce offspring. "
        "Reproduction requires genetic material from one or two parents. "
        "Without reproduction, a species disappears when its members die."
    ),
    "respiration": (
        "Respiration is the process by which cells release energy from food. "
        "Respiration requires oxygen in most organisms. "
        "Respiration produces carbon dioxide as a byproduct."
    ),
    "digestion": (
        "Digestion is the process of breaking food into molecules small enough to absorb. "
        "Digestion requires acids and enzymes. "
        "Digestion enables nutrients to enter the bloodstream."
    ),
    "brain": (
        "The brain is the organ that processes information and controls behaviour. "
        "The brain contains billions of neurons connected by synapses. "
        "The brain controls movement, sensation, memory, and decision-making."
    ),
    "neuron": (
        "A neuron is a cell that transmits electrical signals in the nervous system. "
        "Neurons connect to each other through synapses. "
        "Networks of neurons enable processing of information and production of behaviour."
    ),
    "synapse": (
        "A synapse is a connection between two neurons. "
        "Signals cross synapses using chemical messengers. "
        "The strength of synapses changes with use, enabling learning."
    ),
    "immune": (
        "The immune system is a network of cells that defends the body against pathogens. "
        "The immune system recognises and attacks foreign substances. "
        "The immune system remembers past infections, enabling faster responses to them."
    ),
    "virus": (
        "A virus is a microscopic agent that infects living cells to reproduce. "
        "A virus requires a living host cell to replicate. "
        "Some viruses cause disease by damaging or killing the cells they infect."
    ),
    "bacteria": (
        "Bacteria are single-celled organisms that live in almost every environment. "
        "Some bacteria cause disease by producing toxins or destroying tissue. "
        "Many bacteria are beneficial — they decompose waste and aid digestion."
    ),
    "fungus": (
        "A fungus is an organism that feeds by decomposing dead organic matter. "
        "Fungi return nutrients to the soil by breaking down dead plants and animals. "
        "Fungi are neither plants nor animals."
    ),
    "seed": (
        "A seed contains a plant embryo and stored nutrients. "
        "A seed requires water and warmth to germinate. "
        "A germinated seed grows into a plant that produces more seeds."
    ),
    "root": (
        "A root is the part of a plant that anchors it in the soil. "
        "Roots absorb water and nutrients from the soil. "
        "Without roots, a plant cannot obtain the water it requires."
    ),
    "leaf": (
        "A leaf is the part of a plant where most photosynthesis takes place. "
        "Leaves contain chlorophyll, which absorbs sunlight. "
        "Leaves enable gas exchange — taking in carbon dioxide and releasing oxygen."
    ),
    "chlorophyll": (
        "Chlorophyll is a pigment found in plant cells. "
        "Chlorophyll absorbs sunlight and enables photosynthesis. "
        "Chlorophyll causes plants to appear green."
    ),
    "insect": (
        "An insect is a small animal with six legs and a three-part body. "
        "Insects are the most numerous animals on Earth. "
        "Many insects enable plant reproduction by carrying pollen between flowers."
    ),
    "pollination": (
        "Pollination is the transfer of pollen from one flower to another. "
        "Pollination enables fertilisation and the production of seeds. "
        "Insects, birds, and wind are the main agents that carry out pollination."
    ),

    # ---- Social / Human ----
    "language": (
        "Language is a system of symbols used to communicate ideas. "
        "Language enables coordination between individuals who cannot observe each other directly. "
        "Language requires a shared code between speakers and listeners."
    ),
    "cooperation": (
        "Cooperation is working together toward a shared goal. "
        "Cooperation enables groups to achieve things no individual could accomplish alone. "
        "Cooperation requires trust that others will contribute their share."
    ),
    "trust": (
        "Trust is the belief that another will act reliably and honestly. "
        "Trust enables cooperation between people who cannot monitor each other closely. "
        "Trust is built slowly through consistent behaviour and lost quickly through betrayal."
    ),
    "rule": (
        "A rule is a statement that describes what is permitted and what is not. "
        "Rules enable many individuals to share resources without constant conflict. "
        "Rules require enforcement to remain effective."
    ),
    "community": (
        "A community is a group of individuals sharing a place or purpose. "
        "Communities enable cooperation on tasks too large for individuals. "
        "Strong communities require shared norms and enforcement of those norms."
    ),
    "trade": (
        "Trade is the exchange of goods or services between parties. "
        "Trade enables specialisation — each party produces what it does best and exchanges the surplus. "
        "Trade requires trust that both parties will honour the exchange."
    ),
    "communication": (
        "Communication is the transfer of information from one mind to another. "
        "Communication requires a shared code between sender and receiver. "
        "Effective communication enables coordination and cooperation."
    ),
    "fairness": (
        "Fairness is treating similar cases in the same way. "
        "Perceived fairness enables cooperation within groups. "
        "Perceived unfairness causes defection and breakdown of cooperation."
    ),
    "punishment": (
        "Punishment is a negative consequence applied for violating a rule. "
        "Punishment deters future rule violations. "
        "Groups that enforce punishment maintain cooperation longer than groups that do not."
    ),

    # ---- Time and change ----
    "time": (
        "Time is the dimension in which events occur in sequence. "
        "Events happen before and after each other. "
        "Time enables change — without time, nothing could change."
    ),
    "cause": (
        "A cause is what makes an event happen. "
        "Every event requires at least one cause. "
        "Identifying a cause enables prediction and prevention of its effects."
    ),
    "change": (
        "Change is a transition from one state to another. "
        "Change requires a cause — things do not change without something acting on them. "
        "Some changes are fast and visible; others are slow and only apparent over long periods."
    ),
    "cycle": (
        "A cycle is a sequence of events that repeats. "
        "Day and night form a cycle caused by Earth's rotation. "
        "Seasons form a cycle caused by Earth's orbit and tilt."
    ),
    "growth": (
        "Growth is an increase in size, number, or complexity over time. "
        "Growth requires energy and resources. "
        "Living things grow by adding new cells."
    ),
    "decay": (
        "Decay is the process of breaking down into simpler parts. "
        "Fungi and bacteria cause decay by breaking down dead organic matter. "
        "Decay enables nutrients to return to the soil."
    ),
    "adaptation": (
        "Adaptation is a trait that enables a species to survive in its environment. "
        "Adaptations arise through natural selection over many generations. "
        "A species that cannot adapt to environmental change is at risk of extinction."
    ),
    "extinction": (
        "Extinction is the permanent disappearance of a species. "
        "Extinction occurs when a species cannot survive environmental change. "
        "Extinction removes a species from its ecosystem, affecting all organisms that depended on it."
    ),

    # ---- Environment / Earth ----
    "soil": (
        "Soil is a mixture of minerals, organic matter, water, and air. "
        "Soil enables plant growth by providing nutrients, water, and anchorage for roots. "
        "Healthy soil contains bacteria, fungi, and small animals that recycle nutrients."
    ),
    "river": (
        "A river is a large natural stream of water that flows toward the sea. "
        "Rivers are formed by rainfall collecting and flowing downhill. "
        "Rivers shape the landscape by eroding rock and depositing sediment."
    ),
    "ocean": (
        "An ocean is a vast body of salt water covering most of Earth's surface. "
        "Oceans regulate Earth's temperature by absorbing and releasing heat. "
        "Oceans contain the majority of living organisms on Earth."
    ),
    "forest": (
        "A forest is a dense area of trees and other plants. "
        "Forests produce oxygen, absorb carbon dioxide, and regulate local climate. "
        "Forests contain more species of living things per unit area than most other habitats."
    ),
    "atmosphere": (
        "The atmosphere is the layer of gases that surrounds Earth. "
        "The atmosphere contains oxygen, which most living things require. "
        "The atmosphere controls Earth's temperature by trapping heat from the sun."
    ),
    "climate": (
        "Climate is the long-term pattern of weather in a region. "
        "Climate controls which species can survive in a region. "
        "Changing climate affects all organisms adapted to the previous conditions."
    ),
    "weather": (
        "Weather is the short-term state of the atmosphere at a place and time. "
        "Weather affects daily life — rain, wind, and temperature influence what organisms can do. "
        "Weather is driven by heat from the sun and the movement of air and water."
    ),
}


class LocalDictionary:
    """
    Offline knowledge source — used by the feeder when Wikipedia fails.

    Entries are short definitions written to produce clean relation edges
    through the text processor.
    """

    def lookup(self, concept: str) -> str | None:
        """
        Return definition text for concept, or None if not found.

        Tries exact lowercase match, then first word only (handles
        "immune system" → "immune", "solar energy" → lookup fails gracefully).
        """
        norm = concept.strip().lower()
        if norm in ENTRIES:
            return ENTRIES[norm]
        # Try first word — catches "immune system", "carbon dioxide", etc.
        first = norm.split()[0] if norm else ""
        if first and first != norm and first in ENTRIES:
            return ENTRIES[first]
        return None

    @property
    def size(self) -> int:
        return len(ENTRIES)
