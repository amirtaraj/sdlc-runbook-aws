export function ThinkingIndicator({ label }: { label: string }) {
  return (
    <div className="thinking" role="status" aria-live="polite">
      <span className="dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      {label}
    </div>
  );
}
