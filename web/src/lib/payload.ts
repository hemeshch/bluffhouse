// Derived indexes over a replay payload, computed once per load.
//
// Reasoning pairing: every LLM decision (action / attention / beliefs / comm)
// carries a private "reasoning" field in its JSON reply, recorded only in the
// transcript. Here each call is re-attached to the event it produced so the
// feed can show why — including comm calls that produced NO event (the model
// chose silence), which anchor to the same street's attention event.

import type { GameEvent, LLMCall, Observation, ReplayPayload } from "../types";
import { groupHands } from "./reduce";

export interface PhaseNote {
  kind: "action" | "attention" | "beliefs" | "comm";
  agent: string;
  text: string | null;
  /** provider-native chain-of-thought, when the adapter captured one */
  thinking: string | null;
  fault: boolean;
}

export interface Silence {
  agent: string;
  text: string | null;
  thinking: string | null;
}

export interface PayloadIndex {
  hands: Map<number, GameEvent[]>;
  handNos: number[];
  /** agent -> (source_event_id -> Observation) */
  obsByAgent: Record<string, Map<string, Observation>>;
  /** event_id -> private reasoning behind that event */
  notes: Record<string, PhaseNote[]>;
  /** attention event_id -> comm decisions that street that chose silence */
  silences: Record<string, Silence[]>;
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

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}

/** Group one agent's calls of a phase by decision, keep the last attempt. */
function decisions(calls: LLMCall[], phase: string): LLMCall[][] {
  const groups = new Map<number, LLMCall[]>();
  for (const c of calls) {
    if ((c.phase || "action") !== phase) continue;
    if (!groups.has(c.decision_id)) groups.set(c.decision_id, []);
    groups.get(c.decision_id)!.push(c);
  }
  return [...groups.keys()].sort((a, b) => a - b).map((d) => groups.get(d)!);
}

function noteFrom(
  kind: PhaseNote["kind"],
  agent: string,
  grp: LLMCall[],
): PhaseNote {
  const ok = grp.filter((c) => !c.parse_error).at(-1);
  const j = ok ? looseJson(ok.response_text) : null;
  const last = grp.at(-1)!;
  return {
    kind,
    agent,
    text: j ? str(j.reasoning) : null,
    thinking: ok?.thinking ?? last.thinking ?? null,
    fault: grp.some((c) => c.parse_error),
  };
}

export function indexPayload(payload: ReplayPayload): PayloadIndex {
  const hands = groupHands(payload.events);
  const handNos = [...hands.keys()].sort((a, b) => a - b);

  const obsByAgent: Record<string, Map<string, Observation>> = {};
  for (const [aid, list] of Object.entries(payload.observations ?? {})) {
    obsByAgent[aid] = new Map(list.map((o) => [o.source_event_id, o]));
  }

  const notes: Record<string, PhaseNote[]> = {};
  const silences: Record<string, Silence[]> = {};
  const push = <T,>(store: Record<string, T[]>, key: string, value: T) => {
    (store[key] ??= []).push(value);
  };

  for (const [aid, calls] of Object.entries(payload.llm ?? {})) {
    const eventsBy = (type: GameEvent["type"], who: (e: GameEvent) => string) =>
      payload.events.filter((e) => e.type === type && who(e) === aid);

    // action: k-th decision ↔ k-th action_taken
    const actions = eventsBy("action_taken", (e) => ("agent_id" in e ? e.agent_id : ""));
    decisions(calls, "action").forEach((grp, k) => {
      if (k < actions.length) push(notes, actions[k].event_id, noteFrom("action", aid, grp));
    });

    // attention: the harness emits an event for every live player every
    // street (a failed/absent plan becomes the default), so k-th ↔ k-th holds
    const attns = eventsBy("attention_committed", (e) => ("agent_id" in e ? e.agent_id : ""));
    decisions(calls, "attention").forEach((grp, k) => {
      if (k < attns.length) push(notes, attns[k].event_id, noteFrom("attention", aid, grp));
    });

    // beliefs: an event exists only when the call parsed to a non-empty
    // report — advance the event pointer on success only
    const beliefs = eventsBy("beliefs_updated", (e) => ("agent_id" in e ? e.agent_id : ""));
    let bi = 0;
    for (const grp of decisions(calls, "beliefs")) {
      if (grp.every((c) => c.parse_error)) continue;
      if (bi >= beliefs.length) break;
      push(notes, beliefs[bi].event_id, noteFrom("beliefs", aid, grp));
      bi++;
    }

    // comm: a sent message pairs with its message_sent event (in-order per
    // hand); a null message is a silence, anchored to the same street's
    // attention event when one exists (mode 5+)
    const sent = payload.events.filter(
      (e) => e.type === "message_sent" && "sender" in e && e.sender === aid,
    );
    let si = 0;
    decisions(calls, "comm").forEach((grp, k) => {
      const note = noteFrom("comm", aid, grp);
      const ok = grp.filter((c) => !c.parse_error).at(-1);
      const j = ok ? looseJson(ok.response_text) : null;
      const spoke = j ? Boolean(str(j.message) || str(j.surface)) : false;
      if (spoke && si < sent.length && sent[si].hand_no === grp.at(-1)!.hand_no) {
        push(notes, sent[si].event_id, note);
        si++;
        return;
      }
      if (k < attns.length) {
        push(silences, attns[k].event_id, {
          agent: aid,
          text: note.fault ? "(reply could not be parsed)" : note.text,
          thinking: note.thinking,
        });
      }
    });
  }

  return {
    hands,
    handNos,
    obsByAgent,
    notes,
    silences,
    hasLedgers: payload.events.some((e) => e.type === "ledger_updated"),
    hasAttention: payload.events.some((e) => e.type === "attention_committed"),
  };
}
