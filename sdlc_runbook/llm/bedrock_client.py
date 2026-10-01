"""Amazon Bedrock implementation of LLMClient (LLM_PROVIDER=bedrock).

Uses the Bedrock Converse API. Structured output is obtained by offering the stage schema
as the only tool and forcing the model to call it (toolChoice); the tool's input is the
stage output. If a model does not support forcing a specific tool, the client falls back
to toolChoice "any" (still the only tool). The agent validates the JSON against the schema
and re-prompts once, exactly as with Azure OpenAI.

Credentials come from the standard AWS chain (EC2 instance role, SSO or `aws configure`);
no keys are stored by the app. boto3 is imported lazily, so it is only needed for Bedrock.
"""
import json

from ..config import Settings
from ..exceptions import AgentError
from .base import LLMResult

_TOOL_DESCRIPTION = "Return the complete stage output. The input must match this JSON schema exactly."
_TRANSIENT = {"ThrottlingException", "ServiceQuotaExceededException", "ModelTimeoutException",
              "ServiceUnavailableException", "InternalServerException", "ModelNotReadyException"}


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code", "") or type(exc).__name__
    return type(exc).__name__


class BedrockClient:
    def __init__(self, settings: Settings, client=None):
        self._settings = settings
        self._client = client          # tests pass a fake with a .converse(**kwargs) method

    def _get_client(self):
        if self._client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as e:  # pragma: no cover - depends on the environment
                raise AgentError("LLM_PROVIDER=bedrock needs boto3: pip install -r requirements.txt") from e
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self._settings.aws_region,
                # Specification calls can take a while; retry throttling with backoff.
                config=Config(read_timeout=300, retries={"max_attempts": 4, "mode": "adaptive"}),
            )
        return self._client

    def complete_json(self, deployment: str, messages: list[dict], schema_name: str, schema: dict,
                      max_tokens: int) -> LLMResult:
        request = {
            "modelId": deployment,
            "system": [{"text": m["content"]} for m in messages if m["role"] == "system"],
            "messages": [{"role": m["role"], "content": [{"text": m["content"]}]}
                         for m in messages if m["role"] != "system"],
            "inferenceConfig": {
                "maxTokens": min(max_tokens, self._settings.bedrock_max_output_tokens, self._settings.max_tokens),
                "temperature": self._settings.temperature,
            },
            "toolConfig": {
                "tools": [{"toolSpec": {"name": schema_name, "description": _TOOL_DESCRIPTION,
                                        "inputSchema": {"json": schema}}}],
                "toolChoice": {"tool": {"name": schema_name}},
            },
        }
        response = self._converse(request, deployment)
        return self._to_result(response)

    def _converse(self, request: dict, deployment: str) -> dict:
        client = self._get_client()
        try:
            return client.converse(**request)
        except Exception as e:  # botocore raises ClientError subclasses; matched by error code
            code, message = _error_code(e), str(e)
            if code == "ValidationException" and "toolchoice" in message.lower():
                # This model can't be forced to a named tool; with one tool, "any" is equivalent.
                request["toolConfig"]["toolChoice"] = {"any": {}}
                try:
                    return client.converse(**request)
                except Exception as retry_error:
                    e, code, message = retry_error, _error_code(retry_error), str(retry_error)
            raise self._map_error(code, message, deployment) from e

    def _map_error(self, code: str, message: str, model: str) -> AgentError:
        region = self._settings.aws_region
        if code in ("NoCredentialsError", "PartialCredentialsError", "UnauthorizedSSOTokenError",
                    "TokenRetrievalError", "SSOTokenLoadError"):
            return AgentError("No usable AWS credentials. On EC2, attach the IAM role to the instance; "
                              "on a laptop, run `aws configure` or `aws sso login`.")
        if code == "AccessDeniedException":
            return AgentError(f"Bedrock denied access to '{model}' in {region}. Enable model access in the "
                              "Bedrock console for this region and allow bedrock:InvokeModel on it in IAM.")
        if code == "ResourceNotFoundException":
            return AgentError(f"Bedrock model '{model}' was not found in {region}. Check BEDROCK_MODEL_ID and the region.")
        if code == "ValidationException" and "on-demand throughput" in message.lower():
            return AgentError(f"'{model}' can't be called on-demand in {region}. Use its inference profile id "
                              f"instead (for example 'us.{model}').")
        if code in _TRANSIENT:
            return AgentError(f"Bedrock is busy or throttling requests ({code}). Retry the stage in a moment.")
        return AgentError(f"Bedrock call to '{model}' failed ({code}): {message[:300]}")

    @staticmethod
    def _to_result(response: dict) -> LLMResult:
        stop = response.get("stopReason")
        if stop in ("guardrail_intervened", "content_filtered"):
            raise AgentError("Bedrock blocked this request or its response (content filter).")
        content = response.get("output", {}).get("message", {}).get("content", [])
        tool_use = next((block["toolUse"] for block in content if "toolUse" in block), None)
        if tool_use is not None:
            text = json.dumps(tool_use.get("input", {}), ensure_ascii=False)
        else:
            # No tool call (unusual): pass any text through; the agent's JSON check re-prompts.
            text = "".join(block.get("text", "") for block in content)
        usage = response.get("usage", {})
        return LLMResult(text, int(usage.get("inputTokens", 0)), int(usage.get("outputTokens", 0)))
