import json
import os
import tempfile
import unittest
from unittest.mock import patch

from legal_agent import db
from legal_agent.authority_validation import add_authority
from legal_agent.courtlistener_access import CourtListenerAccess, validate_output_citations
from legal_agent.drafting import get_document, save_document
from legal_agent.export import export_case
from legal_agent.intake import create_case
from legal_agent.resource_throttle import ResourceBudget, ThrottlingAgent, reset_throttling_agent


class FakeConnector:
    def __init__(self, response):
        self.response = response
        self.queries = []

    def lookup_citation(self, text=None, **kwargs):
        self.queries.append(text)
        return self.response

    def search_legal(self, query, court=None, **kwargs):
        self.queries.append(query)
        return self.response

    def search_dockets(self, query, court=None, **kwargs):
        self.queries.append(query)
        return self.response


class TestCourtListenerAccess(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)

    def tearDown(self):
        reset_throttling_agent(None)
        os.unlink(self.temp_db.name)

    def test_validate_output_citations_disabled_is_visible(self):
        access = CourtListenerAccess(
            FakeConnector(
                {
                    "ok": False,
                    "status": "disabled",
                    "message": "CourtListener connector is disabled.",
                    "results": [],
                }
            )
        )

        result = validate_output_citations(
            [{"id": 1, "title": "Test", "citation": "123 Cal. 456"}],
            access=access,
        )

        self.assertEqual(result["status"], "disabled")
        self.assertFalse(result["checked"])
        self.assertIn("disabled", result["message"].lower())

    def test_validate_output_citations_uses_citation_strings_only(self):
        connector = FakeConnector(
            {
                "ok": True,
                "status": "ok",
                "results": [{"title": "Smith v. Jones", "citation": "123 Cal. 456"}],
            }
        )
        access = CourtListenerAccess(connector)

        result = validate_output_citations(
            [
                {
                    "id": 1,
                    "title": "Private Matter Authority",
                    "citation": "123 Cal. 456",
                    "source_text_excerpt": "Private client facts should not be sent.",
                }
            ],
            access=access,
        )

        self.assertEqual(result["status"], "validated")
        self.assertEqual(connector.queries, ["123 Cal. 456"])

    def test_validate_output_citations_obeys_citation_check_budget(self):
        reset_throttling_agent(
            ThrottlingAgent(
                ResourceBudget(
                    citation_checks_per_run=1,
                    ai_requests_per_minute=10,
                    http_requests_per_minute=10,
                )
            )
        )
        connector = FakeConnector({"ok": True, "status": "ok", "results": [{"citation": "123 Cal. 456"}]})
        access = CourtListenerAccess(connector)

        result = validate_output_citations(
            [
                {"id": 1, "title": "First", "citation": "123 Cal. 456"},
                {"id": 2, "title": "Second", "citation": "789 Cal. 101"},
            ],
            access=access,
        )

        self.assertEqual(connector.queries, ["123 Cal. 456"])
        self.assertEqual(result["citation_count"], 2)
        self.assertEqual(result["skipped_citation_count"], 1)
        self.assertIn("deferred", result["message"])

    def test_save_document_persists_courtlistener_status(self):
        case_id = create_case("Draft Guardrail Case", jurisdiction="California", db_path=self.temp_db.name)
        add_authority(
            case_id,
            authority_type="case",
            title="Smith v. Jones",
            citation="123 Cal. 456",
            jurisdiction="California",
            court="California Supreme Court",
            year=2020,
            source_url="https://example.com",
            source_text_excerpt="Published authority excerpt long enough for verification.",
            verified=True,
            db_path=self.temp_db.name,
        )
        fake_result = {
            "source": "CourtListener",
            "status": "disabled",
            "checked": False,
            "message": "CourtListener citation guardrail was not run because the connector is disabled.",
            "results": [],
        }

        with patch("legal_agent.drafting.validate_output_citations", return_value=fake_result):
            result = save_document(case_id, "complaint", self.temp_db.name)

        document = get_document(result["document_id"], self.temp_db.name)
        verification_status = json.loads(document["verification_status"])

        self.assertEqual(result["citation_validation"]["status"], "disabled")
        self.assertEqual(verification_status["courtlistener"]["status"], "disabled")

    def test_export_includes_courtlistener_guardrail_section(self):
        case_id = create_case("Export Guardrail Case", jurisdiction="California", db_path=self.temp_db.name)
        fake_result = {
            "source": "CourtListener",
            "status": "no_citations",
            "checked": True,
            "message": "No stored verified authority citations were available for CourtListener validation.",
            "results": [],
        }

        with patch("legal_agent.export.validate_output_citations", return_value=fake_result):
            output = export_case(case_id, "markdown", db_path=self.temp_db.name)

        self.assertIn("## CourtListener Citation Guardrail", output)
        self.assertIn("Status: no_citations", output)

    def test_find_similar_cases_returns_determination_metadata(self):
        access = CourtListenerAccess(
            FakeConnector(
                {
                    "ok": True,
                    "status": "ok",
                    "results": [
                        {
                            "title": "Similar v. Case",
                            "citation": "1 Cal. 5th 1",
                            "date": "2024-01-01",
                            "absolute_url": "https://www.courtlistener.com/opinion/1/",
                            "result_type": "search",
                            "raw_metadata": {},
                        }
                    ],
                }
            )
        )

        result = access.find_similar_cases("contract damages")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["results"][0]["determination"]["determined"])

    def test_validate_presented_case_identifies_public_determination(self):
        access = CourtListenerAccess(
            FakeConnector(
                {
                    "ok": True,
                    "status": "ok",
                    "results": [
                        {
                            "title": "Determined v. Case",
                            "citation": "2 Cal. 5th 2",
                            "date": "2023-06-01",
                            "absolute_url": "https://www.courtlistener.com/opinion/2/",
                            "result_type": "citation",
                            "raw_metadata": {"date_filed": "2023-06-01"},
                        }
                    ],
                }
            )
        )

        result = access.validate_presented_case(citation="2 Cal. 5th 2")

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "public_record_with_determination")
        self.assertIn("does not prove", result["accuracy_warning"])


if __name__ == "__main__":
    unittest.main()
