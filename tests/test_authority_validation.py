import os
import tempfile
import unittest

from legal_agent import db
from legal_agent.intake import create_case
from legal_agent.authority_validation import add_authority, verify_authority, get_verified_authorities, get_unverified_authorities


class TestAuthorityValidation(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)
        self.case_id = create_case("Authority Case", jurisdiction="California", db_path=self.temp_db.name)

    def tearDown(self):
        os.unlink(self.temp_db.name)

    def test_verify_authority(self):
        auth_id = add_authority(
            case_id=self.case_id,
            authority_type="case",
            title="Placeholder Authority",
            citation="123 P.2d 456",
            jurisdiction="California",
            court="Supreme Court",
            year=2020,
            source_url="https://example.com",
            source_text_excerpt="Excerpt from an official opinion describing the holding.",
            verified=False,
            db_path=self.temp_db.name,
        )
        self.assertEqual(auth_id, 1)
        unverified = get_unverified_authorities(1, self.temp_db.name)
        self.assertEqual(len(unverified), 1)
        self.assertFalse(unverified[0]["verified"])
        verify_authority(auth_id, True, self.temp_db.name)
        verified = get_verified_authorities(1, self.temp_db.name)
        self.assertEqual(len(verified), 1)
        self.assertTrue(verified[0]["verified"])


if __name__ == "__main__":
    unittest.main()
