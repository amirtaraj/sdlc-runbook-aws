import type { ReactNode } from "react";

interface Props {
  tone: "error" | "terminal";
  children: ReactNode;
  reasons?: string[];
  action?: { label: string; onClick: () => void; disabled?: boolean };
}

export function StatusMessage({ tone, children, reasons, action }: Props) {
  return (
    <div className={`status-message status-${tone}`} role={tone === "error" ? "alert" : "status"}>
      <div>
        <span>{children}</span>
        {reasons && reasons.length > 0 && (
          <ul className="status-reasons">
            {reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        )}
      </div>
      {action && (
        <button type="button" className="btn btn-secondary" onClick={action.onClick} disabled={action.disabled}>
          {action.label}
        </button>
      )}
    </div>
  );
}
