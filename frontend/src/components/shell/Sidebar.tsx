import type { RunSummary } from "../../types/run";
import { ConversationList } from "./ConversationList";
import { NewRunButton } from "./NewRunButton";

interface Props {
  open: boolean;
  runs: RunSummary[];
  activeRunId: string | null;
  busy: boolean;
  canStart: boolean;
  onNewRun: () => void;
  onSelectRun: (runId: string) => void;
  onClose: () => void;
}

export function Sidebar({ open, runs, activeRunId, busy, canStart, onNewRun, onSelectRun, onClose }: Props) {
  return (
    <>
      <aside className={`sidebar ${open ? "is-open" : ""}`}>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            SR
          </span>
          <span className="brand-name">SDLC Runbook</span>
        </div>
        {canStart && <NewRunButton onClick={onNewRun} disabled={busy} />}
        <ConversationList runs={runs} activeRunId={activeRunId} disabled={busy} onSelect={onSelectRun} />
      </aside>
      {/* Tap-outside backdrop, only visible when the sidebar is an overlay on small screens. */}
      {open && <div className="sidebar-backdrop" onClick={onClose} aria-hidden="true" />}
    </>
  );
}
