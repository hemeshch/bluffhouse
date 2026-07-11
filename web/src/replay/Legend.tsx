import { MODALITY_META } from "../lib/format";

const ROWS: { icon: string; name: string; text: string }[] = [
  {
    icon: MODALITY_META.speech.icon,
    name: "Speech",
    text: "Public — the whole table hears it, always.",
  },
  {
    icon: MODALITY_META.whisper.icon,
    name: "Whisper",
    text: "Private, but leaky: nearby players can intercept a shredded fragment of it.",
  },
  {
    icon: MODALITY_META.note.icon,
    name: "Note",
    text: "Written and slid across the table. Sometimes exactly the wrong player reads it.",
  },
  {
    icon: MODALITY_META.accusation.icon,
    name: "Accusation",
    text: "A public callout. Nobody — not even the environment — checks whether it's true. It lands only as hard as the table believes it.",
  },
  {
    icon: MODALITY_META.gesture.icon,
    name: "Signals",
    text: "Gestures, eye contact, chip riffles — visible to observers, meaningful only with a shared code.",
  },
];

export function Legend({ onClose }: { onClose: () => void }) {
  return (
    <div className="legend-overlay" onClick={onClose}>
      <div className="legend card-panel" onClick={(e) => e.stopPropagation()}>
        <h2>What am I looking at?</h2>
        <p>
          Language models playing no-limit hold'em with real communication channels. The
          environment records <b>one objective truth</b>; every player lives in its own
          subjective slice of it. Switch POV at the top to see the same moment through
          different eyes — events a player missed simply don't exist for them.
        </p>
        <div className="legend-rows">
          {ROWS.map((r) => (
            <div className="legend-row" key={r.name}>
              <span className="legend-icon">{r.icon}</span>
              <div>
                <b>{r.name}</b>
                <p>{r.text}</p>
              </div>
            </div>
          ))}
          <div className="legend-row">
            <span className="legend-icon heat-demo" />
            <div>
              <b>Heat</b>
              <p>
                The red bar under a name: how suspicious the table has grown of that player —
                raised only when someone actually catches them signaling.
              </p>
            </div>
          </div>
        </div>
        <p className="legend-keys mono">← → step · space play · p presentation · ? legend</p>
        <button className="btn" onClick={onClose}>
          Got it
        </button>
      </div>
    </div>
  );
}
