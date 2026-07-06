"""One hand of no-limit hold'em, adapted from pokerkit into the bluffhouse
event stream.

pokerkit owns betting legality, side pots, and showdown resolution. The
harness owns the seed and the deck. This adapter drives pokerkit with
explicit cards and translates its operation log into typed GameEvents, so
the event log — not pokerkit state — is the ground truth everything else
consumes.

Seat convention: `order` runs clockwise from the first blind and the button
is always the LAST seat. Three-handed or more, order[0] posts the small
blind. Heads-up follows pokerkit's convention: order[0] posts the big blind
and order[1] is the button, posts the small blind, and acts first preflop.
"""

import warnings
from collections.abc import Callable

from pokerkit import Automation, Mode, NoLimitTexasHoldem
from pokerkit.state import (
    BlindOrStraddlePosting,
    BoardDealing,
    CheckingOrCalling,
    ChipsPulling,
    CompletionBettingOrRaisingTo,
    Folding,
    HoleCardsShowingOrMucking,
    HoleDealing,
)

from bluffhouse.engine.deck import Deck
from bluffhouse.models import (
    ActionTaken,
    ActionType,
    BlindPosted,
    BoardDealt,
    GameEvent,
    HandEnded,
    HandStarted,
    HoleCardsDealt,
    LegalActions,
    PokerAction,
    PotAwarded,
    SeatView,
    ShowdownReveal,
    Street,
    TableView,
)

EventSink = Callable[[GameEvent], GameEvent]

STREETS: tuple[Street, ...] = ("preflop", "flop", "turn", "river")

_AUTOMATIONS = (
    Automation.ANTE_POSTING,
    Automation.BET_COLLECTION,
    Automation.BLIND_OR_STRADDLE_POSTING,
    Automation.RUNOUT_COUNT_SELECTION,
    Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
    Automation.HAND_KILLING,
    Automation.CHIPS_PUSHING,
    Automation.CHIPS_PULLING,
)


