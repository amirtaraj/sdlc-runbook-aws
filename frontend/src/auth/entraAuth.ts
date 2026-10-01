// Entra ID sign-in (MOCK_AUTH off on the server), via MSAL. Loaded lazily so the mock-auth
// build never pulls it in. Tokens stay in session storage; the API validates them.
import type { AccountInfo, IPublicClientApplication } from "@azure/msal-browser";
import type { AuthConfig } from "../api/runsApi";

export interface EntraSession {
  account: AccountInfo | null;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  authHeader: () => Promise<string | null>;
}

export async function createEntraSession(config: AuthConfig): Promise<EntraSession> {
  const { PublicClientApplication, InteractionRequiredAuthError } = await import("@azure/msal-browser");
  const scopes = [config.api_scope!];
  const msal: IPublicClientApplication = new PublicClientApplication({
    auth: {
      clientId: config.client_id!,
      authority: `https://login.microsoftonline.com/${config.tenant_id}`,
      redirectUri: window.location.origin,
    },
    cache: { cacheLocation: "sessionStorage" },
  });
  await msal.initialize();
  const redirect = await msal.handleRedirectPromise();
  const account = redirect?.account ?? msal.getAllAccounts()[0] ?? null;
  if (account) msal.setActiveAccount(account);

  return {
    account,
    login: () => msal.loginRedirect({ scopes }),
    logout: () => msal.logoutRedirect({ account: msal.getActiveAccount() ?? undefined }),
    authHeader: async () => {
      const active = msal.getActiveAccount();
      if (!active) return null;
      try {
        const result = await msal.acquireTokenSilent({ scopes, account: active });
        return `Bearer ${result.accessToken}`;
      } catch (e) {
        if (e instanceof InteractionRequiredAuthError) await msal.acquireTokenRedirect({ scopes, account: active });
        return null;
      }
    },
  };
}
