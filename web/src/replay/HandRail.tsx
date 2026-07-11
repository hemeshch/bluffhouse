import type { PayloadIndex } from "../lib/payload";
import type { RunMeta } from "../types";
import { playerColor } from "../lib/format";

export function HandRail({
  index,
  run,
  handNo,
  agentIds,
  onPick,
}: {
  index: PayloadIndex;
  run: RunMeta;
  handNo: number;
  agentIds: string[];
  onPick: (hand: number) => void;
}) {
  return (
    <aside className="hand-rail">
      <div className="section-label">Hands</div>
      <div className="hand-list">
        {index.handNos.map((h) => {
          const ended = index.hands.get(h)?.find((e) => e.type === "hand_ended");
          const winners =
            ended && ended.type === "hand_ended"
              ? Object.entries(ended.deltas)
                  .filter(([, d]) => d > 0)
                  .sort((a, b) => b[1] - a[1])
              : [];
          return (
            <button
              key={h}
              className={`hand-item${h === handNo ? " on" : ""}`}
              onClick={() => onPick(h)}
            >
              <span className="hand-no">{h}</span>
              <span className="hand-winners">
                {winners.map(([a, d]) => (
                  <span key={a} style={{ color: playerColor(agentIds, a) }}>
                    {a} +{d}{" "}
                  </span>
                ))}
              </span>
            </button>
          );
        })}
      </div>
      <div className="hand-final">
        <div className="section-label">Chip count</div>
        {Object.entries(run.final_stacks)
          .sort((a, b) => b[1] - a[1])
          .map(([a, s]) => (
            <div className="final-row" key={a}>
              <span style={{ color: playerColor(agentIds, a) }}>{a}</span>
              <b className="mono">{s}</b>
            </div>
          ))}
      </div>
    </aside>
  );
}
