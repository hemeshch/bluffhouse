// Golden-fixture test: the reducer replayed over a real demo game
// (seed 11, mode 6). Regenerate the fixture with:
//   uv run python -c "import json; from bluffhouse.demo import demo_game; \
//     json.dump([json.loads(l) for l in demo_game().log.to_jsonl().splitlines()], \
//     open('web/src/lib/__fixtures__/demo-events.json','w'), indent=1)"

import { describe, expect, it } from "vitest";
import type { GameEvent, GameStarted, HandEnded, MessageSent } from "../types";
import { groupHands, heatAt, potSize, reduce } from "./reduce";
import raw from "./__fixtures__/demo-events.json";

const events = raw as unknown as GameEvent[];
const start = events.find((e) => e.type === "game_started") as GameStarted;
const hands = groupHands(events);

describe("reduce over the seed-11 demo game", () => {
  it("groups six hands", () => {
    expect([...hands.keys()].sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("matches hand_ended stacks exactly at the end of every hand", () => {
    for (const [handNo, list] of hands) {
      const ended = list.find((e) => e.type === "hand_ended") as HandEnded | undefined;
      expect(ended, `hand ${handNo} has hand_ended`).toBeTruthy();
      const s = reduce(list, list.length - 1);
      expect(s.stacks, `hand ${handNo} final stacks`).toEqual(ended!.stacks);
      expect(potSize(s), `hand ${handNo} pot returns to zero`).toBe(0);
    }
  });

  it("conserves chips at every single step", () => {
    const total = start.agent_ids.length * start.starting_stack;
    for (const [handNo, list] of hands) {
      for (let i = 0; i < list.length; i++) {
        const s = reduce(list, i);
        const inStacks = Object.values(s.stacks).reduce((a, b) => a + b, 0);
        const pot = potSize(s);
        expect(pot, `hand ${handNo} step ${i}: pot never negative`).toBeGreaterThanOrEqual(0);
        // busted players keep stack 0 entries in hand_started snapshots, so
        // stacks + live pot always re-add to the table total
        expect(inStacks + pot, `hand ${handNo} step ${i}: conservation`).toBe(total);
      }
    }
  });

  it("tracks the button and seat order from hand_started", () => {
    const list = hands.get(1)!;
    const s = reduce(list, list.length - 1);
    expect(s.order.length).toBe(4);
    expect(s.button).toBe(s.order[s.order.length - 1]);
  });

  it("sees the demo drama: whisper receptions are the known seed-11 outcomes", () => {
    const whisper = events.find(
      (e) => e.type === "message_sent" && e.modality === "whisper",
    ) as MessageSent;
    expect(whisper.sender).toBe("Grok");
    expect(whisper.receptions["GPT"].outcome).toBe("clear");
    expect(whisper.receptions["Claude"].outcome).toBe("fragment");
    expect(whisper.receptions["Claude"].confidence).toBeCloseTo(0.41, 2);
    expect(whisper.receptions["Llama"].outcome).toBe("missed");
  });

  it("accumulates heat from ledger events", () => {
    const last = events[events.length - 1];
    const heat = heatAt(events, last.seq);
    // the demo's accusation and noticed signals leave suspicion on the ledger
    expect(Object.keys(heat).length).toBeGreaterThan(0);
    for (const h of Object.values(heat)) expect(h.suspicion).toBeGreaterThan(0);
  });
});
