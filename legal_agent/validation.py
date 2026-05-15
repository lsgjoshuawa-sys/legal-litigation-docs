"""Input validation utilities for the GUI and CLI."""

import re
from typing import Any, Dict, List, Optional, Tuple


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


class InputValidator:
    """Validate user inputs for the application."""
    
    # Regex patterns
    CITATION_PATTERN = re.compile(r'^[A-Za-z0-9\s\.,()]+$')
    URL_PATTERN = re.compile(r'^https?://[^\s]+$')
    DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    
    @staticmethod
    def validate_case_title(title: str) -> str:
        """Validate and sanitize case title."""
        if not title or not isinstance(title, str):
            raise ValidationError("Case title is required and must be text")
        title = title.strip()
        if len(title) < 3:
            raise ValidationError("Case title must be at least 3 characters")
        if len(title) > 255:
            raise ValidationError("Case title must not exceed 255 characters")
        return title
    
    @staticmethod
    def validate_party_name(name: str) -> str:
        """Validate and sanitize party name."""
        if not name or not isinstance(name, str):
            raise ValidationError("Party name is required and must be text")
        name = name.strip()
        if len(name) < 2:
            raise ValidationError("Party name must be at least 2 characters")
        if len(name) > 255:
            raise ValidationError("Party name must not exceed 255 characters")
        return name
    
    @staticmethod
    def validate_fact_text(text: str) -> str:
        """Validate and sanitize fact text."""
        if not text or not isinstance(text, str):
            raise ValidationError("Fact text is required and must be text")
        text = text.strip()
        if len(text) < 10:
            raise ValidationError("Fact must be at least 10 characters")
        if len(text) > 5000:
            raise ValidationError("Fact must not exceed 5000 characters")
        return text
    
    @staticmethod
    def validate_citation(citation: str) -> str:
        """Validate and sanitize legal citation."""
        if not citation or not isinstance(citation, str):
            raise ValidationError("Citation is required and must be text")
        citation = citation.strip()
        if len(citation) < 3:
            raise ValidationError("Citation must be at least 3 characters")
        if len(citation) > 500:
            raise ValidationError("Citation must not exceed 500 characters")
        if not InputValidator.CITATION_PATTERN.match(citation):
            raise ValidationError("Citation contains invalid characters")
        return citation
    
    @staticmethod
    def validate_url(url: str) -> str:
        """Validate URL format."""
        if not url:
            return ""  # Optional field
        if not isinstance(url, str):
            raise ValidationError("URL must be text")
        url = url.strip()
        if len(url) > 2048:
            raise ValidationError("URL must not exceed 2048 characters")
        if not InputValidator.URL_PATTERN.match(url):
            raise ValidationError("Invalid URL format. Must start with http:// or https://")
        return url
    
    @staticmethod
    def validate_date(date_str: str) -> str:
        """Validate date format (YYYY-MM-DD)."""
        if not date_str:
            return ""  # Optional field
        if not isinstance(date_str, str):
            raise ValidationError("Date must be text")
        if not InputValidator.DATE_PATTERN.match(date_str):
            raise ValidationError("Date must be in YYYY-MM-DD format")
        # Validate actual date values
        try:
            from datetime import datetime
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str
        except ValueError:
            raise ValidationError("Invalid date value")
    
    @staticmethod
    def validate_claim_name(name: str) -> str:
        """Validate claim name."""
        if not name or not isinstance(name, str):
            raise ValidationError("Claim name is required and must be text")
        name = name.strip()
        if len(name) < 5:
            raise ValidationError("Claim name must be at least 5 characters")
        if len(name) > 255:
            raise ValidationError("Claim name must not exceed 255 characters")
        return name
    
    @staticmethod
    def validate_evidence_title(title: str) -> str:
        """Validate evidence title."""
        if not title or not isinstance(title, str):
            raise ValidationError("Evidence title is required and must be text")
        title = title.strip()
        if len(title) < 3:
            raise ValidationError("Evidence title must be at least 3 characters")
        if len(title) > 255:
            raise ValidationError("Evidence title must not exceed 255 characters")
        return title
    
    @staticmethod
    def validate_action_text(text: str) -> str:
        """Validate action item text."""
        if not text or not isinstance(text, str):
            raise ValidationError("Action text is required and must be text")
        text = text.strip()
        if len(text) < 5:
            raise ValidationError("Action text must be at least 5 characters")
        if len(text) > 1000:
            raise ValidationError("Action text must not exceed 1000 characters")
        return text
    
    @staticmethod
    def validate_form_data(data: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
        """Validate form data completeness."""
        missing_fields = [f for f in required_fields if not data.get(f)]
        if missing_fields:
            raise ValidationError(f"Missing required fields: {', '.join(missing_fields)}")
        return data
