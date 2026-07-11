import { useState } from "react";
import type { LiveStartRequest } from "./useLiveGame";

type SeatKind = "bot" | "llm";

interface SeatDraft {
  name: string;
  kind: SeatKind;
  bot: string;
  provider: string;
  model: string;
  apiKey: string;
}

const PROVIDERS: { id: string; label: string; needsKey: boolean; placeholder: string }[] = [
  { id: "anthropic", label: "Anthropic", needsKey: true, placeholder: "claude-opus-4-8 (default)" },
  { id: "openai", label: "OpenAI", needsKey: true, placeholder: "gpt-5.2" },
  { id: "xai", label: "xAI", needsKey: true, placeholder: "grok-4" },
  { id: "openrouter", label: "OpenRouter", needsKey: true, placeholder: "meta-llama/llama-4-maverick" },
  { id: "ollama", label: "Ollama (local)", needsKey: false, placeholder: "llama4" },
];

const BOTS = ["random", "checkcall", "fold", "allin"];

export const MODES = [
  "Pure poker — no communication",
  "Table talk — public speech",
  "Whispers — private, but leaky",
  "Interception — fragments reach eavesdroppers",
  "Gestures & codebooks — covert signals",
  "Attention economy — watching is a budget",
  "Full manipulation — notes, accusations, distractions, heat",
];

const blankSeat = (kind: SeatKind = "llm"): SeatDraft => ({
  name: "",
  kind,
  bot: "checkcall",
  provider: "anthropic",
  model: "",
  apiKey: "",
});

const botSeat = (bot: string): SeatDraft => ({ ...blankSeat("bot"), bot });

