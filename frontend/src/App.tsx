import { AuthProvider, useAuth } from "./auth/AuthContext";
import { LoginScreen } from "./components/login/LoginScreen";
import { AppShell } from "./components/shell/AppShell";
import { ThemeProvider } from "./theme/ThemeContext";

function Screens() {
  const { status, error, user } = useAuth();
  if (status === "loading") return <div className="login-screen muted">Connecting…</div>;
  if (status === "error") {
    return (
      <div className="login-screen">
        <p className="error-text">{error}</p>
      </div>
    );
  }
  return user ? <AppShell /> : <LoginScreen />;
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Screens />
      </AuthProvider>
    </ThemeProvider>
  );
}
