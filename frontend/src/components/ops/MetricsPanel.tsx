// AgentOps view: run outcomes, LLM success rate, latency, tokens and cost, and the health of
// each external API. Refreshes every 10 s while open.
import { useEffect, useState } from "react";
import { ApiError, runsApi } from "../../api/runsApi";
import type { Metrics } from "../../types/run";

const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="stat-tile">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {hint && <span className="stat-hint muted">{hint}</span>}
    </div>
  );
}

export function MetricsPanel({ onClose }: { onClose: () => void }) {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      runsApi.metrics().then(
        (m) => alive && (setMetrics(m), setError(null)),
        (e) => alive && setError(e instanceof ApiError ? e.message : String(e)),
      );
    void load();
    const timer = window.setInterval(load, 10_000);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => {
      alive = false;
      window.clearInterval(timer);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-label="Operations metrics" onClick={(e) => e.stopPropagation()}>
        <header className="drawer-header">
          <h2>Operations</h2>
          <button type="button" className="icon-button" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </header>
        {error && <p className="error-text">{error}</p>}
        {!metrics && !error && <p className="muted">Loading…</p>}
        {metrics && (
          <>
            <div className="stat-grid">
              <Tile label="Runs" value={String(metrics.runs.total)} hint={`${metrics.runs.by_status.completed} completed · ${metrics.runs.by_status.rejected} rejected`} />
              <Tile label="Completion rate" value={pct(metrics.runs.completion_rate)} hint="of finished runs" />
              <Tile label="LLM success" value={pct(metrics.llm.success_rate)} hint={`${metrics.llm.calls} calls`} />
              <Tile label="p95 latency" value={`${(metrics.llm.p95_latency_ms / 1000).toFixed(1)}s`} hint={`avg ${(metrics.llm.avg_latency_ms / 1000).toFixed(1)}s`} />
              <Tile label="Tokens" value={metrics.llm.total_tokens.toLocaleString()} hint={`${metrics.llm.prompt_tokens.toLocaleString()} in · ${metrics.llm.completion_tokens.toLocaleString()} out`} />
              <Tile label="Est. cost" value={`$${metrics.llm.estimated_cost_usd.toFixed(4)}`} hint="model list price" />
            </div>

            <h3 className="drawer-heading">By stage</h3>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Stage</th>
                    <th>Calls</th>
                    <th>Success</th>
                    <th>p95</th>
                    <th>Tokens</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(metrics.llm.by_stage).map(([stage, s]) => (
                    <tr key={stage}>
                      <td>{stage}</td>
                      <td>{s.calls}</td>
                      <td>{pct(s.success_rate)}</td>
                      <td>{(s.p95_latency_ms / 1000).toFixed(1)}s</td>
                      <td>{s.total_tokens.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 className="drawer-heading">External APIs</h3>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Calls</th>
                    <th>Success</th>
                    <th>p95</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(metrics.services).map(([name, s]) => (
                    <tr key={name}>
                      <td>{name}</td>
                      <td>{s.calls}</td>
                      <td>{pct(s.success_rate)}</td>
                      <td>{s.p95_latency_ms} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {metrics.llm.recent_errors.length > 0 && (
              <>
                <h3 className="drawer-heading">Recent errors</h3>
                <ul className="error-list">
                  {metrics.llm.recent_errors.map((e, i) => (
                    <li key={i}>
                      <strong>{e.stage}</strong>: {e.error}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </aside>
    </div>
  );
}
