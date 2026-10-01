"""Azure OpenAI (Microsoft Foundry) implementation of LLMClient.

Auth is chosen by Settings.resolved_auth:
  key    AZURE_OPENAI_API_KEY sent as the api-key header
  entra  short-lived Entra ID tokens from DefaultAzureCredential (az login / managed identity),
         scoped to Azure AI services only; the identity needs "Cognitive Services OpenAI User"
"""
from azure.core.exceptions import ClientAuthenticationError
from openai import AuthenticationError, AzureOpenAI, BadRequestError, OpenAIError, PermissionDeniedError

from ..config import Settings
from ..exceptions import AgentError
from .base import LLMResult

_TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"


class AzureOpenAIClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client: AzureOpenAI | None = None

    def _get_client(self) -> AzureOpenAI:
        # Created lazily so unit tests and --help never touch credentials.
        if self._client is None:
            s = self._settings
            if not s.endpoint:
                raise AgentError("AZURE_OPENAI_ENDPOINT is not set. Add your Foundry endpoint to .env.")
            if s.resolved_auth == "key":
                self._client = AzureOpenAI(azure_endpoint=s.endpoint, api_key=s.api_key, api_version=s.api_version)
            else:
                from azure.identity import DefaultAzureCredential, get_bearer_token_provider

                self._client = AzureOpenAI(
                    azure_endpoint=s.endpoint,
                    azure_ad_token_provider=get_bearer_token_provider(DefaultAzureCredential(), _TOKEN_SCOPE),
                    api_version=s.api_version,
                )
        return self._client

    def _auth_hint(self) -> str:
        if self._settings.resolved_auth == "key":
            return "Check AZURE_OPENAI_API_KEY matches a key of this Foundry resource."
        return ("Run `az login`, and make sure your identity has the 'Cognitive Services OpenAI User' "
                "role on the Foundry resource (or set AZURE_OPENAI_AUTH=key).")

    def complete_json(self, deployment: str, messages: list[dict], schema_name: str, schema: dict,
                      max_tokens: int) -> LLMResult:
        try:
            resp = self._get_client().chat.completions.create(
                model=deployment,
                messages=messages,
                temperature=self._settings.temperature,
                max_tokens=min(max_tokens, self._settings.max_tokens),
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema, "strict": True},
                },
            )
        except (AuthenticationError, PermissionDeniedError, ClientAuthenticationError) as e:
            raise AgentError(
                f"Authentication with Azure OpenAI failed using {self._settings.describe_auth()}. "
                f"{self._auth_hint()} ({type(e).__name__})"
            ) from e
        except BadRequestError as e:
            if getattr(e, "code", None) == "content_filter":
                raise AgentError("Azure's content filter blocked this request.") from e
            raise AgentError(f"Azure OpenAI rejected the request to '{deployment}': {e}") from e
        except OpenAIError as e:
            raise AgentError(f"Azure OpenAI call to '{deployment}' failed: {e}") from e

        choice = resp.choices[0]
        if choice.finish_reason == "content_filter":
            raise AgentError("Azure's content filter blocked this request or its response.")
        if choice.message.refusal:
            raise AgentError(f"Model refused the request: {choice.message.refusal}")
        usage = resp.usage
        return LLMResult(
            text=choice.message.content or "",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )
