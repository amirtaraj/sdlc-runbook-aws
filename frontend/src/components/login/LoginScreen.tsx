// Sign-in screen. Mock mode (MOCK_AUTH=yes): pick an email and a role, nothing is verified.
// Entra mode: a single button that redirects to Microsoft sign-in.
import { useState, type FormEvent } from "react";
import { useAuth } from "../../auth/AuthContext";
import { APPROVER, VIEWER } from "../../auth/types";
import { ThemeToggle } from "../../theme/ThemeToggle";

function Brand() {
  return (
    <div className="brand brand-centered">
      <span className="brand-mark" aria-hidden="true">
        SR
      </span>
      <span className="brand-name">SDLC Runbook</span>
    </div>
  );
}

export function LoginScreen() {
  const { config, loginMock, loginEntra } = useAuth();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(APPROVER);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (config?.mode === "entra") loginEntra();
    else loginMock(email, role);
  };

  return (
    <div className="login-screen">
      <ThemeToggle />
      <form className="card login-card" onSubmit={submit}>
        <Brand />
        <p className="muted login-subtitle">From business requirement to dev-ready backlog, with you approving every stage.</p>
        {config?.mode === "entra" ? (
          <button type="submit" className="btn btn-primary btn-block">
            Sign in with Microsoft
          </button>
        ) : (
          <>
            <label>
              Email
              <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoFocus />
            </label>
            <fieldset className="role-picker">
              <legend>Role</legend>
              <label>
                <input type="radio" name="role" checked={role === APPROVER} onChange={() => setRole(APPROVER)} />
                Approver <span className="muted">start runs and approve stages</span>
              </label>
              <label>
                <input type="radio" name="role" checked={role === VIEWER} onChange={() => setRole(VIEWER)} />
                Viewer <span className="muted">read-only</span>
              </label>
            </fieldset>
            <button type="submit" className="btn btn-primary btn-block">
              Sign in
            </button>
            <p className="muted login-note">Mock sign-in for local development: no account is checked.</p>
          </>
        )}
      </form>
    </div>
  );
}