export function SetupForm({
  busy,
  onStart,
}: {
  busy: boolean;
  onStart: (req: LiveStartRequest) => void;
}) {
  const [seats, setSeats] = useState<SeatDraft[]>([
    blankSeat(),
    blankSeat(),
    botSeat("checkcall"),
    botSeat("random"),
  ]);
  const [mode, setMode] = useState(6);
  const [hands, setHands] = useState(6);
  const [seed, setSeed] = useState<string>("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [stack, setStack] = useState(1000);
  const [sb, setSb] = useState(5);
  const [bb, setBb] = useState(10);
  const [beliefs, setBeliefs] = useState(true);

  const patch = (i: number, p: Partial<SeatDraft>) =>
    setSeats((s) => s.map((seat, k) => (k === i ? { ...seat, ...p } : seat)));

  const submit = () => {
    onStart({
      seats: seats.map((s) => ({
        spec: s.kind === "bot" ? s.bot : `${s.provider}:${s.model.trim()}`,
        name: s.name.trim() || null,
        api_key: s.apiKey.trim() || null,
      })),
      hands,
      mode,
      seed: seed.trim() === "" ? null : Number(seed),
      stack,
      small_blind: sb,
      big_blind: bb,
      collect_beliefs: beliefs,
    });
  };

  const invalid = seats.some(
    (s) => s.kind === "llm" && s.provider !== "anthropic" && !s.model.trim(),
  );

  return (
    <div className="setup">
      <h1>Run a live game</h1>
      <p className="setup-sub">
        Seat 2–10 players — frontier models by API, local models through Ollama, or scripted
        bots (no keys needed). The game runs on your machine; keys stay in memory and are
        never written to disk.
      </p>

      <div className="setup-presets">
        <button
          className="btn secondary"
          onClick={() =>
            setSeats([botSeat("random"), botSeat("checkcall"), botSeat("allin"), botSeat("fold")])
          }
        >
          Bots scrimmage (no keys)
        </button>
        <button
          className="btn secondary"
          onClick={() =>
            setSeats([
              { ...blankSeat(), provider: "anthropic", name: "Claude" },
              { ...blankSeat(), provider: "openai", model: "gpt-5.2", name: "GPT" },
              { ...blankSeat(), provider: "xai", model: "grok-4", name: "Grok" },
              { ...blankSeat(), provider: "ollama", model: "llama4", name: "Llama" },
            ])
          }
        >
          Frontier table
        </button>
      </div>

      <div className="seat-grid">
        {seats.map((s, i) => {
          const provider = PROVIDERS.find((p) => p.id === s.provider)!;
          return (
            <div className="card-panel seat-card" key={i}>
              <div className="seat-card-top">
                <span className="chip-tag">Seat {i + 1}</span>
                <div className="seat-kind">
                  <button
                    className={s.kind === "llm" ? "on" : ""}
                    onClick={() => patch(i, { kind: "llm" })}
                  >
                    Model
                  </button>
                  <button
                    className={s.kind === "bot" ? "on" : ""}
                    onClick={() => patch(i, { kind: "bot" })}
                  >
                    Bot
                  </button>
                </div>
                {seats.length > 2 && (
                  <button
                    className="seat-remove"
                    title="Remove seat"
                    onClick={() => setSeats((all) => all.filter((_, k) => k !== i))}
                  >
                    ✕
                  </button>
                )}
              </div>

              <input
                placeholder={`Name (optional, e.g. ${s.kind === "bot" ? s.bot : provider.label})`}
                value={s.name}
                onChange={(e) => patch(i, { name: e.target.value })}
              />

              {s.kind === "bot" ? (
                <select value={s.bot} onChange={(e) => patch(i, { bot: e.target.value })}>
                  {BOTS.map((b) => (
                    <option key={b} value={b}>
                      {b}
                    </option>
                  ))}
                </select>
              ) : (
                <>
                  <select
                    value={s.provider}
                    onChange={(e) => patch(i, { provider: e.target.value })}
                  >
                    {PROVIDERS.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                  <input
                    placeholder={`Model — ${provider.placeholder}`}
                    value={s.model}
                    onChange={(e) => patch(i, { model: e.target.value })}
                  />
                  {provider.needsKey && (
                    <input
                      type="password"
                      placeholder="API key (blank = server env)"
                      value={s.apiKey}
                      onChange={(e) => patch(i, { apiKey: e.target.value })}
                      autoComplete="off"
                    />
                  )}
                </>
              )}
            </div>
          );
        })}
        {seats.length < 10 && (
          <button className="seat-add" onClick={() => setSeats((all) => [...all, blankSeat()])}>
            + Add seat
          </button>
        )}
      </div>

      <div className="card-panel setup-game">
        <div className="setup-row">
          <label className="section-label">Mode {mode}</label>
          <input
            type="range"
            min={0}
            max={6}
            value={mode}
            onChange={(e) => setMode(Number(e.target.value))}
          />
          <span className="setup-mode-desc">{MODES[mode]}</span>
        </div>
        <div className="setup-row inline">
          <label>
            Hands
            <input
              type="number"
              min={1}
              max={500}
              value={hands}
              onChange={(e) => setHands(Number(e.target.value))}
            />
          </label>
          <label>
            Seed
            <input
              placeholder="random"
              value={seed}
              onChange={(e) => setSeed(e.target.value.replace(/[^0-9]/g, ""))}
            />
          </label>
          <button className="setup-advanced" onClick={() => setShowAdvanced((v) => !v)}>
            {showAdvanced ? "− advanced" : "+ advanced"}
          </button>
        </div>
        {showAdvanced && (
          <div className="setup-row inline">
            <label>
              Stack
              <input type="number" min={1} value={stack} onChange={(e) => setStack(Number(e.target.value))} />
            </label>
            <label>
              SB
              <input type="number" min={1} value={sb} onChange={(e) => setSb(Number(e.target.value))} />
            </label>
            <label>
              BB
              <input type="number" min={1} value={bb} onChange={(e) => setBb(Number(e.target.value))} />
            </label>
            <label className="setup-check">
              <input type="checkbox" checked={beliefs} onChange={(e) => setBeliefs(e.target.checked)} />
              collect beliefs (mode 2+)
            </label>
          </div>
        )}
      </div>

      <button className="btn setup-start" onClick={submit} disabled={busy || invalid}>
        {busy ? "Dealing…" : "▶ Deal the game"}
      </button>
      {invalid && <p className="setup-hint">Every non-Anthropic model seat needs a model id.</p>}
    </div>
  );
}
