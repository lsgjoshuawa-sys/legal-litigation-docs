import os
import tempfile
import unittest

from legal_agent import db
from legal_agent.intake import create_case, add_claim, add_evidence
from legal_agent.evidence import element_checklist, evidence_review


class TestEvidenceReview(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)
        self.case_id = create_case("Evidence Case", legal_track="A", db_path=self.temp_db.name)

    def tearDown(self):
        os.unlink(self.temp_db.name)

    def test_element_checklist(self):
        claim_id = add_claim(
            self.case_id,
            "Negligence",
            "cause of action",
            "California",
            "[\"Duty\", \"Breach\", \"Causation\", \"Damages\"]",
            db_path=self.temp_db.name,
        )
        add_evidence(
            self.case_id,
            "Police report",
            "document",
            "Contains information about breach and causation.",
            supports_claims_json='["Negligence"]',
            db_path=self.temp_db.name,
        )
        checklist = element_checklist(self.case_id, claim_id, self.temp_db.name)
        self.assertIn("Breach", checklist["supported_elements"])
        self.assertIn("Damages", checklist["missing_elements"])
        review = evidence_review(self.case_id, self.temp_db.name)
        self.assertEqual(review["case_id"], self.case_id)


if __name__ == "__main__":
    unittest.main()
