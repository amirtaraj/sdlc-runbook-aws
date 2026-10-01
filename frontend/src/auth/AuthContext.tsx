// Picks the sign-in mode the server reports (GET /auth/config) and exposes one interface:
// { mode, user, loginMock, loginEntra, logout }. The API client gets its auth header from here.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { configureApiAuth, fetchAuthConfig, runsApi, type AuthConfig } from "../api/runsApi";
import { createEntraSession, type EntraSession } from "./entraAuth";
import { mockAuthHeader, mockUserFromEmail, readMockUser, storeMockUser } from "./mockAuth";
import type { AuthUser } from "./types";

interface AuthContextValue {
  status: "loading" | "ready" | "error";
  error: string | null;
  config: AuthConfig | null;
  user: AuthUser | null;
  loginMock: (email: string, role: string) => void;
  loginEntra: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function initialsOf(name: string, email: string): string {
  const words = (name || email).split(/[\s.@_-]+/).filter(Boolean);
  return ((words[0]?.[0] ?? "?") + (words[1]?.[0] ?? "")).toUpperCase();
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");
  const [error, setError] = useState<string | null>(null);
  const [config, setConfig] = useState<AuthConfig | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const entra = useRef<EntraSession | null>(null);
  const mockUser = useRef<AuthUser | null>(null);

  const logout = useCallback(() => {
    if (config?.mode === "entra") {
      void entra.current?.logout();
    } else {
      mockUser.current = null;
      storeMockUser(null);
    }
    setUser(null);
  }, [config]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await fetchAuthConfig();
        if (cancelled) return;
        setConfig(cfg);
        if (cfg.mode === "mock") {
          mockUser.current = readMockUser();
          configureApiAuth(async () => (mockUser.current ? mockAuthHeader(mockUser.current) : null), () => {
            mockUser.current = null;
            storeMockUser(null);
            setUser(null);
          });
          setUser(mockUser.current);
        } else {
          const session = await createEntraSession(cfg);
          entra.current = session;
          configureApiAuth(session.authHeader, () => setUser(null));
          if (session.account) {
            // Roles come from the token; ask the API what it sees.
            const me = await runsApi.me();
            if (!cancelled) setUser({ name: me.name, email: me.email, roles: me.roles, initials: initialsOf(me.name, me.email) });
          }
        }
        if (!cancelled) setStatus("ready");
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setStatus("error");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const loginMock = useCallback((email: string, role: string) => {
    const next = mockUserFromEmail(email || "demo.user@example.com", role);
    mockUser.current = next;
    storeMockUser(next);
    setUser(next);
  }, []);

  const loginEntra = useCallback(() => {
    void entra.current?.login();
  }, []);

  const value = useMemo(
    () => ({ status, error, config, user, loginMock, loginEntra, logout }),
    [status, error, config, user, loginMock, loginEntra, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
