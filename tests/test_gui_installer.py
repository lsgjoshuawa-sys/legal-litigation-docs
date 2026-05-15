import tempfile
import unittest
from pathlib import Path

from scripts.gui_installer import parse_env_file, update_env_file, valid_openai_key


class GuiInstallerHelperTest(unittest.TestCase):
    def test_update_env_file_preserves_existing_values_and_adds_required_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "# Existing config\n"
                "OPENAI_API_KEY=old-key\n"
                "COURTLISTENER_ENABLED=false\n"
                "UNRELATED=value\n",
                encoding="utf-8",
            )

            update_env_file(
                env_path,
                {
                    "OPENAI_API_KEY": "sk-test-new",
                    "LEGAL_AGENT_OPENAI_MODEL": "gpt-4o-mini",
                    "COURTLISTENER_ENABLED": "true",
                },
            )

            loaded = parse_env_file(env_path)
            self.assertEqual(loaded["OPENAI_API_KEY"], "sk-test-new")
            self.assertEqual(loaded["LEGAL_AGENT_OPENAI_MODEL"], "gpt-4o-mini")
            self.assertEqual(loaded["COURTLISTENER_ENABLED"], "true")
            self.assertEqual(loaded["UNRELATED"], "value")

    def test_openai_key_validation_rejects_missing_placeholder_and_whitespace(self):
        self.assertFalse(valid_openai_key(""))
        self.assertFalse(valid_openai_key("your_openai_api_key_here"))
        self.assertFalse(valid_openai_key("sk-test bad"))
        self.assertTrue(valid_openai_key("sk-test-good"))


if __name__ == "__main__":
    unittest.main()

