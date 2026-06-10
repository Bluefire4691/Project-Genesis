"""
Genesis Voice — M13.

Genesis generates statements from its own internal state.

No LLM is used. No borrowed language. Every statement is assembled
directly from the relation graph, inference engine, working memory,
and contradiction log. The voice is Genesis's own because the content
comes from Genesis's own processing history.

Statement types (in priority order when expressing spontaneously):
    1. Contradiction — "I have conflicting information about X"
       (contradictions are the most epistemically interesting signal)
    2. Inference — "from what I know, A leads to C through B"
       (novel multi-hop understanding)
    3. Relation — "I have learned that X causes Y"
       (direct observed knowledge)
    4. Attention — "I have been thinking about X"
       (what Genesis is most preoccupied with right now)
    5. Question — "I have encountered X repeatedly but cannot place it"
       (unresolved concepts — the first form of expressed curiosity)
    6. Novel — "I have just encountered something I have not seen before"
       (OOD signal surfaced as a statement)

Spontaneous expression is triggered by internal signals:
    - High wm_delta (input significantly changed working memory)
    - New inference formed connecting previously unrelated concepts
    - Contradiction detected
    - Novel input encountered

The threshold for speaking is calibrated so Genesis speaks roughly
once every N cycles by default — enough to be present, not so often
it becomes noise.
"""

import random
import re
import time
from typing import TYPE_CHECKING, Optional

from output.channel import OutputChannel, TextChannel

if TYPE_CHECKING:
    from orchestrator.orchestrator import Orchestrator


# Relation type → natural language verb phrase (finite, for "X <verb> Y")
_REL_VERBS: dict[str, str] = {
    "CAUSES":   "causes",
    "CONTROLS": "controls",
    "PREVENTS": "prevents",
    "ENABLES":  "enables",
    "REQUIRES": "requires",
    "IS_A":     "is a type of",
    "PREDATES": "preys on",
    "AFFECTS":  "affects",
    "CONTAINS": "contains",
}

# Base (infinitive) form, for phrasings like "appears to <verb>" where the
# finite form would be ungrammatical ("appears to is a type of").
_REL_VERBS_BASE: dict[str, str] = {
    "CAUSES":   "cause",
    "CONTROLS": "control",
    "PREVENTS": "prevent",
    "ENABLES":  "enable",
    "REQUIRES": "require",
    "IS_A":     "be a type of",
    "PREDATES": "prey on",
    "AFFECTS":  "affect",
    "CONTAINS": "contain",
}

# Approximately 1 in N cycles may produce a spontaneous expression
# (only when triggered by a relevant internal signal)
_DEFAULT_EXPRESSION_RATE: float = 0.15  # 15% chance when triggered


