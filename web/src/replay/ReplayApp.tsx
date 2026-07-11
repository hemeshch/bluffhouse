import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GameEvent, ReplayPayload } from "../types";
import { indexPayload } from "../lib/payload";
import { reduce } from "../lib/reduce";
import { PovBar } from "./PovBar";
import { HandRail } from "./HandRail";
import { Table } from "./Table";
import { Caption } from "./Caption";
import { Transport } from "./Transport";
import { Feed } from "./Feed";
import { Legend } from "./Legend";
import "./Replay.css";

export interface ReplayAppProps {
  payload: ReplayPayload;
  /** rendered as the whole page (single-file replay.html) vs inside the SPA shell */
  standalone?: boolean;
  /** open directly in presentation mode */
  startPresenting?: boolean;
  /** deep link: initial hand / event index / point of view */
  startHand?: number;
  startCursor?: number;
  startPov?: string;
}

export type Pov = "truth" | (string & {});

/** How long autoplay lingers on an event — social moments get room to land. */
function holdMs(e: GameEvent | undefined, visible: boolean): number {
  if (!e) return 950;
  if (!visible) return 500;
  switch (e.type) {
    case "message_sent":
      return 3000;
    case "ledger_updated":
      return 1700;
    case "attention_committed":
      return 1600;
    case "beliefs_updated":
      return 1500;
    case "board_dealt":
    case "showdown_reveal":
    case "pot_awarded":
      return 1500;
    case "hand_started":
      return 1300;
    case "hole_cards_dealt":
      return 650;
    case "blind_posted":
      return 550;
    default:
      return 950;
  }
}

export function ReplayApp({
  payload,
  standalone,
  startPresenting,
  startHand,
  startCursor,
  startPov,
}: ReplayAppProps) {
  const index = useMemo(() => indexPayload(payload), [payload]);
  const { run } = payload;

  const [pov, setPov] = useState<Pov>(
    startPov && (startPov === "truth" || run.agent_ids.includes(startPov)) ? startPov : "truth",
  );
  const [handNo, setHandNo] = useState(
    startHand && index.hands.has(startHand) ? startHand : (index.handNos[0] ?? 1),
  );
  const [cursor, setCursor] = useState(startCursor ?? 0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [presenting, setPresenting] = useState(Boolean(startPresenting));
  const [legendOpen, setLegendOpen] = useState(false);

  const events = index.hands.get(handNo) ?? [];
  const safeCursor = Math.min(cursor, Math.max(events.length - 1, 0));
  const event = events[safeCursor];
  const state = useMemo(() => reduce(events, safeCursor), [events, safeCursor]);

  const goto = useCallback((hand: number, at: number) => {
    setHandNo(hand);
    setCursor(at);
  }, []);

  const step = useCallback(
    (d: number) => {
      const list = index.hands.get(handNo) ?? [];
      const next = safeCursor + d;
      if (next < 0) {
        const i = index.handNos.indexOf(handNo);
        if (i > 0) {
          const prev = index.handNos[i - 1];
          goto(prev, (index.hands.get(prev)?.length ?? 1) - 1);
        }
        return;
      }
      if (next >= list.length) {
        const i = index.handNos.indexOf(handNo);
        if (i < index.handNos.length - 1) goto(index.handNos[i + 1], 0);
        else setPlaying(false);
        return;
      }
      setCursor(next);
    },
    [index, handNo, safeCursor, goto],
  );

  // autoplay with per-event pacing
  const stepRef = useRef(step);
  stepRef.current = step;
  const visibleToPov =
    pov === "truth" || (event && index.obsByAgent[pov]?.has(event.event_id)) || false;
  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(
      () => stepRef.current(1),
      holdMs(event, Boolean(visibleToPov)) / speed,
    );
    return () => clearTimeout(t);
  }, [playing, speed, event, visibleToPov]);

  // keyboard transport
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.key === "ArrowLeft") {
        stepRef.current(-1);
        e.preventDefault();
      } else if (e.key === "ArrowRight") {
        stepRef.current(1);
        e.preventDefault();
      } else if (e.key === " ") {
        setPlaying((p) => !p);
        e.preventDefault();
      } else if (e.key === "p" || e.key === "P") {
        setPresenting((p) => !p);
      } else if (e.key === "?") {
        setLegendOpen((o) => !o);
      } else if (e.key === "Escape") {
        setPresenting(false);
        setLegendOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  if (!index.handNos.length) {
    return <div style={{ padding: 40, color: "var(--muted)" }}>This run has no hands.</div>;
  }

  return (
    <div className={`theater${presenting ? " presenting" : ""}${standalone ? " standalone" : ""}`}>
      <div className="theater-top">
        {standalone && <span className="theater-wordmark">bluffhouse</span>}
        <span className="theater-meta mono">
          seed {run.seed} · {run.hands_played} hands · blinds {run.small_blind}/{run.big_blind}
        </span>
        <PovBar agentIds={run.agent_ids} pov={pov} onPick={setPov} />
      </div>

      <div className="theater-main">
        <HandRail
          index={index}
          run={run}
          handNo={handNo}
          agentIds={run.agent_ids}
          onPick={(h) => goto(h, 0)}
        />

        <section className="stage">
          <Table
            run={run}
            events={events}
            allEvents={payload.events}
            cursor={safeCursor}
            state={state}
            pov={pov}
            hasLedgers={index.hasLedgers}
            presenting={presenting}
          />
          <Caption
            event={event}
            pov={pov}
            index={index}
            agentIds={run.agent_ids}
            presenting={presenting}
          />
          <Transport
            events={events}
            cursor={safeCursor}
            playing={playing}
            speed={speed}
            presenting={presenting}
            onSeek={setCursor}
            onStep={step}
            onTogglePlay={() => setPlaying((p) => !p)}
            onSpeed={setSpeed}
            onPresent={() => setPresenting((p) => !p)}
            onLegend={() => setLegendOpen(true)}
          />
        </section>

        <Feed
          events={events}
          cursor={safeCursor}
          pov={pov}
          index={index}
          agentIds={run.agent_ids}
          onJump={setCursor}
        />
      </div>

      {legendOpen && <Legend onClose={() => setLegendOpen(false)} />}
    </div>
  );
}
