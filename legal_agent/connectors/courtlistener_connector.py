from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from legal_agent.logger import get_logger
from legal_agent.resource_throttle import get_throttling_agent

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://www.courtlistener.com/api/rest/v4"
DEFAULT_TIMEOUT_SECONDS = 15
COURTLISTENER_V4_ROOT = "/api/rest/v4"
VALID_SEARCH_TYPES = {"o", "r", "rd", "d", "p", "oa"}
FULL_TEXT_KEYS = {
    "plain_text",
    "html",
    "html_lawbox",
    "html_columbia",
    "html_anon_2020",
    "html_with_citations",
    "xml_harvard",
    "extracted_by_ocr",
}


def _load_dotenv(env_path: str | Path | None = None) -> None:
    path = Path(env_path) if env_path else Path.cwd() / ".env"
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("Unable to read .env file for CourtListener configuration: %s", exc)
        return

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        if key.startswith("COURTLISTENER_") and not os.environ.get(key):
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _valid_base_url(value: str) -> bool:
    return value.startswith(("https://", "http://")) and COURTLISTENER_V4_ROOT in value


def _safe_cache_path() -> Path:
    configured = os.getenv("COURTLISTENER_CACHE_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".legal_agent" / "cache" / "courtlistener_cache.json"


class CourtListenerConnector:
    """Local-first connector for CourtListener REST API v4."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        token: str | None = None,
        base_url: str | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        cache_path: str | Path | None = None,
    ) -> None:
        _load_dotenv()
        self.enabled = _env_bool("COURTLISTENER_ENABLED", False) if enabled is None else enabled
        self.token = token if token is not None else os.getenv("COURTLISTENER_API_TOKEN", "")
        configured_base_url = (base_url or os.getenv("COURTLISTENER_BASE_URL") or DEFAULT_BASE_URL).strip()
        if not _valid_base_url(configured_base_url):
            logger.warning("Ignoring invalid CourtListener base URL; using REST API v4 default.")
            configured_base_url = DEFAULT_BASE_URL
        self.base_url = configured_base_url.rstrip("/")
        self.timeout = timeout
        self.cache_path = Path(cache_path) if cache_path else _safe_cache_path()

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "LitigationExpertAISystem/0.1",
        }
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            return self._disabled_response()
        if not self.token:
            return self._credentials_missing_response()

        method = method.upper()
        params = self._clean_params(params)
        data = self._clean_params(data)
        url = self._build_url(endpoint, params if method == "GET" else None)
        body = None
        if method != "GET" and data:
            body = urllib.parse.urlencode(data, doseq=True).encode("utf-8")

        request = urllib.request.Request(url, data=body, method=method, headers=self._headers())
        try:
            with get_throttling_agent().gate("http", metadata={"endpoint": endpoint, "method": method}):
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                    payload = json.loads(raw) if raw else {}
                    return {
                        "ok": True,
                        "status": "ok",
                        "status_code": getattr(response, "status", 200),
                        "data": payload,
                    }
        except ValueError as exc:
            logger.warning("CourtListener request throttled: %s", exc)
            return {
                "ok": False,
                "status": "throttled",
                "status_code": None,
                "source": "CourtListener",
                "message": str(exc),
                "results": [],
            }
        except urllib.error.HTTPError as exc:
            return self._http_error_response(exc)
        except TimeoutError:
            return self._timeout_response()
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                return self._timeout_response()
            logger.warning("CourtListener request failed: %s", exc)
            return {
                "ok": False,
                "status": "request_failed",
                "status_code": None,
                "message": "CourtListener request failed. Check the network connection.",
                "results": [],
            }
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("CourtListener response handling failed: %s", exc)
            return {
                "ok": False,
                "status": "invalid_response",
                "status_code": None,
                "message": "CourtListener returned a response that could not be processed.",
                "results": [],
            }

    def search_legal(
        self,
        query: str,
        court: str | None = None,
        jurisdiction: str | None = None,
        date_filed_after: str | None = None,
        date_filed_before: str | None = None,
        search_type: str = "o",
        semantic: bool = True,
        *,
        bypass_cache: bool = False,
    ) -> dict[str, Any]:
        search_type = search_type if search_type in VALID_SEARCH_TYPES else "o"
        params = {
            "q": query,
            "type": search_type,
            "court": court,
            "jurisdiction": jurisdiction,
            "filed_after": date_filed_after,
            "filed_before": date_filed_before,
        }
        if semantic and search_type == "o":
            params["semantic"] = "true"
        return self._cached_collection("GET", "/search/", params=params, result_type="search", bypass_cache=bypass_cache)

    def search_dockets(
        self,
        query: str,
        court: str | None = None,
        *,
        bypass_cache: bool = False,
    ) -> dict[str, Any]:
        params = {"docket_number": query, "court": court}
        return self._cached_collection("GET", "/dockets/", params=params, result_type="docket", bypass_cache=bypass_cache)

    def search_opinions(
        self,
        query: str,
        court: str | None = None,
        *,
        bypass_cache: bool = False,
    ) -> dict[str, Any]:
        params = {"q": query}
        if court:
            params["cluster__docket__court"] = court
        return self._cached_collection("GET", "/opinions/", params=params, result_type="opinion", bypass_cache=bypass_cache)

    def lookup_citation(
        self,
        text: str | None = None,
        volume: str | int | None = None,
        reporter: str | None = None,
        page: str | int | None = None,
        *,
        bypass_cache: bool = False,
    ) -> dict[str, Any]:
        data = {"text": text, "volume": volume, "reporter": reporter, "page": page}
        clean_data = self._clean_params(data)
        if not clean_data:
            return {
                "ok": False,
                "status": "invalid_request",
                "source": "CourtListener",
                "message": "Provide citation text or volume, reporter, and page.",
                "results": [],
            }
        cache_key = self._cache_key("POST", "/citation-lookup/", None, clean_data)
        if not bypass_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                cached["cached"] = True
                return cached

        response = self._request("POST", "/citation-lookup/", data=clean_data)
        if not response.get("ok"):
            return response
        raw_items = self._as_list(response.get("data"))
        if not raw_items:
            return {
                "ok": True,
                "status": "no_citations",
                "source": "CourtListener",
                "cached": False,
                "message": "CourtListener did not find legal citations in the submitted text.",
                "results": [],
                "raw_count": 0,
            }
        results = [self._normalize_result(item, "citation") for item in raw_items]
        statuses = [int(item.get("status", 0) or 0) for item in raw_items]
        if any(status == 429 for status in statuses):
            status = "throttled_citations"
            message = "CourtListener parsed citations, but one or more were throttled."
        elif any(status == 404 for status in statuses) or any(not result.get("match_count", 0) for result in results):
            status = "unmatched_citations"
            message = "CourtListener parsed citation text, but one or more citations had no database match."
        elif any(status == 300 for status in statuses):
            status = "ambiguous_citations"
            message = "CourtListener found multiple possible matches for at least one citation."
        else:
            status = "ok"
            message = f"CourtListener citation lookup returned {len(results)} parsed citation result(s)."
        payload = {
            "ok": True,
            "status": status,
            "source": "CourtListener",
            "cached": False,
            "message": message,
            "results": results,
            "raw_count": len(results),
        }
        self._set_cached(cache_key, payload)
        return payload

    def get_courts(self, *, bypass_cache: bool = False) -> dict[str, Any]:
        return self._cached_collection("GET", "/courts/", result_type="court", bypass_cache=bypass_cache)

    def _cached_collection(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        result_type: str = "search",
        bypass_cache: bool = False,
    ) -> dict[str, Any]:
        clean_params = self._clean_params(params)
        clean_data = self._clean_params(data)
        cache_key = self._cache_key(method, endpoint, clean_params, clean_data)
        if not bypass_cache:
            cached = self._get_cached(cache_key)
            if cached is not None:
                cached["cached"] = True
                return cached

        response = self._request(method, endpoint, params=clean_params, data=clean_data)
        if not response.get("ok"):
            return response
        raw_data = response.get("data")
        raw_results = self._extract_results(raw_data)
        results = [self._normalize_result(item, result_type) for item in raw_results]
        payload = {
            "ok": True,
            "status": "ok" if results else "no_results",
            "source": "CourtListener",
            "cached": False,
            "endpoint": endpoint,
            "request_params": clean_params,
            "message": f"CourtListener returned {len(results)} result(s).",
            "results": results,
            "raw_count": raw_data.get("count", len(results)) if isinstance(raw_data, dict) else len(results),
            "next": raw_data.get("next") if isinstance(raw_data, dict) else None,
            "previous": raw_data.get("previous") if isinstance(raw_data, dict) else None,
        }
        self._set_cached(cache_key, payload)
        return payload

    def _normalize_result(self, item: dict[str, Any], result_type: str) -> dict[str, Any]:
        citation = item.get("citation") or item.get("citations") or item.get("citation_string") or ""
        if isinstance(citation, list):
            citation = "; ".join(str(part) for part in citation)
        normalized_citations = item.get("normalized_citations")
        clusters = item.get("clusters") if isinstance(item.get("clusters"), list) else []
        first_cluster = clusters[0] if clusters and isinstance(clusters[0], dict) else {}
        title = (
            item.get("caseNameFull")
            or item.get("caseName")
            or item.get("case_name")
            or item.get("name")
            or first_cluster.get("case_name")
            or first_cluster.get("caseName")
            or str(citation)
            or "Untitled CourtListener result"
        )
        absolute_url = item.get("absolute_url") or first_cluster.get("absolute_url")
        if absolute_url and str(absolute_url).startswith("/"):
            absolute_url = f"https://www.courtlistener.com{absolute_url}"
        resource_uri = item.get("resource_uri") or first_cluster.get("resource_uri")
        return {
            "source": "CourtListener",
            "title": str(title),
            "citation": str(citation),
            "court": self._string_or_empty(item.get("court") or item.get("court_id") or first_cluster.get("court")),
            "date": self._string_or_empty(
                item.get("dateFiled")
                or item.get("date_filed")
                or item.get("dateArgued")
                or item.get("date_filed_is_approximate")
                or first_cluster.get("date_filed")
            ),
            "docket_number": self._string_or_empty(item.get("docketNumber") or item.get("docket_number") or first_cluster.get("docket_number")),
            "absolute_url": absolute_url,
            "resource_uri": resource_uri,
            "snippet": self._string_or_empty(item.get("snippet") or item.get("text") or item.get("suitNature") or item.get("error_message")),
            "result_type": result_type,
            "lookup_status": item.get("status"),
            "normalized_citations": normalized_citations if isinstance(normalized_citations, list) else [],
            "match_count": len(clusters) if result_type == "citation" else None,
            "raw_metadata": self._sanitize_metadata(item),
        }

    def _sanitize_metadata(self, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                if key in FULL_TEXT_KEYS:
                    continue
                sanitized[key] = self._sanitize_metadata(item)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize_metadata(item) for item in value]
        return value

    def _extract_results(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict):
            return self._as_list(data.get("results"))
        return self._as_list(data)

    def _as_list(self, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
        return []

    def _disabled_response(self) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "disabled",
            "source": "CourtListener",
            "message": "CourtListener connector is disabled. Set COURTLISTENER_ENABLED=true to enable it.",
            "results": [],
        }

    def _credentials_missing_response(self) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "credentials_missing",
            "source": "CourtListener",
            "message": "CourtListener API token is missing. Set COURTLISTENER_API_TOKEN in .env.",
            "results": [],
        }

    def _timeout_response(self) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "timeout",
            "source": "CourtListener",
            "message": "CourtListener request timed out. Try again later.",
            "results": [],
        }

    def _http_error_response(self, exc: urllib.error.HTTPError) -> dict[str, Any]:
        status_code = exc.code
        messages = {
            401: "CourtListener authentication failed. Check COURTLISTENER_API_TOKEN.",
            403: "CourtListener access was forbidden for this token.",
            404: "CourtListener endpoint or resource was not found.",
            429: "CourtListener rate limit reached. Try again later.",
        }
        if status_code >= 500:
            message = "CourtListener service error. Try again later."
        else:
            message = messages.get(status_code, "CourtListener API request failed.")
        logger.warning("CourtListener API error %s: %s", status_code, message)
        return {
            "ok": False,
            "status": "api_error",
            "status_code": status_code,
            "source": "CourtListener",
            "message": message,
            "results": [],
        }

    def _build_url(self, endpoint: str, params: dict[str, Any] | None = None) -> str:
        url = f"{self.base_url}/{endpoint.strip('/')}/"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
        return url

    def _clean_params(self, values: dict[str, Any] | None) -> dict[str, Any]:
        if not values:
            return {}
        cleaned: dict[str, Any] = {}
        for key, value in values.items():
            if value is None:
                continue
            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue
            cleaned[key] = value
        return cleaned

    def _cache_key(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None,
        data: dict[str, Any] | None,
    ) -> str:
        payload = {
            "method": method.upper(),
            "endpoint": endpoint.strip("/"),
            "params": self._clean_params(params),
            "data": self._clean_params(data),
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _get_cached(self, cache_key: str) -> dict[str, Any] | None:
        cache = self._read_cache()
        entry = cache.get(cache_key)
        if not isinstance(entry, dict):
            return None
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            return None
        return dict(payload)

    def _set_cached(self, cache_key: str, payload: dict[str, Any]) -> None:
        cache = self._read_cache()
        cache[cache_key] = {
            "timestamp": time.time(),
            "payload": payload,
        }
        self._write_cache(cache)

    def _read_cache(self) -> dict[str, Any]:
        try:
            if not self.cache_path.exists():
                return {}
            raw = self.cache_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Unable to read CourtListener cache: %s", exc)
            return {}

    def _write_cache(self, cache: dict[str, Any]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
        except OSError as exc:
            fallback = Path(tempfile.gettempdir()) / "legal_agent" / "courtlistener_cache.json"
            try:
                fallback.parent.mkdir(parents=True, exist_ok=True)
                fallback.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")
                self.cache_path = fallback
            except OSError:
                logger.warning("Unable to write CourtListener cache: %s", exc)

    def _string_or_empty(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return "; ".join(str(item) for item in value)
        return str(value)
