import os
import tempfile
import unittest
from unittest.mock import patch

from legal_agent import db
from legal_agent.authority_validation import add_authority, list_authorities
from legal_agent.case_profile import build_case_profile
from legal_agent.drafting import save_document
from legal_agent.intake import (
    add_action_item,
    add_claim,
    add_evidence,
    add_fact,
    add_party,
    create_case,
    get_case,
    list_action_items,
    list_claims,
    list_evidence,
    list_facts,
    list_parties,
)
from legal_agent.research import add_research_log, get_research_logs


class TestPartialRecording(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)

    def tearDown(self):
        os.unlink(self.temp_db.name)

    def test_incomplete_case_profile_records_are_saved_and_itemized(self):
        case_id = create_case("", db_path=self.temp_db.name)

        add_party(case_id, "", db_path=self.temp_db.name)
        add_fact(case_id, "", date="not a formal date", db_path=self.temp_db.name)
        add_claim(case_id, "", required_elements_json="bad json", db_path=self.temp_db.name)
        add_evidence(case_id, "", supports_claims_json="claim one, claim two", db_path=self.temp_db.name)
        add_action_item(case_id, "", status="", db_path=self.temp_db.name)
        add_research_log(case_id, "", "", "", "bad ids", self.temp_db.name)
        add_authority(case_id, "", "", "", "", "", db_path=self.temp_db.name)
        db.log_audit_event(case_id, "", "", "", self.temp_db.name)
        citation_status = {
            "source": "CourtListener",
            "status": "disabled",
            "checked": False,
            "message": "CourtListener connector is disabled.",
            "results": [],
        }
        with patch("legal_agent.drafting.validate_output_citations", return_value=citation_status):
            save_document(case_id, "", self.temp_db.name)

        self.assertEqual(get_case(case_id, self.temp_db.name).title, "Untitled Case")
        self.assertEqual(list_parties(case_id, self.temp_db.name)[0].name, "Unnamed Party")
        self.assertEqual(list_facts(case_id, self.temp_db.name)[0].fact_text, "Untitled fact note")
        self.assertEqual(list_claims(case_id, self.temp_db.name)[0].claim_name, "Unspecified Claim or Defense")
        self.assertEqual(list_evidence(case_id, self.temp_db.name)[0].title, "Untitled Evidence")
        self.assertEqual(list_action_items(case_id, self.temp_db.name)[0].action_text, "Untitled Action Item")
        self.assertEqual(get_research_logs(case_id, self.temp_db.name)[0]["query"], "Untitled Research Note")
        self.assertEqual(list_authorities(case_id, self.temp_db.name)[0]["title"], "Untitled Authority")

        profile = build_case_profile(case_id, self.temp_db.name)
        item_types = {item["item_type"] for item in profile["items"]}
        self.assertTrue(
            {
                "case",
                "party",
                "fact",
                "claim_or_defense",
                "evidence",
                "action_item",
                "research_log",
                "unverified_authority",
                "audit_event",
                "document",
            }.issubset(item_types)
        )


if __name__ == "__main__":
    unittest.main()
