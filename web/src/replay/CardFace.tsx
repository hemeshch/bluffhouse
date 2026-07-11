import { cardParts } from "../lib/format";

export function CardFace({
  code,
  back = false,
  slot = false,
  big = false,
}: {
  code?: string | null;
  back?: boolean;
  slot?: boolean;
  big?: boolean;
}) {
  const size = big ? " big" : "";
  if (slot) return <div className={`pcard slot${size}`} />;
  if (back || !code) return <div className={`pcard back${size}`} />;
  const { rank, suit, red } = cardParts(code);
  return (
    <div className={`pcard face${red ? " red" : ""}${size}`}>
      <b>{rank}</b>
      <i>{suit}</i>
    </div>
  );
}
