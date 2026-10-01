"""Runtime settings, read once from environment variables (and an optional .env file).

Real environment variables always win over values in .env. See .env.example for every
variable. Groups:

  Model provider   LLM_PROVIDER              azure (default) | bedrock
  Azure OpenAI     AZURE_OPENAI_*            model endpoint, deployment, auth (key | entra | auto)
  Amazon Bedrock   AWS_REGION, BEDROCK_*     region, model id, output cap (auth: AWS credential chain)
  Saved runs       RUN_STORE, DYNAMODB_TABLE memory (default) | dynamodb
  App auth         MOCK_AUTH, ENTRA_*        MOCK_AUTH=yes -> mock sign-in, otherwise Entra ID
  External APIs    CONTENT_SAFETY_*, LANGUAGE_*, SEARCH_*, DEVOPS_*
                   default to the custom local services (local_services/, no Azure cost).
                   Each speaks the real Azure API contract, so moving one to Azure later
                   is an endpoint + key change only.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .exceptions import ConfigError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
# Stages that accept a <STAGE>_DEPLOYMENT override; the stage list itself comes from RUNBOOK.md.
STAGES = ("classification", "discovery", "requirements", "feasibility", "impact", "design", "tasks",
          "specification", "build_test")
LOCAL_SERVICES_URL = "http://127.0.0.1:8001"

AuthMode = Literal["auto", "key", "entra"]
AUTH_MODES: tuple[AuthMode, ...] = ("auto", "key", "entra")
Provider = Literal["azure", "bedrock"]
PROVIDERS: tuple[Provider, ...] = ("azure", "bedrock")
DEFAULT_BEDROCK_MODEL = "amazon.nova-lite-v1:0"

# USD per 1M tokens (input, output), for the cost estimate in metrics only. Approximate list
# prices (Azure Global Standard; Bedrock on-demand, US regions). Update when prices change.
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o-mini": (0.15, 0.60),
    "amazon.nova-micro-v1:0": (0.035, 0.14),
    "amazon.nova-lite-v1:0": (0.06, 0.24),
    "amazon.nova-pro-v1:0": (0.80, 3.20),
    "anthropic.claude-3-haiku-20240307-v1:0": (0.25, 1.25),
    "anthropic.claude-3-5-haiku-20241022-v1:0": (0.80, 4.00),
}

# Bedrock cross-region inference profile ids prefix the model id with a geography.
_PROFILE_PREFIXES = ("us.", "eu.", "apac.", "global.", "us-gov.", "jp.", "au.", "ca.")


def price_for(model: str) -> tuple[float, float]:
    """(input, output) USD per 1M tokens; inference-profile ids priced as their base model."""
    for prefix in _PROFILE_PREFIXES:
        if model.startswith(prefix):
            model = model[len(prefix):]
            break
    return MODEL_PRICES.get(model, (0.0, 0.0))


def load_env_file(path: Path = ENV_FILE) -> None:
    """Minimal .env reader (KEY=VALUE lines, # comments). Never overrides real env vars."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


def _flag(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    return default if not value else value in ("1", "true", "yes", "y", "on")


@dataclass(frozen=True)
class ServiceEndpoint:
    """One external REST API: base URL + key. The key never appears in repr()."""

    endpoint: str
    api_key: str | None = field(default=None, repr=False)

    @property
    def is_local(self) -> bool:
        return self.endpoint.rstrip("/").startswith(LOCAL_SERVICES_URL)


@dataclass(frozen=True)
class AppAuthSettings:
    """How users of the web app sign in. mock=True is for local development only."""

    mock: bool = True
    tenant_id: str = ""
    client_id: str = ""        # the SPA app registration (used by the browser)
    api_audience: str = ""     # expected `aud` of access tokens, e.g. api://<api-client-id>
    api_scope: str = ""        # scope the SPA requests, e.g. api://<api-client-id>/Runbook.Access

    def validate(self) -> None:
        if self.mock:
            return
        missing = [n for n, v in (("ENTRA_TENANT_ID", self.tenant_id), ("ENTRA_CLIENT_ID", self.client_id),
                                  ("ENTRA_API_AUDIENCE", self.api_audience), ("ENTRA_API_SCOPE", self.api_scope)) if not v]
        if missing:
            raise ConfigError(f"MOCK_AUTH is off, so Entra ID sign-in needs: {', '.join(missing)}.")


@dataclass(frozen=True)
class Settings:
    # ---- Model provider ----
    llm_provider: Provider = "azure"

    # ---- Amazon Bedrock (LLM_PROVIDER=bedrock) ----
    aws_region: str = ""
    # Bedrock models have per-model output limits (Amazon Nova: 5,000 tokens); stage limits
    # from RUNBOOK.md are capped at this value.
    bedrock_max_output_tokens: int = 5000

    # ---- Where runs are saved (RUN_STORE) ----
    run_store: str = "memory"           # memory | dynamodb
    dynamodb_table: str = ""

    # ---- Azure OpenAI (LLM_PROVIDER=azure) ----
    endpoint: str = ""          # AZURE_OPENAI_ENDPOINT, e.g. https://<resource>.cognitiveservices.azure.com/
    api_version: str = "2024-10-21"
    auth_mode: AuthMode = "auto"
    # repr=False keeps the key out of logs, tracebacks and debug prints.
    api_key: str | None = field(default=None, repr=False)
    default_deployment: str = "gpt-4.1-nano"
    stage_deployments: dict[str, str] = field(default_factory=dict)
    temperature: float = 0.2
    max_tokens: int = 16000     # hard ceiling; each stage's own limit comes from RUNBOOK.md

    # ---- App sign-in ----
    app_auth: AppAuthSettings = field(default_factory=AppAuthSettings)

    # ---- External APIs (custom local services by default) ----
    content_safety: ServiceEndpoint = field(default_factory=lambda: ServiceEndpoint(LOCAL_SERVICES_URL))
    language: ServiceEndpoint = field(default_factory=lambda: ServiceEndpoint(LOCAL_SERVICES_URL))
    search: ServiceEndpoint = field(default_factory=lambda: ServiceEndpoint(LOCAL_SERVICES_URL))
    search_index: str = "engineering-standards"
    devops: ServiceEndpoint = field(default_factory=lambda: ServiceEndpoint(f"{LOCAL_SERVICES_URL}/devops/demo-org"))
    devops_project: str = "sdlc-runbook"
    service_timeout_seconds: float = 10.0

    # ---- Files ----
    trace_log_path: Path = PROJECT_ROOT / "trace_log.jsonl"
    audit_log_path: Path = LOG_DIR / "audit_log.jsonl"
    llm_calls_log_path: Path = LOG_DIR / "llm_calls.jsonl"
    output_dir: Path = PROJECT_ROOT / "output"
    estimates_dataset_path: Path = DATA_DIR / "datasets" / "historical_tasks.csv"
    runbook_path: Path = PROJECT_ROOT / "runbook" / "RUNBOOK.md"
    tech_stacks_path: Path = DATA_DIR / "tech_stacks.json"

    def __post_init__(self):
        if self.llm_provider not in PROVIDERS:
            raise ConfigError(f"LLM_PROVIDER must be one of {', '.join(PROVIDERS)} (got {self.llm_provider!r}).")
        if self.llm_provider == "bedrock":
            if not self.aws_region:
                raise ConfigError("LLM_PROVIDER=bedrock needs AWS_REGION (the region where the model is enabled).")
        else:
            if self.auth_mode not in AUTH_MODES:
                raise ConfigError(f"AZURE_OPENAI_AUTH must be one of {', '.join(AUTH_MODES)} (got {self.auth_mode!r}).")
            if self.auth_mode == "key" and not self.api_key:
                raise ConfigError("AZURE_OPENAI_AUTH=key but AZURE_OPENAI_API_KEY is not set.")
        if self.run_store not in ("memory", "dynamodb"):
            raise ConfigError(f"RUN_STORE must be memory or dynamodb (got {self.run_store!r}).")
        if self.run_store == "dynamodb" and not (self.dynamodb_table and self.aws_region):
            raise ConfigError("RUN_STORE=dynamodb needs DYNAMODB_TABLE and AWS_REGION.")
        self.app_auth.validate()

    @classmethod
    def from_env(cls, env_file: Path | None = ENV_FILE) -> "Settings":
        if env_file:
            load_env_file(env_file)
        d = cls.__dataclass_fields__
        overrides = {s: _env(f"{s.upper()}_DEPLOYMENT") for s in STAGES if _env(f"{s.upper()}_DEPLOYMENT")}

        def service(prefix: str, default: str) -> ServiceEndpoint:
            return ServiceEndpoint(_env(f"{prefix}_ENDPOINT", default), _env(f"{prefix}_KEY") or None)

        provider = _env("LLM_PROVIDER", "azure").lower()
        if provider == "bedrock":
            default_model = _env("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL)
        else:
            default_model = _env("AZURE_OPENAI_DEPLOYMENT", d["default_deployment"].default)

        return cls(
            llm_provider=provider,
            aws_region=_env("AWS_REGION") or _env("AWS_DEFAULT_REGION"),
            bedrock_max_output_tokens=int(_env("BEDROCK_MAX_OUTPUT_TOKENS", "5000")),
            run_store=_env("RUN_STORE", "memory").lower(),
            dynamodb_table=_env("DYNAMODB_TABLE"),
            endpoint=_env("AZURE_OPENAI_ENDPOINT", d["endpoint"].default),
            api_version=_env("AZURE_OPENAI_API_VERSION", d["api_version"].default),
            auth_mode=_env("AZURE_OPENAI_AUTH", "auto").lower(),
            api_key=_env("AZURE_OPENAI_API_KEY") or None,
            default_deployment=default_model,
            stage_deployments=overrides,
            app_auth=AppAuthSettings(
                mock=_flag("MOCK_AUTH", default=False),
                tenant_id=_env("ENTRA_TENANT_ID"),
                client_id=_env("ENTRA_CLIENT_ID"),
                api_audience=_env("ENTRA_API_AUDIENCE"),
                api_scope=_env("ENTRA_API_SCOPE"),
            ),
            content_safety=service("CONTENT_SAFETY", LOCAL_SERVICES_URL),
            language=service("LANGUAGE", LOCAL_SERVICES_URL),
            search=service("SEARCH", LOCAL_SERVICES_URL),
            search_index=_env("SEARCH_INDEX", d["search_index"].default),
            devops=ServiceEndpoint(_env("DEVOPS_ORG_URL", f"{LOCAL_SERVICES_URL}/devops/demo-org"), _env("DEVOPS_PAT") or None),
            devops_project=_env("DEVOPS_PROJECT", d["devops_project"].default),
        )

    @property
    def resolved_auth(self) -> Literal["key", "entra", "aws-iam"]:
        if self.llm_provider == "bedrock":
            return "aws-iam"
        if self.auth_mode == "auto":
            return "key" if self.api_key else "entra"
        return self.auth_mode

    def describe_auth(self) -> str:
        """Human-readable auth method, safe to print (never includes the key)."""
        if self.resolved_auth == "aws-iam":
            return f"AWS credentials (IAM role / SSO / aws configure), Bedrock in {self.aws_region}"
        if self.resolved_auth == "key":
            return "API key (AZURE_OPENAI_API_KEY)"
        return "Entra ID (DefaultAzureCredential: az login / managed identity)"

    def deployment_for(self, stage: str) -> str:
        return self.stage_deployments.get(stage, self.default_deployment)
