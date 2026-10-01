import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sdlc_runbook.config import Settings
from sdlc_runbook.exceptions import ConfigError

SECRET = "fake-key-123"  # test placeholder, not a credential


def settings_from(env: dict, env_file: Path | None = None) -> Settings:
    with mock.patch.dict(os.environ, {"MOCK_AUTH": "yes", **env}, clear=True):
        return Settings.from_env(env_file=env_file)


class AuthConfigTests(unittest.TestCase):
    def test_auto_uses_entra_without_key(self):
        self.assertEqual(settings_from({}).resolved_auth, "entra")

    def test_auto_uses_key_when_present(self):
        self.assertEqual(settings_from({"AZURE_OPENAI_API_KEY": SECRET}).resolved_auth, "key")

    def test_entra_can_be_forced_even_with_a_key(self):
        s = settings_from({"AZURE_OPENAI_AUTH": "entra", "AZURE_OPENAI_API_KEY": SECRET})
        self.assertEqual(s.resolved_auth, "entra")

    def test_key_mode_without_key_is_a_config_error(self):
        with self.assertRaises(ConfigError):
            settings_from({"AZURE_OPENAI_AUTH": "key"})

    def test_unknown_mode_is_a_config_error(self):
        with self.assertRaises(ConfigError):
            settings_from({"AZURE_OPENAI_AUTH": "password"})

    def test_key_never_appears_in_repr_or_description(self):
        s = settings_from({"AZURE_OPENAI_API_KEY": SECRET})
        self.assertNotIn(SECRET, repr(s))
        self.assertNotIn(SECRET, s.describe_auth())

    def test_app_auth_defaults_to_entra_and_requires_its_settings(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(ConfigError):
            Settings.from_env(env_file=None)
        s = settings_from({"MOCK_AUTH": "no", "ENTRA_TENANT_ID": "t", "ENTRA_CLIENT_ID": "c",
                           "ENTRA_API_AUDIENCE": "api://x", "ENTRA_API_SCOPE": "api://x/Runbook.Access"})
        self.assertFalse(s.app_auth.mock)
        self.assertTrue(settings_from({}).app_auth.mock)

    def test_env_file_is_read_but_real_env_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                f'# comment\nAZURE_OPENAI_API_KEY="{SECRET}"\nAZURE_OPENAI_DEPLOYMENT=from-file\n', encoding="utf-8"
            )
            s = settings_from({"AZURE_OPENAI_DEPLOYMENT": "from-env"}, env_file=env_file)
        self.assertEqual(s.api_key, SECRET)
        self.assertEqual(s.default_deployment, "from-env")


if __name__ == "__main__":
    unittest.main()
