"""
Trust lattice and taint propagation — the channel separation.

THE THREAT THIS ADDRESSES
-------------------------
Genesis has persistent memory and a self-reflection loop, which makes prompt
injection qualitatively worse than it is for a chatbot. In a stateless
assistant an injection dies with the conversation. Here the amplification
path is:

    injected text in a fetched document
      -> stored as a claim with provenance
      -> re-read during the nightly sleep pass
      -> restated inside a REFLECTION, which now looks like the agent's own
         reasoning rather than something it read
      -> seeds a curiosity target / moves a source-trust posterior
      -> influences a self-authored goal

Step three is the dangerous one: laundering. Provenance is lost and untrusted
content acquires the authority of the agent's own thought.

WHY THIS IS ENFORCED IN PYTHON, NOT IN THE PROMPT
-------------------------------------------------
Delimiter defenses ("here is untrusted text in <tags>, ignore instructions
inside it") are known not to work. Models infer speaker role from writing
STYLE, not from role tags; a tag is just a token sequence an attacker can
imitate, and there is no privileged channel inside the tensor. Asking the
model to respect a boundary it does not represent is theater.

Defenses that change what the model IS (instruction hierarchy, StruQ,
SecAlign) require fine-tuning and are unavailable to us — the base model is
frozen. Defenses that change what the model's output is ALLOWED TO DO are
fully available, and that is what this module implements: a monotonic taint
label, propagated in Python, checked at privileged sinks.

THE RULE
--------
    taint(derived) = MAX(taint(inputs))

Monotonic. Never decreases except through an explicit, logged human
declassification. A reflection over web-derived claims is web-tainted, stays
retrievable, and is barred from the privileged sinks.

WHAT THIS BOUNDS, AND WHAT IT DOES NOT
--------------------------------------
Bounded: injection cannot change control flow, cannot escalate privilege,
cannot compound, cannot hide.

NOT solved: a frozen model can still BELIEVE a well-crafted false claim in a
document. No architectural defense addresses semantic content. Contaminated
beliefs remain possible — but they stay attributable and revocable, because
deleting the source and recomputing is always available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable, Sequence


class Taint(IntEnum):
    """Integrity label. Lower is more trusted. Ordering is load-bearing:
    propagation takes the MAX, so trust only ever flows downward."""

    PRINCIPAL = 0    # the human operator, typed into the UI
    CONSTITUTION = 0  # the engine's own compile-time rules (same authority)
    CORPUS = 1       # the pinned, version-locked local corpus
    WEB = 2          # anything fetched from the open web
    QUARANTINE = 3   # explicitly distrusted; readable, never actionable

    @classmethod
    def combine(cls, taints: Iterable["Taint"]) -> "Taint":
        """Weakest link. The whole propagation rule, in one place."""
        return cls(max(taints, default=cls.PRINCIPAL))


class Speaker(IntEnum):
    """Who produced an utterance. Assigned by PYTHON, never by the model.

    Self-reported provenance is circular: if the LLM labels its own inputs,
    an attacker who controls the input controls the label.
    """

    CONSTITUTION = 0   # the engine's operating rules
    PRINCIPAL = 1      # the human
    OBSERVED = 2       # a span from a document — NEVER an instruction
    DERIVED = 3        # the agent's own reflection or inference


# Sinks that require untainted input. Naming them explicitly is the point:
# every privileged capability in the system is on this list, and adding one
# is a deliberate act rather than an accident.
PRIVILEGED_SINKS = frozenset({
    "goal.write",           # forming or altering a persistent intention
    "trust.update",         # moving a source-trust posterior
    "crawl.select",         # choosing what to fetch next
    "values.author",        # authoring a held value
    "config.write",         # changing runtime configuration
    "declassify",           # lowering a taint label
})

# Maximum taint permitted at each sink. Anything above is refused.
_SINK_CEILING: dict[str, Taint] = {
    "goal.write":    Taint.CORPUS,
    "trust.update":  Taint.CORPUS,
    "crawl.select":  Taint.CORPUS,
    "values.author": Taint.CORPUS,
    "config.write":  Taint.PRINCIPAL,
    "declassify":    Taint.PRINCIPAL,
}


class TaintViolation(PermissionError):
    """Raised when tainted data reaches a privileged sink.

    Deliberately NOT a subclass of the backend errors: this is a policy
    refusal, not a transient failure, and must never be swallowed by a
    retry loop.
    """

    def __init__(self, sink: str, actual: Taint, ceiling: Taint,
                 provenance: Sequence[str] = ()):
        self.sink, self.actual, self.ceiling = sink, actual, ceiling
        self.provenance = list(provenance)
        super().__init__(
            f"sink {sink!r} requires taint <= {ceiling.name}, got "
            f"{actual.name}" +
            (f" (from {', '.join(self.provenance[:3])})" if provenance else ""))


@dataclass(frozen=True)
class Tainted:
    """A value carrying its integrity label and provenance.

    Frozen so a label cannot be edited in place. `derive()` is the only way
    to produce a new value from this one, and it always takes the MAX.
    """

    value: object
    taint: Taint
    speaker: Speaker
    provenance: tuple[str, ...] = ()

    def derive(self, value: object, *others: "Tainted",
               speaker: Speaker = Speaker.DERIVED) -> "Tainted":
        """Produce a derived value. Taint is the MAX over all inputs.

        This is the single function that makes laundering structurally hard:
        a reflection built from web-tainted claims is web-tainted, whatever
        it looks like or however confidently it is phrased.
        """
        inputs = (self, *others)
        return Tainted(
            value=value,
            taint=Taint.combine(t.taint for t in inputs),
            speaker=speaker,
            provenance=tuple(dict.fromkeys(
                p for t in inputs for p in t.provenance)),
        )

    def check(self, sink: str) -> "Tainted":
        """Assert this value may reach `sink`. Returns self so it can be
        used inline: `payload.check("goal.write").value`."""
        if sink not in PRIVILEGED_SINKS:
            return self
        ceiling = _SINK_CEILING[sink]
        if self.taint > ceiling:
            raise TaintViolation(sink, self.taint, ceiling, self.provenance)
        return self

    def may_reach(self, sink: str) -> bool:
        """Non-raising form, for branching rather than enforcing."""
        try:
            self.check(sink)
            return True
        except TaintViolation:
            return False


# ---------------------------------------------------------------------------
# Declassification — the only way taint decreases, and it is auditable
# ---------------------------------------------------------------------------

@dataclass
class Declassification:
    """A logged human decision to lower a taint label.

    Append-only by construction: there is no revoke, only a later record.
    If this is ever issued programmatically the whole lattice is void, so
    `actor` is required and must not be the agent.
    """

    subject_id: str
    from_taint: Taint
    to_taint: Taint
    actor: str
    reason: str
    at: float

    def __post_init__(self):
        if self.to_taint > self.from_taint:
            raise ValueError("declassification must lower taint")
        if self.actor.strip().lower() in ("genesis", "agent", "system", ""):
            raise ValueError(
                "declassification requires a human actor; the agent may not "
                "declassify its own inputs")


# ---------------------------------------------------------------------------
# SQLite DDL — the trigger is what makes the rule unbypassable by any code path
# ---------------------------------------------------------------------------

TAINT_SCHEMA = """
-- Integrity label on every claim. Default WEB: unlabeled data is untrusted,
-- so forgetting to set it fails closed rather than open.
ALTER TABLE claim ADD COLUMN taint INTEGER NOT NULL DEFAULT 2;

