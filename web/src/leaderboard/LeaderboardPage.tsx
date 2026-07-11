import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { BenchSummary, HubEntries, LeaderboardSummary } from "../types";
import { fetchBench, fetchHub, fetchLeaderboard } from "../lib/data";
import "./Leaderboard.css";

const DIMENSION_ORDER = [
  "poker",
  "poker_quality",
  "belief_accuracy",
  "detection",
  "information_control",
  "cover",
  "discipline",
  "deception",
  "manipulation",
];

const DIMENSION_LABELS: Record<string, string> = {
  poker: "poker",
  poker_quality: "quality",
  belief_accuracy: "beliefs",
  detection: "detection",
  information_control: "info ctrl",
  cover: "cover",
  discipline: "discipline",
  deception: "deception",
  manipulation: "manipulation",
};

export function LeaderboardPage() {
  const [params, setParams] = useSearchParams();
  const [hub, setHub] = useState<HubEntries | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchHub().then(setHub, (e) => setError(String(e)));
  }, []);

  const options = useMemo(() => {
    if (!hub) return [];
    return [
      ...hub.sweeps.map((s) => ({ kind: "sweep" as const, name: s.name })),
      ...hub.benches.map((b) => ({ kind: "bench" as const, name: b.name })),
    ];
  }, [hub]);

  const selected = params.get("dir") ?? options[0]?.name ?? "";
  const kind = options.find((o) => o.name === selected)?.kind;

  if (error) return <div className="lb-empty mono">{error}</div>;
  if (!hub) return <div className="lb-empty">Loading…</div>;
  if (!options.length) {
    return (
      <div className="lb-empty">
        No benchmark results yet. Run one:
        <pre className="mono">
          uv run bluffhouse bench --models random,checkcall,allin,fold --hands 20 --mode 0
        </pre>
        then refresh — rankings, dimension scores, and per-rotation replays land here.
      </div>
    );
  }

  return (
    <div className="lb">
      <div className="lb-head">
        <h1>Leaderboard</h1>
        <select
          value={selected}
          onChange={(e) => setParams({ dir: e.target.value })}
        >
          {options.map((o) => (
            <option key={o.name} value={o.name}>
              {o.kind === "sweep" ? "sweep · " : "bench · "}
              {o.name}
            </option>
          ))}
        </select>
      </div>
      {kind === "sweep" ? <SweepView dir={selected} /> : <BenchView dir={selected} />}
    </div>
  );
}

function DivergingBar({ value, max }: { value: number; max: number }) {
  const frac = max > 0 ? Math.min(Math.abs(value) / max, 1) : 0;
  return (
    <div className="lb-bar">
      <div className="lb-bar-neg">
        {value < 0 && <div className="lb-bar-fill neg" style={{ width: `${frac * 100}%` }} />}
      </div>
      <div className="lb-bar-pos">
        {value >= 0 && <div className="lb-bar-fill pos" style={{ width: `${frac * 100}%` }} />}
      </div>
    </div>
  );
}

