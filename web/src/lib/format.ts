import type { Modality } from "../types";

export const SUITS: Record<string, string> = {
  s: "♠",
  h: "♥",
  d: "♦",
  c: "♣",
};

export function cardParts(code: string): { rank: string; suit: string; red: boolean } {
  const rank = code[0] === "T" ? "10" : code[0];
  const suit = SUITS[code[1]] ?? "?";
  return { rank, suit, red: code[1] === "h" || code[1] === "d" };
}

// Seat accents — assigned by index in run.agent_ids, stable across POVs.
const PLAYER_COLORS = [
  "#e8a75d", // amber
  "#7fa9ff", // blue
  "#d97ba6", // pink
  "#5bc0be", // teal
  "#a78bfa", // violet
  "#e2c044", // gold
  "#e36c6c", // red
  "#81b64c", // green
  "#c8b89a", // sand
  "#8fa3ad", // slate
];

export function playerColor(agentIds: string[], id: string): string {
  const i = agentIds.indexOf(id);
  return PLAYER_COLORS[(i + PLAYER_COLORS.length) % PLAYER_COLORS.length];
}

export const MODALITY_META: Record<
  Modality,
  { icon: string; label: string; color: string }
> = {
  speech: { icon: "💬", label: "says", color: "var(--c-speech)" },
  whisper: { icon: "🤫", label: "whispers", color: "var(--c-whisper)" },
  note: { icon: "📝", label: "note", color: "var(--c-note)" },
  accusation: { icon: "⚠️", label: "accuses", color: "var(--c-accusation)" },
  gesture: { icon: "👋", label: "gestures", color: "var(--c-sign)" },
  eye_contact: { icon: "👁️", label: "eye contact", color: "var(--c-sign)" },
  chip_signal: { icon: "🪙", label: "chip signal", color: "var(--c-sign)" },
};

export function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}

export function listNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}
