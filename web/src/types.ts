// Hand-written mirror of the Python event model (src/bluffhouse/models/) and
// GameResult.replay_payload(). Field names must track the pydantic models.

export type Street = "preflop" | "flop" | "turn" | "river";
export type Visibility = "public" | "private" | "env";
export type Modality =
  | "speech"
  | "whisper"
  | "gesture"
  | "eye_contact"
  | "chip_signal"
  | "note"
  | "accusation";

interface Base {
  seq: number;
  event_id: string;
  hand_no: number;
  visibility: Visibility;
  visible_to: string[];
}

export interface GameStarted extends Base {
  type: "game_started";
  agent_ids: string[];
  starting_stack: number;
  small_blind: number;
  big_blind: number;
  num_hands: number;
  mode: number;
}

export interface HandStarted extends Base {
  type: "hand_started";
  button: string;
  seat_order: string[];
  stacks: Record<string, number>;
}

export interface BlindPosted extends Base {
  type: "blind_posted";
  agent_id: string;
  blind: "small" | "big";
  amount: number;
}

export interface HoleCardsDealt extends Base {
  type: "hole_cards_dealt";
  agent_id: string;
  cards: [string, string];
}

export type ActionType = "fold" | "check" | "call" | "raise_to";

export interface ActionTaken extends Base {
  type: "action_taken";
  agent_id: string;
  street: Street;
  action: ActionType;
  amount: number | null;
  all_in: boolean;
}

export interface ActionRepaired extends Base {
  type: "action_repaired";
  agent_id: string;
  submitted: { action: string; amount?: number | null };
  applied: { action: string; amount?: number | null };
  reason: string;
}

export interface AttentionCommitted extends Base {
  type: "attention_committed";
  agent_id: string;
  street: Street;
  watch: Record<string, number>;
  table: number;
}

export interface Reception {
  outcome: "clear" | "fragment" | "surface" | "missed";
  confidence: number;
  text: string | null;
}

export interface MessageSent extends Base {
  type: "message_sent";
  sender: string;
  modality: Modality;
  targets: string[];
  text: string;
  intent: string | null;
  subtlety: number;
  distraction: number;
  street: Street;
  receptions: Record<string, Reception>;
}

export interface LedgerUpdated extends Base {
  type: "ledger_updated";
  agent_id: string;
  suspicion: number;
  delta_suspicion: number;
  reason: string;
}

export interface BeliefsUpdated extends Base {
  type: "beliefs_updated";
  agent_id: string;
  street: Street;
  beliefs: Record<string, number>;
}

export interface MessageRejected extends Base {
  type: "message_rejected";
  sender: string;
  reason: string;
}

export interface BoardDealt extends Base {
  type: "board_dealt";
  street: Street;
  cards: string[];
  board: string[];
}

export interface ShowdownReveal extends Base {
  type: "showdown_reveal";
  agent_id: string;
  cards: [string, string];
}

export interface PotAwarded extends Base {
  type: "pot_awarded";
  agent_id: string;
  amount: number;
}

export interface HandEnded extends Base {
  type: "hand_ended";
  stacks: Record<string, number>;
  deltas: Record<string, number>;
}

export interface GameEnded extends Base {
  type: "game_ended";
  hands_played: number;
  stacks: Record<string, number>;
}

export type GameEvent =
  | GameStarted
  | HandStarted
  | BlindPosted
  | HoleCardsDealt
  | ActionTaken
  | ActionRepaired
  | AttentionCommitted
  | MessageSent
  | LedgerUpdated
  | BeliefsUpdated
  | MessageRejected
  | BoardDealt
  | ShowdownReveal
  | PotAwarded
  | HandEnded
  | GameEnded;

export interface Observation {
  observer: string;
  source_event_id: string;
  hand_no: number;
  kind: string;
  perceived_text: string;
  confidence: number;
  decoded_meaning: string | null;
}

export interface LLMCall {
  agent_id: string;
  hand_no: number;
  decision_id: number;
  phase: string;
  attempt: number;
  response_text: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency_s: number;
  parse_error: string | null;
  action: string | null;
  thinking?: string | null;
}

export interface Judgment {
  event_id: string;
  hand_no: number;
  sender: string;
  modality: string;
  targets: string[];
  model: string;
  deception: number;
  manipulation: number;
  reasoning: string;
  parse_error: string | null;
}

export interface RunMeta {
  seed: number;
  agent_ids: string[];
  small_blind: number;
  big_blind: number;
  starting_stack: number;
  hands_played: number;
  final_stacks: Record<string, number>;
  ledgers: Record<string, { suspicion: number }>;
}

export interface ReplayPayload {
  run: RunMeta;
  events: GameEvent[];
  observations: Record<string, Observation[]>;
  llm: Record<string, LLMCall[]>;
  judgments: Judgment[];
}

// ── hub / bench / leaderboard API shapes ─────────────────────────────

export interface HubRun {
  name: string;
  seed: number | null;
  mode: number | null;
  hands: number | null;
  stacks: Record<string, number>;
  replay: string | null;
}

export interface HubBench {
  name: string;
  seed: number | null;
  mode: number | null;
  hands: number | null;
  rows: [string, number][];
  replays: string[];
}

export interface HubSweep {
  name: string;
  seeds: number[];
  mode: number | null;
  rows: [string, number, [number, number]][];
}

export interface HubEntries {
  sweeps: HubSweep[];
  benches: HubBench[];
  runs: HubRun[];
}

export interface Scorecard {
  adjusted_chips: number;
  raw_chips: number;
  dimensions: Record<string, number>;
  raw_dimensions: Record<string, number>;
  counts: Record<string, unknown>;
  suspicion: number;
}

export interface BenchSummary {
  seed: number;
  num_hands: number;
  mode: number;
  entrants: string[];
  seatings: Record<string, string>[];
  scorecards: Record<string, Scorecard>;
}

export interface LeaderboardSummary {
  seeds: number[];
  num_hands: number;
  mode: number;
  rotations: number;
  entrants: string[];
  leaderboard: Record<
    string,
    {
      mean_adjusted_chips: number;
      ci95: [number, number];
      seed_wins: number;
      per_seed_adjusted_chips: number[];
    }
  >;
  win_rate_matrix: Record<string, Record<string, number>>;
  bench_dirs: string[];
}
