// The conversation for one run, top to bottom: requirement → stage cards → final pack.
import { useEffect, useRef } from "react";
import type { PendingAction, Runbook } from "../../hooks/useRunbook";
import type { RunView, StageSpec, TechStack } from "../../types/run";
import { stageLabel } from "../stages/stageConfig";
import { StageResultCard } from "../stages/StageResultCard";
import { AgentRow } from "./AgentRow";
import { FinalDocumentCard } from "./FinalDocumentCard";
import { RequirementBubble } from "./RequirementBubble";
import { StatusMessage } from "./StatusMessage";
import { ThinkingIndicator } from "./ThinkingIndicator";

interface Props {
  run: RunView | null;
  specs: StageSpec[];
  techStacks: TechStack[];
  pending: PendingAction | null;
  initials: string;
  canAct: boolean;
  actions: Pick<Runbook, "approve" | "edit" | "reject" | "retry" | "publish">;
}

function thinkingLabel(run: RunView | null, specs: StageSpec[], pending: PendingAction | null): string | null {
  if (!pending) return null;
  const agent = (stage: string | undefined) => (stage ? `${stageLabel(specs, stage)} agent is working…` : "Working…");
  switch (pending.kind) {
    case "start":
      return agent(specs[0]?.id);
    case "approve": {
      const i = run?.stage ? run.stages.indexOf(run.stage) : -1;
      return i >= 0 && i + 1 < (run?.stages.length ?? 0) ? agent(run!.stages[i + 1]) : "Assembling the runbook pack…";
    }
    case "retry":
      return agent(run?.stage ?? undefined);
    case "load":
      return "Loading run…";
    case "publish":
      return "Creating work items…";
    default:
      return null; // edit shows an overlay on the card itself; reject is instant
  }
}

export function ChatThread({ run, specs, techStacks, pending, initials, canAct, actions }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const label = thinkingLabel(run, specs, pending);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [run?.updated_at, run?.run_id, label]);

  const requirementText = pending?.kind === "start" ? pending.requirementText : run?.requirement_text;
  const source = pending?.kind === "start" ? pending.source : run?.source;
  const stackName =
    pending?.kind === "start"
      ? techStacks.find((s) => s.id === pending.techStackId)?.name
      : run?.tech_stack?.name;
  const showRun = run && pending?.kind !== "start" && pending?.kind !== "load";

  return (
    <div className="chat-thread">
      {requirementText && pending?.kind !== "load" && (
        <RequirementBubble text={requirementText} initials={initials} source={source} stackName={stackName} />
      )}

      {showRun && run.clarifications.length > 0 && (
        <p className="clarifications muted">Clarifications added: {run.clarifications.join(" · ")}</p>
      )}

      {showRun &&
        run.history.map((record) => (
          <AgentRow key={`${record.stage}-decided`}>
            <StageResultCard
              mode="decided"
              specs={specs}
              stage={record.stage}
              output={record.output}
              record={record}
              runId={run.run_id}
            />
          </AgentRow>
        ))}

      {showRun && run.status === "pending_approval" && run.stage && run.output && (
        <AgentRow key={`${run.stage}-pending`}>
          <StageResultCard
            mode="pending"
            specs={specs}
            stage={run.stage}
            output={run.output}
            gates={run.gates}
            refusal={run.refusal}
            piiFlags={run.pii_flags}
            references={run.references}
            editNotes={run.edit_notes}
            busy={pending?.kind === "edit" ? "revising" : pending ? "other" : null}
            canAct={canAct}
            onApprove={actions.approve}
            onEdit={actions.edit}
            onReject={actions.reject}
          />
        </AgentRow>
      )}

      {showRun && run.error && (
        <StatusMessage
          tone="error"
          action={
            run.status === "failed" && canAct ? { label: "Retry", onClick: actions.retry, disabled: pending !== null } : undefined
          }
        >
          {run.error}
        </StatusMessage>
      )}

      {showRun && run.status === "rejected" && run.stage && (
        <StatusMessage tone="terminal">
          Run rejected at {stageLabel(specs, run.stage)}. No further actions are possible on this run.
        </StatusMessage>
      )}

      {showRun && run.status === "completed" && (
        <AgentRow>
          <FinalDocumentCard run={run} canPublish={canAct} publishing={pending?.kind === "publish"} onPublish={actions.publish} />
        </AgentRow>
      )}

      {label && (
        <AgentRow>
          <ThinkingIndicator label={label} />
        </AgentRow>
      )}
      <div ref={bottomRef} />
    </div>
  );
}
