import { useCallback, useRef, useState } from "react";
import type { GameEvent } from "../types";

export interface LiveConfig {
  seed: number;
  num_hands: number;
  small_blind: number;
  big_blind: number;
  starting_stack: number;
  agent_ids: string[];
  mode: number;
  collect_beliefs: boolean;
}

export interface LiveActivity {
  agent: string;
  phase: string;
  hand: number;
  street: string;
}

export interface LiveDone {
  status: string;
  run_dir: string | null;
  error: string | null;
}

export interface LiveSeatRequest {
  spec: string;
  name?: string | null;
  api_key?: string | null;
}

export interface LiveStartRequest {
  seats: LiveSeatRequest[];
  hands: number;
  mode: number;
  seed?: number | null;
  stack?: number;
  small_blind?: number;
  big_blind?: number;
  collect_beliefs?: boolean;
}

export function useLiveGame() {
  const [config, setConfig] = useState<LiveConfig | null>(null);
  const [events, setEvents] = useState<GameEvent[]>([]);
  const [activity, setActivity] = useState<LiveActivity | null>(null);
  const [done, setDone] = useState<LiveDone | null>(null);
  const [error, setError] = useState<string | null>(null);
  const jobRef = useRef<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const start = useCallback(async (req: LiveStartRequest) => {
    setError(null);
    setEvents([]);
    setActivity(null);
    setDone(null);
    const res = await fetch("/api/live", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    if (!res.ok) {
      let detail = `${res.status}`;
      try {
        detail = (await res.json()).detail ?? detail;
      } catch {
        /* keep status */
      }
      throw new Error(detail);
    }
    const body = (await res.json()) as { job: string; config: LiveConfig };
    jobRef.current = body.job;
    setConfig(body.config);

    const es = new EventSource(`/api/live/${body.job}/events`);
    esRef.current = es;
    es.addEventListener("event", (e) => {
      const ev = JSON.parse((e as MessageEvent).data) as GameEvent;
      setEvents((prev) => [...prev, ev]);
    });
    es.addEventListener("status", (e) => {
      setActivity(JSON.parse((e as MessageEvent).data) as LiveActivity);
    });
    es.addEventListener("done", (e) => {
      setDone(JSON.parse((e as MessageEvent).data) as LiveDone);
      setActivity(null);
      es.close();
    });
    es.onerror = () => {
      // EventSource reconnects with Last-Event-ID on its own; only surface
      // a hard failure if the run never finishes.
      if (es.readyState === EventSource.CLOSED && !jobDone()) {
        setError("stream lost — the server may have stopped");
      }
    };
    const jobDone = () => Boolean(done);
  }, [done]);

  const stop = useCallback(() => {
    if (jobRef.current) void fetch(`/api/live/${jobRef.current}/stop`, { method: "POST" });
  }, []);

  const reset = useCallback(() => {
    esRef.current?.close();
    jobRef.current = null;
    setConfig(null);
    setEvents([]);
    setActivity(null);
    setDone(null);
    setError(null);
  }, []);

  return { config, events, activity, done, error, start, stop, reset };
}
