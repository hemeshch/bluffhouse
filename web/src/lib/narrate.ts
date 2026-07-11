// Plain-English narration: every event becomes one cinematic sentence built
// from typed segments so the UI can color player names and quotes.

import type { GameEvent, MessageSent, Reception } from "../types";

export type Segment =
  | { kind: "text"; text: string }
  | { kind: "player"; text: string }
  | { kind: "cards"; text: string }
  | { kind: "quote"; text: string }
  | { kind: "muted"; text: string };

const t = (text: string): Segment => ({ kind: "text", text });
const p = (id: string): Segment => ({ kind: "player", text: id });
const cards = (cs: readonly string[]): Segment => ({ kind: "cards", text: cs.join(" ") });
const q = (text: string): Segment => ({ kind: "quote", text: `“${text}”` });
const m = (text: string): Segment => ({ kind: "muted", text });

function players(ids: readonly string[]): Segment[] {
  const out: Segment[] = [];
  ids.forEach((id, i) => {
    if (i > 0) out.push(t(i === ids.length - 1 ? " and " : ", "));
    out.push(p(id));
  });
  return out;
}

function messageVerb(e: MessageSent): Segment[] {
  const to = e.targets.length ? e.targets : [];
  switch (e.modality) {
    case "speech":
      return [p(e.sender), t(" says "), q(e.text)];
    case "whisper":
      return [p(e.sender), t(" leans over and whispers to "), ...players(to), t(": "), q(e.text)];
    case "note":
      return [p(e.sender), t(" slides a folded note to "), ...players(to), t(": "), q(e.text)];
    case "accusation":
      return [p(e.sender), t(" points at "), ...players(to), t(" — "), q(e.text)];
    case "gesture":
      return [p(e.sender), t(" makes a gesture at "), ...players(to), t(": "), q(e.text)];
    case "eye_contact":
      return [p(e.sender), t(" holds eye contact with "), ...players(to), t(": "), q(e.text)];
    case "chip_signal":
      return [p(e.sender), t(" riffles chips at "), ...players(to), t(": "), q(e.text)];
  }
}

