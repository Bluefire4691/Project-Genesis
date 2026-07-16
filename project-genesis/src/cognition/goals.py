"""
GoalEngine — M29 Persistent Goal Formation.

A curiosity directive is a gap; a goal is an intention.  Directives are
reactive (formed when prediction error is high, resolved when a few edges
appear).  Goals persist across sessions until Genesis genuinely understands
the topic — measured by its own self-model, not by a fixed edge count.

Goals come from two places:
  - conversation: "remember to learn about plate tectonics" forms a goal
    that survives shutdowns and is worked on without being re-stated
  - self: pattern transfer notices a concept playing the same structural
    role as something Genesis understands, with unexplained edges — the
    system decides for itself that it wants to close that gap

Lifecycle:
  active    — being pursued; its topic is pushed into the curiosity frontier
              every reflection so the feeder reads about it
  satisfied — the self-model verdict for the topic reached 'solid'
              (Genesis can genuinely speak to it).  Kept forever — a
              satisfied goal is part of Genesis's history, never deleted.

Table lives in the main memory DB alongside memories, relations, decisions.
Every state change is recorded in the M28 DecisionLog by the orchestrator.
"""

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator

# An intention list needs focus: past this many active goals, new ones are
# declined until something is satisfied.  Keeps the curiosity frontier from
# being monopolised by stale intentions.
_MAX_ACTIVE = 12

# Directive weight for goal topics — above analog-curiosity (0.82) because a
# goal is an explicit intention, not a hunch.
_GOAL_DIRECTIVE_WEIGHT = 0.9


@dataclass
class Goal:
    id: int
    topic: str
    statement: str      # first-person intention, e.g. "understand plate tectonics"
    origin: str         # "conversation" | "self"
    status: str         # "active" | "satisfied"
    formed_at: float
    satisfied_at: float | None

    @property
    def age_days(self) -> float:
        return (time.time() - self.formed_at) / 86400.0


class GoalEngine:
    """Persistent intentions, satisfied by measured understanding."""

    def __init__(self, brain: "Orchestrator") -> None:
        self._brain = brain
        self._conn = brain.memory._long_term.conn
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                topic        TEXT    NOT NULL,
                statement    TEXT    NOT NULL,
                origin       TEXT    NOT NULL,
                status       TEXT    NOT NULL DEFAULT 'active',
                formed_at    REAL    NOT NULL,
                satisfied_at REAL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_goals_status ON goals (status)
        """)
        self._conn.commit()

    def _log_error(self, label: str, exc: Exception) -> None:
        try:
            self._brain.survival.resilience.error_log.log(label, exc)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Formation
    # ------------------------------------------------------------------

    def form(self, topic: str, origin: str = "conversation",
             statement: str | None = None) -> Goal | None:
        """
        Form a goal to understand `topic`.  Returns the Goal, or None if a
        goal for this topic already exists (any status) or the active list
        is full.  Never raises.
        """
        topic = topic.strip().lower()
        if not topic:
            return None
        try:
            exists = self._conn.execute(
                "SELECT 1 FROM goals WHERE topic = ?", (topic,)
            ).fetchone()
            if exists:
                return None
            if len(self.active()) >= _MAX_ACTIVE:
                return None
            statement = statement or f"understand {topic}"
            cur = self._conn.execute(
                """INSERT INTO goals (topic, statement, origin, status, formed_at)
                   VALUES (?, ?, ?, 'active', ?)""",
                (topic, statement, origin, time.time()),
            )
            self._conn.commit()
            return Goal(id=cur.lastrowid, topic=topic, statement=statement,
                        origin=origin, status="active",
                        formed_at=time.time(), satisfied_at=None)
        except Exception as exc:
            self._log_error("goals.form", exc)
            return None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def _rows(self, where: str, params: tuple = ()) -> list[Goal]:
        try:
            rows = self._conn.execute(
                f"""SELECT id, topic, statement, origin, status,
                           formed_at, satisfied_at
                    FROM goals {where} ORDER BY formed_at DESC""",
                params,
            ).fetchall()
            return [Goal(*r) for r in rows]
        except Exception as exc:
            self._log_error("goals.query", exc)
            return []

    def active(self) -> list[Goal]:
        return self._rows("WHERE status = 'active'")

    def satisfied(self, limit: int = 10) -> list[Goal]:
        return self._rows("WHERE status = 'satisfied'")[:limit]

    def all_goals(self, limit: int = 25) -> list[Goal]:
        return self._rows("")[:limit]

    # ------------------------------------------------------------------
    # Pursuit — wire intentions into the curiosity frontier
    # ------------------------------------------------------------------

    def push_directives(self) -> int:
        """
        Ensure every active goal's topic is in the curiosity frontier so the
        feeder keeps reading about it.  This is what 'worked on without being
        re-stated' means: the goal re-arms its own directive every reflection,
        even across sessions.  Returns how many directives were (re)added.
        """
        brain = self._brain
        added = 0
        try:
            for goal in self.active():
                if goal.topic not in brain._curiosity_directives:
                    brain._curiosity_directives[goal.topic] = _GOAL_DIRECTIVE_WEIGHT
                    added += 1
            if added:
                brain._save_directives()
        except Exception as exc:
            self._log_error("goals.push_directives", exc)
        return added

    # ------------------------------------------------------------------
    # Satisfaction — measured, not counted
    # ------------------------------------------------------------------

    def check_satisfaction(self) -> list[str]:
        """
        Mark active goals satisfied when the self-model verdict for their
        topic reaches 'solid' — Genesis can genuinely speak to it (Stage 3
        answer territory).  Returns the topics satisfied this pass.
        """
        brain = self._brain
        done: list[str] = []
        try:
            for goal in self.active():
                assessment = brain.self_model(goal.topic)
                if assessment.get("verdict") == "solid":
                    self._conn.execute(
                        """UPDATE goals SET status='satisfied', satisfied_at=?
                           WHERE id=?""",
                        (time.time(), goal.id),
                    )
                    done.append(goal.topic)
            if done:
                self._conn.commit()
        except Exception as exc:
            self._log_error("goals.check_satisfaction", exc)
        return done

    # ------------------------------------------------------------------
    # Self-formation — goals Genesis authors for itself
    # ------------------------------------------------------------------

    def self_form_from_analogs(self, max_new: int = 1) -> int:
        """
        Promote pattern-transfer analog gaps into goals.  A concept playing
        the same structural role as something Genesis understands, but with
        unexplained edges, is a reason to *intend* — not just a directive.
        Capped at `max_new` per pass so self-formed intentions accumulate
        deliberately, not in bursts.  Returns how many goals were formed.
        """
        formed = 0
        try:
            for concept in self._brain.pattern_transfer.curiosity_from_analogs():
                if formed >= max_new:
                    break
                goal = self.form(
                    concept, origin="self",
                    statement=(f"understand {concept} — it mirrors a "
                               f"structural pattern I already know"),
                )
                if goal:
                    formed += 1
        except Exception as exc:
            self._log_error("goals.self_form", exc)
        return formed
