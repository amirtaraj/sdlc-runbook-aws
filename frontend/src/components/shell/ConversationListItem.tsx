import type { RunStatus, RunSummary } from "../../types/run";
import { relativeTime } from "../../utils/format";

const STATUS_LABEL: Record<RunStatus, string> = {
  not_started: "Starting",
  pending_approval: "Needs review",
  failed: "Failed",
  completed: "Completed",
  rejected: "Rejected",
};

interface Props {
  run: RunSummary;
  active: boolean;
  disabled: boolean;
  onSelect: (runId: string) => void;
}

export function ConversationListItem({ run, active, disabled, onSelect }: Props) {
  return (
    <li>
      <button
        type="button"
        className={`conversation-item ${active ? "is-active" : ""}`}
        aria-current={active ? "true" : undefined}
        disabled={disabled}
        onClick={() => onSelect(run.run_id)}
        title={run.title}
      >
        <span className="conversation-title">{run.title}</span>
        <span className="conversation-meta">
          <span className={`status-dot status-dot-${run.status}`} aria-hidden="true" />
          {STATUS_LABEL[run.status]} · {relativeTime(run.updated_at)}
        </span>
      </button>
    </li>
  );
}