class HandEngine:
    def __init__(
        self,
        hand_no: int,
        order: list[str],
        stacks: dict[str, int],
        small_blind: int,
        big_blind: int,
        deck: Deck,
        emit: EventSink,
    ):
        self.hand_no = hand_no
        self.order = list(order)
        self.deck = deck
        self._emit = emit
        self._small_blind = small_blind
        self._big_blind = big_blind
        self._start_stacks = {aid: stacks[aid] for aid in order}
        self._hole: dict[str, list[str]] = {aid: [] for aid in order}
        self._board: list[str] = []
        self._op_cursor = 0
        self._street_at_action: Street = "preflop"
        self._ended = False

        self.state = NoLimitTexasHoldem.create_state(
            automations=_AUTOMATIONS,
            ante_trimming_status=True,
            raw_antes=0,
            raw_blinds_or_straddles=(small_blind, big_blind),
            min_bet=big_blind,
            raw_starting_stacks=[stacks[aid] for aid in order],
            player_count=len(order),
            mode=Mode.CASH_GAME,
        )
        self.button = order[-1]

        self._emit(
            HandStarted(
                hand_no=hand_no,
                button=self.button,
                seat_order=tuple(order),
                stacks=dict(self._start_stacks),
            )
        )
        self._drain_ops()  # blinds post during state creation
        while self.state.can_deal_hole():
            self.state.deal_hole(self.deck.draw())
        self._drain_ops()
        self._advance()

    # ── public surface ──────────────────────────────────────────────

    @property
    def hand_over(self) -> bool:
        return not self.state.status

    @property
    def street(self) -> Street | None:
        index = self.state.street_index
        return STREETS[index] if index is not None else None

    @property
    def actor(self) -> str | None:
        index = self.state.actor_index
        return self.order[index] if index is not None else None

    @property
    def board(self) -> tuple[str, ...]:
        return tuple(self._board)

    @property
    def stacks(self) -> dict[str, int]:
        return {aid: self.state.stacks[i] for i, aid in enumerate(self.order)}

    def hole_cards(self, agent_id: str) -> tuple[str, str]:
        cards = self._hole[agent_id]
        return (cards[0], cards[1])

    def legal_actions(self) -> LegalActions:
        state = self.state
        callable_ = state.can_check_or_call()
        to_call = state.checking_or_calling_amount if callable_ else 0
        can_raise = state.can_complete_bet_or_raise_to()
        with warnings.catch_warnings():
            # pokerkit warns "no reason to fold" even when merely queried
            warnings.simplefilter("ignore", UserWarning)
            can_fold = state.can_fold()
        return LegalActions(
            can_fold=can_fold,
            can_check=callable_ and to_call == 0,
            can_call=callable_ and to_call > 0,
            call_amount=to_call,
            can_raise=can_raise,
            min_raise_to=state.min_completion_betting_or_raising_to_amount if can_raise else None,
            max_raise_to=state.max_completion_betting_or_raising_to_amount if can_raise else None,
        )

    def table_view(self) -> TableView:
        state = self.state
        seats = [
            SeatView(
                agent_id=aid,
                seat=i,
                stack=state.stacks[i],
                bet=state.bets[i],
                folded=not state.statuses[i],
                all_in=state.statuses[i] and state.stacks[i] == 0,
            )
            for i, aid in enumerate(self.order)
        ]
        return TableView(
            hand_no=self.hand_no,
            street=self.street,
            board=self.board,
            pot=state.total_pot_amount,
            button=self.button,
            small_blind=self._small_blind,
            big_blind=self._big_blind,
            seats=seats,
            to_act=self.actor,
        )

    def apply(self, action: PokerAction) -> None:
        """Apply a LEGAL action for the current actor. The harness is
        responsible for validation/repair before calling this."""
        if self.actor is None:
            raise RuntimeError("no player to act")
        street = self.street
        assert street is not None
        self._street_at_action = street

        if action.action is ActionType.FOLD:
            self.state.fold()
        elif action.action in (ActionType.CHECK, ActionType.CALL):
            self.state.check_or_call()
        elif action.action is ActionType.RAISE_TO:
            if action.amount is None:
                raise ValueError("raise_to requires an amount")
            self.state.complete_bet_or_raise_to(action.amount)
        self._drain_ops()
        self._advance()

    # ── pokerkit plumbing ───────────────────────────────────────────

    def _advance(self) -> None:
        """Burn and deal board cards until someone can act or the hand is
        over. Handles all-in runouts, where several streets deal at once."""
        state = self.state
        while state.status and state.actor_index is None:
            if state.can_burn_card():
                state.burn_card(self.deck.draw())
                self._drain_ops()
            elif state.can_deal_board():
                count = state.board_dealing_count
                assert count, "board dealing expected but count is empty"
                state.deal_board("".join(self.deck.draw() for _ in range(count)))
                self._drain_ops()
            else:
                break
        self._drain_ops()
        if not state.status and not self._ended:
            self._ended = True
            stacks = self.stacks
            deltas = {aid: stacks[aid] - self._start_stacks[aid] for aid in self.order}
            self._emit(HandEnded(hand_no=self.hand_no, stacks=stacks, deltas=deltas))

    def _drain_ops(self) -> None:
        ops = self.state.operations
        while self._op_cursor < len(ops):
            op = ops[self._op_cursor]
            self._op_cursor += 1
            self._translate(op)

    def _translate(self, op: object) -> None:
        if isinstance(op, BlindOrStraddlePosting):
            if len(self.order) == 2:  # heads-up: the button posts the small blind
                kind = "big" if op.player_index == 0 else "small"
            else:
                kind = "small" if op.player_index == 0 else "big"
            self._emit(
                BlindPosted(
                    hand_no=self.hand_no,
                    agent_id=self.order[op.player_index],
                    blind=kind,
                    amount=op.amount,
                )
            )
        elif isinstance(op, HoleDealing):
            aid = self.order[op.player_index]
            self._hole[aid].extend(repr(c) for c in op.cards)
            if len(self._hole[aid]) == 2:
                self._emit(
                    HoleCardsDealt(
                        hand_no=self.hand_no,
                        agent_id=aid,
                        cards=self.hole_cards(aid),
                        visible_to=(aid,),
                    )
                )
        elif isinstance(op, Folding):
            self._emit_action(op.player_index, ActionType.FOLD, None)
        elif isinstance(op, CheckingOrCalling):
            if op.amount == 0:
                self._emit_action(op.player_index, ActionType.CHECK, None)
            else:
                self._emit_action(op.player_index, ActionType.CALL, op.amount)
        elif isinstance(op, CompletionBettingOrRaisingTo):
            self._emit_action(op.player_index, ActionType.RAISE_TO, op.amount)
        elif isinstance(op, BoardDealing):
            dealt = tuple(repr(c) for c in op.cards)
            self._board.extend(dealt)
            street: Street = {3: "flop", 4: "turn", 5: "river"}[len(self._board)]
            self._emit(
                BoardDealt(
                    hand_no=self.hand_no,
                    street=street,
                    cards=dealt,
                    board=tuple(self._board),
                )
            )
        elif isinstance(op, HoleCardsShowingOrMucking):
            if op.hole_cards:  # empty tuple = mucked
                cards = tuple(repr(c) for c in op.hole_cards)
                self._emit(
                    ShowdownReveal(
                        hand_no=self.hand_no,
                        agent_id=self.order[op.player_index],
                        cards=(cards[0], cards[1]),
                    )
                )
        elif isinstance(op, ChipsPulling):
            # amount = chips collected. When everyone folds, this includes
            # the winner's own uncalled bet; net profit lives in HandEnded.deltas.
            self._emit(
                PotAwarded(
                    hand_no=self.hand_no,
                    agent_id=self.order[op.player_index],
                    amount=op.amount,
                )
            )
        # CardBurning, BetCollection, ChipsPushing, HandKilling and friends
        # are internal bookkeeping with no informational content for agents.

    def _emit_action(self, player_index: int, kind: ActionType, amount: int | None) -> None:
        self._emit(
            ActionTaken(
                hand_no=self.hand_no,
                agent_id=self.order[player_index],
                street=self._street_at_action,
                action=kind,
                amount=amount,
                all_in=self.state.statuses[player_index] and self.state.stacks[player_index] == 0,
            )
        )
