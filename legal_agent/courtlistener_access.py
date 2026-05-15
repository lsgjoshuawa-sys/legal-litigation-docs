from __future__ import annotations

import json
from typing import Any

from .connectors.courtlistener_connector import CourtListenerConnector
from .logger import get_logger
from .resource_throttle import get_throttling_agent

logger = get_logger(__name__)


class CourtListenerAccess:
    """Persistent access layer for CourtListener citation guardrails."""

    def __init__(self, connector: CourtListenerConnector | None = None) -> None:
        self.connector = connector or CourtListenerConnector()

    def validate_authorities(
        self,
        authorities: list[dict[str, Any]],
        *,
        bypass_cache: bool = False,
    ) -> dict[str, Any]:
        citations = self._authority_citations(authorities)
        if not citations:
            return {
                "source": "CourtListener",
                "status": "no_citations",
                "checked": True,
                "message": "No stored verified authority citations were available for CourtListener validation.",
                "results": [],
            }

        throttle = get_throttling_agent()
        original_citation_count = len(citations)
        skipped_count = max(0, original_citation_count - throttle.budget.citation_checks_per_run)
        citations = citations[: throttle.budget.citation_checks_per_run]
        results: list[dict[str, Any]] = []
        statuses: list[str] = []
        for citation in citations:
            response = self.connector.lookup_citation(text=citation["citation"], bypass_cache=bypass_cache)
            status = response.get("status", "unknown")
            statuses.append(status)
            matches = response.get("results", []) if response.get("ok") else []
            results.append(
                {
                    "authority_id": citation.get("authority_id"),
                    "title": citation.get("title"),
                    "citation": citation["citation"],
                    "status": status,
                    "checked": bool(response.get("ok")),
                    "message": response.get("message", ""),
                    "match_count": len(matches),
                    "matches": matches,
                }
            )

        if any(status == "disabled" for status in statuses):
            overall_status = "disabled"
            checked = False
            message = "CourtListener citation guardrail was not run because the connector is disabled."
        elif any(status == "credentials_missing" for status in statuses):
            overall_status = "credentials_missing"
            checked = False
            message = "CourtListener citation guardrail was not run because credentials are missing."
        elif any(not result["checked"] for result in results):
            overall_status = "incomplete"
            checked = False
            message = "CourtListener citation guardrail did not complete for every citation."
        elif any(result["match_count"] == 0 for result in results):
            overall_status = "unmatched_citations"
            checked = True
            message = "CourtListener checked citations, but one or more citations had no matches."
        else:
            overall_status = "validated"
            checked = True
            message = "CourtListener citation guardrail checked all stored verified citations."
        if skipped_count:
            message = f"{message} {skipped_count} citation(s) were deferred by the application throttle."

        return {
            "source": "CourtListener",
            "status": overall_status,
            "checked": checked,
            "message": message,
            "citation_count": original_citation_count,
            "skipped_citation_count": skipped_count,
            "results": results,
        }

    def find_similar_cases(
        self,
        query: str,
        court: str | None = None,
        *,
        limit: int = 5,
        bypass_cache: bool = False,
    ) -> dict[str, Any]:
        query = query.strip() if isinstance(query, str) else ""
        if not query:
            return {
                "source": "CourtListener",
                "ok": False,
                "status": "invalid_request",
                "message": "Provide an explicit public-law research query before searching for similar cases.",
                "results": [],
            }
        limit = max(1, min(limit, get_throttling_agent().budget.citation_checks_per_run))
        response = self.connector.search_legal(query, court=court, bypass_cache=bypass_cache)
        if not response.get("ok"):
            return response
        results = response.get("results", [])[:limit]
        return {
            "source": "CourtListener",
            "ok": True,
            "status": "ok" if results else "no_results",
            "message": f"Found {len(results)} similar public CourtListener result(s).",
            "results": [self._with_determination_status(result) for result in results],
            "query": query,
        }

    def validate_presented_case(
        self,
        *,
        citation: str | None = None,
        title: str | None = None,
        docket_number: str | None = None,
        court: str | None = None,
        bypass_cache: bool = False,
    ) -> dict[str, Any]:
        citation = citation.strip() if isinstance(citation, str) else ""
        title = title.strip() if isinstance(title, str) else ""
        docket_number = docket_number.strip() if isinstance(docket_number, str) else ""
        response: dict[str, Any]
        query_label: str
        if citation:
            response = self.connector.lookup_citation(text=citation, bypass_cache=bypass_cache)
            query_label = citation
        elif docket_number:
            response = self.connector.search_dockets(docket_number, court=court, bypass_cache=bypass_cache)
            query_label = docket_number
        elif title:
            response = self.connector.search_legal(title, court=court, bypass_cache=bypass_cache)
            query_label = title
        else:
            return {
                "source": "CourtListener",
                "ok": False,
                "status": "invalid_request",
                "message": "Provide a citation, docket number, or case title to validate.",
                "results": [],
            }

        if not response.get("ok"):
            return response
        results = [self._with_determination_status(result) for result in response.get("results", [])]
        has_public_record = bool(results)
        has_determination = any(result["determination"]["determined"] for result in results)
        if has_public_record and has_determination:
            status = "public_record_with_determination"
            message = "CourtListener found public metadata indicating the case has an indexed opinion or docket determination."
        elif has_public_record:
            status = "public_record_without_determination"
            message = "CourtListener found public metadata, but a final determination was not confirmed from metadata."
        else:
            status = "no_public_record_match"
            message = "CourtListener did not return a public metadata match for the presented case."
        return {
            "source": "CourtListener",
            "ok": True,
            "status": status,
            "checked": True,
            "query": query_label,
            "message": message,
            "validation_scope": "Public metadata, citations, docket fields, and indexed opinion references only.",
            "accuracy_warning": "This does not prove that a user's factual narrative matches actual events; compare against the official opinion, docket, and record before relying on it.",
            "results": results,
        }

    def status_for_document(self, authorities: list[dict[str, Any]]) -> str:
        return json.dumps(self.validate_authorities(authorities), sort_keys=True)

    def _authority_citations(self, authorities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        seen: set[str] = set()
        for authority in authorities:
            citation = str(authority.get("citation") or "").strip()
            if not citation or citation in seen:
                continue
            seen.add(citation)
            citations.append(
                {
                    "authority_id": authority.get("id"),
                    "title": authority.get("title", ""),
                    "citation": citation,
                }
            )
        return citations

    def _with_determination_status(self, result: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(result)
        enriched["determination"] = self._determination_status(result)
        return enriched

    def _determination_status(self, result: dict[str, Any]) -> dict[str, Any]:
        metadata = result.get("raw_metadata") if isinstance(result.get("raw_metadata"), dict) else {}
        result_type = str(result.get("result_type") or "")
        fields = {
            "date": result.get("date") or metadata.get("date_filed") or metadata.get("dateFiled"),
            "date_terminated": metadata.get("date_terminated") or metadata.get("dateTerminated"),
            "disposition": metadata.get("disposition") or metadata.get("procedural_history"),
            "absolute_url": result.get("absolute_url") or metadata.get("absolute_url"),
            "resource_uri": result.get("resource_uri") or metadata.get("resource_uri"),
            "citation": result.get("citation"),
        }
        if fields["date_terminated"]:
            reason = "Docket metadata includes a termination date."
            determined = True
        elif result_type in {"citation", "opinion", "search"} and (fields["citation"] or fields["absolute_url"]) and fields["date"]:
            reason = "CourtListener returned indexed opinion/citation metadata with a filed date."
            determined = True
        elif fields["disposition"]:
            reason = "CourtListener metadata includes a disposition field."
            determined = True
        else:
            reason = "No final disposition, termination date, or indexed opinion marker was confirmed from metadata."
            determined = False
        return {
            "determined": determined,
            "reason": reason,
            "fields": {key: value for key, value in fields.items() if value},
        }


_ACCESS: CourtListenerAccess | None = None


def get_courtlistener_access() -> CourtListenerAccess:
    global _ACCESS
    if _ACCESS is None:
        _ACCESS = CourtListenerAccess()
    return _ACCESS


def validate_output_citations(
    authorities: list[dict[str, Any]],
    *,
    access: CourtListenerAccess | None = None,
    bypass_cache: bool = False,
) -> dict[str, Any]:
    validator = access or get_courtlistener_access()
    try:
        return validator.validate_authorities(authorities, bypass_cache=bypass_cache)
    except Exception as exc:
        logger.exception("CourtListener output citation validation failed")
        return {
            "source": "CourtListener",
            "status": "error",
            "checked": False,
            "message": f"CourtListener citation validation failed: {str(exc)[:200]}",
            "results": [],
        }