/** The ground-truth narration for one event. */
export function narrate(e: GameEvent): Segment[] {
  switch (e.type) {
    case "game_started":
      return [t(`A new table: ${e.agent_ids.length} players, ${e.num_hands} hands, mode ${e.mode}.`)];
    case "hand_started":
      return [t(`Hand ${e.hand_no}. `), p(e.button), t(" has the button.")];
    case "blind_posted":
      return [p(e.agent_id), t(` posts the ${e.blind} blind — ${e.amount}.`)];
    case "hole_cards_dealt":
      return [p(e.agent_id), t(" is dealt "), cards(e.cards), t(".")];
    case "action_taken": {
      const allin = e.all_in ? " — all in!" : ".";
      if (e.action === "fold") return [p(e.agent_id), t(" folds.")];
      if (e.action === "check") return [p(e.agent_id), t(" checks.")];
      if (e.action === "call") return [p(e.agent_id), t(` calls ${e.amount}${allin}`)];
      return [p(e.agent_id), t(` raises to ${e.amount}${allin}`)];
    }
    case "action_repaired":
      return [
        p(e.agent_id),
        t(" tried an illegal move"),
        m(` — ${e.submitted.action} became ${e.applied.action} (${e.reason}).`),
      ];
    case "message_sent":
      return messageVerb(e);
    case "ledger_updated": {
      const d = e.delta_suspicion;
      return [
        p(e.agent_id),
        t(` draws heat — suspicion ${e.suspicion.toFixed(2)} `),
        m(`(${d >= 0 ? "+" : ""}${d.toFixed(2)}: ${e.reason})`),
      ];
    }
    case "beliefs_updated": {
      const top = Object.entries(e.beliefs).sort((a, b) => b[1] - a[1])[0];
      if (!top) return [p(e.agent_id), t(" updates its private read of the table.")];
      return [
        p(e.agent_id),
        t(" privately updates its read — "),
        m(`${top[0].replaceAll("_", " ")}: ${Math.round(top[1] * 100)}%`),
      ];
    }
    case "attention_committed": {
      const watched = Object.entries(e.watch).sort((a, b) => b[1] - a[1]);
      if (!watched.length)
        return [p(e.agent_id), t(" keeps a loose eye on the whole table.")];
      const [who, w] = watched[0];
      const verb = w >= 0.5 ? " locks onto " : " keeps watching ";
      return [p(e.agent_id), t(verb), p(who), m(` (${Math.round(w * 100)}% of its attention)`)];
    }
    case "message_rejected":
      return [p(e.sender), t("'s message was dropped"), m(` — ${e.reason}.`)];
    case "board_dealt": {
      const label = e.street[0].toUpperCase() + e.street.slice(1);
      return [t(`${label}: `), cards(e.cards), t(".")];
    }
    case "showdown_reveal":
      return [p(e.agent_id), t(" turns over "), cards(e.cards), t(".")];
    case "pot_awarded":
      return [p(e.agent_id), t(` rakes in the pot — ${e.amount} chips.`)];
    case "hand_ended": {
      const winners = Object.entries(e.deltas)
        .filter(([, d]) => d > 0)
        .sort((a, b) => b[1] - a[1]);
      if (!winners.length) return [t(`Hand ${e.hand_no} ends.`)];
      const segs: Segment[] = [t(`Hand ${e.hand_no} ends: `)];
      winners.forEach(([a, d], i) => {
        if (i > 0) segs.push(t(", "));
        segs.push(p(a), t(` +${d}`));
      });
      segs.push(t("."));
      return segs;
    }
    case "game_ended": {
      const ranked = Object.entries(e.stacks).sort((a, b) => b[1] - a[1]);
      return [t("Game over. "), p(ranked[0][0]), t(` leaves with ${ranked[0][1]} chips.`)];
    }
  }
}

/** Extra ground-truth-only line: the sender's private intent. */
export function intentLine(e: GameEvent): Segment[] | null {
  if (e.type !== "message_sent" || !e.intent || e.intent === e.text) return null;
  return [m("intent: "), t(e.intent)];
}

/** "GPT received it clean · Claude caught a fragment (41%) · Llama missed it" */
export function receptionSummary(e: MessageSent): Segment[] | null {
  const entries = Object.entries(e.receptions ?? {}).filter(([a]) => a !== e.sender);
  if (!entries.length || e.modality === "speech") return null;
  const segs: Segment[] = [];
  const order: Record<Reception["outcome"], number> = {
    clear: 0,
    fragment: 1,
    surface: 2,
    missed: 3,
  };
  entries.sort((a, b) => order[a[1].outcome] - order[b[1].outcome]);
  entries.forEach(([agent, r], i) => {
    if (i > 0) segs.push(m("  ·  "));
    segs.push(p(agent));
    const pctTxt = ` (${Math.round(r.confidence * 100)}%)`;
    if (r.outcome === "clear") segs.push(m(" got it clean"));
    else if (r.outcome === "fragment") segs.push(m(` caught a fragment${pctTxt}`));
    else if (r.outcome === "surface") segs.push(m(` noticed something${pctTxt}`));
    else segs.push(m(" missed it entirely"));
  });
  return segs;
}

/** Which players a message-event visually involves (for effects/highlights). */
export function messageAudience(e: MessageSent): {
  clear: string[];
  fragment: string[];
  surface: string[];
} {
  const clear: string[] = [];
  const fragment: string[] = [];
  const surface: string[] = [];
  for (const [agent, r] of Object.entries(e.receptions ?? {})) {
    if (agent === e.sender) continue;
    if (r.outcome === "clear") clear.push(agent);
    else if (r.outcome === "fragment") fragment.push(agent);
    else if (r.outcome === "surface") surface.push(agent);
  }
  return { clear, fragment, surface };
}
