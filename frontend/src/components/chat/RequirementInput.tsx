// Composer for a new run: type the requirement, or attach / drop a document (.txt .md .docx .pdf).
// An uploaded document is screened by the guardrails first; personal data can be redacted
// ("Redact and continue"), while credentials or injected instructions block it outright.
// A loaded document shows in its own preview card; the text box then takes an optional note.
import { useRef, useState, type DragEvent } from "react";
import { ApiError, runsApi } from "../../api/runsApi";
import type { DocumentExtract, DocumentSource, TechStack } from "../../types/run";
import { DocumentPreview } from "./DocumentPreview";

const EXAMPLES = [
  "Employees need a web app to request annual leave, with manager approval and an HR dashboard of who is out.",
  "Build a customer feedback portal where users submit ideas, vote on them, and product managers mark status.",
];
const ACCEPT = ".txt,.md,.docx,.pdf";

interface Props {
  disabled: boolean;
  techStacks: TechStack[];
  defaultStackId: string;
  onSubmit: (text: string, source: DocumentSource | undefined, techStackId: string | undefined) => void;
}

type Upload =
  | { state: "reading"; filename: string }
  | { state: "error"; filename: string; message: string }
  | { state: "review"; doc: DocumentExtract }                                     // guardrails found something
  | { state: "loaded"; source: DocumentSource; text: string; categories: string[] }; // shown in the preview card

const sourceOf = (doc: DocumentExtract, redacted: boolean): DocumentSource => ({
  filename: doc.filename, kind: doc.kind, sha256: doc.sha256, pages: doc.pages, chars: doc.chars, redacted,
});

/** The requirement sent to the agents: the document, plus the requester's note if any. */
function combine(documentText: string, note: string): string {
  if (!documentText) return note;
  return note ? `${documentText}\n\nNote from the requester:\n${note}` : documentText;
}

export function RequirementInput({ disabled, techStacks, defaultStackId, onSubmit }: Props) {
  const [text, setText] = useState("");
  const [stackId, setStackId] = useState("");
  const chosenStack = stackId || defaultStackId;
  const [upload, setUpload] = useState<Upload | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const loaded = upload?.state === "loaded" ? upload : null;
  const busy = disabled || upload?.state === "reading";
  const requirement = combine(loaded?.text.trim() ?? "", text.trim());
  const canSubmit = !busy && upload?.state !== "review" && requirement.length > 0;

  const submit = () => {
    if (!canSubmit) return;
    onSubmit(requirement, loaded?.source, chosenStack || undefined);
    setText("");
    setUpload(null);
  };

  const readFile = async (file: File) => {
    setUpload({ state: "reading", filename: file.name });
    try {
      const doc = await runsApi.extractDocument(file);
      if (doc.blocked_reasons.length || doc.pii_categories.length) {
        setUpload({ state: "review", doc });
      } else {
        setUpload({ state: "loaded", source: sourceOf(doc, false), text: doc.text, categories: [] });
      }
    } catch (e) {
      setUpload({ state: "error", filename: file.name, message: e instanceof ApiError ? e.message : String(e) });
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && !busy) void readFile(file);
  };

  return (
    <div className="composer">
      {!text && !upload && (
        <div className="examples">
          {EXAMPLES.map((example) => (
            <button key={example} type="button" className="chip" onClick={() => setText(example)} disabled={disabled}>
              {example}
            </button>
          ))}
        </div>
      )}

      {upload?.state === "review" && (
        <div className={`upload-review ${upload.doc.blocked_reasons.length ? "is-blocked" : ""}`} role="alert">
          <strong>{upload.doc.filename}</strong>
          {upload.doc.blocked_reasons.length > 0 ? (
            <>
              <p>This document can't be used as it is:</p>
              <ul>
                {upload.doc.blocked_reasons.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
              {upload.doc.pii_categories.length > 0 && (
                <p className="muted">It also contains personal data ({upload.doc.pii_categories.join(", ")}).</p>
              )}
              <div className="button-row">
                <button type="button" className="btn btn-secondary" onClick={() => setUpload(null)}>
                  Choose another file
                </button>
              </div>
            </>
          ) : (
            <>
              <p>
                Personal data was found: <b>{upload.doc.pii_categories.join(", ")}</b>. The runbook only works with
                anonymised data, so these details will be replaced with placeholders like <code>[Email]</code>. You can
                review the redacted text before starting.
              </p>
              <div className="button-row">
                <button type="button" className="btn btn-ghost" onClick={() => setUpload(null)}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() =>
                    setUpload({
                      state: "loaded",
                      source: sourceOf(upload.doc, true),
                      text: upload.doc.redacted_text ?? "",
                      categories: upload.doc.pii_categories,
                    })
                  }
                >
                  Redact and continue
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {loaded && (
        <DocumentPreview
          source={loaded.source}
          text={loaded.text}
          redactedCategories={loaded.categories}
          disabled={disabled}
          onChange={(value) => setUpload({ ...loaded, text: value })}
          onRemove={() => setUpload(null)}
        />
      )}

      {(upload?.state === "reading" || upload?.state === "error") && (
        <div className={`doc-chip ${upload.state === "error" ? "is-error" : ""}`}>
          <span aria-hidden="true">📄</span>
          {upload.state === "reading" ? (
            <span>Reading {upload.filename}…</span>
          ) : (
            <span>
              {upload.filename}: {upload.message}
            </span>
          )}
          {upload.state === "error" && (
            <button type="button" className="doc-chip-remove" aria-label="Dismiss" onClick={() => setUpload(null)}>
              ✕
            </button>
          )}
        </div>
      )}

      <div
        className={`composer-box ${dragging ? "is-dragging" : ""} ${loaded ? "has-document" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          if (!busy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) void readFile(file);
          }}
        />
        <textarea
          aria-label={loaded ? "Optional note for the agents" : "Business requirement"}
          rows={loaded ? 2 : 3}
          value={text}
          disabled={busy || upload?.state === "review"}
          placeholder={
            loaded
              ? "Add a note for the agents (optional), e.g. focus on the mobile experience…"
              : "Describe the business requirement, or drop a document here…"
          }
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          type="button"
          className="composer-attach"
          aria-label={loaded ? "Replace the document" : "Attach a requirements document"}
          title="Attach a document (.txt, .md, .docx, .pdf)"
          disabled={busy}
          onClick={() => fileInput.current?.click()}
        >
          +
        </button>
        {techStacks.length > 0 && (
          <label className="stack-picker" title="Tech stack used by Design, Tasks and the specs">
            <span className="visually-hidden">Tech stack</span>
            <select value={chosenStack} disabled={busy} onChange={(e) => setStackId(e.target.value)}>
              {techStacks.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <button type="button" className="btn btn-primary composer-send" onClick={submit} disabled={!canSubmit}>
          Start run
        </button>
        {dragging && <div className="drop-hint">Drop to read the document</div>}
      </div>
      <p className="composer-hint">
        <span>Enter to start · Shift+Enter for a new line · attach .txt, .md, .docx or .pdf (up to 5 MB)</span>
      </p>
    </div>
  );
}