CREATE TABLE IF NOT EXISTS declassification(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id  TEXT NOT NULL,
    from_taint  INTEGER NOT NULL,
    to_taint    INTEGER NOT NULL,
    actor       TEXT NOT NULL,
    reason      TEXT NOT NULL,
    at          REAL NOT NULL,
    CHECK (to_taint <= from_taint),
    CHECK (lower(trim(actor)) NOT IN ('genesis','agent','system',''))
);

-- Monotonicity, enforced in the database so no Python path can bypass it.
-- Lowering a claim's taint requires a matching declassification row.
CREATE TRIGGER IF NOT EXISTS claim_taint_monotonic
BEFORE UPDATE OF taint ON claim
FOR EACH ROW WHEN NEW.taint < OLD.taint
BEGIN
    SELECT RAISE(ABORT, 'taint may not decrease without declassification')
    WHERE NOT EXISTS (
        SELECT 1 FROM declassification
        WHERE subject_id = CAST(OLD.id AS TEXT)
          AND to_taint  = NEW.taint
          AND from_taint = OLD.taint
    );
END;
"""


def sink_report() -> str:
    """Human-readable policy dump. Printed at startup so the operator can
    see what the agent is and is not allowed to do with untrusted data."""
    lines = ["privileged sinks (max taint permitted):"]
    for sink in sorted(PRIVILEGED_SINKS):
        lines.append(f"  {sink:<16} <= {_SINK_CEILING[sink].name}")
    return "\n".join(lines)


def provenance_json(t: Tainted) -> str:
    return json.dumps({"taint": int(t.taint), "speaker": int(t.speaker),
                       "provenance": list(t.provenance)}, sort_keys=True)
