import os
import tempfile
import unittest
from unittest.mock import patch

from legal_agent import db
from legal_agent.ai_analysis import generate_argument_analysis
from legal_agent.authority_validation import add_authority
from legal_agent.intake import add_claim, add_evidence, create_case


class TestAIAnalysis(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)
        self.case_id = create_case("AI Layer Case", description="Stored facts only.", db_path=self.temp_db.name)
        add_claim(self.case_id, "Negligence", "defense", notes="Challenge causation.", db_path=self.temp_db.name)
        add_evidence(self.case_id, "Camera footage", "video", "Shows disputed timeline.", db_path=self.temp_db.name)
        add_authority(
            self.case_id,
            "case",
            "Example v. Authority",
            "123 Cal. App. 5th 456",
            "California",
            "Court of Appeal",
            year=2024,
            source_text_excerpt="A published authority excerpt long enough to support local review.",
            verified=True,
            db_path=self.temp_db.name,
        )

    def tearDown(self):
        os.unlink(self.temp_db.name)

    def test_local_ai_analysis_is_accessible_without_api_key(self):
        citation_status = {
            "source": "CourtListener",
            "status": "disabled",
            "checked": False,
            "message": "CourtListener connector is disabled.",
            "results": [],
        }

        with patch("legal_agent.ai_analysis.get_stored_api_key", return_value=None):
            with patch("legal_agent.ai_analysis.validate_output_citations", return_value=citation_status):
                result = generate_argument_analysis(self.case_id, self.temp_db.name)

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "local")
        self.assertIn("Negligence", result["analysis"])
        self.assertIn("No system can guarantee less than 1% doubt", result["analysis"])
        self.assertIn("profile", result)

    def test_openai_ai_analysis_receives_case_profile_context(self):
        citation_status = {
            "source": "CourtListener",
            "status": "validated",
            "checked": True,
            "message": "Citation validated.",
            "results": [],
        }

        with patch("legal_agent.ai_analysis.get_stored_api_key", return_value="sk-test"):
            with patch("legal_agent.ai_analysis.validate_output_citations", return_value=citation_status):
                with patch("legal_agent.ai_analysis.analyze_text", return_value="Generated workup") as analyze_text:
                    result = generate_argument_analysis(self.case_id, self.temp_db.name)

        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "openai")
        self.assertEqual(result["analysis"], "Generated workup")
        analyze_text.assert_called_once()
        _, context, instructions = analyze_text.call_args.args
        self.assertIn("Camera footage", context)
        self.assertIn("Example v. Authority", context)
        self.assertIn("Do not invent citations", instructions)


if __name__ == "__main__":
    unittest.main()
