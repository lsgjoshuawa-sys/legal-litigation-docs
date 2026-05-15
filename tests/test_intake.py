import os
import tempfile
import unittest

from legal_agent import db
from legal_agent.case_tracks import TRACK_STATE_CIVIL
from legal_agent.intake import create_case, add_party, add_fact, add_claim, add_evidence, add_action_item, generate_timeline, get_case


class TestIntake(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)

    def tearDown(self):
        os.unlink(self.temp_db.name)

    def test_create_case_and_add_entities(self):
        case_id = create_case("Test Case", description="A test matter.", legal_track="A", court_name="Superior Court", db_path=self.temp_db.name)
        self.assertEqual(case_id, 1)
        case = get_case(case_id, self.temp_db.name)
        self.assertEqual(case.title, "Test Case")
        self.assertEqual(case.legal_track, TRACK_STATE_CIVIL)

        party_id = add_party(case_id, "Alice", "plaintiff", "individual", "Primary plaintiff", self.temp_db.name)
        self.assertEqual(party_id, 1)

        fact_id = add_fact(case_id, "A fact exists.", date="2026-05-14", relevance="material", db_path=self.temp_db.name)
        self.assertEqual(fact_id, 1)

        claim_id = add_claim(case_id, "Breach of Contract", "cause of action", "California", "[\"Offer\", \"Acceptance\"]", db_path=self.temp_db.name)
        self.assertEqual(claim_id, 1)

        evidence_id = add_evidence(case_id, "Contract", "document", "Signed agreement.", supports_claims_json='["Breach of Contract"]', db_path=self.temp_db.name)
        self.assertEqual(evidence_id, 1)

        action_id = add_action_item(case_id, "Draft complaint", "filing", due_date="2026-06-01", db_path=self.temp_db.name)
        self.assertEqual(action_id, 1)

        timeline = generate_timeline(case_id, self.temp_db.name)
        self.assertEqual(len(timeline), 1)
        self.assertEqual(timeline[0].action_text, "Draft complaint")


if __name__ == "__main__":
    unittest.main()
