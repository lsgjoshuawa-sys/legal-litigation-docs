from __future__ import annotations
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, List, Dict, Optional
import json


class RecordAccessMixin:
    """Allow records to be used by both attribute-style and dict-style GUI code."""

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def _json_to_list(value: str | None) -> List[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return []
    except (ValueError, TypeError):
        return []


def _list_to_json(value: List[str]) -> str:
    return json.dumps(value)


def _json_to_dict(value: str | None) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
        return {}
    except (ValueError, TypeError):
        return {}


def _dict_to_json(value: Dict[str, Any]) -> str:
    return json.dumps(value)


@dataclass
class Case(RecordAccessMixin):
    id: Optional[int] = None
    title: str = ""
    description: str = ""
    legal_track: str = ""
    jurisdiction: str = ""
    court_name: str = ""
    court_level: str = ""
    district: str = ""
    judge: str = ""
    department: str = ""
    filing_status: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


@dataclass
class Party(RecordAccessMixin):
    id: Optional[int] = None
    case_id: Optional[int] = None
    name: str = ""
    role: str = ""
    type: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Fact(RecordAccessMixin):
    id: Optional[int] = None
    case_id: Optional[int] = None
    date: str = ""
    fact_text: str = ""
    source_evidence_id: Optional[int] = None
    relevance: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


@dataclass
class Claim(RecordAccessMixin):
    id: Optional[int] = None
    case_id: Optional[int] = None
    claim_name: str = ""
    claim_type: str = ""
    jurisdiction_basis: str = ""
    required_elements_json: str = "[]"
    status: str = ""
    notes: str = ""

    def required_elements(self) -> List[str]:
        return _json_to_list(self.required_elements_json)

    def set_required_elements(self, elements: List[str]) -> None:
        self.required_elements_json = _list_to_json(elements)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["required_elements"] = self.required_elements()
        return data


@dataclass
class Evidence(RecordAccessMixin):
    id: Optional[int] = None
    case_id: Optional[int] = None
    title: str = ""
    evidence_type: str = ""
    description: str = ""
    file_path: str = ""
    date_obtained: str = ""
    supports_claims_json: str = "[]"
    admissibility_notes: str = ""
    weakness_notes: str = ""

    def supports_claims(self) -> List[str]:
        return _json_to_list(self.supports_claims_json)

    def set_supports_claims(self, claims: List[str]) -> None:
        self.supports_claims_json = _list_to_json(claims)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["supports_claims"] = self.supports_claims()
        return data


@dataclass
class ActionItem(RecordAccessMixin):
    id: Optional[int] = None
    case_id: Optional[int] = None
    action_text: str = ""
    category: str = ""
    due_date: str = ""
    dependency: str = ""
    status: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Authority(RecordAccessMixin):
    id: Optional[int] = None
    case_id: Optional[int] = None
    authority_type: str = ""
    title: str = ""
    citation: str = ""
    jurisdiction: str = ""
    court: str = ""
    year: Optional[int] = None
    source_url: str = ""
    source_text_excerpt: str = ""
    treatment_status: str = "unknown"
    treatment_notes: str = ""
    verified: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data


@dataclass
class ResearchLog(RecordAccessMixin):
    id: Optional[int] = None
    case_id: Optional[int] = None
    query: str = ""
    source: str = ""
    result_summary: str = ""
    authority_ids_json: str = "[]"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def authority_ids(self) -> List[int]:
        value = _json_to_list(self.authority_ids_json)
        return [int(item) for item in value if item.isdigit()]

    def set_authority_ids(self, ids: List[int]) -> None:
        self.authority_ids_json = _list_to_json([str(id) for id in ids])

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["authority_ids"] = self.authority_ids()
        data["created_at"] = self.created_at.isoformat()
        return data


@dataclass
class Document(RecordAccessMixin):
    id: Optional[int] = None
    case_id: Optional[int] = None
    document_type: str = ""
    title: str = ""
    outline_json: str = "{}"
    draft_markdown: str = ""
    verification_status: str = ""
    vulnerability_status: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def outline(self) -> Dict[str, Any]:
        return _json_to_dict(self.outline_json)

    def set_outline(self, outline: Dict[str, Any]) -> None:
        self.outline_json = _dict_to_json(outline)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["outline"] = self.outline()
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data


@dataclass
class VulnerabilityCheck(RecordAccessMixin):
    id: Optional[int] = None
    case_id: Optional[int] = None
    document_id: Optional[int] = None
    issue_type: str = ""
    risk_level: str = ""
    description: str = ""
    supporting_authority_id: Optional[int] = None
    recommended_fix: str = ""
    resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SettingsRecord(RecordAccessMixin):
    key: str
    value: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditLogRecord(RecordAccessMixin):
    id: Optional[int] = None
    case_id: Optional[int] = None
    event_type: str = ""
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return data
