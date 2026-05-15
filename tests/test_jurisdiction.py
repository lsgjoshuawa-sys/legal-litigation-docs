import os
import tempfile
import unittest

from legal_agent import db
from legal_agent.case_tracks import TRACK_FEDERAL_EDCA
from legal_agent.intake import create_case
from legal_agent.jurisdiction import classify_case, get_procedural_rules


class TestJurisdiction(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)

    def tearDown(self):
        os.unlink(self.temp_db.name)

    def test_classify_case_by_track(self):
        case_id = create_case("Federal Mortgage", legal_track="B", court_name="Eastern District of California", db_path=self.temp_db.name)
        result = classify_case(case_id, self.temp_db.name)
        self.assertEqual(result["classification"], "Federal Eastern District of California")
        rules = get_procedural_rules(case_id, self.temp_db.name)
        self.assertIn("Federal Rules of Civil Procedure", rules["rules"])

    def test_classify_case_by_descriptive_track(self):
        case_id = create_case("Federal Matter", legal_track=TRACK_FEDERAL_EDCA, db_path=self.temp_db.name)
        result = classify_case(case_id, self.temp_db.name)

        self.assertEqual(result["classification"], "Federal Eastern District of California")
        self.assertIn("Procedure track", result["reason"])


if __name__ == "__main__":
    unittest.main()
