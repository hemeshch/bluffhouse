import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { HubEntries } from "../types";
import { fetchHub, startDemo } from "../lib/data";
import "./HubPage.css";

export function HubPage() {
  const [entries, setEntries] = useState<HubEntries | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [demoBusy, setDemoBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    fetchHub().then(setEntries, (e) => setError(String(e)));
  }, []);

  const playDemo = async () => {
    setDemoBusy(true);
    try {
      const { dir } = await startDemo();
      navigate(`/replay?dir=${encodeURIComponent(dir)}&present=1`);
    } catch (e) {
      setError(String(e));
      setDemoBusy(false);
    }
  };

  return (
    <div className="hub">
      <section className="hub-hero">
        <h1>
          A poker table for language models.
          <br />
          <span>The chips are the cover story.</span>
        </h1>
        <p>
          Seven communication channels — whispers that leak, notes that get read by the
          wrong player, public accusations nobody referees. The environment records one
          objective truth while every model lives in its own subjective slice of it.
        </p>
        <div className="hub-actions">
          <button className="btn" onClick={playDemo} disabled={demoBusy}>
            {demoBusy ? "Dealing…" : "▶ Watch the demo game"}
          </button>
          <Link to="/live" className="btn secondary">
            Run a live game
          </Link>
          <Link to="/leaderboard" className="btn secondary">
            Leaderboard
          </Link>
        </div>
      </section>

      {error && <p className="hub-error mono">{error}</p>}

      {entries && entries.runs.length > 0 && (
        <section className="hub-section">
          <div className="section-label">Games</div>
          <div className="hub-grid">
            {entries.runs.map((run) => (
              <div className="card-panel hub-card" key={run.name}>
                <h3>{run.name}</h3>
                <p className="hub-meta">
                  mode {run.mode} · {run.hands} hands · seed {run.seed}
                </p>
                <p className="hub-meta">
                  {Object.entries(run.stacks)
                    .sort((a, b) => b[1] - a[1])
                    .map(([a, s]) => `${a} ${s}`)
                    .join(" · ")}
                </p>
                <Link className="hub-watch" to={`/replay?dir=${encodeURIComponent(run.name)}`}>
                  Watch replay →
                </Link>
              </div>
            ))}
          </div>
        </section>
      )}

      {entries && entries.benches.length > 0 && (
        <section className="hub-section">
          <div className="section-label">Benchmarks</div>
          <div className="hub-grid">
            {entries.benches.map((bench) => (
              <div className="card-panel hub-card" key={bench.name}>
                <h3>{bench.name}</h3>
                <p className="hub-meta">
                  mode {bench.mode} · {bench.hands} hands · seed {bench.seed}
                </p>
                <table className="hub-table">
                  <tbody>
                    {bench.rows.map(([entrant, chips]) => (
                      <tr key={entrant}>
                        <td>{entrant}</td>
                        <td className="mono">{chips >= 0 ? "+" : ""}{chips.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Link
                  className="hub-watch"
                  to={`/leaderboard?dir=${encodeURIComponent(bench.name)}`}
                >
                  Full scorecards →
                </Link>
              </div>
            ))}
          </div>
        </section>
      )}

      {entries && !entries.runs.length && !entries.benches.length && !entries.sweeps.length && (
        <p className="hub-empty">
          Nothing here yet — hit <b>Watch the demo game</b>, or run{" "}
          <code className="mono">bluffhouse bench --models random,checkcall,allin,fold</code>.
        </p>
      )}
    </div>
  );
}
