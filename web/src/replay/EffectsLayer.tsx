// Table-space effects: communication drawn as geometry, not chat logs.
// Whispers arc between seats (interceptors get a thinner tap line), notes
// physically slide across the felt, accusations fire a beam, attention is a
// persistent gaze line, heat ticks float off the plaque.

import type { GameEvent, LedgerUpdated, MessageSent, PotAwarded } from "../types";
import type { TableState } from "../lib/reduce";
import type { Pov } from "./ReplayApp";
import { arcPath, VB_H, VB_W, type SeatGeom } from "./geometry";

const MODALITY_STROKE: Record<string, string> = {
  whisper: "var(--c-whisper)",
  note: "var(--c-note)",
  accusation: "var(--c-accusation)",
  gesture: "var(--c-sign)",
  eye_contact: "var(--c-sign)",
  chip_signal: "var(--c-sign)",
};

interface Arc {
  from: SeatGeom;
  to: SeatGeom;
  kind: "clear" | "fragment" | "surface";
}

/** Which arcs the active POV is entitled to see for this message. */
function arcsFor(e: MessageSent, geoms: Record<string, SeatGeom>, pov: Pov): Arc[] {
  const sender = geoms[e.sender];
  if (!sender) return [];
  const arcs: Arc[] = [];
  const push = (agent: string, kind: Arc["kind"]) => {
    const to = geoms[agent];
    if (to) arcs.push({ from: sender, to, kind });
  };

  if (pov === "truth") {
    for (const [agent, r] of Object.entries(e.receptions ?? {})) {
      if (agent === e.sender || r.outcome === "missed") continue;
      push(agent, r.outcome as Arc["kind"]);
    }
  } else if (pov === e.sender) {
    // the sender knows who it aimed at — not who intercepted
    for (const target of e.targets) push(target, "clear");
  } else {
    const r = e.receptions?.[pov];
    if (r && r.outcome !== "missed") push(pov, r.outcome as Arc["kind"]);
  }
  return arcs;
}

export function EffectsLayer({
  event,
  state,
  geoms,
  pov,
}: {
  event: GameEvent | undefined;
  state: TableState;
  geoms: Record<string, SeatGeom>;
  pov: Pov;
  agentIds: string[];
}) {
  const msg = event?.type === "message_sent" ? (event as MessageSent) : null;
  const isSpeechlike = msg && (msg.modality === "speech" || msg.modality === "accusation");
  const arcs = msg && !isSpeechlike ? arcsFor(msg, geoms, pov) : [];
  const stroke = msg ? (MODALITY_STROKE[msg.modality] ?? "var(--c-speech)") : "";

  // persistent gaze lines: who is watching whom, this street
  const gazes: { from: SeatGeom; to: SeatGeom; w: number }[] = [];
  for (const [watcher, att] of Object.entries(state.attention)) {
    if (pov !== "truth" && pov !== watcher) continue;
    if (state.folded[watcher]) continue;
    for (const [target, w] of Object.entries(att.watch)) {
      if (w <= 0.05 || !geoms[watcher] || !geoms[target]) continue;
      gazes.push({ from: geoms[watcher], to: geoms[target], w });
    }
  }

  const accusation =
    msg && msg.modality === "accusation" && (pov === "truth" || !!msg.receptions?.[pov])
      ? msg.targets.map((t) => ({ from: geoms[msg.sender], to: geoms[t] })).filter((b) => b.from && b.to)
      : [];

  const speechRipple =
    msg && msg.modality === "speech" && (pov === "truth" || !!msg.receptions?.[pov])
      ? geoms[msg.sender]
      : null;

  const distraction = msg && msg.distraction > 0.3;

  const ledger = event?.type === "ledger_updated" ? (event as LedgerUpdated) : null;
  const award = event?.type === "pot_awarded" ? (event as PotAwarded) : null;

  return (
    <>
      <svg
        className="fx"
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        preserveAspectRatio="none"
        key={event?.event_id ?? "none"}
      >
        {/* gaze lines under everything else */}
        {gazes.map((g, i) => (
          <g key={`gaze-${i}`} className="fx-gaze" style={{ opacity: 0.16 + g.w * 0.35 }}>
            <path d={arcPath(g.from.vbInner, g.to.vbInner, 0.12)} strokeWidth={1 + g.w * 3.5} />
            <circle cx={g.to.vbInner.x} cy={g.to.vbInner.y} r={2.5 + g.w * 3} />
          </g>
        ))}

        {/* whisper / note / signal arcs */}
        {arcs.map((a, i) => {
          const d = arcPath(a.from.vbInner, a.to.vbInner, 0.3);
          return (
            <g key={`arc-${i}`} className={`fx-arc ${a.kind}`} style={{ color: stroke } as React.CSSProperties}>
              <path className="fx-arc-glow" d={d} />
              <path className="fx-arc-line" d={d} />
              {a.kind === "fragment" && (
                <circle className="fx-tap" cx={a.to.vbInner.x} cy={a.to.vbInner.y} r={7} />
              )}
              {msg?.modality === "note" && a.kind !== "surface" && (
                <g className="fx-note">
                  <rect x={-9} y={-6.5} width={18} height={13} rx={2} />
                  <line x1={-5} y1={-1.5} x2={5} y2={-1.5} />
                  <line x1={-5} y1={2.5} x2={3} y2={2.5} />
                  <animateMotion dur="1.1s" fill="freeze" path={d} keyPoints="0;1" keyTimes="0;1" />
                </g>
              )}
            </g>
          );
        })}

        {/* accusation beam */}
        {accusation.map((b, i) => (
          <g key={`beam-${i}`} className="fx-beam">
            <line x1={b.from.vbInner.x} y1={b.from.vbInner.y} x2={b.to.vbInner.x} y2={b.to.vbInner.y} />
            <circle cx={b.to.vbInner.x} cy={b.to.vbInner.y} r={16} className="fx-beam-hit" />
          </g>
        ))}

        {/* speech ripple */}
        {speechRipple && (
          <g className="fx-ripple">
            {[0, 1, 2].map((k) => (
              <circle
                key={k}
                cx={speechRipple.vb.x}
                cy={speechRipple.vb.y}
                r={20}
                style={{ animationDelay: `${k * 0.28}s` }}
              />
            ))}
          </g>
        )}
      </svg>

      {distraction && <div className="fx-distraction" key={`d-${event!.event_id}`} />}

      {ledger && geoms[ledger.agent_id] && (
        <div
          className="fx-heat-tick mono"
          key={`h-${ledger.event_id}`}
          style={{
            left: `${geoms[ledger.agent_id].pct.x}%`,
            top: `${geoms[ledger.agent_id].pct.y}%`,
          }}
        >
          {ledger.delta_suspicion >= 0 ? "+" : ""}
          {ledger.delta_suspicion.toFixed(2)} heat
        </div>
      )}

      {award && geoms[award.agent_id] && (
        <div
          className="fx-award"
          key={`a-${award.event_id}`}
          style={
            {
              "--tx": `${geoms[award.agent_id].wagerPct.x}%`,
              "--ty": `${geoms[award.agent_id].wagerPct.y}%`,
            } as React.CSSProperties
          }
        >
          <span className="pot-chip" />
          <span className="pot-chip" />
          <span className="pot-chip" />
        </div>
      )}
    </>
  );
}
