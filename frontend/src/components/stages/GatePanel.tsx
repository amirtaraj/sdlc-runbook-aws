import type { GateResult } from "../../types/run";

export function GatePanel({ gates, override }: { gates: GateResult[]; override?: string | null }) {
  if (!gates.length) return null;
  const failed = gates.filter((g) => !g.passed).length;
  return (
    <details className={`gate-panel ${failed ? "has-failures" : ""}`} open={failed > 0}>
      <summary>
        Quality gates: {gates.length - failed}/{gates.length} passed
        {failed > 0 && <span className="tag tag-rejected">{failed} failed</span>}
        {override && <span className="tag tag-pending">Overridden</span>}
      </summary>
      <ul>
        {gates.map((g, i) => (
          <li key={i} className={g.passed ? "gate-pass" : "gate-fail"}>
            <span aria-hidden="true">{g.passed ? "✓" : "✕"}</span>
            <span>
              {g.description || g.check}
              <span className="muted"> ({g.detail})</span>
            </span>
          </li>
        ))}
      </ul>
      {override && <p className="edit-note muted">Override reason: {override}</p>}
    </details>
  );
}
