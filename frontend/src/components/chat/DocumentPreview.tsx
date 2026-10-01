// Readable preview of an uploaded requirements document, with an in-place editor.
// Redaction placeholders ([Email], [Person], ...) are highlighted so the reviewer sees what was masked.
import { Fragment, useState } from "react";
import type { DocumentSource } from "../../types/run";
import { plural } from "../../utils/format";

interface Props {
  source: DocumentSource;
  text: string;
  redactedCategories: string[];
  disabled: boolean;
  onChange: (text: string) => void;
  onRemove: () => void;
}

function Highlighted({ text, categories }: { text: string; categories: string[] }) {
  if (!categories.length) return <>{text}</>;
  const pattern = new RegExp(`(\\[(?:${categories.map((c) => c.replace(/\W/g, "")).join("|")})\\])`, "g");
  return (
    <>
      {text.split(pattern).map((part, i) =>
        i % 2 === 1 ? (
          <mark key={i} className="redaction">
            {part}
          </mark>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

export function DocumentPreview({ source, text, redactedCategories, disabled, onChange, onRemove }: Props) {
  const [editing, setEditing] = useState(false);
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;

  return (
    <section className="doc-preview" aria-label={`Preview of ${source.filename}`}>
      <header className="doc-preview-header">
        <span className="doc-preview-icon" aria-hidden="true">
          📄
        </span>
        <div className="doc-preview-title">
          <strong title={source.filename}>{source.filename}</strong>
          <span className="muted">
            {source.pages ? `${plural(source.pages, "page")} · ` : ""}
            {plural(words, "word")}
            {source.redacted && " · personal data redacted"}
          </span>
        </div>
        {source.redacted && <span className="tag tag-pending">Redacted</span>}
        <div className="doc-preview-actions">
          <button type="button" className="btn btn-ghost" onClick={() => setEditing((v) => !v)} disabled={disabled}>
            {editing ? "Done" : "Edit"}
          </button>
          <button type="button" className="icon-button" aria-label="Remove document" onClick={onRemove} disabled={disabled}>
            ✕
          </button>
        </div>
      </header>
      {editing ? (
        <textarea
          className="doc-preview-editor"
          aria-label="Document text"
          value={text}
          autoFocus
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <div className="doc-preview-body" tabIndex={0}>
          <Highlighted text={text} categories={source.redacted ? redactedCategories : []} />
        </div>
      )}
    </section>
  );
}
