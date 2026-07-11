// Derived indexes over a replay payload, computed once per load.

import type { GameEvent, Observation, ReplayPayload } from "../types";
import { groupHands } from "./reduce";

export interface Reasoning {
  agent: string;
  text: string | null;
  fault: boolean;
}

export interface PayloadIndex {
  hands: Map<number, GameEvent[]>;
  handNos: number[];
  /** agent -> (source_event_id -> Observation) */
  obsByAgent: Record<string, Map<string, Observation>>;
  /** action_taken event_id -> the model reasoning behind it */
  reasoning: Record<string, Reasoning>;
  hasLedgers: boolean;
  hasAttention: boolean;
}

function looseJson(text: string): Record<string, unknown> | null {
  const i = text.indexOf("{");
  const j = text.lastIndexOf("}");
  if (i < 0 || j <= i) return null;
  try {
    return JSON.parse(text.slice(i, j + 1));
  } catch {
    return null;
  }
}

export function indexPayload(payload: ReplayPayload): PayloadIndex {
  const hands = groupHands(payload.events);
  const handNos = [...hands.keys()].sort((a, b) => a - b);

  const obsByAgent: Record<string, Map<string, Observation>> = {};
  for (const [aid, list] of Object.entries(payload.observations ?? {})) {
    obsByAgent[aid] = new Map(list.map((o) => [o.source_event_id, o]));
  }

  // The k-th action-phase decision of an agent explains its k-th action_taken.
  const reasoning: Record<string, Reasoning> = {};
  for (const [aid, calls] of Object.entries(payload.llm ?? {})) {
    const actions = payload.events.filter(
      (e) => e.type === "action_taken" && e.agent_id === aid,
    );
    const groups = new Map<number, typeof calls>();
    for (const c of calls) {
      if ((c.phase || "action") !== "action") continue;
      if (!groups.has(c.decision_id)) groups.set(c.decision_id, []);
      groups.get(c.decision_id)!.push(c);
    }
    [...groups.keys()]
      .sort((a, b) => a - b)
      .forEach((d, k) => {
        if (k >= actions.length) return;
        const grp = groups.get(d)!;
        const ok = grp.filter((c) => !c.parse_error).at(-1);
        let text: string | null = null;
        if (ok) {
          const j = looseJson(ok.response_text);
          if (j && typeof j.reasoning === "string") text = j.reasoning;
        }
        reasoning[actions[k].event_id] = {
          agent: aid,
          text,
          fault: grp.some((c) => c.parse_error),
        };
      });
  }

  return {
    hands,
    handNos,
    obsByAgent,
    reasoning,
    hasLedgers: payload.events.some((e) => e.type === "ledger_updated"),
    hasAttention: payload.events.some((e) => e.type === "attention_committed"),
  };
}
