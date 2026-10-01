import type { ReactNode } from "react";

/** Left-aligned row for anything the agents produce, with the runbook avatar beside it. */
export function AgentRow({ children }: { children: ReactNode }) {
  return (
    <div className="agent-row">
      <span className="agent-avatar" aria-hidden="true" title="Runbook agent">
        SR
      </span>
      <div className="agent-content">{children}</div>
    </div>
  );
}
