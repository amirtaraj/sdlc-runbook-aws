export function NewRunButton({ onClick, disabled }: { onClick: () => void; disabled: boolean }) {
  return (
    <button type="button" className="btn btn-primary new-run-button" onClick={onClick} disabled={disabled}>
      + New Run
    </button>
  );
}
