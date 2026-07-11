import { useMemo } from "react";
import type { GameEvent, MessageSent, Reception, RunMeta } from "../types";
import type { TableState } from "../lib/reduce";
import { heatAt, potSize, streetOf } from "../lib/reduce";
import { MODALITY_META, playerColor } from "../lib/format";
import type { Pov } from "./ReplayApp";
import { seatGeometry } from "./geometry";
import { Seat } from "./Seat";
import { CardFace } from "./CardFace";
import { EffectsLayer } from "./EffectsLayer";

export function Table({
  run,
  events,
  allEvents,
  cursor,
  state,
  pov,
  hasLedgers,
  presenting,
}: {
  run: RunMeta;
  events: GameEvent[];
  allEvents: GameEvent[];
  cursor: number;
  state: TableState;
  pov: Pov;
  hasLedgers: boolean;
  presenting: boolean;
}) {
  const event = events[cursor];
  const geoms = useMemo(() => seatGeometry(state.order), [state.order.join("|")]);
  const heat = useMemo(
    () => (hasLedgers && event ? heatAt(allEvents, event.seq) : {}),
    [hasLedgers, allEvents, event?.seq],
  );

  const pot = potSize(state);
  const street = streetOf(state);

  return (
    <div className={`table-wrap${presenting ? " big" : ""}`}>
      <div className="felt">
        <div className="felt-inner" />

        <div className="table-center">
          <div className="street-label">
            hand {event?.hand_no ?? ""} · {street}
          </div>
          <div className="board">
            {Array.from({ length: 5 }, (_, i) => (
              <CardFace key={i} code={state.board[i]} slot={!state.board[i]} big />
            ))}
          </div>
          <div className={`pot${pot > 0 ? "" : " empty"}`}>
            <span className="pot-chip" />
            <span className="mono">{pot}</span>
          </div>
        </div>

        {state.order.map((id) => (
          <Seat
            key={id}
            id={id}
            geom={geoms[id]}
            state={state}
            event={event}
            agentIds={run.agent_ids}
            pov={pov}
            heat={heat[id]}
            showHeat={hasLedgers}
            isButton={state.button === id}
            bigBlind={run.big_blind}
          />
        ))}

        {event?.type === "message_sent" && (
          <MessageBubble e={event} pov={pov} geoms={geoms} agentIds={run.agent_ids} />
        )}

        <EffectsLayer event={event} state={state} geoms={geoms} pov={pov} agentIds={run.agent_ids} />
      </div>
    </div>
  );
}

/** What the active POV perceives of a message: the bubble contents. */
function povReception(e: MessageSent, pov: Pov): Reception | null {
  if (pov === "truth") return { outcome: "clear", confidence: 1, text: null };
  return e.receptions?.[pov] ?? null;
}

function MessageBubble({
  e,
  pov,
  geoms,
  agentIds,
}: {
  e: MessageSent;
  pov: Pov;
  geoms: ReturnType<typeof seatGeometry>;
  agentIds: string[];
}) {
  const rec = povReception(e, pov);
  if (!rec || rec.outcome === "missed") return null;
  const geom = geoms[e.sender];
  if (!geom) return null;

  const meta = MODALITY_META[e.modality];
  const who = e.targets.join(", ");
  let from: string;
  let body: string | null = e.text;

  if (rec.outcome === "fragment") {
    from = e.modality === "note" ? `the note ${e.sender} passed, read` : `overheard from ${e.sender}`;
    body = rec.text;
  } else if (rec.outcome === "surface") {
    from = e.modality === "note" ? `${e.sender} slips something to ${who}` : `${e.sender} signals ${who}`;
    body = e.modality === "note" ? "(contents unseen)" : body;
  } else if (e.modality === "whisper") from = `${e.sender} whispers to ${who}`;
  else if (e.modality === "note") from = `${e.sender} slips a note to ${who}`;
  else if (e.modality === "accusation") from = `${e.sender} accuses ${who}`;
  else if (e.modality === "speech") from = `${e.sender} says`;
  else from = `${e.sender} signals ${who}`;

  return (
    <div
      className={`bubble m-${e.modality}${rec.outcome === "fragment" ? " fragment" : ""}`}
      style={{ left: `${geom.bubblePct.x}%`, top: `${geom.bubblePct.y}%` }}
    >
      <span className="bubble-from">
        <span className="bubble-icon">{meta.icon}</span>
        <span style={{ color: playerColor(agentIds, e.sender) }}>{from}</span>
        {rec.confidence < 1 && (
          <span className="bubble-conf mono">~{Math.round(rec.confidence * 100)}%</span>
        )}
      </span>
      {body}
    </div>
  );
}
