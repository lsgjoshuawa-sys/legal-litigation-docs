import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from legal_agent import db
from legal_agent.authority_validation import add_authority, get_authority, verify_authority
from legal_agent.intake import create_case
from legal_agent.logger import _resolve_console_log_level, _resolve_file_log_level
from legal_agent.observability import safe_context
from legal_agent.openai_client import load_dotenv, summarize_facts
import logging


class TestProductionHardening(unittest.TestCase):
    def test_verify_authority_accepts_legacy_db_path_argument(self):
        temp_db = tempfile.NamedTemporaryFile(delete=False)
        temp_db.close()
        try:
            db.init_db(temp_db.name)
            case_id = create_case("Legacy Verify Case", db_path=temp_db.name)
            authority_id = add_authority(
                case_id=case_id,
                authority_type="Case Law",
                title="Jurisdiction Optional Case",
                citation="Smith v. Jones, 123 Cal. 456 (2015)",
                jurisdiction="California",
                court="California Supreme Court",
                year=2015,
                source_url="https://example.com/opinion",
                source_text_excerpt="The court explained the controlling rule in a published opinion.",
                db_path=temp_db.name,
            )

            self.assertTrue(verify_authority(authority_id, temp_db.name))
            self.assertTrue(get_authority(authority_id, temp_db.name)["verified"])
        finally:
            os.unlink(temp_db.name)

    def test_load_dotenv_uses_standard_env_file_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(
                "OPENAI_API_KEY=test-key\n"
                "LEGAL_AGENT_OPENAI_MAX_REQUESTS_PER_MINUTE=10\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                loaded = load_dotenv(env_file)

            self.assertEqual(loaded["OPENAI_API_KEY"], "test-key")
            self.assertEqual(loaded["LEGAL_AGENT_OPENAI_MAX_REQUESTS_PER_MINUTE"], "10")

    def test_openai_client_supports_modern_sdk_shape(self):
        class FakeMessage:
            content = "Short summary."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]

        class FakeCompletions:
            def create(self, **kwargs):
                self.kwargs = kwargs
                return FakeResponse()

        class FakeChat:
            def __init__(self):
                self.completions = FakeCompletions()

        class FakeOpenAIModule:
            RateLimitError = type("RateLimitError", (Exception,), {})
            AuthenticationError = type("AuthenticationError", (Exception,), {})
            APIConnectionError = type("APIConnectionError", (Exception,), {})
            APITimeoutError = type("APITimeoutError", (Exception,), {})
            APIError = type("APIError", (Exception,), {})

            class OpenAI:
                def __init__(self, api_key):
                    self.api_key = api_key
                    self.chat = FakeChat()

        with patch("legal_agent.openai_client.openai", FakeOpenAIModule):
            result = summarize_facts("test-api-key", "Material fact text.")

        self.assertEqual(result, "Short summary.")

    def test_openai_client_is_reused_for_same_sdk_and_key(self):
        class FakeMessage:
            content = "Short summary."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]

        class FakeCompletions:
            def create(self, **kwargs):
                return FakeResponse()

        class FakeChat:
            def __init__(self):
                self.completions = FakeCompletions()

        class FakeOpenAIModule:
            created = 0
            RateLimitError = type("RateLimitError", (Exception,), {})
            AuthenticationError = type("AuthenticationError", (Exception,), {})
            APIConnectionError = type("APIConnectionError", (Exception,), {})
            APITimeoutError = type("APITimeoutError", (Exception,), {})
            APIError = type("APIError", (Exception,), {})

            class OpenAI:
                def __init__(self, api_key):
                    FakeOpenAIModule.created += 1
                    self.api_key = api_key
                    self.chat = FakeChat()

        with patch("legal_agent.openai_client.openai", FakeOpenAIModule):
            self.assertEqual(summarize_facts("same-test-api-key", "Material fact text."), "Short summary.")
            self.assertEqual(summarize_facts("same-test-api-key", "More material fact text."), "Short summary.")

        self.assertEqual(FakeOpenAIModule.created, 1)

    def test_backend_observability_redacts_sensitive_context(self):
        context = safe_context(
            {
                "api_key": "sk-test-secret",
                "legal_text": "Detailed private legal narrative",
                "case_id": 12,
                "operation": "unit_test",
            }
        )

        self.assertEqual(context["case_id"], 12)
        self.assertEqual(context["operation"], "unit_test")
        self.assertTrue(context["api_key"]["redacted"])
        self.assertTrue(context["legal_text"]["redacted"])

    def test_repeated_database_initialization_is_detected_and_skipped(self):
        temp_db = tempfile.NamedTemporaryFile(delete=False)
        temp_db.close()
        try:
            db.init_db(temp_db.name)
            with self.assertLogs("legal_agent.performance", level="WARNING") as captured:
                db.init_db(temp_db.name)
            self.assertIn("database_initialization_repeated", "\n".join(captured.output))
        finally:
            os.unlink(temp_db.name)

    def test_default_logging_is_warning_first_for_diagnostics(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_resolve_console_log_level(), logging.WARNING)
            self.assertEqual(_resolve_file_log_level(), logging.WARNING)

    def test_logging_level_can_be_enabled_for_verbose_investigation(self):
        with patch.dict(os.environ, {"LEGAL_AGENT_LOG_LEVEL": "DEBUG"}, clear=True):
            self.assertEqual(_resolve_console_log_level(), logging.DEBUG)
            self.assertEqual(_resolve_file_log_level(), logging.DEBUG)


if __name__ == "__main__":
    unittest.main()
