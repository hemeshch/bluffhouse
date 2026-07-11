import type { GameEvent } from "../types";

const TICK_COLORS: Partial<Record<GameEvent["type"], string>> = {
  message_sent: "var(--c-whisper)",
  ledger_updated: "var(--c-accusation)",
  board_dealt: "var(--green)",
  pot_awarded: "var(--c-note)",
};

export function Transport({
  events,
  cursor,
  playing,
  speed,
  presenting,
  onSeek,
  onStep,
  onTogglePlay,
  onSpeed,
  onPresent,
  onLegend,
}: {
  events: GameEvent[];
  cursor: number;
  playing: boolean;
  speed: number;
  presenting: boolean;
  onSeek: (i: number) => void;
  onStep: (d: number) => void;
  onTogglePlay: () => void;
  onSpeed: (s: number) => void;
  onPresent: () => void;
  onLegend: () => void;
}) {
  const max = Math.max(events.length - 1, 0);
  return (
    <div className="transport">
      <button className="t-btn" onClick={() => onStep(-1)} title="Back (←)">
        ◀
      </button>
      <button className="t-btn play" onClick={onTogglePlay} title="Play/pause (space)">
        {playing ? "⏸" : "▶"}
      </button>
      <button className="t-btn" onClick={() => onStep(1)} title="Forward (→)">
        ▶▶
      </button>

      <div className="scrub-wrap">
        <div className="scrub-ticks">
          {events.map((e, i) => {
            const color = TICK_COLORS[e.type];
            if (!color) return null;
            return (
              <span
                key={i}
                className="scrub-tick"
                style={{ left: `${max ? (i / max) * 100 : 0}%`, background: color }}
              />
            );
          })}
        </div>
        <input
          type="range"
          min={0}
          max={max}
          value={cursor}
          onChange={(e) => onSeek(Number(e.target.value))}
        />
      </div>

      <span className="t-counter mono">
        {cursor + 1} / {events.length}
      </span>

      <select value={speed} onChange={(e) => onSpeed(Number(e.target.value))} title="Speed">
        {[0.5, 1, 1.5, 2, 4].map((s) => (
          <option key={s} value={s}>
            {s}×
          </option>
        ))}
      </select>

      <button className={`t-btn${presenting ? " on" : ""}`} onClick={onPresent} title="Presentation mode (p)">
        ⛶
      </button>
      <button className="t-btn" onClick={onLegend} title="What am I looking at? (?)">
        ?
      </button>
    </div>
  );
}
