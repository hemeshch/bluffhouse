// Renders narration Segment[] with colored player names, card glyphs, quotes.

import type { Segment } from "../lib/narrate";
import { cardParts, playerColor } from "../lib/format";

export function CardGlyphs({ codes }: { codes: string }) {
  return (
    <span className="seg-cards">
      {codes.split(/\s+/).map((code, i) => {
        if (!code) return null;
        const { rank, suit, red } = cardParts(code);
        return (
          <span key={i} className={`seg-card${red ? " red" : ""}`}>
            {rank}
            {suit}
          </span>
        );
      })}
    </span>
  );
}

export function SegText({ segs, agentIds }: { segs: Segment[]; agentIds: string[] }) {
  return (
    <>
      {segs.map((s, i) => {
        switch (s.kind) {
          case "player":
            return (
              <b key={i} className="seg-player" style={{ color: playerColor(agentIds, s.text) }}>
                {s.text}
              </b>
            );
          case "cards":
            return <CardGlyphs key={i} codes={s.text} />;
          case "quote":
            return (
              <span key={i} className="seg-quote">
                {s.text}
              </span>
            );
          case "muted":
            return (
              <span key={i} className="seg-muted">
                {s.text}
              </span>
            );
          default:
            return <span key={i}>{s.text}</span>;
        }
      })}
    </>
  );
}