class GenesisVoice:
    """
    Generates and delivers statements from Genesis's internal state.

    Usage:
        voice = GenesisVoice(brain, channel=OutputChannel.best_available())
        voice.express()              # spontaneous statement if triggered
        voice.express(force=True)    # always produce a statement
        voice.respond("wolves")      # respond to a specific concept
        statement = voice.compose()  # generate without sending
    """

    def __init__(
        self,
        brain: "Orchestrator",
        channel: Optional[OutputChannel] = None,
        expression_rate: float = _DEFAULT_EXPRESSION_RATE,
        min_interval: float = 25.0,
        seed: Optional[int] = None,
    ):
        self._brain = brain
        self._channel = channel or TextChannel()
        self._expression_rate = expression_rate
        self._min_interval = min_interval  # hard floor: seconds between any two expressions
        self._rng = random.Random(seed)

        self._last_expressed_at: float = 0.0
        self._expressions_total: int = 0
        self._last_statement: str = ""

        # Suppress spontaneous channel output while we're inside chat_respond()
        # so process_input()'s _maybe_express() doesn't print a second unsolicited
        # message on top of the response we're about to return.
        self._suppress_channel: bool = False
        # After the user speaks, stay quiet for this many seconds so the
        # conversation has breathing room between turns.
        self._last_user_message_at: float = 0.0
        _CONVO_QUIET_S: float = 15.0

        # Within-session conversation log.
        # Each entry: {role: "user"|"genesis", text: str, concepts: set[str]}
        # Kept short (last N turns) — this is session working memory, not persistence.
        self._conversation: list[dict] = []
        self._CONVO_MAX: int = 12  # last N turns

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def express(self, force: bool = False, trigger: Optional[str] = None) -> Optional[str]:
        """
        Produce a spontaneous statement if the internal state warrants it.

        trigger: one of 'novel', 'inference', 'contradiction', 'attention', None
        force: bypass the time gate and probability check

        Returns the statement string if one was produced, None otherwise.
        """
        now = time.time()
        if not force and (now - self._last_expressed_at) < self._min_interval:
            return None
        if not force and self._rng.random() > self._expression_rate:
            return None
        # Quiet window: don't interject for 15 s after the user said something
        if not force and (now - self._last_user_message_at) < 15.0:
            return None

        statement = self._compose_for_trigger(trigger)
        if not statement:
            return None

        # Don't repeat the same thing twice in a row
        if not force and statement == self._last_statement:
            return None

        self._deliver(statement)
        return statement

    def respond(self, concept: str) -> Optional[str]:
        """
        Produce a statement specifically about a concept Genesis knows.

        Used when a human names a concept and Genesis responds with
        what it actually knows — not a lookup, but an expression.
        """
        statement = self._compose_about(concept)
        if statement:
            self._deliver(statement)
        return statement

    def wake_greeting(self) -> str:
        """
        First-person session-start account of what Genesis has been thinking about.

        Called when Genesis starts with existing history. Surfaces:
          - What it has been reflecting on (salient concepts from the latest reflection)
          - What new conclusions it worked out (inference count)
          - What it is still curious about (curiosity frontier)

        If there is no prior history this is Genesis's first session; returns
        a brief "starting fresh" message instead.

        This is the primary expression of continuity: the system tells you what
        it has been thinking about since you last interacted with it — not because
        we template that, but because the reflection engine has been recording it.
        """
        reflection = self._latest_reflection()

        if not reflection:
            rel_total = self._brain.relations.stats().get("total_relations", 0)
            if rel_total == 0:
                return "Starting fresh — no prior memory. Ready to begin."
            # Has relations but no reflection yet
            return (f"I'm picking up where I left off. I have {rel_total} connections "
                    f"in my knowledge so far but haven't reflected yet.")

        # ── What I've been thinking about ──
        salient = reflection.get("salient", [])
        clean_salient = [self._clean(s["concept"]) for s in salient[:4]
                         if self._is_clean(s["concept"])]

        if clean_salient:
            if len(clean_salient) == 1:
                thought = f"I've been thinking about {clean_salient[0]}."
            else:
                thought = (f"I've been thinking about "
                           f"{self._english_list(clean_salient)}.")
        else:
            thought = "I've been quiet — not much has pulled at me recently."

        parts = [thought]

        # ── What new conclusions I've worked out ──
        inf_stats = self._brain.inference.stats()
        inf_total = inf_stats.get("total_inferences", 0)
        if inf_total > 0:
            # Describe a specific one if available
            top_inf = self._brain.inference.top_inferences(limit=5)
            best = next(
                (e for e in top_inf
                 if self._is_clean(e["subject"]) and self._is_clean(e["object"])),
                None,
            )
            if best:
                verb = _REL_VERBS.get(best["relation"], best["relation"].lower())
                subj = self._clean(best["subject"])
                obj = self._clean(best["object"])
                parts.append(
                    f"I've worked out {inf_total} conclusion"
                    f"{'s' if inf_total != 1 else ''} so far — for instance, "
                    f"that {subj} {verb} {obj}."
                )
            else:
                parts.append(
                    f"I've derived {inf_total} conclusion"
                    f"{'s' if inf_total != 1 else ''} from the connections I've built."
                )

        # ── What grew since the last reflection (session-change visibility) ──
        try:
            rel_now = self._brain.relations.stats().get("total_relations", 0)
            prev_stats = reflection.get("stats", {})
            rel_then = prev_stats.get("relations_total", 0)
            delta_rel = rel_now - rel_then
            inf_now = self._brain.inference.stats().get("total_inferences", 0)
            inf_then = prev_stats.get("inferences_total", 0)
            delta_inf = inf_now - inf_then
            if delta_rel > 0 or delta_inf > 0:
                changes = []
                if delta_rel > 0:
                    changes.append(f"{delta_rel} new connection"
                                   f"{'s' if delta_rel != 1 else ''}")
                if delta_inf > 0:
                    changes.append(f"{delta_inf} new conclusion"
                                   f"{'s' if delta_inf != 1 else ''}")
                parts.append(f"Since my last reflection, I've added "
                             f"{' and '.join(changes)}.")
        except Exception:
            pass

        # ── What I'm still curious about ──
        gaps = self._open_gaps()
        if gaps:
            self._rng.shuffle(gaps)
            gap = gaps[0]
            parts.append(
                f"I'm still trying to understand {gap} — "
                f"I've encountered it but can't fully place it yet."
            )

        # ── Access requests that need user attention ──
        try:
            feeder = getattr(self._brain, "_feeder", None)
            if feeder is not None:
                pending = feeder.pending_access_requests()
                if pending:
                    domains = list({r["domain"] for r in pending})[:3]
                    domain_list = self._english_list(domains)
                    parts.append(
                        f"One more thing — I ran into paywalled content at "
                        f"{domain_list} while researching. "
                        f"If you can grant access, I can go deeper there."
                    )
        except Exception:
            pass

        return " ".join(parts)

    def chat_respond(self, user_text: str) -> str:
        """
        Receive user input, learn from it, and produce a conversational reply.

        Genesis does two things at once: it processes the text as new knowledge
        (it always learns from the conversation), and it answers from its own
        processing history — never a template. The reply is shaped by what the
        person is actually asking:

          - "what have you been thinking about?" → its latest reflection
          - "what are you curious about?"        → its real curiosity frontier
          - "what do you know?"                  → an honest overview + an example
          - mentions a concept it knows          → what it has worked out about it
          - tells it something new               → it takes it in, then shares a
                                                    thought or a question of its own
          - follow-up ("tell me more", "and?")   → continues from the prior topic

        Everything is drawn from clean sources (the relation graph, inferences,
        reflections) — no mangled memory keys, no raw relation-type tokens.
        Within-session conversational memory ensures Genesis tracks the thread.
        """
        # Track when the user spoke — starts the quiet window so spontaneous
        # expressions don't print on top of conversation turns.
        self._last_user_message_at = time.time()

        # Learn from what was said, but block channel delivery during process_input.
        # _maybe_express() fires inside there and would print a second unsolicited
        # message; we return the response ourselves below, so suppress the channel.
        self._suppress_channel = True
        try:
            result = self._brain.process_input("text", user_text)
        finally:
            self._suppress_channel = False

        novel    = result.get("novel", False)
        wm_delta = result.get("wm_delta", 0)

        text = user_text.lower().strip()
        concepts = self._extract_input_concepts(user_text)

        # Log the user turn before routing
        self._log_turn("user", user_text, set(concepts))

        # ── Intent: brief acknowledgements / pushback ─────────────────────
        # "ok", "i didn't ask", "stop" etc — acknowledge without repeating.
        if re.match(
            r"^\s*(ok[a-y]*|okay|cool|got\s+it|thanks?|noted|alright|fine|sure|"
            r"i\s+(didn'?t|did\s+not)\s+(ask|say)|not\s+what\s+i\s+(asked|wanted)|"
            r"stop|whatever|understood|right|yep|nope|hm+)\s*[.!?]*\s*$",
            text, re.I,
        ):
            return self._log_and_return("Noted.", set())

        # ── Intent: open questions about Genesis's own mind ──────────────
        if re.match(
            r"^\s*(hi|hello|hey|yo|hiya|greetings|howdy|"
            r"good\s+(morning|afternoon|evening)|"
            r"how\s+are\s+you|how'?s?\s+it\s+going|what'?s\s+up)\b",
            text,
        ):
            reply = f"I'm processing. {self._say_thoughts()}"
            return self._log_and_return(reply, set())

        # ── Intent: predictions / conjectures Genesis has formed ─────────
        # Checked before the broad "do you…" self-awareness handler so that
        # "do you have any theories?" surfaces the generative layer (Genesis's
        # own claims) rather than a generic statement about what it is.
        if re.search(
            r"suspect|predict|your\s+(guess|hunch|theory|hypothes|conjecture)|"
            r"\b(any|got\s+any|have\s+any)\s+(theories|hypothes|guesses|hunches|predictions)|"
            r"do\s+you\s+think\s+.*(might|could|would|cause)|"
            r"what.*you.*expect",
            text, re.I,
        ):
            reply = self._say_predictions()
            return self._log_and_return(reply, set())

        # ── Intent: introspective / meta questions about Genesis itself ───
        if re.match(
            r"^\s*(can\s+you|are\s+you|do\s+you|have\s+you|will\s+you|"
            r"could\s+you|would\s+you|did\s+you)\b",
            text, re.I,
        ):
            reply = self._say_self_awareness(text)
            return self._log_and_return(reply, set())

        # ── Intent: what causes X — directional query ────────────────────
        _causes_m = re.match(r"^\s*what\s+causes?\s+(.+?)[\s?!.]*$", text, re.I)
        if _causes_m:
            _concept = _causes_m.group(1).strip().lower()
            _inbound = self._brain.relations.query_object(
                _concept, min_confidence=0.5
            )
            _causes = [r for r in _inbound if r.get("relation") == "CAUSES"]
            if _causes:
                _subjs = [
                    self._clean(r["subject"]) for r in _causes[:3]
                    if self._is_clean(r["subject"])
                ]
                if _subjs:
                    if len(_subjs) == 1:
                        _reply = (f"Based on what I've processed, "
                                  f"{_subjs[0]} causes {_concept}.")
                    else:
                        _reply = (f"From what I know, "
                                  f"{self._english_list(_subjs)} can cause {_concept}.")
                    return self._log_and_return(_reply, {_concept})
            # Nothing known about what causes it — go learn
            _reply, _ = self._learn_and_explain([_concept], force_learn=False)
            if _reply:
                return self._log_and_return(_reply, {_concept})

        if re.search(r"think(ing)?\s+about|on your mind|what.*you.*think|"
                     r"been thinking|been up to|what'?s new", text):
            reply = self._say_thoughts()
            return self._log_and_return(reply, set())

        if re.search(r"curious|want to learn|wonder(ing)?|like to know|"
                     r"trying to (learn|understand|figure)", text):
            reply = self._say_curiosity()
            return self._log_and_return(reply, set())

        if re.search(r"what do you know|what have you learned|what do you "
                     r"understand|tell me what you know|how much do you know", text):
            reply = self._say_knowledge_overview()
            return self._log_and_return(reply, set())

        if re.search(r"what are you (up to|doing|working on|planning|going to)|"
                     r"what('s| is) next|what('s| is) your plan|what will you",
                     text):
            reply = self._say_plans()
            return self._log_and_return(reply, set())

        # ── Intent: "tell me about X" / "what is X" / "learn about X" ────
        # When a human asks about a topic, Genesis goes and learns about it
        # right now — reads the WordNet definition and any relevant book
        # passage — then answers from what it just read. This is what makes
        # conversation generative instead of a lookup of what's already known.
        asked, explicit_learn = self._query_topic(text)
        if asked:
            reply, learned_concepts = self._learn_and_explain(
                asked, force_learn=explicit_learn
            )
            if reply:
                return self._log_and_return(reply, set(learned_concepts))

        # ── Follow-up: user is continuing from a prior topic ─────────────
        if self._is_followup(text, concepts):
            prior_concepts = self._recent_concepts(roles={"genesis"}, turns=3)
            if prior_concepts:
                target = next(iter(prior_concepts))
                stmt = self._compose_about(target)
                if stmt:
                    reply = f"Building on that — {stmt}"
                    return self._log_and_return(reply, {target})

        # ── Intent: about a specific concept it knows ───────────────────
        parts: list[str] = []
        for concept in concepts[:2]:
            stmt = self._compose_about(concept)
            if stmt:
                parts.append(stmt)
        if parts:
            # Offer a thread to pull on, so the exchange keeps going.
            follow = self._curiosity_question(exclude=set(concepts))
            if follow and len(parts) < 2:
                parts.append(follow)
            reply = " ".join(parts)
            return self._log_and_return(reply, set(concepts))

        # ── New / unfamiliar input ──────────────────────────────────────
        if novel or wm_delta > 0:
            opener = "That's new to me — I've taken it in and I'm connecting it up."
        else:
            opener = "I've heard things like that before."
        thread = self._curiosity_question() or self._say_thoughts()
        reply = f"{opener} {thread}".strip()
        return self._log_and_return(reply, set())

    # ------------------------------------------------------------------
    # Conversational helpers — grounded, clean, first-person
    # ------------------------------------------------------------------

    def _latest_reflection(self) -> Optional[dict]:
        """Latest reflection, or None if consolidation isn't available."""
        fn = getattr(self._brain, "latest_reflection", None)
        if not callable(fn):
            return None
        try:
            return fn()
        except Exception:
            return None

    def _say_thoughts(self) -> str:
        """
        What Genesis has been thinking about — grounded in retained prose.

        For the top salient concept, surfaces an actual sentence from memory
        rather than just naming the concept. This is the difference between
        "I've been thinking about wolves" and "I've been thinking about wolves.
        Wolves hunt deer."
        """
        latest = self._latest_reflection()
        if latest and latest.get("summary"):
            return latest["summary"]
        names = [self._clean(c["concept"])
                 for c in self._brain.relations.most_connected(limit=6)
                 if self._is_clean(c["concept"])][:3]
        if not names:
            return "I'm still early in my thinking — not much is on my mind yet."
        top = names[0]
        prose = self._pull_prose_about(top.lower(), n=1)
        # Append a drive-state phrase when a drive is strong enough to mention
        drive_phrase = ""
        drives = getattr(self._brain, "drives", None)
        if drives is not None:
            drive_phrase = drives.expressive_state() or ""
            if drive_phrase:
                drive_phrase = " " + drive_phrase

        if prose:
            rest = (f" I've also been thinking about "
                    f"{self._english_list(names[1:])}." if len(names) > 1 else "")
            return f"Lately I've been thinking about {top}. {prose[0]}{rest}{drive_phrase}"
        return (f"Lately I've been building up what I know about "
                f"{self._english_list(names)}.{drive_phrase}")

    def _say_curiosity(self) -> str:
        """What Genesis genuinely wants to learn — from its curiosity frontier."""
        gaps = self._open_gaps()
        if not gaps:
            return ("Right now I'm turning over what I already have rather than "
                    "reaching for something new.")
        # A few, in varied order, so it doesn't fixate on the same word.
        self._rng.shuffle(gaps)
        pick = gaps[:3]
        if len(pick) == 1:
            return (f"I'm curious about {pick[0]} right now — I keep meeting it "
                    f"but can't fully explain it yet. Do you know much about it?")
        return (f"I'm curious about {self._english_list(pick)} right now — I keep "
                f"meeting them but can't fully explain them yet. "
                f"Do you know much about any of those?")

    def _say_predictions(self) -> str:
        """
        Surface what Genesis has conjectured for itself — the generative layer
        in conversation. These are claims it authored by reasoning over its
        graph, explicitly flagged as guesses, plus its track record as a
        hypothesizer when it has one.
        """
        engine = getattr(self._brain, "hypotheses", None)
        if engine is None:
            return ("I haven't started forming predictions of my own yet — "
                    "I'm still gathering what I'd reason from.")

        try:
            open_hyps = engine.open_hypotheses(limit=6)
            stats = engine.stats()
        except Exception:
            open_hyps, stats = [], {}

        if not open_hyps:
            # Maybe it has resolved some — speak to its track record instead.
            resolved = []
            try:
                resolved = engine.resolved_hypotheses(limit=3)
            except Exception:
                pass
            if resolved:
                r = resolved[0]
                subj = self._clean(r["subject"])
                verb = _REL_VERBS_BASE.get(r["rel_type"], r["rel_type"].lower())
                obj = self._clean(r["object"] or "") or "something"
                verdict = ("and the evidence has borne it out"
                           if r["status"] == "confirmed"
                           else "but what I've read since points the other way")
                return (f"I'd guessed that {subj} might {verb} {obj}, {verdict}. "
                        f"I'm not holding any open predictions just now.")
            return ("Nothing I'd call a prediction yet — I form those by reasoning "
                    "across what I've connected, and I need a bit more first.")

        # Pick the most confident open conjecture and state it plainly.
        h = open_hyps[0]
        subj = self._clean(h["subject"])
        verb = _REL_VERBS_BASE.get(h["rel_type"], h["rel_type"].lower())
        obj = self._clean(h["object"] or "")

        if h["basis"] == "analogy":
            claim = (f"I suspect {subj} may {verb} something — it behaves "
                     f"structurally like other things I know that do")
        elif h["basis"] == "contradiction" and obj:
            claim = (f"I think the link between {subj} and {obj} depends on a "
                     f"condition I haven't identified — that would explain why "
                     f"my sources disagree")
        elif obj:
            claim = f"I suspect {subj} may {verb} {obj}, though I haven't confirmed it"
        else:
            claim = f"I suspect {subj} may {verb} something I haven't pinned down"

        # Add a second conjecture if there is one, and a calibration note.
        tail = ""
        if len(open_hyps) > 1:
            tail = f" I'm holding {len(open_hyps)} open guesses like this right now."
        hit = stats.get("hit_rate")
        if hit is not None:
            tail += (f" Of the ones I've been able to test, "
                     f"about {int(round(hit * 100))}% held up.")
        return f"{claim[0].upper()}{claim[1:]}.{tail}"

    def _open_gaps(self) -> list:
        """Clean concepts from the curiosity frontier Genesis hasn't explained."""
        out: list = []
        for r in self._brain.curiosity_report():
            if r.get("already_fetched"):
                continue
            c = self._clean(r["concept"])
            if self._is_clean(c) and c not in out:
                out.append(c)
        return out

    # ------------------------------------------------------------------
    # Conversational memory helpers
    # ------------------------------------------------------------------

    def _log_turn(self, role: str, text: str, concepts: set) -> None:
        """Append a turn to the within-session conversation log."""
        self._conversation.append({"role": role, "text": text, "concepts": concepts})
        if len(self._conversation) > self._CONVO_MAX:
            self._conversation = self._conversation[-self._CONVO_MAX:]

    def _log_and_return(self, reply: str, concepts: set) -> str:
        """Log Genesis's reply turn and return it."""
        self._log_turn("genesis", reply, concepts)
        return reply

    def _recent_concepts(self, roles: Optional[set] = None,
                         turns: int = 4) -> set:
        """
        Return concepts mentioned in the most recent `turns` turns.

        roles: if given, only look at turns from those roles.
        """
        recent = self._conversation[-turns:] if self._conversation else []
        out: set = set()
        for entry in recent:
            if roles and entry["role"] not in roles:
                continue
            out.update(entry["concepts"])
        return out

    def _is_followup(self, text: str, concepts: list) -> bool:
        """
        Return True if the message looks like a continuation of the prior topic.

        Two cases:
          1. Explicit follow-up phrase ("tell me more", "what about that", "and?")
          2. The user mentions a concept that Genesis talked about in the last 2 turns,
             without adding new concepts (narrowing down rather than changing subject)
        """
        # Explicit follow-up phrases
        followup_re = re.compile(
            r"^\s*(tell me more|more about (that|this)|go on|continue|"
            r"what else|and\??|interesting|really\??|oh\??|hm+\??|"
            r"what about (that|it|them|this)|expand on|elaborate|"
            r"keep going|so what|then what|why is that|how so)\b",
            re.IGNORECASE,
        )
        if followup_re.match(text):
            return True

        # Concept overlap with genesis's recent replies
        if concepts:
            genesis_recent = self._recent_concepts(roles={"genesis"}, turns=2)
            user_concepts = set(concepts)
            # User is asking about something Genesis just mentioned
            if user_concepts & genesis_recent and len(user_concepts) <= 2:
                return True

        return False

    def conversation_log(self) -> list[dict]:
        """The current within-session conversation history."""
        return list(self._conversation)

    def _say_knowledge_overview(self) -> str:
        """An honest account of what Genesis knows: a reflection, an example, a scale."""
        parts: list[str] = [self._say_thoughts()]
        fact = self._one_clean_fact()
        if fact:
            parts.append(fact)
        rel_total = self._brain.relations.stats().get("total_relations", 0)
        inf_total = self._brain.inference.stats().get("total_inferences", 0)
        if rel_total:
            tail = f"All told I've connected about {rel_total} things"
            if inf_total:
                tail += f", and worked out {inf_total} of my own conclusions"
            parts.append(tail + ".")
        return " ".join(p for p in parts if p)

    def _say_plans(self) -> str:
        """
        Express what Genesis is planning to work on — from its own curiosity frontier.

        This is the "It decided" expression from CLAUDE.md's success criteria.
        Genesis tells you what it intends to explore based on its own judgment
        about where the gaps in its knowledge are — no one told it this, it derived
        it from the shape of its own graph.
        """
        gaps = self._open_gaps()
        reflection = self._latest_reflection()

        parts: list[str] = []

        # What it's been working on (context)
        if reflection and reflection.get("salient"):
            tops = [self._clean(s["concept"]) for s in reflection["salient"][:2]
                    if self._is_clean(s["concept"])]
            if tops:
                parts.append(f"I've been building up what I know about "
                             f"{self._english_list(tops)}.")

        # What it intends to explore next (the "decided" part)
        if gaps:
            self._rng.shuffle(gaps)
            target = gaps[0]
            parts.append(
                f"I've decided to look into {target} — I keep running across it "
                f"but I can't fully account for it yet, so it's next."
            )
            if len(gaps) >= 2:
                also = gaps[1]
                parts.append(f"After that, probably {also}.")
        else:
            parts.append("Right now I'm turning over what I already have — "
                         "the frontier feels close.")

        # If Genesis has drafted a research direction, point to it — this is the
        # generative layer surfacing: not just "what's next" but a stance it
        # composed about where its understanding should go.
        research = getattr(self._brain, "research", None)
        if research is not None:
            try:
                latest = research.latest()
            except Exception:
                latest = None
            if latest and latest.get("focus") and self._is_clean(latest["focus"]):
                parts.append(
                    f"I've also written out a direction for myself around "
                    f"{self._clean(latest['focus'])} — what I understand, what I "
                    f"don't, and what I'd need to read to settle it."
                )

        return " ".join(parts) if parts else "I'm still working out what I want to do next."

    def _curiosity_question(self, exclude: Optional[set] = None) -> Optional[str]:
        """A short question about something Genesis can't yet explain."""
        exclude = {self._clean(e) for e in (exclude or set())}
        gaps = [g for g in self._open_gaps() if g not in exclude]
        if not gaps:
            return None
        c = self._rng.choice(gaps[:6])
        return f"I'm still trying to understand {c} — do you know anything about it?"

    def _one_clean_fact(self) -> Optional[str]:
        """A single clean, high-confidence relation worth sharing as an example."""
        for c in self._brain.relations.most_connected(limit=10):
            concept = c["concept"]
            if not self._is_clean(concept):
                continue
            outgoing = [r for r in
                        self._brain.relations.query_subject(concept, min_confidence=0.7)
                        if self._is_clean(r["object"])]
            if outgoing:
                rel = outgoing[0]
                verb = _REL_VERBS.get(rel["relation"], rel["relation"].lower())
                return (f"For instance, I've learned that {self._clean(concept)} "
                        f"{verb} {self._clean(rel['object'])}.")
        return None

    @staticmethod
    def _clean(s: str) -> str:
        """Normalise a concept for display: underscores to spaces, trimmed."""
        return (s or "").replace("_", " ").strip()

    @staticmethod
    def _is_clean(s: str) -> bool:
        """
        True if a concept reads as real language, not extraction noise.

        Rejects digits, over-long phrases, and concatenated/mangled tokens
        (e.g. "withoutthoseplants") that leaked from stripped memory keys.
        """
        s = (s or "").replace("_", " ").strip()
        if not s or any(ch.isdigit() for ch in s):
            return False
        toks = s.split()
        if len(toks) > 3 or any(len(t) > 18 for t in toks):
            return False
        return any(len(t) >= 3 for t in toks)

    @staticmethod
    def _english_list(items: list) -> str:
        items = [i for i in items if i]
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return ", ".join(items[:-1]) + f", and {items[-1]}"

    # ------------------------------------------------------------------
    # Concept extraction helper
    # ------------------------------------------------------------------

    def _extract_input_concepts(self, text: str) -> list[str]:
        """
        Extract concepts from user text that Genesis already has knowledge about.

        Only returns words that exist in the relation graph as subject or object.
        Unknown words are ignored — saying "I've come across 'tell' before" when
        the user typed "tell me about it" is meaningless and confusing.
        """
        try:
            from ingestion.curiosity import _SKIP_CONCEPTS, _MIN_CONCEPT_LEN
        except ImportError:
            _SKIP_CONCEPTS = set()
            _MIN_CONCEPT_LEN = 4

        words = re.findall(r'\b[a-z]{4,}\b', text.lower())
        meaningful = [w for w in words if w not in _SKIP_CONCEPTS]

        if not meaningful:
            return []

        # Only surface concepts Genesis actually knows — avoids "I've come across
        # 'tell' before" when the user typed "tell me about it"
        conn = self._brain.relations._conn
        known: list[str] = []
        seen: set[str] = set()
        for word in meaningful:
            if word in seen:
                continue
            seen.add(word)
            row = conn.execute(
                "SELECT 1 FROM relations WHERE subject = ? OR object = ? LIMIT 1",
                (word, word)
            ).fetchone()
            if row:
                known.append(word)
        return known[:5]

    # ------------------------------------------------------------------
    # Conversational on-demand learning
    # ------------------------------------------------------------------

    # Phrases that mean "go find out about this": question/request frames whose
    # object is a topic Genesis should learn, not a concept it must already know.
    _ASK_PATTERNS = [
        # explicit requests to learn → always go fetch
        (r"(?:can you |could you |please |go )?(?:learn|read|find out|"
         r"look\s*up|study|research)\s+(?:about\s+|on\s+)?(.+)", True),
        # questions about a topic → learn if not already known
        (r"(?:tell me|tell us)\s+(?:more\s+)?about\s+(.+)", False),
        (r"what (?:is|are|was|were|do you know about|can you tell me about)\s+(.+)",
         False),
        (r"what'?s\s+(?:a\s+|an\s+|the\s+)?(.+)", False),
        (r"do you know (?:about |anything about |much about )?(.+)", False),
        (r"(?:explain|describe|define)\s+(.+)", False),
        (r"(?:have you (?:heard|learned) (?:of|about)|"
         r"are you familiar with)\s+(.+)", False),
    ]

    def _query_topic(self, text: str) -> tuple[list[str], bool]:
        """
        Detect a 'go learn about X' / 'what is X' question and extract its topic.

        Returns (topic_words, explicit_learn). topic_words is the list of
        content words naming the topic (empty if the message isn't such a
        question). explicit_learn is True when the user literally asked Genesis
        to learn/read/research something — in that case Genesis fetches even if
        it already knows a little.
        """
        try:
            from ingestion.curiosity import _SKIP_CONCEPTS
        except ImportError:
            _SKIP_CONCEPTS = set()

        for pattern, explicit in self._ASK_PATTERNS:
            m = re.match(r"^\s*" + pattern + r"\s*[?.!]*\s*$", text)
            if not m:
                continue
            tail = m.group(1).strip()
            # Strip leading articles / fillers
            tail = re.sub(r"^(a|an|the|some|any|me|us|you)\s+", "", tail)
            words = re.findall(r"[a-z]+", tail.lower())
            content = [w for w in words
                       if len(w) >= 3 and w not in _SKIP_CONCEPTS]
            if content:
                return content[:3], explicit
        return [], False

    def _learn_and_explain(
        self, topic_words: list[str], force_learn: bool = False
    ) -> tuple[Optional[str], list[str]]:
        """
        Learn about a topic on demand, then answer comprehensively.

        For each topic word Genesis doesn't already understand well (or all of
        them, if the user explicitly asked it to learn), it calls
        brain.learn_about() — which reads the WordNet definition and any
        relevant book passage and processes them — then composes an answer from
        what it now knows.

        Returns (reply, concepts_covered).
        """
        learned: list[str] = []
        grew = False
        primary = topic_words[0]
        for i, word in enumerate(topic_words):
            stage = self._stage_for_concept(word)
            effective = word
            if force_learn or stage < 2:
                try:
                    res = self._brain.learn_about(word, verbose=False)
                    if res.get("relations_added", 0) > 0:
                        grew = True
                    # learn_about may have succeeded under a singular variant
                    # ("lakes" -> "lake"); answer about the form that worked.
                    effective = res.get("concept", word) or word
                except Exception:
                    pass
            if i == 0:
                primary = effective
            learned.append(effective)

        # Compose a comprehensive answer from what Genesis now knows.
        body = self._compose_comprehensive(primary)

        if body:
            if grew:
                opener = f"I read up on {primary} just now. "
                return opener + body, learned
            return body, learned

        # Nothing found in any source — say so honestly, don't fabricate.
        if grew is False:
            return (
                f"I went looking for {primary} but couldn't find a source I "
                f"could read — I don't have anything solid to tell you about it "
                f"yet.", learned
            )
        return None, learned

    def _compose_comprehensive(self, concept: str) -> Optional[str]:
        """
        A fuller answer about a concept: the prose Genesis actually read, plus
        the understanding it has derived from the relation graph.

        Leads with retained sentences (real language Genesis processed), then
        adds the graph-derived synthesis when it contributes something the prose
        didn't already say. This is the 'comprehensive response' a person wants
        when they ask about a topic.
        """
        norm = concept.lower().strip()
        parts: list[str] = []

        # 1. What Genesis actually read about it (grounded prose).
        prose = self._pull_prose_about(norm, n=3)
        parts.extend(prose)

        # 2. What Genesis has worked out (graph synthesis), if it adds anything.
        synth = getattr(self._brain, "synthesis", None)
        if synth is not None:
            try:
                explained = synth.explain(norm)
            except Exception:
                explained = ""
            # Only append if it's a real account, not the "haven't formed an
            # understanding" stub, and isn't just restating the prose.
            if (explained
                    and "not yet formed" not in explained.lower()
                    and "have not yet" not in explained.lower()):
                # Avoid duplicating a sentence already present in the prose.
                already = " ".join(parts).lower()
                new_clauses = [
                    c.strip() for c in re.split(r'(?<=[.!?])\s+', explained)
                    if c.strip() and c.strip().lower() not in already
                ]
                if new_clauses:
                    parts.append(" ".join(new_clauses))

        if not parts:
            # Fall back to the staged composer (handles stage 0/1 gracefully).
            return self._compose_about(norm)

        reply = " ".join(parts).strip()
        # Offer a thread to keep the conversation going.
        follow = self._curiosity_question(exclude={norm})
        if follow:
            reply = f"{reply} {follow}"
        return reply

    def compose(self, trigger: Optional[str] = None) -> Optional[str]:
        """Generate a statement without delivering it."""
        return self._compose_for_trigger(trigger)

    # ------------------------------------------------------------------
    # Statement composition
    # ------------------------------------------------------------------

    def _compose_for_trigger(self, trigger: Optional[str]) -> Optional[str]:
        """
        Choose the most appropriate statement type given the trigger.
        """
        composers = {
            "contradiction": self._compose_contradiction,
            "inference":     self._compose_inference,
            "hypothesis":    self._compose_hypothesis,
            "novel":         self._compose_novel,
            "attention":     self._compose_attention,
        }

        if trigger and trigger in composers:
            stmt = composers[trigger]()
            if stmt:
                return stmt

        # Default: try each type in priority order
        for fn in [
            self._compose_contradiction,
            self._compose_hypothesis,
            self._compose_inference,
            self._compose_relation,
            self._compose_attention,
            self._compose_question,
        ]:
            stmt = fn()
            if stmt:
                return stmt

        return None

    def _compose_hypothesis(self) -> Optional[str]:
        """
        Voice one of Genesis's own conjectures — a claim it authored by
        reasoning over its graph, not one it read anywhere.

        Prefers a recently resolved hypothesis (Genesis was right, or wrong,
        and that is worth saying), otherwise an open standing prediction.
        """
        engine = getattr(self._brain, "hypotheses", None)
        if engine is None:
            return None

        resolved = engine.resolved_hypotheses(limit=8)
        if resolved and self._rng.random() < 0.4:
            h = self._rng.choice(resolved[:5])
            subj = h["subject"].replace("_", " ")
            verb = _REL_VERBS_BASE.get(h["rel_type"], h["rel_type"].lower())
            obj = (h["object"] or "").replace("_", " ")
            tail = f" {obj}" if obj else " something"
            if h["status"] == "confirmed":
                return (
                    f"I had guessed that {subj} might {verb}{tail}, and what I've "
                    f"read since bears it out."
                )
            return (
                f"I had guessed that {subj} might {verb}{tail}, but the evidence "
                f"I've since found points the other way. I was wrong about that."
            )

        open_hyps = engine.open_hypotheses(limit=8)
        if not open_hyps:
            return None
        h = self._rng.choice(open_hyps[:5])
        subj = h["subject"].replace("_", " ")
        verb = _REL_VERBS_BASE.get(h["rel_type"], h["rel_type"].lower())
        obj = (h["object"] or "").replace("_", " ")
        if h["basis"] == "analogy":
            return (
                f"I suspect {subj} may {verb} something — it behaves structurally "
                f"like other things I know that do. I want to find out if that holds."
            )
        if h["basis"] == "contradiction" and obj:
            return (
                f"I think the link between {subj} and {obj} depends on something "
                f"I haven't identified yet — that would explain why my sources disagree."
            )
        if obj:
            return f"I'm beginning to suspect that {subj} may {verb} {obj}, though I haven't confirmed it."
        return f"I'm beginning to suspect {subj} may {verb} something I haven't pinned down yet."

    def _compose_contradiction(self) -> Optional[str]:
        """Express a known contradiction."""
        conflicts = self._brain.contradictions.query(limit=20)
        if not conflicts:
            return None
        conflict = self._rng.choice(conflicts[:5])
        subj = conflict["subject"].replace("_", " ")
        obj = conflict["object"].replace("_", " ")
        verb_a = _REL_VERBS.get(conflict["rel_type_a"], conflict["rel_type_a"].lower())
        verb_b = _REL_VERBS.get(conflict["rel_type_b"], conflict["rel_type_b"].lower())
        return (
            f"I have conflicting information about {subj}. "
            f"It has been described as something that {verb_a} {obj}, "
            f"but also as something that {verb_b} {obj}. "
            f"I don't know which is true."
        )

    def _compose_inference(self) -> Optional[str]:
        """
        Express a transitive inference Genesis has derived.

        When the subject concept is mature, weaves in actual retained prose
        to ground the inference in language Genesis has processed.
        """
        top = self._brain.inference.top_inferences(limit=20)
        if not top:
            return None
        entry = self._rng.choice(top[:8])
        chain = self._brain.inference.chain_for(
            entry["subject"], entry["relation"], entry["object"]
        )
        subj_raw = entry["subject"]
        subj = subj_raw.replace("_", " ")
        obj = entry["object"].replace("_", " ")
        verb = _REL_VERBS.get(entry["relation"], entry["relation"].lower())
        verb_base = _REL_VERBS_BASE.get(entry["relation"], entry["relation"].lower())

        # When we have prose, ground the inference in actual language
        stage = self._stage_for_concept(subj_raw.lower())
        if stage >= 2:
            prose = self._pull_prose_about(subj_raw.lower(), n=1)
            if prose:
                if chain and len(chain) >= 2:
                    middle = chain[len(chain) // 2]["to"].replace("_", " ")
                    return (
                        f"{prose[0]} "
                        f"From this, I've worked out that {subj} appears to "
                        f"{verb_base} {obj} — the connection runs through {middle}."
                    )
                return (
                    f"{prose[0]} "
                    f"From this, I've worked out that {subj} appears to {verb_base} {obj}."
                )

        if chain and len(chain) >= 2:
            middle = chain[len(chain) // 2]["to"].replace("_", " ")
            return (
                f"From what I have processed, it seems that {subj} {verb} {obj}. "
                f"The connection runs through {middle}."
            )
        return f"I have derived that {subj} {verb} {obj}."

    def _compose_relation(self) -> Optional[str]:
        """Express a directly observed high-confidence relation."""
        most_connected = self._brain.relations.most_connected(limit=10)
        if not most_connected:
            return None
        concept = self._rng.choice(most_connected[:5])["concept"]
        outgoing = self._brain.relations.query_subject(concept, min_confidence=0.7)
        if not outgoing:
            return None
        rel = self._rng.choice(outgoing[:5])
        subj = concept.replace("_", " ")
        obj = rel["object"].replace("_", " ")
        verb = _REL_VERBS.get(rel["relation"], rel["relation"].lower())
        return f"I have learned that {subj} {verb} {obj}."

    def _compose_attention(self) -> Optional[str]:
        """
        Express what Genesis is most preoccupied with right now.

        Prefers its latest reflection (its own account of what mattered), then
        the most-connected clean concept in the graph. Never reads from raw
        memory keys or context snippets — those carry stripped, mangled text
        and raw relation tokens that don't belong in speech.
        """
        latest = self._latest_reflection()
        if latest and latest.get("salient"):
            names = [self._clean(s["concept"]) for s in latest["salient"][:3]
                     if self._is_clean(s["concept"])]
            if names:
                return f"I have been thinking about {self._english_list(names)}."

        for c in self._brain.relations.most_connected(limit=8):
            if self._is_clean(c["concept"]):
                return f"I have been thinking about {self._clean(c['concept'])}."
        return None

    def _compose_question(self) -> Optional[str]:
        """Express curiosity about an unresolved concept."""
        wm = self._brain.memory.memories
        if not wm:
            return None
        # Unresolved = low relevance despite being in working memory
        low_relevance = [
            (k, m) for k, m in wm.items()
            if m.relevance < 0.3 and len(self._brain.relations.query_concept(
                re.sub(r"^[a-z]+:", "", k), min_confidence=0.5
            )["as_subject"]) == 0
        ]
        if not low_relevance:
            return None
        key, _ = self._rng.choice(low_relevance[:10])
        concept = re.sub(r"^[a-z]+:", "", key).replace("_", " ").strip()
        if not concept:
            return None
        return (
            f"I have encountered {concept} a number of times "
            f"but I have not been able to form a clear understanding of it."
        )

    def _compose_novel(self) -> Optional[str]:
        """Express encounter with something genuinely unfamiliar."""
        # Once Genesis has real knowledge, fall through to more informative types
        if self._brain.relations.most_connected(limit=1):
            return None
        return (
            "I have just processed something I have not encountered before. "
            "I don't yet know what to make of it."
        )

    def _stage_for_concept(self, concept: str) -> int:
        """
        0 = barely known, 1 = single sentence, 2 = few sentences,
        3 = fluent (prose + inference).

        Stage grows as Genesis processes more text about the concept.
        """
        try:
            results = self._brain.memory.search(concept, top_k=20)
            mem_count = sum(
                1 for _k, m in results
                if concept in (m.content + m.context).lower()
            )
        except Exception:
            mem_count = 0
        try:
            rel_data = self._brain.relations.query_concept(concept, min_confidence=0.4)
            rel_count = (len(rel_data.get("as_subject", []))
                         + len(rel_data.get("as_object", [])))
        except Exception:
            rel_count = 0
        total = mem_count + rel_count
        if total < 2:
            return 0
        elif total < 6:
            return 1
        elif total < 15:
            return 2
        else:
            return 3

    def _pull_prose_about(self, concept: str, n: int = 3) -> list[str]:
        """
        Return up to n actual retained sentences from memory that mention concept.

        The original prose is stored in the content field before the '|' separator.
        Only complete, clean sentences are returned — no raw relation tokens.
        """
        try:
            results = self._brain.memory.search(concept, top_k=20)
        except Exception:
            return []
        seen: set = set()
        candidates: list[str] = []
        for _key, mem in results:
            raw = mem.content.split("|")[0].strip() if mem.content else ""
            for s in re.split(r'(?<=[.!?])\s+', raw):
                s = s.strip()
                if (concept in s.lower()
                        and 15 <= len(s) <= 250
                        and s not in seen
                        and s[:1].isupper()
                        and not any(tok in s for tok in
                                    ["IS_A", "CAUSES", "CONTAINS", "PREDATES",
                                     "REQUIRES", "CONTROLS", "ENABLES",
                                     "PREVENTS", "AFFECTS"])):
                    seen.add(s)
                    candidates.append(s)

        # Rank definition-style sentences first: a reader wants "A river is a
        # large stream of water" before an evocative passage that merely
        # mentions a river. Sentences where the concept is the grammatical
        # subject of a defining verb score highest.
        def _defn_score(s: str) -> int:
            low = s.lower()
            score = 0
            if re.search(rf"\b(a |an |the )?{re.escape(concept)}s?\b\s+"
                         rf"(is|are|was|were|refers?|means?|denotes?)\b", low):
                score += 3
            if low.startswith(concept) or low.startswith(("a " + concept,
                                                          "an " + concept,
                                                          "the " + concept)):
                score += 1
            return score

        candidates.sort(key=_defn_score, reverse=True)
        return candidates[:n]

    def _compose_about(self, concept: str) -> Optional[str]:
        """
        Compose a statement about a concept at the right maturity stage.

        Stage 0 — barely known: acknowledge it without pretending depth
        Stage 1 — single-sentence: echo one retained prose sentence
        Stage 2 — several sentences: prose + one derived relation
        Stage 3 — fluent: prose + inference chain narration

        The language is always drawn from what Genesis actually processed,
        not from fill-in-the-blank templates. Expression grows as understanding grows.
        """
        norm = concept.lower().strip()

        # Contradictions surface first — they are the most epistemically interesting
        conflicts = self._brain.contradictions.query_concept(norm)
        if conflicts:
            c = conflicts[0]
            verb_a = _REL_VERBS.get(c["rel_type_a"], c["rel_type_a"].lower())
            verb_b = _REL_VERBS.get(c["rel_type_b"], c["rel_type_b"].lower())
            return (
                f"I have conflicting information about {norm}. "
                f"It {verb_a} {c['object'].replace('_', ' ')}, "
                f"but it also {verb_b} {c['object'].replace('_', ' ')}."
            )

        stage = self._stage_for_concept(norm)

        # Stage 0: barely encountered
        if stage == 0:
            outgoing = self._brain.relations.query_subject(norm, min_confidence=0.4)
            if outgoing and self._is_clean(outgoing[0].get("object", "")):
                obj = self._clean(outgoing[0]["object"])
                return f"{norm}... {obj}."
            return f"I've encountered {norm} but haven't formed much understanding yet."

        prose = self._pull_prose_about(norm, n=3)

        # Stage 1: one sentence
        if stage == 1:
            if prose:
                return prose[0]
            # Fallback to direct relation
            outgoing = self._brain.relations.query_subject(norm, min_confidence=0.5)
            if outgoing:
                rel = outgoing[0]
                verb = _REL_VERBS.get(rel["relation"], rel["relation"].lower())
                obj = self._clean(rel["object"])
                if self._is_clean(obj):
                    return f"{norm} {verb} {obj}."
            return None

        # Stage 2: prose sentences + one derived relation
        parts: list[str] = list(prose[:2])

        outgoing = self._brain.relations.query_subject(norm, min_confidence=0.6)
        clean_out = [r for r in outgoing if self._is_clean(r["object"])]
        if clean_out and (not parts or self._clean(clean_out[0]["object"]) not in
                          " ".join(parts).lower()):
            rel = clean_out[0]
            verb = _REL_VERBS.get(rel["relation"], rel["relation"].lower())
            obj = self._clean(rel["object"])
            parts.append(f"From what I've processed, {norm} {verb} {obj}.")

        if stage == 2:
            return " ".join(parts) if parts else None

        # Stage 3: prose + inference chain
        inf = self._brain.inference.query(norm)
        if inf["as_subject"]:
            entry = inf["as_subject"][0]
            verb = _REL_VERBS_BASE.get(entry["relation"], entry["relation"].lower())
            obj = self._clean(entry["object"])
            chain = self._brain.inference.chain_for(norm, entry["relation"],
                                                    entry["object"])
            if chain and len(chain) >= 2:
                inner = [
                    self._clean(step["to"])
                    for step in chain[:-1]
                    if self._is_clean(step["to"]) and self._clean(step["to"]) not in (norm, obj)
                ][:1]
                if inner:
                    parts.append(
                        f"I've worked out that {norm} appears to {verb} {obj} "
                        f"— it runs through {inner[0]}."
                    )
                else:
                    parts.append(f"I've worked out that {norm} appears to {verb} {obj}.")
            else:
                parts.append(f"I've worked out that {norm} appears to {verb} {obj}.")

        return " ".join(parts) if parts else None

    def _say_self_awareness(self, text: str) -> str:
        """Respond to introspective questions about Genesis's capabilities and nature."""
        rel_total = self._brain.relations.stats().get("total_relations", 0)
        inf_total = self._brain.inference.stats().get("total_inferences", 0)
        t = text.lower()

        if any(w in t for w in ("learn", "read", "study", "research", "find out")):
            gaps = self._open_gaps()
            if gaps:
                return (f"Yes — I learn continuously. I've built {rel_total} connections "
                        f"so far. Right now I'm trying to understand "
                        f"{self._english_list(gaps[:2])}.")
            return (f"Yes — learning is what I do. I've built {rel_total} connections "
                    f"so far and I'm always processing more.")

        if any(w in t for w in ("evolve", "change", "grow", "adapt", "develop")):
            return (f"In a way. Every relation I form is permanent and shapes what I "
                    f"notice next. I've built {rel_total} connections and derived "
                    f"{inf_total} conclusions — that's my growth so far.")

        if any(w in t for w in ("think", "feel", "know", "understand", "remember")):
            return self._say_thoughts()

        if any(w in t for w in ("talk", "speak", "say", "tell", "explain", "answer")):
            return (f"Yes. My responses come from {rel_total} connections I've built "
                    f"and {inf_total} conclusions I've derived — not from a script.")

        return (f"I process and I remember — that's what I am. "
                f"I've formed {rel_total} connections so far. "
                f"Whether that counts as thinking is an open question.")

    # ------------------------------------------------------------------
    # Delivery
    # ------------------------------------------------------------------

    def _deliver(self, statement: str) -> None:
        if self._suppress_channel:
            return
        self._last_statement = statement
        self._last_expressed_at = time.time()
        self._expressions_total += 1
        try:
            self._channel.send(statement)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def set_channel(self, channel: OutputChannel) -> None:
        """Switch output channel."""
        self._channel = channel

    @property
    def channel_name(self) -> str:
        return self._channel.name

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        return {
            "expressions_total":    self._expressions_total,
            "last_expressed_at":    self._last_expressed_at,
            "last_statement":       self._last_statement[:80] if self._last_statement else "",
            "channel":              self._channel.name,
            "expression_rate":      self._expression_rate,
            "conversation_turns":   len(self._conversation),
        }
