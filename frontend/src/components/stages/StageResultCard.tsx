// One card per stage. The pending card shows gate results, refusals, PII warnings and the
// Approve / Edit / Reject actions; decided cards are collapsed and read-only.
import { useState } from "react";
import { runsApi } from "../../api/runsApi";
import type { GateResult, Reference, StageOutput, StageRecord, StageSpec } from "../../types/run";
import { downloadText } from "../../utils/format";
import { ApprovalActions } from "./ApprovalActions";
import { EditPanel } from "./EditPanel";
import { GatePanel } from "./GatePanel";
import { SpecList } from "./SpecList";
import { StageContent } from "./StageContent";
import { accentClass, stageLabel, summarize } from "./stageConfig";

interface Common {
  specs: StageSpec[];
  stage: string;
  output: StageOutput;
}

interface PendingProps extends Common {
  mode: "pending";
  gates: GateResult[];
  refusal: string | null;
  piiFlags: string[];
  references: Reference[];
  editNotes: string[];
  busy: "revising" | "other" | null;
  canAct: boolean;
  onApprove: (overrideReason?: string) => void;
  onEdit: (correction: string) => void;
  onReject: () => void;
}

interface DecidedProps extends Common {
  mode: "decided";
  record: StageRecord;
  runId: string;
}

const DECISION_TAG = {
  approved: { text: "✓ Approved", className: "tag-approved" },
  edited: { text: "✓ Approved after edits", className: "tag-approved" },
  rejected: { text: "✕ Rejected", className: "tag-rejected" },
} as const;

function References({ items }: { items: Reference[] }) {
  if (!items.length) return null;
  return (
    <p className="references muted">
      Grounded on:{" "}
      {items.map((r) => (
        <span key={r.id} className="ref-chip" title={r.title}>
          {r.id}
        </span>
      ))}
    </p>
  );
}

export function StageResultCard(props: PendingProps | DecidedProps) {
  const { specs, stage, output } = props;
  const spec = specs.find((s) => s.id === stage);
  const label = stageLabel(specs, stage);
  const [expanded, setExpanded] = useState(props.mode === "pending");
  const [panel, setPanel] = useState<"none" | "edit" | "override">("none");
  const isPending = props.mode === "pending";
  const showBody = isPending || expanded;

  const classes = ["card", "stage-card", accentClass(specs, stage)];
  if (props.mode === "decided" && props.record.decision === "rejected") classes.push("is-rejected");

  const downloadDoc = async () => {
    if (props.mode !== "decided") return;
    downloadText(`${props.runId}-${stage}.md`, await runsApi.stageDocument(props.runId, stage));
  };

  return (
    <article className={classes.join(" ")} aria-label={`${label} stage`}>
      <header className="stage-card-header">
        <span className="stage-badge">{label}</span>
        {props.mode === "decided" ? (
          <>
            <span className={`tag ${DECISION_TAG[props.record.decision].className}`}>
              {DECISION_TAG[props.record.decision].text}
            </span>
            {props.record.gate_override && <span className="tag tag-pending">Gate override</span>}
            <span className="header-actions">
              {props.record.decision !== "rejected" && (
                <button type="button" className="btn btn-link" onClick={downloadDoc}>
                  Document
                </button>
              )}
              <button type="button" className="btn btn-link" aria-expanded={expanded} onClick={() => setExpanded((v) => !v)}>
                {expanded ? "Collapse" : "Expand"}
              </button>
            </span>
          </>
        ) : props.refusal ? (
          <span className="tag tag-rejected">Refused by agent</span>
        ) : (
          <span className="tag tag-pending">Awaiting your review</span>
        )}
      </header>

      {!showBody && <p className="stage-summary muted">{summarize(output)}</p>}

      {isPending && props.refusal && (
        <div className="refusal-banner" role="alert">
          <strong>The agent refused under the runbook rules:</strong> {props.refusal}
          <p className="muted">Edit the request to fix the problem, or reject the run.</p>
        </div>
      )}

      {isPending && props.piiFlags.length > 0 && (
        <p className="warning-banner" role="alert">
          Possible personal data in this output ({props.piiFlags.join(", ")}). Check before approving.
        </p>
      )}

      {showBody && !(isPending && props.refusal) && (
        <div className={`stage-body ${isPending && props.busy === "revising" ? "is-busy" : ""}`}>
          {spec?.for_each && spec.collect_as ? (
            <SpecList
              items={(output[spec.collect_as] as StageOutput[]) ?? []}
              itemSchema={spec.schema.properties?.[spec.collect_as]?.items}
            />
          ) : (
            <StageContent schema={spec?.schema} output={output} />
          )}
          {isPending && props.busy === "revising" && <div className="busy-overlay">Revising with your correction…</div>}
        </div>
      )}

      {showBody && <References items={isPending ? props.references : props.record.references} />}
      {showBody && <GatePanel gates={isPending ? props.gates : props.record.gates} override={isPending ? null : props.record.gate_override} />}

      {props.mode === "decided" && props.record.edit_note && expanded && (
        <p className="edit-note muted">Corrections applied: {props.record.edit_note}</p>
      )}
      {props.mode === "decided" && expanded && <p className="edit-note muted">Decided by {props.record.actor}</p>}

      {isPending && (
        <footer className="stage-card-footer">
          {props.editNotes.length > 0 && (
            <p className="edit-note muted">
              Revised {props.editNotes.length}× · last correction: “{props.editNotes[props.editNotes.length - 1]}”
            </p>
          )}
          {!props.canAct ? (
            <p className="muted">You have read-only access (Viewer). An Approver must review this stage.</p>
          ) : panel === "edit" ? (
            <EditPanel
              disabled={props.busy !== null}
              label={spec?.edit_mode === "clarify" ? "Add a clarification" : "What should change?"}
              placeholder={
                spec?.edit_mode === "clarify"
                  ? "Answer the questions or add missing context; it becomes part of the requirement."
                  : "e.g. Add a requirement for SSO login and drop the mobile app assumption"
              }
              onCancel={() => setPanel("none")}
              onSubmit={(text) => {
                setPanel("none");
                props.onEdit(text);
              }}
            />
          ) : panel === "override" ? (
            <EditPanel
              disabled={props.busy !== null}
              label="Why approve despite the failed quality gates?"
              placeholder="This reason is recorded in the audit trail."
              submitLabel="Approve with override"
              onCancel={() => setPanel("none")}
              onSubmit={(reason) => {
                setPanel("none");
                props.onApprove(reason);
              }}
            />
          ) : (
            <ApprovalActions
              disabled={props.busy !== null}
              approveDisabled={!!props.refusal}
              approveLabel={props.gates.some((g) => !g.passed) ? "Approve with override…" : "Approve"}
              editLabel={spec?.edit_mode === "clarify" ? "Clarify" : "Edit"}
              onApprove={() => (props.gates.some((g) => !g.passed) ? setPanel("override") : props.onApprove())}
              onEdit={() => setPanel("edit")}
              onReject={props.onReject}
            />
          )}
        </footer>
      )}
    </article>
  );
}
