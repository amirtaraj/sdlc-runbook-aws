import { useState } from "react";
import { runsApi } from "../../api/runsApi";
import type { RunView } from "../../types/run";
import { downloadBlob, downloadText, plural } from "../../utils/format";

interface TraceRow {
  id: string;
  text: string;
  components: string[];
  tasks: string[];
}

/** Requirement -> components -> tasks, from the ids the approved stages reference. */
function traceability(run: RunView): TraceRow[] {
  const out = (stage: string) => run.history.find((h) => h.stage === stage)?.output ?? {};
  const reqs = (out("requirements").functional_requirements as { id: string; text: string }[]) ?? [];
  const components = (out("design").components as { id: string; satisfies: string[] }[]) ?? [];
  const tasks = (out("tasks").tasks as { id: string; traces_to: string[] }[]) ?? [];
  return reqs.map((r) => ({
    id: r.id,
    text: r.text,
    components: components.filter((c) => c.satisfies?.includes(r.id)).map((c) => c.id),
    tasks: tasks.filter((t) => t.traces_to?.includes(r.id)).map((t) => t.id),
  }));
}

interface Props {
  run: RunView;
  canPublish: boolean;
  publishing: boolean;
  onPublish: () => void;
}

export function FinalDocumentCard({ run, canPublish, publishing, onPublish }: Props) {
  const [preview, setPreview] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const rows = traceability(run);
  const gaps = rows.filter((r) => !r.tasks.length).length;
  const markdown = run.document_markdown ?? "";
  const taskCount = ((run.history.find((h) => h.stage === "tasks")?.output.tasks as unknown[]) ?? []).length;

  const download = async () => {
    setDownloadError(null);
    try {
      downloadText(`${run.run_id}.md`, await runsApi.document(run.run_id));
    } catch (e) {
      setDownloadError(e instanceof Error ? e.message : String(e));
    }
  };

  const downloadSpecPack = async () => {
    setDownloadError(null);
    try {
      downloadBlob(`${run.run_id}-spec-pack.zip`, await runsApi.specPack(run.run_id));
    } catch (e) {
      setDownloadError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <article className="card final-card" aria-label="Runbook pack">
      <header className="stage-card-header">
        <span className="stage-badge badge-final">Runbook pack</span>
        <span className="tag tag-approved">✓ All stages approved</span>
      </header>
      <h3 className="stage-title">{markdown.split("\n")[0].replace(/^#\s*/, "") || run.title}</h3>
      <p className="muted">
        {plural(run.history.length, "approved stage")} · {plural(taskCount, "task")} · {run.agent_seconds}s agent time ·{" "}
        {run.usage.total_tokens.toLocaleString()} tokens · ${run.usage.cost_usd.toFixed(4)}
      </p>

      {rows.length > 0 && (
        <section className="stage-section">
          <h4>Traceability {gaps > 0 && <span className="tag tag-rejected">{gaps} requirement(s) without tasks</span>}</h4>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Requirement</th>
                  <th>Description</th>
                  <th>Components</th>
                  <th>Tasks</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="nowrap">{r.id}</td>
                    <td>{r.text}</td>
                    <td className="id-list">{r.components.join(", ") || "—"}</td>
                    <td className="id-list">{r.tasks.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {run.published.length > 0 && (
        <section className="stage-section">
          <h4>Published work items</h4>
          <ul>
            {run.published.map((p) => (
              <li key={p.work_item_id}>
                #{p.work_item_id} · {p.title}
              </li>
            ))}
          </ul>
        </section>
      )}

      {preview && <pre className="markdown-preview">{markdown}</pre>}
      {downloadError && <p className="error-text">{downloadError}</p>}
      <div className="button-row">
        <button type="button" className="btn btn-ghost" onClick={() => setPreview((v) => !v)}>
          {preview ? "Hide preview" : "Preview Markdown"}
        </button>
        <button type="button" className="btn btn-secondary" onClick={download}>
          Download pack (.md)
        </button>
        {canPublish && run.published.length === 0 && (
          <button type="button" className="btn btn-secondary" onClick={onPublish} disabled={publishing}>
            {publishing ? "Publishing…" : "Publish to Azure DevOps"}
          </button>
        )}
        {run.spec_pack_available && (
          <button type="button" className="btn btn-primary" onClick={downloadSpecPack}>
            Download spec pack
          </button>
        )}
      </div>
    </article>
  );
}
