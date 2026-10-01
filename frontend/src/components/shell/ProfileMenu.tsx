import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../auth/AuthContext";

export function ProfileMenu() {
  const { user, config, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (!user) return null;
  return (
    <div className="profile-menu" ref={rootRef}>
      <button
        type="button"
        className="avatar avatar-button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${user.name}`}
        onClick={() => setOpen((v) => !v)}
      >
        {user.initials}
      </button>
      {open && (
        <div className="dropdown" role="menu">
          <div className="dropdown-user">
            <strong>{user.name}</strong>
            <span className="muted">{user.email}</span>
            <span className="muted">
              {user.roles.map((r) => r.replace("Runbook.", "")).join(", ")} · {config?.mode === "entra" ? "Entra ID" : "Mock sign-in"}
            </span>
          </div>
          <button type="button" role="menuitem" className="dropdown-item" onClick={logout}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
