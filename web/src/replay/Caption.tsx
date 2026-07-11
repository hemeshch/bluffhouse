import type { GameEvent } from "../types";
import type { PayloadIndex } from "../lib/payload";
import { intentLine, narrate } from "../lib/narrate";
import type { Pov } from "./ReplayApp";
import { SegText } from "./segments";

export function Caption({
  event,
  pov,
  index,
  agentIds,
  presenting,
}: {
  event: GameEvent | undefined;
  pov: Pov;
  index: PayloadIndex;
  agentIds: string[];
  presenting: boolean;
}) {
  if (!event) return <div className="caption" />;

  if (pov === "truth") {
    const intent = intentLine(event);
    return (
      <div className={`caption${presenting ? " big" : ""}`} key={event.event_id}>
        <span className="caption-kicker">the table sees everything</span>
        <div className="caption-line">
          <SegText segs={narrate(event)} agentIds={agentIds} />
        </div>
        {intent && (
          <div className="caption-intent">
            <SegText segs={intent} agentIds={agentIds} />
          </div>
        )}
      </div>
    );
  }

  const obs = index.obsByAgent[pov]?.get(event.event_id);
  return (
    <div
      className={`caption${presenting ? " big" : ""}${obs ? "" : " dim"}`}
      key={event.event_id + pov}
    >
      <span className="caption-kicker">what {pov} sees</span>
      <div className="caption-line">
        {obs ? (
          <>
            {obs.perceived_text}
            {obs.confidence < 1 && (
              <span className="conf-chip mono">~{Math.round(obs.confidence * 100)}% sure</span>
            )}
          </>
        ) : (
          <>nothing — this moment never reached {pov}.</>
        )}
      </div>
    </div>
  );
}
