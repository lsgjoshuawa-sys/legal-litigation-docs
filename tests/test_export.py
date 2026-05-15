import os
import tempfile
import unittest

from legal_agent import db
from legal_agent.intake import create_case, add_action_item
from legal_agent.authority_validation import add_authority, verify_authority
from legal_agent.export import export_case


class TestExport(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)
        self.case_id = create_case("Export Case", legal_track="A", db_path=self.temp_db.name)

    def tearDown(self):
        os.unlink(self.temp_db.name)

    def test_export_markdown_and_json(self):
        add_action_item(self.case_id, "Review pleadings", "review", due_date="2026-05-20", db_path=self.temp_db.name)
        auth_id = add_authority(
            case_id=self.case_id,
            authority_type="statute",
            title="California Code of Civil Procedure section",
            citation="Cal. Civ. Proc. Code § 425.16",
            jurisdiction="California",
            court="",
            year=2026,
            source_url="https://leginfo.legislature.ca.gov",
            source_text_excerpt="Anti-SLAPP statute",
            verified=True,
            db_path=self.temp_db.name,
        )
        self.assertEqual(auth_id, 1)
        markdown = export_case(self.case_id, "markdown", db_path=self.temp_db.name)
        self.assertIn("## Case Summary", markdown)
        json_output = export_case(self.case_id, "json", db_path=self.temp_db.name)
        self.assertIn("\"case\"", json_output)


if __name__ == "__main__":
    unittest.main()
