// All run state for the app shell: the runbook's stage definitions, the sidebar history,
// the run open in the main panel, and whichever request is currently in flight.
import { useCallback, useEffect, useState } from "react";
import { ApiError, runsApi } from "../api/runsApi";
import type { DocumentSource, RunSummary, RunView, StageSpec, TechStack } from "../types/run";

export type PendingAction =
  | { kind: "start"; requirementText: string; source?: DocumentSource; techStackId?: string }
  | { kind: "approve" | "edit" | "reject" | "retry" | "load" | "publish" };

export interface UiError {
  message: string;
  reasons: string[];
}

const toUiError = (e: unknown): UiError =>
  e instanceof ApiError ? { message: e.message, reasons: e.reasons } : { message: String(e), reasons: [] };

export function useRunbook() {
  const [stageSpecs, setStageSpecs] = useState<StageSpec[]>([]);
  const [techStacks, setTechStacks] = useState<TechStack[]>([]);
  const [defaultStackId, setDefaultStackId] = useState<string>("");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [activeRun, setActiveRun] = useState<RunView | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [error, setError] = useState<UiError | null>(null);

  const refreshRuns = useCallback(async () => {
    try {
      setRuns(await runsApi.list());
    } catch (e) {
      setError(toUiError(e));
    }
  }, []);

  useEffect(() => {
    void refreshRuns();
    runsApi.runbook().then((rb) => setStageSpecs(rb.stages), (e) => setError(toUiError(e)));
    runsApi.techStacks().then(
      (t) => {
        setTechStacks(t.stacks);
        setDefaultStackId(t.default);
      },
      (e) => setError(toUiError(e)),
    );
  }, [refreshRuns]);

  // Runs one request, keeping `pending`, `error`, the active run and the sidebar in sync.
  const perform = useCallback(
    async (action: PendingAction, call: () => Promise<RunView>) => {
      setPending(action);
      setError(null);
      try {
        setActiveRun(await call());
      } catch (e) {
        setError(toUiError(e));
      } finally {
        setPending(null);
        void refreshRuns();
      }
    },
    [refreshRuns],
  );

  const runId = activeRun?.run_id;

  return {
    stageSpecs,
    techStacks,
    defaultStackId,
    runs,
    activeRun,
    pending,
    error,
    dismissError: () => setError(null),
    newRun: () => {
      setActiveRun(null);
      setError(null);
    },
    selectRun: (id: string) => perform({ kind: "load" }, () => runsApi.get(id)),
    startRun: (text: string, source?: DocumentSource, techStackId?: string) =>
      perform({ kind: "start", requirementText: text, source, techStackId }, () =>
        runsApi.start(text, source, techStackId),
      ),
    approve: (overrideReason?: string) =>
      runId && perform({ kind: "approve" }, () => runsApi.approve(runId, overrideReason)),
    edit: (correction: string) => runId && perform({ kind: "edit" }, () => runsApi.edit(runId, correction)),
    reject: () => runId && perform({ kind: "reject" }, () => runsApi.reject(runId)),
    retry: () => runId && perform({ kind: "retry" }, () => runsApi.retry(runId)),
    publish: () => runId && perform({ kind: "publish" }, () => runsApi.publish(runId)),
  };
}

export type Runbook = ReturnType<typeof useRunbook>;
