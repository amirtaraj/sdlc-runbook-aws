// Mock sign-in (MOCK_AUTH=yes on the server): the identity is chosen on the login screen and
// sent as `Authorization: Mock <base64url(JSON)>`. The server rejects it when mock auth is off.
import type { AuthUser } from "./types";

const STORAGE_KEY = "sdlc-runbook.mock-user";

export function mockUserFromEmail(email: string, role: string): AuthUser {
  const clean = email.trim().toLowerCase();
  const parts = (clean.split("@")[0] || "user").split(/[._\-+]+/).filter(Boolean);
  const name = parts.map((p) => p[0].toUpperCase() + p.slice(1)).join(" ") || "User";
  const initials = (parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2)).toUpperCase();
  return { name, email: clean, initials, roles: [role] };
}

export function readMockUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function storeMockUser(user: AuthUser | null): void {
  try {
    if (user) localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage unavailable: the session just won't survive a refresh
  }
}

export function mockAuthHeader(user: AuthUser): string {
  const json = JSON.stringify({ name: user.name, email: user.email, roles: user.roles });
  const b64 = btoa(String.fromCharCode(...new TextEncoder().encode(json)));
  return `Mock ${b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}`;
}
