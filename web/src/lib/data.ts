// Data access: the replay viewer runs in two delivery modes — embedded
// (single-file replay.html, payload injected at build marker) or served
// (SPA fetching from the local API).

import type {
  BenchSummary,
  HubEntries,
  LeaderboardSummary,
  ReplayPayload,
} from "../types";

declare global {
  interface Window {
    __BLUFFHOUSE_EMBED__?: ReplayPayload | null;
  }
}

export function embeddedPayload(): ReplayPayload | null {
  return typeof window !== "undefined" ? (window.__BLUFFHOUSE_EMBED__ ?? null) : null;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const fetchHub = () => getJson<HubEntries>("/api/hub");

export const fetchReplay = (dir: string) =>
  getJson<ReplayPayload>(`/api/replay?dir=${encodeURIComponent(dir)}`);

export const fetchBench = (dir: string) =>
  getJson<BenchSummary>(`/api/bench?dir=${encodeURIComponent(dir)}`);

export const fetchLeaderboard = (dir: string) =>
  getJson<LeaderboardSummary>(`/api/leaderboard?dir=${encodeURIComponent(dir)}`);

export async function startDemo(): Promise<{ dir: string }> {
  const res = await fetch("/api/demo", { method: "POST" });
  if (!res.ok) throw new Error(`demo failed: ${res.status} ${await res.text()}`);
  return res.json();
}
