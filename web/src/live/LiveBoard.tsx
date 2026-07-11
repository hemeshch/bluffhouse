import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import type { GameEvent, MessageSent, RunMeta } from "../types";
import { reduce } from "../lib/reduce";
import { narrate, intentLine } from "../lib/narrate";
import { MODALITY_META } from "../lib/format";
import { Table } from "../replay/Table";
import { SegText } from "../replay/segments";
import type { LiveActivity, LiveConfig, LiveDone } from "./useLiveGame";

export function LiveBoard({
  config,
  events,
  activity,
  done,
  onStop,
  onReset,
}: {
  config: LiveConfig;
  events: GameEvent[];
  activity: LiveActivity | null;
  done: LiveDone | null;
  onStop: () => void;
  onReset: () => void;
}) {
  const run: RunMeta = useMemo(
    () => ({
      seed: config.seed,
      agent_ids: config.agent_ids,
      small_blind: config.small_blind,
      big_blind: config.big_blind,
      starting_stack: config.starting_stack,
      hands_played: config.num_hands,
      final_stacks: {},
      ledgers: {},
    }),
    [config],
  );

  const handEvents = useMemo(() => {
    const current = events.length ? events[events.length - 1].hand_no : 0;
    const hand = current >= 1 ? current : Math.max(...events.map((e) => e.hand_no), 0);
    return events.filter((e) => e.hand_no === hand && e.hand_no >= 1);
  }, [events]);

  const state = useMemo(
    () => reduce(handEvents, handEvents.length - 1),
    [handEvents],
  );
  const last = events[events.length - 1];
  const hasLedgers = useMemo(() => events.some((e) => e.type === "ledger_updated"), [events]);

  // elapsed-time ticker for the "X is thinking…" chip
  const [now, setNow] = useState(0);
  const sinceRef = useRef(Date.now());
  useEffect(() => {
    sinceRef.current = Date.now();
    setNow(0);
    if (!activity) return;
    const t = setInterval(() => setNow(Math.floor((Date.now() - sinceRef.current) / 1000)), 1000);
    return () => clearInterval(t);
  }, [activity, events.length]);

  return (
    <div className="liveboard">
      <div className="live-stage">
        <div className="live-topline">
          <span className="mono live-meta">
            seed {config.seed} · mode {config.mode} · {config.num_hands} hands
          </span>
          {activity && !done && (
            <span className="live-activity">
              <span className="live-dot" />
              <b>{activity.agent}</b>&nbsp;is thinking — {activity.phase}, hand {activity.hand}
              {now >= 3 && <span className="mono">&nbsp;({now}s)</span>}
            </span>
          )}
          {!activity && !done && <span className="live-activity dim">dealing…</span>}
          {done && (
            <span className={`live-done ${done.status}`}>
              {done.status === "done"
                ? "game complete"
                : done.status === "stopped"
                  ? "stopped"
                  : `error: ${done.error}`}
            </span>
          )}
          <span className="live-buttons">
            {!done && (
              <button className="btn secondary" onClick={onStop}>
                ■ Stop
              </button>
            )}
            {done?.run_dir && (
              <Link className="btn" to={`/replay?dir=${encodeURIComponent(done.run_dir)}`}>
                Watch the full replay →
              </Link>
            )}
            {done && (
              <button className="btn secondary" onClick={onReset}>
                New game
              </button>
            )}
          </span>
        </div>

        {handEvents.length > 0 ? (
          <Table
            run={run}
            events={handEvents}
            allEvents={events}
            cursor={handEvents.length - 1}
            state={state}
            pov="truth"
            hasLedgers={hasLedgers}
            presenting={false}
          />
        ) : (
          <div className="live-waiting">Shuffling up…</div>
        )}

        {last && (
          <div className="caption" key={last.event_id}>
            <span className="caption-kicker">live · ground truth</span>
            <div className="caption-line">
              <SegText segs={narrate(last)} agentIds={config.agent_ids} />
            </div>
            {intentLine(last) && (
              <div className="caption-intent">
                <SegText segs={intentLine(last)!} agentIds={config.agent_ids} />
              </div>
            )}
          </div>
        )}
      </div>

      <LiveFeed events={events} agentIds={config.agent_ids} />
    </div>
  );
}

function LiveFeed({ events, agentIds }: { events: GameEvent[]; agentIds: string[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [events.length]);

  return (
    <aside className="feed-panel">
      <div className="feed-title">
        Live feed — <b>every event as it lands</b>
      </div>
      <div className="feed" ref={ref}>
        {events.map((e, i) => {
          const isMsg = e.type === "message_sent";
          const modality = isMsg ? (e as MessageSent).modality : null;
          return (
            <div
              key={e.event_id}
              className={`feed-line ${
                isMsg ? `msg m-${modality}` : e.visibility !== "public" ? "env" : ""
              }${i === events.length - 1 ? " last" : ""}`}
            >
              {modality && <span className="feed-icon">{MODALITY_META[modality].icon}</span>}
              <span className="feed-text">
                <SegText segs={narrate(e)} agentIds={agentIds} />
              </span>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
