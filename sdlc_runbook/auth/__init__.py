"""App sign-in and role-based authorization.

MOCK_AUTH=yes  -> MockAuthenticator: the browser sends a mock identity (local dev only).
otherwise      -> EntraAuthenticator: validates Entra ID access tokens (signature, issuer,
                  audience, expiry) and reads app roles from the `roles` claim.

Roles (Entra app roles, or picked on the mock sign-in screen):
  Runbook.Approver  start runs, approve / edit / reject stages, publish the backlog
  Runbook.Viewer    read runs, documents and metrics only
"""
from .authenticators import Authenticator, EntraAuthenticator, MockAuthenticator, build_authenticator
from .principal import APPROVER, ROLES, VIEWER, Principal

__all__ = [
    "Authenticator", "EntraAuthenticator", "MockAuthenticator", "build_authenticator",
    "APPROVER", "VIEWER", "ROLES", "Principal",
]
