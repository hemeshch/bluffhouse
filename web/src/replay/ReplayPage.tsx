import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { ReplayPayload } from "../types";
import { fetchReplay } from "../lib/data";
import { ReplayApp } from "./ReplayApp";

export function ReplayPage() {
  const [params] = useSearchParams();
  const dir = params.get("dir") ?? "";
  const present = params.get("present") === "1";
  const hand = params.get("hand");
  const at = params.get("at");
  const [payload, setPayload] = useState<ReplayPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPayload(null);
    setError(null);
    if (dir) fetchReplay(dir).then(setPayload, (e) => setError(String(e)));
  }, [dir]);

  if (!dir) return <Notice text="No run selected — pick one from the home page." />;
  if (error) return <Notice text={error} />;
  if (!payload) return <Notice text="Loading replay…" />;
  return (
    <ReplayApp
      payload={payload}
      startPresenting={present}
      startHand={hand ? Number(hand) : undefined}
      startCursor={at ? Number(at) : undefined}
      startPov={params.get("pov") ?? undefined}
    />
  );
}

function Notice({ text }: { text: string }) {
  return <div style={{ padding: 40, color: "var(--muted)" }}>{text}</div>;
}
