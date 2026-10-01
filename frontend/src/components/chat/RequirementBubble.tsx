// The user's message (the requirement), right-aligned with their initials, opposite the agents.
import { useState } from "react";
import type { DocumentSource } from "../../types/run";

const PREVIEW_CHARS = 600;

interface Props {
  text: string;
  initials: string;
  source?: DocumentSource | null;
  stackName?: string;
}

export function RequirementBubble({ text, initials, source, stackName }: Props) {
  const [expanded, setExpanded] = useState(false);
  const long = text.length > PREVIEW_CHARS;
  const shown = long && !expanded ? `${text.slice(0, PREVIEW_CHARS).trimEnd()}…` : text;

  return (
    <div className="user-row">
      <section className="user-message" aria-label="Your requirement">
        {source && (
          <div className="requirement-source">
            📄 {source.filename}
            {source.redacted && " · personal data redacted"}
          </div>
        )}
        <div className="requirement-text">{shown}</div>
        {stackName && <div className="requirement-stack">Tech stack: {stackName}</div>}
        {long && (
          <button type="button" className="btn btn-link requirement-toggle" onClick={() => setExpanded((v) => !v)}>
            {expanded ? "Show less" : `Show all ${text.length.toLocaleString()} characters`}
          </button>
        )}
      </section>
      <span className="avatar avatar-sm" aria-hidden="true" title="You">
        {initials}
      </span>
    </div>
  );
}
