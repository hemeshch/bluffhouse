// Shared seat geometry: seats on an ellipse around the felt, expressed both
// as % of the table box (for absolutely-positioned DOM) and in viewBox
// coordinates (for the SVG effects overlay). seat_order[0] sits bottom-center.

export const VB_W = 1000;
export const VB_H = 620;

export interface SeatGeom {
  id: string;
  angle: number;
  /** seat center, % of table box */
  pct: { x: number; y: number };
  /** seat center, viewBox coords */
  vb: { x: number; y: number };
  /** arc anchor just inside the seat, viewBox coords */
  vbInner: { x: number; y: number };
  /** bet chips position, toward table center */
  wagerPct: { x: number; y: number };
  /** message bubble anchor */
  bubblePct: { x: number; y: number };
}

export function seatGeometry(order: string[]): Record<string, SeatGeom> {
  const n = Math.max(order.length, 1);
  const geoms: Record<string, SeatGeom> = {};
  order.forEach((id, i) => {
    const angle = Math.PI / 2 + (i * 2 * Math.PI) / n;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const at = (r: number, rv?: number) => ({
      x: 50 + r * cos,
      y: 50 + (rv ?? r) * sin,
    });
    const pct = at(42, 43);
    const inner = at(31, 30);
    geoms[id] = {
      id,
      angle,
      pct,
      vb: { x: (pct.x / 100) * VB_W, y: (pct.y / 100) * VB_H },
      vbInner: { x: (inner.x / 100) * VB_W, y: (inner.y / 100) * VB_H },
      wagerPct: at(25, 26),
      bubblePct: at(23, 20),
    };
  });
  return geoms;
}

/** A curved path between two seats, bowing toward/away from table center. */
export function arcPath(a: { x: number; y: number }, b: { x: number; y: number }, bow = 0.25): string {
  const mx = (a.x + b.x) / 2;
  const my = (a.y + b.y) / 2;
  const cx = mx + (VB_W / 2 - mx) * bow;
  const cy = my + (VB_H / 2 - my) * bow;
  return `M ${a.x.toFixed(1)} ${a.y.toFixed(1)} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
}
