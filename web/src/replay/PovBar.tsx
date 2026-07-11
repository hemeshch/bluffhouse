import type { Pov } from "./ReplayApp";
import { playerColor } from "../lib/format";

export function PovBar({
  agentIds,
  pov,
  onPick,
}: {
  agentIds: string[];
  pov: Pov;
  onPick: (p: Pov) => void;
}) {
  return (
    <nav className="pov-bar">
      <button
        className={`pov-tab${pov === "truth" ? " on" : ""}`}
        onClick={() => onPick("truth")}
        title="Ground truth: every event, every intent"
      >
        <span className="pov-badge env">ENV</span>
        The table
      </button>
      {agentIds.map((id) => (
        <button
          key={id}
          className={`pov-tab${pov === id ? " on" : ""}`}
          onClick={() => onPick(id)}
          title={`Only what ${id} actually perceived`}
        >
          <span className="pov-ava" style={{ background: playerColor(agentIds, id) }}>
            {id[0]}
          </span>
          {id}
        </button>
      ))}
    </nav>
  );
}
