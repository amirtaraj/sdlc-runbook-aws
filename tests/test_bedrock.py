"""Bedrock client tests with a fake Converse client: no AWS account, SDK or credentials needed."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sdlc_runbook.bootstrap import SessionFactory
from sdlc_runbook.config import Settings, price_for
from sdlc_runbook.exceptions import AgentError, ConfigError
from sdlc_runbook.llm import BedrockClient

from .fakes import local_services_transport, make_settings

SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"],
          "additionalProperties": False}
MESSAGES = [
    {"role": "system", "content": "You are the requirements agent."},
    {"role": "user", "content": '{"requirement_text": "leave tracker"}'},
]


class FakeClientError(Exception):
    """Shaped like botocore's ClientError: error code in .response."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(f"An error occurred ({code}) when calling the Converse operation: {message}")
        self.response = {"Error": {"Code": code, "Message": message}}


class FakeConverse:
    def __init__(self, responses):
        self.requests = []
        self._responses = list(responses)

    def converse(self, **request):
        self.requests.append(request)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def tool_response(payload: dict, stop: str = "tool_use") -> dict:
    return {
        "output": {"message": {"role": "assistant", "content": [
            {"text": "Here you go."},
            {"toolUse": {"toolUseId": "t1", "name": "requirements_output", "input": payload}},
        ]}},
        "stopReason": stop,
        "usage": {"inputTokens": 1200, "outputTokens": 300, "totalTokens": 1500},
    }


def bedrock_settings(**overrides) -> Settings:
    return Settings(llm_provider="bedrock", aws_region="us-east-1", **overrides)


class BedrockClientTests(unittest.TestCase):
    def call(self, fake: FakeConverse, max_tokens: int = 4000, settings: Settings | None = None):
        client = BedrockClient(settings or bedrock_settings(), client=fake)
        return client.complete_json("amazon.nova-lite-v1:0", MESSAGES, "requirements_output", SCHEMA, max_tokens)

    def test_request_shape_and_result(self):
        fake = FakeConverse([tool_response({"title": "Leave Tracker"})])
        result = self.call(fake, max_tokens=8000)
        req = fake.requests[0]
        self.assertEqual(req["modelId"], "amazon.nova-lite-v1:0")
        self.assertEqual(req["system"], [{"text": "You are the requirements agent."}])
        self.assertEqual(req["messages"], [{"role": "user", "content": [{"text": MESSAGES[1]["content"]}]}])
        self.assertEqual(req["inferenceConfig"], {"maxTokens": 5000, "temperature": 0.2})  # capped for Nova
        tool = req["toolConfig"]["tools"][0]["toolSpec"]
        self.assertEqual((tool["name"], tool["inputSchema"]), ("requirements_output", {"json": SCHEMA}))
        self.assertEqual(req["toolConfig"]["toolChoice"], {"tool": {"name": "requirements_output"}})
        self.assertEqual(result.text, '{"title": "Leave Tracker"}')
        self.assertEqual((result.prompt_tokens, result.completion_tokens), (1200, 300))

    def test_output_cap_is_configurable(self):
        fake = FakeConverse([tool_response({"title": "x"})])
        self.call(fake, max_tokens=8000, settings=bedrock_settings(bedrock_max_output_tokens=8192))
        self.assertEqual(fake.requests[0]["inferenceConfig"]["maxTokens"], 8000)

    def test_falls_back_to_any_tool_when_named_tool_choice_unsupported(self):
        fake = FakeConverse([FakeClientError("ValidationException", "This model doesn't support the toolChoice.tool field"),
                             tool_response({"title": "x"})])
        self.call(fake)
        self.assertEqual(fake.requests[1]["toolConfig"]["toolChoice"], {"any": {}})

    def test_text_without_tool_call_is_passed_through_for_validation(self):
        response = {"output": {"message": {"role": "assistant", "content": [{"text": '{"title": "y"}'}]}},
                    "stopReason": "end_turn", "usage": {"inputTokens": 5, "outputTokens": 3}}
        self.assertEqual(self.call(FakeConverse([response])).text, '{"title": "y"}')

    def test_content_filter_is_an_agent_error(self):
        with self.assertRaises(AgentError) as ctx:
            self.call(FakeConverse([tool_response({}, stop="guardrail_intervened")]))
        self.assertIn("content filter", str(ctx.exception))

    def test_errors_are_mapped_to_actionable_messages(self):
        cases = {
            FakeClientError("AccessDeniedException", "not authorized"): "Enable model access",
            FakeClientError("ResourceNotFoundException", "model not found"): "Check BEDROCK_MODEL_ID",
            FakeClientError("ValidationException", "Invocation of model ID with on-demand throughput isn't supported"):
                "us.amazon.nova-lite-v1:0",
            FakeClientError("ThrottlingException", "slow down"): "Retry the stage",
            type("NoCredentialsError", (Exception,), {})("Unable to locate credentials"): "aws sso login",
        }
        for error, expected in cases.items():
            with self.assertRaises(AgentError, msg=type(error).__name__) as ctx:
                self.call(FakeConverse([error]))
            self.assertIn(expected, str(ctx.exception))


