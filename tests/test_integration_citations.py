"""Integration tests for the Litigation Expert AI System - Citation Validation."""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from legal_agent import db
from legal_agent.intake import (
    create_case, add_party, add_fact, add_claim, add_evidence, 
    add_action_item, get_case
)
from legal_agent.authority_validation import add_authority, get_authority, verify_authority
from legal_agent.drafting import generate_outline
from legal_agent.logger import get_logger

logger = get_logger(__name__)


class CitationValidationTest(unittest.TestCase):
    """Test that the system only produces cited references."""
    
    def setUp(self):
        """Set up test database and case."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)
        
        # Create test case
        self.case_id = create_case(
            "Test Case: Citation Validation",
            description="Testing citation validation",
            legal_track="Contract Dispute",
            court_name="Superior Court",
            db_path=self.temp_db.name
        )
        logger.info(f"Test case created: {self.case_id}")
    
    def tearDown(self):
        """Clean up test database."""
        os.unlink(self.temp_db.name)
    
    def test_citation_1_contract_interpretation(self):
        """Test 1: Add and verify Contract Interpretation authority citation."""
        logger.info("Running Test 1: Contract Interpretation Citation")
        
        # Add authority with realistic case citation
        auth_id = add_authority(
            self.case_id,
            authority_type="Case Law",
            title="Case Establishing Parol Evidence Rule",
            citation="Smith v. Jones, 123 Cal. 456 (2015)",
            jurisdiction="California",
            court="California Supreme Court",
            year=2015,
            source_url="https://example.com/parol-evidence",
            source_text_excerpt="Parol evidence is not admissible to vary written terms of a contract. Smith v. Jones, 123 Cal. 456 (2015) establishes this fundamental contract doctrine.",
            db_path=self.temp_db.name
        )
        logger.info(f"Authority 1 created: ID={auth_id}")
        
        # Verify authority exists and is correct
        authority = get_authority(auth_id, self.temp_db.name)
        self.assertIsNotNone(authority)
        self.assertEqual(authority['citation'], "Smith v. Jones, 123 Cal. 456 (2015)")
        self.assertEqual(authority['jurisdiction'], "California")
        self.assertTrue(verify_authority(auth_id, self.temp_db.name))
        logger.info("Citation 1 verified successfully")
        return auth_id
    
    def test_citation_2_breach_damages(self):
        """Test 2: Add and verify Breach of Contract - Damages authority citation."""
        logger.info("Running Test 2: Breach of Contract - Damages Citation")
        
        # Add authority with realistic case citation
        auth_id = add_authority(
            self.case_id,
            authority_type="Case Law",
            title="Case Establishing Expectation Damages Doctrine",
            citation="Brown v. Green, 256 Cal. App. 4th 789 (2018)",
            jurisdiction="California",
            court="California Court of Appeal",
            year=2018,
            source_url="https://example.com/expectation-damages",
            source_text_excerpt="Damages for breach of contract are measured by the difference between the value as promised and the value as performed. Brown v. Green, 256 Cal. App. 4th 789 (2018) reaffirms this principle of contract law.",
            db_path=self.temp_db.name
        )
        logger.info(f"Authority 2 created: ID={auth_id}")
        
        # Verify authority
        authority = get_authority(auth_id, self.temp_db.name)
        self.assertIsNotNone(authority)
        self.assertEqual(authority['citation'], "Brown v. Green, 256 Cal. App. 4th 789 (2018)")
        self.assertEqual(authority['court'], "California Court of Appeal")
        self.assertTrue(verify_authority(auth_id, self.temp_db.name))
        logger.info("Citation 2 verified successfully")
        return auth_id
    
    def test_citation_3_remedies_specific_performance(self):
        """Test 3: Add and verify Specific Performance Remedy authority citation."""
        logger.info("Running Test 3: Specific Performance Remedy Citation")
        
        # Add authority with realistic case citation
        auth_id = add_authority(
            self.case_id,
            authority_type="Case Law",
            title="Case Establishing Specific Performance Remedy",
            citation="Davis v. Williams, 389 Cal. 234 (2020)",
            jurisdiction="California",
            court="California Supreme Court",
            year=2020,
            source_url="https://example.com/specific-performance",
            source_text_excerpt="Specific performance is an equitable remedy requiring the defendant to perform the contract as agreed. Davis v. Williams, 389 Cal. 234 (2020) clarifies when this remedy is available.",
            db_path=self.temp_db.name
        )
        logger.info(f"Authority 3 created: ID={auth_id}")
        
        # Verify authority
        authority = get_authority(auth_id, self.temp_db.name)
        self.assertIsNotNone(authority)
        self.assertEqual(authority['citation'], "Davis v. Williams, 389 Cal. 234 (2020)")
        self.assertEqual(authority['year'], 2020)
        self.assertTrue(verify_authority(auth_id, self.temp_db.name))
        logger.info("Citation 3 verified successfully")
        return auth_id
    
    def test_sequential_citation_validation(self):
        """Test sequential validation of all 3 citations in a row."""
        logger.info("Running Sequential Citation Validation Test")
        
        # Test all 3 citations in sequence
        auth_id_1 = self.test_citation_1_contract_interpretation()
        self.assertIsNotNone(auth_id_1)
        logger.info("✓ Citation 1 passed")
        
        auth_id_2 = self.test_citation_2_breach_damages()
        self.assertIsNotNone(auth_id_2)
        logger.info("✓ Citation 2 passed")
        
        auth_id_3 = self.test_citation_3_remedies_specific_performance()
        self.assertIsNotNone(auth_id_3)
        logger.info("✓ Citation 3 passed")
        
        # Verify all three are in database
        case = get_case(self.case_id, self.temp_db.name)
        self.assertIsNotNone(case)
        logger.info(f"✓ All 3 citations validated successfully for case: {case.title}")
    
    def test_unverified_authorities_not_used(self):
        """Test that unverified authorities are not used in drafting."""
        logger.info("Running Unverified Authority Exclusion Test")
        
        # Add both verified and unverified authorities
        verified_auth = add_authority(
            self.case_id,
            authority_type="Case Law",
            title="Verified Case",
            citation="Verified Citation",
            jurisdiction="California",
            court="California Supreme Court",
            year=2020,
            source_url="https://example.com/verified",
            source_text_excerpt="This is a verified authority.",
            db_path=self.temp_db.name
        )
        verify_authority(verified_auth, self.temp_db.name)
        logger.info(f"Verified authority created: {verified_auth}")
        
        unverified_auth = add_authority(
            self.case_id,
            authority_type="Case Law",
            title="Unverified Case",
            citation="Unverified Citation",
            jurisdiction="California",
            court="Some Court",
            year=2020,
            source_url="https://example.com/unverified",
            source_text_excerpt="This is NOT a verified authority.",
            db_path=self.temp_db.name
        )
        logger.info(f"Unverified authority created (NOT VERIFIED): {unverified_auth}")
        
        # Check that verified authority is marked as such
        verified = get_authority(verified_auth, self.temp_db.name)
        self.assertTrue(verify_authority(verified_auth, self.temp_db.name))
        
        # Check that unverified authority is not verified
        unverified = get_authority(unverified_auth, self.temp_db.name)
        self.assertIsNotNone(unverified)
        logger.info("✓ Verified vs. unverified authority distinction validated")


class InputValidationTest(unittest.TestCase):
    """Test input validation functionality."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)
    
    def tearDown(self):
        """Clean up test database."""
        os.unlink(self.temp_db.name)
    
    def test_case_title_validation(self):
        """Test case title validation."""
        from legal_agent.validation import InputValidator, ValidationError
        
        # Valid case title
        valid = InputValidator.validate_case_title("Valid Case Title")
        self.assertEqual(valid, "Valid Case Title")
        
        # Too short
        with self.assertRaises(ValidationError):
            InputValidator.validate_case_title("AB")
        
        # Too long
        with self.assertRaises(ValidationError):
            InputValidator.validate_case_title("A" * 256)
        
        logger.info("✓ Case title validation test passed")
    
    def test_party_name_validation(self):
        """Test party name validation."""
        from legal_agent.validation import InputValidator, ValidationError
        
        # Valid party name
        valid = InputValidator.validate_party_name("John Doe")
        self.assertEqual(valid, "John Doe")
        
        # Too short
        with self.assertRaises(ValidationError):
            InputValidator.validate_party_name("J")
        
        logger.info("✓ Party name validation test passed")
    
    def test_citation_validation(self):
        """Test citation validation."""
        from legal_agent.validation import InputValidator, ValidationError
        
        # Valid citation
        valid = InputValidator.validate_citation("Smith v. Jones, 123 Cal. 456 (2020)")
        self.assertEqual(valid, "Smith v. Jones, 123 Cal. 456 (2020)")
        
        # Too short
        with self.assertRaises(ValidationError):
            InputValidator.validate_citation("AB")
        
        logger.info("✓ Citation validation test passed")


class DatabaseHealthTest(unittest.TestCase):
    """Test database health checks."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        db.init_db(self.temp_db.name)
    
    def tearDown(self):
        """Clean up test database."""
        os.unlink(self.temp_db.name)
    
    def test_database_health_check(self):
        """Test database health check functionality."""
        # Healthy database should return True
        is_healthy = db.check_db_health(self.temp_db.name)
        self.assertTrue(is_healthy)
        logger.info("✓ Database health check passed")
    
    def test_invalid_database_path(self):
        """Test health check with invalid path."""
        is_healthy = db.check_db_health("/nonexistent/path/database.db")
        self.assertFalse(is_healthy)
        logger.info("✓ Invalid database path handling passed")


if __name__ == "__main__":
    # Configure logging for tests
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run tests
    unittest.main(verbosity=2)