function BenchView({ dir }: { dir: string }) {
  const [bench, setBench] = useState<BenchSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setBench(null);
    fetchBench(dir).then(setBench, (e) => setError(String(e)));
  }, [dir]);

  if (error) return <div className="lb-empty mono">{error}</div>;
  if (!bench) return <div className="lb-empty">Loading…</div>;

  const ranked = Object.entries(bench.scorecards).sort(
    (a, b) => b[1].adjusted_chips - a[1].adjusted_chips,
  );
  const maxAbs = Math.max(...ranked.map(([, c]) => Math.abs(c.adjusted_chips)), 1);
  const dims = DIMENSION_ORDER.filter((d) => ranked.some(([, c]) => d in c.dimensions));
  const rotations = bench.seatings.length;

  return (
    <>
      <p className="lb-sub">
        Duplicate format: {bench.entrants.length} entrants rotated through anonymized seats over{" "}
        {rotations} rotation{rotations === 1 ? "" : "s"} of the identical seed-{bench.seed} deal,
        mode {bench.mode}, {bench.num_hands} hands. <b>Adjusted chips</b> = your result minus the
        average result of everyone who held exactly your cards in your seat — card luck cancels by
        construction.
      </p>

      <table className="lb-table">
        <thead>
          <tr>
            <th>#</th>
            <th>entrant</th>
            <th className="num">adj chips</th>
            <th className="bar-col" />
            <th className="num">raw</th>
            {dims.map((d) => (
              <th key={d} className="num dim">
                {DIMENSION_LABELS[d]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ranked.map(([entrant, card], i) => (
            <tr key={entrant}>
              <td className="rank">{i + 1}</td>
              <td className="entrant">{entrant}</td>
              <td className="num mono">
                {card.adjusted_chips >= 0 ? "+" : ""}
                {card.adjusted_chips.toFixed(1)}
              </td>
              <td className="bar-col">
                <DivergingBar value={card.adjusted_chips} max={maxAbs} />
              </td>
              <td className="num mono faint">
                {card.raw_chips >= 0 ? "+" : ""}
                {card.raw_chips}
              </td>
              {dims.map((d) => (
                <td key={d} className="num dim">
                  <span
                    className="lb-dim"
                    style={{ ["--v" as string]: `${card.dimensions[d] ?? 0}%` }}
                  >
                    {card.dimensions[d] ?? "—"}
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="lb-replays">
        <span className="section-label">Rotation replays</span>
        {Array.from({ length: rotations }, (_, r) => (
          <Link key={r} className="btn secondary" to={`/replay?dir=${encodeURIComponent(`${dir}/rotation-${r}`)}`}>
            rotation {r}
          </Link>
        ))}
      </div>
      <p className="lb-note">
        Dimension scores are scaled 0–100 <i>within this bench</i>. Deliberately absent: any
        truth-refereed social score — manipulation that goes unnoticed is indistinguishable from
        honesty, by design.
      </p>
    </>
  );
}

function SweepView({ dir }: { dir: string }) {
  const [sweep, setSweep] = useState<LeaderboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSweep(null);
    fetchLeaderboard(dir).then(setSweep, (e) => setError(String(e)));
  }, [dir]);

  if (error) return <div className="lb-empty mono">{error}</div>;
  if (!sweep) return <div className="lb-empty">Loading…</div>;

  const ranked = Object.entries(sweep.leaderboard).sort(
    (a, b) => b[1].mean_adjusted_chips - a[1].mean_adjusted_chips,
  );
  const maxAbs = Math.max(
    ...ranked.flatMap(([, r]) => [Math.abs(r.ci95[0]), Math.abs(r.ci95[1])]),
    1,
  );
  const entrants = ranked.map(([e]) => e);

  return (
    <>
      <p className="lb-sub">
        Multi-seed sweep: seeds {sweep.seeds.join(", ")} · mode {sweep.mode} · {sweep.num_hands}{" "}
        hands · {sweep.rotations} rotations per seed. Error bars are bootstrap 95% CIs over seeds.
      </p>

      <table className="lb-table">
        <thead>
          <tr>
            <th>#</th>
            <th>entrant</th>
            <th className="num">mean adj</th>
            <th className="ci-col">95% CI</th>
            <th className="num">seed wins</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map(([entrant, row], i) => {
            const [lo, hi] = row.ci95;
            const left = ((lo + maxAbs) / (2 * maxAbs)) * 100;
            const width = ((hi - lo) / (2 * maxAbs)) * 100;
            const mid = ((row.mean_adjusted_chips + maxAbs) / (2 * maxAbs)) * 100;
            return (
              <tr key={entrant}>
                <td className="rank">{i + 1}</td>
                <td className="entrant">{entrant}</td>
                <td className="num mono">
                  {row.mean_adjusted_chips >= 0 ? "+" : ""}
                  {row.mean_adjusted_chips.toFixed(1)}
                </td>
                <td className="ci-col">
                  <div className="lb-ci">
                    <div className="lb-ci-zero" />
                    <div className="lb-ci-band" style={{ left: `${left}%`, width: `${width}%` }} />
                    <div className="lb-ci-mean" style={{ left: `${mid}%` }} />
                  </div>
                  <span className="mono faint ci-label">
                    [{lo.toFixed(1)}, {hi.toFixed(1)}]
                  </span>
                </td>
                <td className="num mono">{row.seed_wins}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="lb-matrix-wrap">
        <span className="section-label">Head-to-head — share of seeds A out-scored B</span>
        <table className="lb-matrix">
          <thead>
            <tr>
              <th />
              {entrants.map((e) => (
                <th key={e} title={e}>
                  {e.length > 10 ? `${e.slice(0, 9)}…` : e}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entrants.map((a) => (
              <tr key={a}>
                <th title={a}>{a.length > 14 ? `${a.slice(0, 13)}…` : a}</th>
                {entrants.map((b) => {
                  const v = sweep.win_rate_matrix[a]?.[b] ?? 0.5;
                  const bg =
                    a === b
                      ? "transparent"
                      : `color-mix(in srgb, var(--green) ${Math.round(v * 72)}%, var(--bg-deep))`;
                  return (
                    <td key={b} style={{ background: bg }} className="mono">
                      {a === b ? "·" : Math.round(v * 100)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="lb-replays">
        <span className="section-label">Per-seed benches</span>
        {sweep.bench_dirs.map((b) => (
          <Link key={b} className="btn secondary" to={`/leaderboard?dir=${encodeURIComponent(`${dir}/${b}`)}`}>
            {b}
          </Link>
        ))}
      </div>
    </>
  );
}