class BedrockConfigTests(unittest.TestCase):
    def from_env(self, env: dict) -> Settings:
        with mock.patch.dict(os.environ, {"MOCK_AUTH": "yes", **env}, clear=True):
            return Settings.from_env(env_file=None)

    def test_bedrock_settings(self):
        s = self.from_env({"LLM_PROVIDER": "bedrock", "AWS_REGION": "us-west-2",
                           "BEDROCK_MODEL_ID": "us.amazon.nova-micro-v1:0", "SPECIFICATION_DEPLOYMENT": "amazon.nova-pro-v1:0"})
        self.assertEqual((s.llm_provider, s.aws_region, s.default_deployment), ("bedrock", "us-west-2", "us.amazon.nova-micro-v1:0"))
        self.assertEqual(s.deployment_for("specification"), "amazon.nova-pro-v1:0")
        self.assertEqual(s.deployment_for("design"), "us.amazon.nova-micro-v1:0")
        self.assertEqual(s.resolved_auth, "aws-iam")
        self.assertIn("us-west-2", s.describe_auth())

    def test_default_model_and_required_region(self):
        self.assertEqual(self.from_env({"LLM_PROVIDER": "bedrock", "AWS_REGION": "us-east-1"}).default_deployment,
                         "amazon.nova-lite-v1:0")
        with self.assertRaises(ConfigError):
            self.from_env({"LLM_PROVIDER": "bedrock"})
        with self.assertRaises(ConfigError):
            self.from_env({"LLM_PROVIDER": "vertex"})

    def test_bedrock_ignores_azure_key_rules(self):
        s = self.from_env({"LLM_PROVIDER": "bedrock", "AWS_REGION": "us-east-1", "AZURE_OPENAI_AUTH": "key"})
        self.assertEqual(s.resolved_auth, "aws-iam")

    def test_prices_understand_inference_profiles(self):
        self.assertEqual(price_for("us.amazon.nova-lite-v1:0"), price_for("amazon.nova-lite-v1:0"))
        self.assertGreater(price_for("amazon.nova-lite-v1:0")[0], 0)
        self.assertEqual(price_for("unknown-model"), (0.0, 0.0))

    def test_factory_selects_bedrock_without_calling_aws(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp), llm_provider="bedrock", aws_region="us-east-1",
                                     default_deployment="amazon.nova-lite-v1:0")
            factory = SessionFactory(settings, transport=local_services_transport(Path(tmp)))
            self.assertIsInstance(factory.agents[0]._llm, BedrockClient)
            self.assertEqual(factory.agents[0].deployment, "amazon.nova-lite-v1:0")


if __name__ == "__main__":
    unittest.main()
