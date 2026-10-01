import type { RunSummary } from "../../types/run";
import { ConversationListItem } from "./ConversationListItem";

interface Props {
  runs: RunSummary[];
  activeRunId: string | null;
  disabled: boolean;
  onSelect: (runId: string) => void;
}

export function ConversationList({ runs, activeRunId, disabled, onSelect }: Props) {
  if (!runs.length) return <p className="sidebar-empty muted">No runs yet. Start one to see it here.</p>;
  return (
    <nav aria-label="Run history">
      <h2 className="sidebar-heading">History</h2>
      <ul className="conversation-list">
        {runs.map((run) => (
          <ConversationListItem
            key={run.run_id}
            run={run}
            active={run.run_id === activeRunId}
            disabled={disabled}
            onSelect={onSelect}
          />
        ))}
      </ul>
    </nav>
  );
}
