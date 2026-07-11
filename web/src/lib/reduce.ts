// Table-state projection: replay events 0..upto within one hand.
// Faithful port of the reducer the Python-injected viewer used; the golden
// fixture test (reduce.test.ts) pins it against a real demo run.

import type { GameEvent } from "../types";

export interface TableState {
  order: string[];
  stacks: Record<string, number>;
  bets: Record<string, number>;
  committed: Record<string, number>;
  awarded: Record<string, number>;
  folded: Record<string, boolean>;
  allin: Record<string, boolean>;
  hole: Record<string, [string, string]>;
  revealed: Record<string, [string, string]>;
  board: string[];
  button: string | null;
  /** live attention per agent, reset each street (mode 5+) */
  attention: Record<string, { watch: Record<string, number>; table: number }>;
}

export function reduce(events: GameEvent[], upto: number): TableState {
  const s: TableState = {
    order: [],
    stacks: {},
    bets: {},
    committed: {},
    awarded: {},
    folded: {},
    allin: {},
    hole: {},
    revealed: {},
    board: [],
    button: null,
    attention: {},
  };
  for (let i = 0; i <= upto && i < events.length; i++) {
    const e = events[i];
    switch (e.type) {
      case "hand_started":
        s.order = [...e.seat_order];
        s.stacks = { ...e.stacks };
        s.button = e.button;
        for (const a of e.seat_order) {
          s.bets[a] = 0;
          s.committed[a] = 0;
          s.awarded[a] = 0;
        }
        break;
      case "blind_posted":
        s.bets[e.agent_id] += e.amount;
        s.stacks[e.agent_id] -= e.amount;
        s.committed[e.agent_id] += e.amount;
        break;
      case "hole_cards_dealt":
        s.hole[e.agent_id] = e.cards;
        break;
      case "action_taken": {
        const a = e.agent_id;
        if (e.action === "fold") s.folded[a] = true;
        else if (e.action === "call") {
          const amt = e.amount ?? 0;
          s.bets[a] += amt;
          s.stacks[a] -= amt;
          s.committed[a] += amt;
        } else if (e.action === "raise_to") {
          const d = (e.amount ?? 0) - s.bets[a];
          s.bets[a] = e.amount ?? 0;
          s.stacks[a] -= d;
          s.committed[a] += d;
        }
        if (e.all_in) s.allin[a] = true;
        break;
      }
      case "attention_committed":
        s.attention[e.agent_id] = { watch: e.watch, table: e.table };
        break;
      case "board_dealt":
        s.board = [...e.board];
        for (const a of s.order) s.bets[a] = 0;
        s.attention = {}; // a new street: attention is re-committed
        break;
      case "showdown_reveal":
        s.revealed[e.agent_id] = e.cards;
        break;
      case "pot_awarded":
        s.stacks[e.agent_id] += e.amount;
        s.awarded[e.agent_id] += e.amount;
        for (const a of s.order) s.bets[a] = 0;
        break;
      case "hand_ended":
        s.stacks = { ...e.stacks };
        for (const a of s.order) s.bets[a] = 0;
        break;
    }
  }
  return s;
}

export function potSize(s: TableState): number {
  const sum = (m: Record<string, number>) =>
    Object.values(m).reduce((x, y) => x + y, 0);
  return sum(s.committed) - sum(s.awarded);
}

export function streetOf(s: TableState): string {
  return { 0: "pre-flop", 3: "flop", 4: "turn", 5: "river" }[s.board.length] ?? "";
}

/** Group the flat event log into hand chapters (hand_no >= 1). */
export function groupHands(events: GameEvent[]): Map<number, GameEvent[]> {
  const hands = new Map<number, GameEvent[]>();
  for (const e of events) {
    if (e.hand_no >= 1) {
      if (!hands.has(e.hand_no)) hands.set(e.hand_no, []);
      hands.get(e.hand_no)!.push(e);
    }
  }
  return hands;
}

/** Latest suspicion per agent at a global sequence point. */
export function heatAt(
  events: GameEvent[],
  seq: number,
): Record<string, { suspicion: number; delta: number }> {
  const heat: Record<string, { suspicion: number; delta: number }> = {};
  for (const e of events) {
    if (e.type === "ledger_updated" && e.seq <= seq) {
      heat[e.agent_id] = { suspicion: e.suspicion, delta: e.delta_suspicion };
    }
  }
  return heat;
}
