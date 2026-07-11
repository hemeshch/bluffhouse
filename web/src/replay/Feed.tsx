import { useEffect, useRef } from "react";
import type { GameEvent, MessageSent } from "../types";
import type { PayloadIndex } from "../lib/payload";
import { intentLine, narrate, receptionSummary } from "../lib/narrate";
import { MODALITY_META } from "../lib/format";
import type { Pov } from "./ReplayApp";
import { SegText } from "./segments";

export function Feed({
  events,
  cursor,
  pov,
  index,
  agentIds,
  onJump,
}: {
  events: GameEvent[];
  cursor: number;
  pov: Pov;
  index: PayloadIndex;
  agentIds: string[];
  onJump: (i: number) => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [cursor, pov]);

  const rows: React.ReactNode[] = [];
  for (let i = 0; i <= cursor && i < events.length; i++) {
    const e = events[i];
    const isMsg = e.type === "message_sent";
    const modality = isMsg ? (e as MessageSent).modality : null;
    const icon = modality ? MODALITY_META[modality].icon : null;
    const current = i === cursor;

    if (pov === "truth") {
      const cls = isMsg ? `msg m-${modality}` : e.visibility !== "public" ? "env" : "";
      rows.push(
        <button
          key={e.event_id}
          className={`feed-line ${cls}${current ? " last" : ""}`}
          onClick={() => onJump(i)}
        >
          {icon && <span className="feed-icon">{icon}</span>}
          <span className="feed-text">
            <SegText segs={narrate(e)} agentIds={agentIds} />
          </span>
        </button>,
      );
      if (isMsg) {
        const intent = intentLine(e);
        if (intent) {
          rows.push(
            <div key={e.event_id + ":i"} className="feed-sub intent">
              <SegText segs={intent} agentIds={agentIds} />
            </div>,
          );
        }
        const recept = receptionSummary(e as MessageSent);
        if (recept) {
          rows.push(
            <div key={e.event_id + ":r"} className="feed-sub recept">
              <SegText segs={recept} agentIds={agentIds} />
            </div>,
          );
        }
      }
    } else {
      const obs = index.obsByAgent[pov]?.get(e.event_id);
      if (obs) {
        rows.push(
          <button
            key={e.event_id}
            className={`feed-line ${isMsg ? `msg m-${modality}` : ""}${current ? " last" : ""}`}
            onClick={() => onJump(i)}
          >
            {icon && <span className="feed-icon">{icon}</span>}
            <span className="feed-text">
              {obs.perceived_text}
              {obs.confidence < 1 && (
                <span className="conf-chip mono">~{Math.round(obs.confidence * 100)}%</span>
              )}
            </span>
          </button>,
        );
      }
    }

    const r = index.reasoning[e.event_id];
    if (r && (pov === "truth" || pov === r.agent)) {
      rows.push(
        <div key={e.event_id + ":think"} className="feed-sub reasoning">
          <span className="feed-think-who">
            {r.agent} was thinking{r.fault ? " · after a malformed reply" : ""}
          </span>
          {r.text ?? "(model reply unusable — safe action substituted)"}
        </div>,
      );
    }
  }

  return (
    <aside className="feed-panel">
      <div className="feed-title">
        {pov === "truth" ? (
          <>
            Ground truth — <b>every event, every intent</b>
          </>
        ) : (
          <>
            Subjective — <b>only what {pov} received</b>
          </>
        )}
      </div>
      <div className="feed" ref={scrollRef}>
        {rows}
      </div>
    </aside>
  );
}
