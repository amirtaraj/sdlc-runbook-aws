"""Exception hierarchy. Interfaces catch these to report errors without a stack trace."""


class RunbookError(Exception):
    """Base class for all expected runbook failures."""


class ConfigError(RunbookError):
    """Settings are missing or invalid."""


class SchemaError(RunbookError, ValueError):
    """A stage output does not match its JSON schema."""


class AgentError(RunbookError):
    """A stage call failed in a way the human needs to see."""


class ServiceError(RunbookError):
    """An external API (content safety, PII, search, DevOps) failed or is unreachable."""


class StorageError(RunbookError):
    """Saving or loading a run (e.g. DynamoDB) failed."""


class GuardrailViolation(RunbookError):
    """Input was blocked by a guardrail (PII, prompt injection, size)."""

    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class DocumentError(RunbookError):
    """An uploaded document is unsupported, too large, unreadable or empty."""


class InvalidAction(RunbookError):
    """An action was requested that the run's current state does not allow."""


class AuthError(RunbookError):
    """The caller is not signed in (401) or lacks the required role (403)."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code
