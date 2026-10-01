import type { Runbook } from "../../hooks/useRunbook";
import { ChatThread } from "./ChatThread";
import { RequirementInput } from "./RequirementInput";
import { StageProgress } from "./StageProgress";
import { StatusMessage } from "./StatusMessage";

interface Props {
  runbook: Runbook;
  initials: string;
  firstName: string;
  canAct: boolean;
}

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

export function MainPanel({ runbook, initials, firstName, canAct }: Props) {
  const { activeRun, pending, error, stageSpecs } = runbook;
  const isNewRun = !activeRun && pending?.kind !== "start" && pending?.kind !== "load";

  const errorBanner = error && (
    <div className="chat-thread">
      <StatusMessage tone="error" reasons={error.reasons} action={{ label: "Dismiss", onClick: runbook.dismissError }}>
        {error.message}
      </StatusMessage>
    </div>
  );

  if (isNewRun) {
    return (
      <main className="main-panel">
        <div className="hero">
          <div className="hero-glow" aria-hidden="true" />
          <div className="empty-state">
            <h1 className="greeting">
              {greeting()}, <span className="greeting-name">{firstName}</span>
            </h1>
            <p className="hero-tagline">Turn a business requirement into approved, traceable delivery documents in hours, not days.</p>
            {!canAct && <p className="muted">You have read-only access. Open a run from the history to review it.</p>}
          </div>
          {canAct && (
            <RequirementInput
              disabled={pending !== null}
              techStacks={runbook.techStacks}
              defaultStackId={runbook.defaultStackId}
              onSubmit={runbook.startRun}
            />
          )}
          {errorBanner}
        </div>
      </main>
    );
  }

  return (
    <main className="main-panel">
      {activeRun && pending?.kind !== "load" && pending?.kind !== "start" && (
        <StageProgress run={activeRun} specs={stageSpecs} />
      )}
      <div className="main-scroll">
        <ChatThread
          run={activeRun}
          specs={stageSpecs}
          techStacks={runbook.techStacks}
          pending={pending}
          initials={initials}
          canAct={canAct}
          actions={runbook}
        />
        {errorBanner}
      </div>
    </main>
  );
}
