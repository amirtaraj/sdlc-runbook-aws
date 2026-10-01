import { useState } from "react";

interface Props {
  disabled: boolean;
  label: string;
  placeholder: string;
  submitLabel?: string;
  onSubmit: (text: string) => void;
  onCancel: () => void;
}

/** Inline textarea + Submit/Cancel, used for edit corrections, clarifications and gate overrides. */
export function EditPanel({ disabled, label, placeholder, submitLabel = "Submit", onSubmit, onCancel }: Props) {
  const [text, setText] = useState("");
  const canSubmit = !disabled && text.trim().length > 0;
  const submit = () => canSubmit && onSubmit(text.trim());

  return (
    <div className="edit-panel">
      <label>
        {label}
        <textarea
          autoFocus
          rows={3}
          value={text}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit();
            if (e.key === "Escape") onCancel();
          }}
        />
      </label>
      <div className="button-row">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={disabled}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary" onClick={submit} disabled={!canSubmit}>
          {submitLabel}
        </button>
      </div>
    </div>
  );
}
