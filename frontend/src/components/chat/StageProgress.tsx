// Sticky stepper above the thread: done stages, the current one, and what is still to come.
import type { RunView, StageSpec } from "../../types/run";

type StepState = "done" | "current" | "rejected" | "upcoming";

function stepState(run: RunView, stageId: string): StepState {
  const record = run.history.find((h) => h.stage === stageId);
  if (record) return record.decision === "rejected" ? "rejected" : "done";
  if (run.stage === stageId && run.status !== "completed") return "current";
  return "upcoming";
}

export function StageProgress({ run, specs }: { run: RunView; specs: StageSpec[] }) {
  if (!specs.length) return null;
  return (
    <nav className="stage-progress" aria-label="Runbook progress">
      <ol>
        {specs.map((spec, i) => {
          const state = stepState(run, spec.id);
          return (
            <li key={spec.id} className={`step step-${state}`} aria-current={state === "current" ? "step" : undefined}>
              <span className="step-dot" aria-hidden="true">
                {state === "done" ? "✓" : state === "rejected" ? "✕" : i + 1}
              </span>
              <span className="step-label">{spec.title}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
