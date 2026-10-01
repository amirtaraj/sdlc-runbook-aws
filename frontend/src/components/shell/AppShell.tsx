import { useCallback, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { canApprove } from "../../auth/types";
import { useRunbook } from "../../hooks/useRunbook";
import { MainPanel } from "../chat/MainPanel";
import { MetricsPanel } from "../ops/MetricsPanel";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppShell() {
  const { user } = useAuth();
  const runbook = useRunbook();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [metricsOpen, setMetricsOpen] = useState(false);
  const closeMetrics = useCallback(() => setMetricsOpen(false), []);
  const { activeRun, pending } = runbook;

  const title = pending?.kind === "start" ? "Starting run…" : activeRun ? activeRun.title : "New Run";

  // On small screens the sidebar is an overlay; close it after any navigation.
  const closeAfter = (fn: () => void) => () => {
    fn();
    setSidebarOpen(false);
  };

  return (
    <div className="app-shell">
      <Sidebar
        open={sidebarOpen}
        runs={runbook.runs}
        activeRunId={activeRun?.run_id ?? null}
        busy={pending !== null}
        canStart={canApprove(user)}
        onNewRun={closeAfter(runbook.newRun)}
        onSelectRun={(id) => closeAfter(() => void runbook.selectRun(id))()}
        onClose={() => setSidebarOpen(false)}
      />
      <div className="workspace">
        <TopBar title={title} onToggleSidebar={() => setSidebarOpen((v) => !v)} onOpenMetrics={() => setMetricsOpen(true)} />
        <MainPanel
          runbook={runbook}
          initials={user?.initials ?? "?"}
          firstName={user?.name.split(" ")[0] ?? "there"}
          canAct={canApprove(user)}
        />
      </div>
      {metricsOpen && <MetricsPanel onClose={closeMetrics} />}
    </div>
  );
}
