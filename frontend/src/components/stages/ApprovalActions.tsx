interface Props {
  disabled: boolean;
  approveDisabled: boolean;
  approveLabel: string;
  editLabel: string;
  onApprove: () => void;
  onEdit: () => void;
  onReject: () => void;
}

export function ApprovalActions({ disabled, approveDisabled, approveLabel, editLabel, onApprove, onEdit, onReject }: Props) {
  return (
    <div className="button-row approval-actions">
      <button type="button" className="btn btn-danger-ghost" onClick={onReject} disabled={disabled}>
        Reject
      </button>
      <button type="button" className="btn btn-secondary" onClick={onEdit} disabled={disabled}>
        {editLabel}
      </button>
      <button type="button" className="btn btn-primary" onClick={onApprove} disabled={disabled || approveDisabled}>
        {approveLabel}
      </button>
    </div>
  );
}
