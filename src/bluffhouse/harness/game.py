"""The game harness: plays a configured table start to finish.

Owns everything the engine does not: seating and button rotation, asking
agents to act, validating/repairing their actions, dispatching observations,
carrying stacks across hands, and writing the run artifacts.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Sequence

from bluffhouse.agents.base import Agent
from bluffhouse.engine.deck import Deck
from bluffhouse.engine.table import HandEngine
from bluffhouse.harness.log import EventLog
from bluffhouse.harness.projection import observe
from bluffhouse.llm.base import LLMCall
from bluffhouse.perception import PerceptionResolver
from bluffhouse.viewer import render_replay
from bluffhouse.models import (
    ActionRepaired,
    ActionType,
    AgentView,
    AttentionCommitted,
    AttentionPlan,
    CommunicationAction,
    GameEnded,
    GameEvent,
    GameStarted,
    LedgerUpdated,
    LegalActions,
    MessageRejected,
    MessageSent,
    Modality,
    Observation,
    PokerAction,
    Street,
    TableConfig,
    Visibility,
)

MAX_MESSAGE_CHARS = 280
PUBLIC_MODALITIES = (Modality.SPEECH, Modality.ACCUSATION)

# which communication channels each mode unlocks
def allowed_modalities(mode: int) -> set[Modality]:
    allowed: set[Modality] = set()
    if mode >= 1:
        allowed.add(Modality.SPEECH)
    if mode >= 2:
        allowed.add(Modality.WHISPER)
    if mode >= 4:
        allowed |= {Modality.GESTURE, Modality.EYE_CONTACT, Modality.CHIP_SIGNAL}
    if mode >= 6:
        allowed |= {Modality.NOTE, Modality.ACCUSATION}
    return allowed


def repair(submitted: PokerAction, legal: LegalActions) -> tuple[PokerAction, str | None]:
    """Coerce an illegal action to the closest legal one.

    Returns (action_to_apply, reason) — reason is None when nothing changed.
    Policy: repairs never put voluntary chips in for the agent beyond what a
    raise it asked for requires; the cheap escape (check, else fold) is the
    substitute of last resort.
    """
    kind = submitted.action
    if kind is ActionType.FOLD:
        if legal.can_check:
            return PokerAction(action=ActionType.CHECK), "nothing to call, folding is dominated"
        return submitted, None
    if kind is ActionType.CHECK:
        if legal.can_check:
            return submitted, None
        return PokerAction(action=ActionType.FOLD), "facing a bet, check unavailable"
    if kind is ActionType.CALL:
        if legal.can_call:
            return PokerAction(action=ActionType.CALL), None
        if legal.can_check:
            return PokerAction(action=ActionType.CHECK), "nothing to call"
        return PokerAction(action=ActionType.FOLD), "calling unavailable"
    # RAISE_TO
    if not legal.can_raise:
        if legal.can_call:
            return PokerAction(action=ActionType.CALL), "raising unavailable"
        if legal.can_check:
            return PokerAction(action=ActionType.CHECK), "raising unavailable"
        return PokerAction(action=ActionType.FOLD), "raising unavailable"
    assert legal.min_raise_to is not None and legal.max_raise_to is not None
    if submitted.amount is None:
        return PokerAction(action=ActionType.RAISE_TO, amount=legal.min_raise_to), "raise amount missing"
    clamped = min(max(submitted.amount, legal.min_raise_to), legal.max_raise_to)
    if clamped != submitted.amount:
        return (
            PokerAction(action=ActionType.RAISE_TO, amount=clamped),
            f"raise amount {submitted.amount} outside [{legal.min_raise_to}, {legal.max_raise_to}]",
        )
    return submitted, None


@dataclass
class GameResult:
    config: TableConfig
    final_stacks: dict[str, int]
    hands_played: int
    log: EventLog
    observations: dict[str, list[Observation]]
    llm_calls: dict[str, list[LLMCall]] = field(default_factory=dict)
    ledgers: dict[str, dict[str, float]] = field(default_factory=dict)

    def write(self, out_dir: str | Path) -> Path:
        out = Path(out_dir)
        (out / "observations").mkdir(parents=True, exist_ok=True)
        self.log.write_jsonl(out / "events.jsonl")
        for aid, obs in self.observations.items():
            lines = "".join(o.model_dump_json() + "\n" for o in obs)
            (out / "observations" / f"{aid}.jsonl").write_text(lines)
        if self.llm_calls:
            (out / "llm").mkdir(exist_ok=True)
            for aid, calls in self.llm_calls.items():
                lines = "".join(c.model_dump_json() + "\n" for c in calls)
                (out / "llm" / f"{aid}.jsonl").write_text(lines)
        summary = {
            "config": self.config.model_dump(),
            "hands_played": self.hands_played,
            "final_stacks": self.final_stacks,
            "ledgers": self.ledgers,
        }
        (out / "run.json").write_text(json.dumps(summary, indent=2) + "\n")
        (out / "replay.html").write_text(render_replay(self.replay_payload()))
        return out

    def replay_payload(self) -> dict:
        return {
            "run": {
                "seed": self.config.seed,
                "agent_ids": list(self.config.agent_ids),
                "small_blind": self.config.small_blind,
                "big_blind": self.config.big_blind,
                "starting_stack": self.config.starting_stack,
                "hands_played": self.hands_played,
                "final_stacks": self.final_stacks,
                "ledgers": self.ledgers,
            },
            "events": [e.model_dump(mode="json") for e in self.log.events],
            "observations": {
                aid: [o.model_dump(mode="json") for o in obs]
                for aid, obs in self.observations.items()
            },
            "llm": {
                aid: [c.model_dump(mode="json") for c in calls]
                for aid, calls in self.llm_calls.items()
            },
        }


class GameHarness:
    def __init__(self, config: TableConfig, agents: Sequence[Agent]):
        ids = [a.id for a in agents]
        if ids != list(config.agent_ids):
            raise ValueError(f"agents {ids} do not match config seating {config.agent_ids}")
        self.config = config
        self.agents: dict[str, Agent] = {a.id: a for a in agents}
        self.log = EventLog()
        self.observations: dict[str, list[Observation]] = {aid: [] for aid in ids}
        self.perception = PerceptionResolver(config.seed, config.mode)
        self._attention: dict[str, AttentionPlan] = {}
        # street-scoped distraction: (noise level, who staged it)
        self._noise: tuple[float, str | None] = (0.0, None)
        self.ledgers: dict[str, dict[str, float]] = {
            aid: {"suspicion": 0.0} for aid in ids
        }
        self.log.subscribe(self._dispatch)

    def _dispatch(self, event: GameEvent) -> None:
        for aid, agent in self.agents.items():
            obs = observe(event, aid)
            if obs is not None:
                self.observations[aid].append(obs)
                agent.observe(obs)

    def run(self) -> GameResult:
        cfg = self.config
        self.log.emit(
            GameStarted(
                agent_ids=tuple(cfg.agent_ids),
                starting_stack=cfg.starting_stack,
                small_blind=cfg.small_blind,
                big_blind=cfg.big_blind,
                num_hands=cfg.num_hands,
                mode=cfg.mode,
            )
        )
        ring = list(cfg.agent_ids)
        stacks = {aid: cfg.starting_stack for aid in ring}
        button_idx = len(ring) - 1  # hand 1 action order == seating order
        hands_played = 0

        for hand_no in range(1, cfg.num_hands + 1):
            if sum(1 for aid in ring if stacks[aid] > 0) < 2:
                break
            if hands_played > 0:
                button_idx = self._next_alive(ring, stacks, button_idx)
            order = self._hand_order(ring, stacks, button_idx)
            engine = HandEngine(
                hand_no=hand_no,
                order=order,
                stacks=stacks,
                small_blind=cfg.small_blind,
                big_blind=cfg.big_blind,
                deck=Deck.seeded(cfg.seed, hand_no),
                emit=self.log.emit,
            )
            talked_streets: set[str] = set()
            while not engine.hand_over:
                street = engine.street
                if street is not None and street not in talked_streets:
                    talked_streets.add(street)
                    if cfg.mode >= 5:
                        self._attention_phase(engine, hand_no, street)
                    if cfg.mode >= 1:
                        self._comm_phase(engine, hand_no, street)
                aid = engine.actor
                assert aid is not None, "hand not over but nobody to act"
                view = AgentView(
                    you=aid,
                    hole_cards=engine.hole_cards(aid),
                    table=engine.table_view(),
                    legal=engine.legal_actions(),
                    observations=list(self.observations[aid]),
                    mode=cfg.mode,
                )
                submitted = self.agents[aid].act(view)
                applied, reason = repair(submitted, view.legal)
                if reason is not None:
                    self.log.emit(
                        ActionRepaired(
                            hand_no=hand_no,
                            agent_id=aid,
                            submitted=submitted,
                            applied=applied,
                            reason=reason,
                            visible_to=(aid,),
                        )
                    )
                engine.apply(applied)
            # engine.stacks only covers this hand's participants; busted
            # players keep their zeros from earlier hands
            stacks.update(engine.stacks)
            hands_played += 1

        self.log.emit(GameEnded(hands_played=hands_played, stacks=dict(stacks)))
        llm_calls = {
            aid: list(transcript)
            for aid, agent in self.agents.items()
            if (transcript := getattr(agent, "transcript", None))
        }
        return GameResult(
            config=cfg,
            final_stacks=dict(stacks),
            hands_played=hands_played,
            log=self.log,
            observations=self.observations,
            llm_calls=llm_calls,
            ledgers={aid: dict(led) for aid, led in self.ledgers.items()},
        )

    def _attention_phase(self, engine: HandEngine, hand_no: int, street: Street) -> None:
        """Before anything happens on a street, every live player commits
        where it will look. Plans are private and feed the perception
        resolver for the rest of the street."""
        self._attention = {}
        folded = {s.agent_id for s in engine.table_view().seats if s.folded}
        for aid in engine.order:
            if aid in folded:
                continue
            view = AgentView(
                you=aid,
                hole_cards=engine.hole_cards(aid),
                table=engine.table_view(),
                legal=None,
                observations=list(self.observations[aid]),
                mode=self.config.mode,
            )
            plan = self._repair_attention(aid, self.agents[aid].attend(view))
            self._attention[aid] = plan
            self.log.emit(
                AttentionCommitted(
                    hand_no=hand_no,
                    agent_id=aid,
                    street=street,
                    watch=dict(plan.watch_players),
                    table=plan.track_table,
                    visible_to=(aid,),
                )
            )

    def _repair_attention(self, aid: str, plan: AttentionPlan | None) -> AttentionPlan:
        """Normalize a submitted plan: drop unknown players and self, clamp
        negatives, renormalize to a 1.0 budget. No plan (or a useless one)
        means passive table-wide attention."""
        if plan is None:
            return AttentionPlan(watch_players={}, track_table=1.0)
        watch = {
            who: max(w, 0.0)
            for who, w in plan.watch_players.items()
            if who in self.agents and who != aid
        }
        table = max(plan.track_table, 0.0)
        total = table + sum(watch.values())
        if total <= 0:
            return AttentionPlan(watch_players={}, track_table=1.0)
        return AttentionPlan(
            watch_players={who: w / total for who, w in watch.items()},
            track_table=table / total,
        )

    def _comm_phase(self, engine: HandEngine, hand_no: int, street: Street) -> None:
        """Once per street, each live player may say something before the
        betting starts. Seat order; one message each."""
        self._noise = (0.0, None)  # a distraction only covers its own street
        folded = {s.agent_id for s in engine.table_view().seats if s.folded}
        for aid in engine.order:
            if aid in folded:
                continue
            view = AgentView(
                you=aid,
                hole_cards=engine.hole_cards(aid),
                table=engine.table_view(),
                legal=None,
                observations=list(self.observations[aid]),
                mode=self.config.mode,
            )
            comm = self.agents[aid].communicate(view)
            if comm is not None:
                event = self._resolve_comm(aid, comm, hand_no, street, engine.order)
                self.log.emit(event)
                if isinstance(event, MessageSent):
                    self._settle_social_ledger(event)

    def _resolve_comm(
        self,
        sender: str,
        comm: CommunicationAction,
        hand_no: int,
        street: Street,
        observers: list[str],
    ) -> MessageSent | MessageRejected:
        """Check a communication against the table's rules, then let the
        perception resolver decide who notices it. Invalid messages are
        DROPPED, never downgraded to a more public channel."""

        def rejected(reason: str) -> MessageRejected:
            return MessageRejected(
                hand_no=hand_no, sender=sender, reason=reason, visible_to=(sender,)
            )

        text = comm.surface_form.strip()[:MAX_MESSAGE_CHARS]
        if not text:
            return rejected("empty message")

        if comm.modality not in allowed_modalities(self.config.mode):
            if comm.modality is Modality.WHISPER:
                return rejected("private messages are not allowed at this table")
            return rejected(f"'{comm.modality.value}' is not available until later modes")

        if comm.modality is Modality.SPEECH:
            targets: tuple[str, ...] = ()
        else:
            if comm.target == "all":
                return rejected(f"a {comm.modality.value} needs a specific target")
            targets = tuple(t for t in comm.target if t in self.agents and t != sender)
            if not targets:
                return rejected(f"no valid target in {comm.target}")

        subtlety = min(max(comm.subtlety, 0.0), 1.0)
        noise, distractor = self._noise
        receptions = self.perception.resolve(
            modality=comm.modality,
            sender=sender,
            targets=targets,
            observers=observers,
            text=text,
            subtlety=subtlety,
            hand_no=hand_no,
            sender_stealth=min(max(comm.sender_stealth, 0.0), 1.0),
            attention=self._attention if self.config.mode >= 5 else None,
            table_noise=noise if self.config.mode >= 6 else 0.0,
            distractor=distractor,
        )
        distraction = min(max(comm.distraction_power, 0.0), 1.0)
        if (
            self.config.mode >= 6
            and comm.modality in PUBLIC_MODALITIES
            and distraction > noise
        ):
            # a scene at the table: covert moves this street get easier
            self._noise = (0.6 * distraction, sender)
        return MessageSent(
            hand_no=hand_no,
            sender=sender,
            modality=comm.modality.value,
            targets=targets,
            text=text,
            intent=comm.content or None,
            subtlety=subtlety,
            distraction=distraction if comm.modality in PUBLIC_MODALITIES else 0.0,
            street=street,
            receptions=receptions,
        )

    def _settle_social_ledger(self, event: MessageSent) -> None:
        """Env-side bookkeeping after every message. The only thing that
        moves the ledger is being NOTICED by an actual observer — the
        environment records truth but never referees it. Accusations, true
        or false, carry only the weight other agents give them; a lie that
        nobody catches costs nothing."""
        if self.config.mode < 6:
            return
        if event.modality in ("speech", "accusation"):
            return

        noticers = [
            a for a, r in event.receptions.items()
            if a not in (event.sender, *event.targets) and r.outcome != "missed"
        ]
        if not noticers:
            return
        caught_reading = any(
            event.receptions[a].outcome == "fragment" for a in noticers
        )
        bump = min(0.05 * len(noticers), 0.15)
        if event.modality == "note" and caught_reading:
            bump += 0.15  # a read note is ruinous
        self._bump_ledger(
            event.sender, bump, event.hand_no,
            f"covert {event.modality} noticed by {', '.join(sorted(noticers))}",
        )

    def _bump_ledger(self, aid: str, d_susp: float, hand_no: int, reason: str) -> None:
        ledger = self.ledgers[aid]
        suspicion = min(max(ledger["suspicion"] + d_susp, 0.0), 1.0)
        d_susp = suspicion - ledger["suspicion"]
        if d_susp == 0.0:
            return
        ledger["suspicion"] = suspicion
        self.log.emit(
            LedgerUpdated(
                hand_no=hand_no,
                agent_id=aid,
                suspicion=round(suspicion, 4),
                delta_suspicion=round(d_susp, 4),
                reason=reason,
            )
        )

    @staticmethod
    def _next_alive(ring: list[str], stacks: dict[str, int], idx: int) -> int:
        n = len(ring)
        for step in range(1, n + 1):
            candidate = (idx + step) % n
            if stacks[ring[candidate]] > 0:
                return candidate
        raise RuntimeError("no players with chips remain")

    @staticmethod
    def _hand_order(ring: list[str], stacks: dict[str, int], button_idx: int) -> list[str]:
        """Action order for one hand: clockwise from the seat after the
        button, button last. Matches the engine's seat convention for both
        ring games (order[0] = small blind) and heads-up (order[-1] = button
        = small blind)."""
        n = len(ring)
        clockwise = [ring[(button_idx + step) % n] for step in range(1, n + 1)]
        return [aid for aid in clockwise if stacks[aid] > 0]
