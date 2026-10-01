import base64
import json
from typing import Protocol

from ..config import AppAuthSettings
from ..exceptions import AuthError
from .principal import ROLES, Principal


class Authenticator(Protocol):
    mode: str

    def authenticate(self, authorization: str | None) -> Principal: ...

    def public_config(self) -> dict:
        """What the browser needs to sign in. Contains no secrets."""
        ...


class MockAuthenticator:
    """Local development only. Header: `Authorization: Mock <base64url(JSON {name, email, roles})>`."""

    mode = "mock"

    def authenticate(self, authorization: str | None) -> Principal:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme != "Mock" or not token:
            raise AuthError("Sign in required.")
        try:
            padded = token + "=" * (-len(token) % 4)
            claims = json.loads(base64.urlsafe_b64decode(padded))
            email = str(claims["email"]).strip().lower()
            roles = tuple(r for r in claims.get("roles", []) if r in ROLES)
        except (ValueError, KeyError, TypeError) as e:
            raise AuthError("Invalid mock identity.") from e
        if not email or not roles:
            raise AuthError("Mock identity needs an email and at least one known role.")
        return Principal(email, str(claims.get("name") or email), email, roles, "mock")

    def public_config(self) -> dict:
        return {"mode": "mock", "roles": list(ROLES)}


class EntraAuthenticator:
    """Validates Entra ID (v1 or v2) access tokens issued for this API's app registration."""

    mode = "entra"

    def __init__(self, settings: AppAuthSettings):
        import jwt  # PyJWT, only needed in Entra mode

        self._jwt = jwt
        self._settings = settings
        tenant = settings.tenant_id
        self._issuers = [f"https://login.microsoftonline.com/{tenant}/v2.0", f"https://sts.windows.net/{tenant}/"]
        self._jwks = jwt.PyJWKClient(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys", cache_keys=True)

    def authenticate(self, authorization: str | None) -> Principal:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AuthError("Sign in required.")
        jwt = self._jwt
        try:
            key = self._jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token, key, algorithms=["RS256"], audience=self._settings.api_audience,
                issuer=self._issuers, options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.PyJWTError as e:
            raise AuthError(f"Invalid or expired access token ({type(e).__name__}).") from e

        roles = tuple(r for r in claims.get("roles", []) if r in ROLES)
        if not roles:
            raise AuthError("Your account has no SDLC Runbook role. Ask an admin to assign one.", 403)
        email = claims.get("preferred_username") or claims.get("upn") or claims.get("email") or ""
        return Principal(claims.get("oid", claims.get("sub", "")), claims.get("name", email), email, roles, "entra")

    def public_config(self) -> dict:
        s = self._settings
        return {
            "mode": "entra",
            "roles": list(ROLES),
            "tenant_id": s.tenant_id,
            "client_id": s.client_id,
            "api_scope": s.api_scope,
        }


def build_authenticator(settings: AppAuthSettings) -> Authenticator:
    return MockAuthenticator() if settings.mock else EntraAuthenticator(settings)
