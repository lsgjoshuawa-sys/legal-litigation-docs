import unittest

from legal_agent.verification import (
    validate_authority_payload,
    validate_local_rule,
    validate_procedural_deadline,
    validate_quotation,
)


class TestVerification(unittest.TestCase):
    def test_statute_citation_validation_success_and_reject(self):
        statute = {
            "authority_type": "statute",
            "citation": "Cal. Civ. Code § 3281",
            "jurisdiction": "California",
            "source_url": "https://leginfo.legislature.ca.gov",
            "source_text_excerpt": "This section describes the statute of limitations for breach of contract claims.",
            "title": "California Civil Code Section 3281",
            "year": 2024,
        }
        result = validate_authority_payload(statute, "California")
        self.assertTrue(result["citation_format"])
        self.assertTrue(result["verified_ready"])

        statute_bad = {**statute, "citation": ""}
        result_bad = validate_authority_payload(statute_bad, "California")
        self.assertFalse(result_bad["citation_format"])
        self.assertFalse(result_bad["verified_ready"])

    def test_case_citation_validation_success_and_malformed(self):
        authority = {
            "authority_type": "case",
            "citation": "Smith v. Jones 123 F.3d 456",
            "jurisdiction": "California",
            "source_url": "https://example.com/case",
            "source_text_excerpt": "The court held the statute of limitations had expired.",
            "title": "Smith v. Jones",
            "year": 2023,
        }
        result = validate_authority_payload(authority, "California")
        self.assertTrue(result["citation_format"])

        malformed = {**authority, "citation": "Smith v. Jones"}
        bad_result = validate_authority_payload(malformed, "California")
        self.assertFalse(bad_result["citation_format"])
        self.assertFalse(bad_result["verified_ready"])

    def test_rule_and_local_rule_validation(self):
        rule = {
            "authority_type": "rule",
            "citation": "Cal. Rules of Court, rule 3.740",
            "jurisdiction": "California",
            "source_url": "https://www.courts.ca.gov",
            "source_text_excerpt": "The rule governs service of process for petitions.",
            "title": "California Rules of Court rule 3.740",
            "year": 2024,
        }
        result = validate_authority_payload(rule, "California")
        self.assertTrue(result["verified_ready"])

        local_rule = {**rule, "authority_type": "local rule", "citation": "EDCA Local Rule 230"}
        local_result = validate_local_rule(local_rule, "Federal Eastern District of California")
        self.assertTrue(local_result["authority_type_valid"])

        wrong_type = {**rule, "authority_type": "statute"}
        bad_local = validate_local_rule(wrong_type, "California")
        self.assertFalse(bad_local["authority_type_valid"])

    def test_procedural_deadline_validation_incomplete_and_conflict(self):
        deadline = {
            "trigger_date": "2026-07-01",
            "rule_reference": "Cal. Civ. Proc. § 335.1",
            "description": "One-year statute of limitations for contract claims.",
            "source_url": "https://leginfo.legislature.ca.gov",
        }
        result = validate_procedural_deadline(deadline)
        self.assertTrue(result["verified_ready"])

        incomplete_deadline = {**deadline, "description": ""}
        bad_result = validate_procedural_deadline(incomplete_deadline)
        self.assertFalse(bad_result["verified_ready"])

    def test_quotation_validation_requires_source_excerpt(self):
        quotation = {
            "quote_text": "The contract was breached when the defendant failed to pay.",
            "source_text_excerpt": "This excerpt contains the exact quotation from the record.",
            "source_url": "https://example.com/record",
        }
        result = validate_quotation(quotation)
        self.assertTrue(result["verified_ready"])

        missing_excerpt = {**quotation, "source_text_excerpt": "Too short"}
        invalid_result = validate_quotation(missing_excerpt)
        self.assertFalse(invalid_result["verified_ready"])

    def test_conflicting_authority_jurisdiction_rejection(self):
        authority = {
            "authority_type": "case",
            "citation": "Smith v. Jones 123 F.3d 456",
            "jurisdiction": "New York",
            "source_url": "https://example.com/case",
            "source_text_excerpt": "A holding from the Second Circuit.",
            "title": "Smith v. Jones",
            "year": 2023,
        }
        result = validate_authority_payload(authority, "California")
        self.assertFalse(result["jurisdiction_match"])
        self.assertFalse(result["verified_ready"])


if __name__ == "__main__":
    unittest.main()
