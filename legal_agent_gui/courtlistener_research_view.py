from __future__ import annotations

import json
import re
from typing import Any

from PySide6 import QtCore, QtWidgets

from legal_agent.courtlistener_access import CourtListenerAccess
from legal_agent.connectors.courtlistener_connector import CourtListenerConnector
from legal_agent.research import add_research_log
from .widgets import BaseView


COURTLISTENER_COURT_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,40}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COURTLISTENER_LOCATION_PRESETS = {
    "Custom / all courts": ("", ""),
    "Sacramento / Eastern District of California": ("Sacramento California", "caed, ca9, cal, calctapp3d"),
    "California state and federal courts": (
        "California",
        "cal, calctapp1d, calctapp2d, calctapp3d, calctapp4d, calctapp5d, calctapp6d, ca9, cacd, caed, cand, casd",
    ),
    "California federal courts": ("California federal", "ca9, cacd, caed, cand, casd"),
    "Ninth Circuit": ("Ninth Circuit", "ca9"),
    "U.S. Supreme Court": ("United States Supreme Court", "scotus"),
}
SEARCH_TYPES = {
    "Case law opinions": "o",
    "Federal cases with documents": "r",
    "Federal docket metadata": "d",
    "Federal filing documents": "rd",
    "Judges": "p",
    "Oral arguments": "oa",
}
SEARCH_STATUSES = {
    "Default published opinions": "",
    "Published / precedential": "published",
    "Unpublished": "unpublished",
    "Errata": "errata",
    "Separate opinion": "separate",
    "In chambers": "in-chambers",
    "Relating to orders": "relating-to",
    "Unknown status": "unknown",
}


class CourtListenerResearchView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__(
            "CourtListener Research",
            "Run explicit CourtListener REST API research queries and citation checks.",
        )
        self.db_path = db_path
        self.case_id: int | None = None
        self.results: list[dict[str, Any]] = []

        self.query_input = QtWidgets.QTextEdit()
        self.query_input.setPlaceholderText("Legal issue or research question, e.g. minimal evidence for street racing citation.")
        self.query_input.setMaximumHeight(120)

        self.location_preset_input = QtWidgets.QComboBox()
        self.location_preset_input.addItems(list(COURTLISTENER_LOCATION_PRESETS.keys()))
        self.location_input = QtWidgets.QLineEdit()
        self.location_input.setPlaceholderText("City, county, state, or regional terms, e.g. Sacramento California")
        self.court_ids_input = QtWidgets.QLineEdit()
        self.court_ids_input.setPlaceholderText("CourtListener IDs, comma-separated, e.g. caed, ca9, cal")
        self.court_input = self.court_ids_input
        self.statute_input = QtWidgets.QLineEdit()
        self.statute_input.setPlaceholderText("Statute or citation terms, e.g. Cal. Veh. Code 23109(a)")
        self.required_terms_input = QtWidgets.QLineEdit()
        self.required_terms_input.setPlaceholderText("Must-include terms, comma-separated")
        self.exclude_terms_input = QtWidgets.QLineEdit()
        self.exclude_terms_input.setPlaceholderText("Terms to exclude, comma-separated")
        self.date_after_input = QtWidgets.QLineEdit()
        self.date_after_input.setPlaceholderText("YYYY-MM-DD")
        self.date_before_input = QtWidgets.QLineEdit()
        self.date_before_input.setPlaceholderText("YYYY-MM-DD")
        self.status_input = QtWidgets.QComboBox()
        self.status_input.addItems(list(SEARCH_STATUSES.keys()))
        self.search_type_input = QtWidgets.QComboBox()
        self.search_type_input.addItems(list(SEARCH_TYPES.keys()))
        self.search_mode_input = QtWidgets.QComboBox()
        self.search_mode_input.addItems(["Keyword / Boolean search", "Semantic natural-language search"])
        self.query_preview = QtWidgets.QPlainTextEdit()
        self.query_preview.setReadOnly(True)
        self.query_preview.setMaximumHeight(95)
        self.query_preview.setPlaceholderText("Built CourtListener query preview")

        form = QtWidgets.QFormLayout()
        form.addRow("Legal issue / citation text:", self.query_input)
        form.addRow("Location preset:", self.location_preset_input)
        form.addRow("Location terms:", self.location_input)
        form.addRow("Court IDs:", self.court_ids_input)
        form.addRow("Statute / code section:", self.statute_input)
        form.addRow("Required terms:", self.required_terms_input)
        form.addRow("Exclude terms:", self.exclude_terms_input)
        form.addRow("Filed after:", self.date_after_input)
        form.addRow("Filed before:", self.date_before_input)
        form.addRow("Precedential status:", self.status_input)
        form.addRow("CourtListener data type:", self.search_type_input)
        form.addRow("Search mode:", self.search_mode_input)
        form.addRow("Query preview:", self.query_preview)
        self.layout.addLayout(form)

        self.search_button = QtWidgets.QPushButton("Search CourtListener")
        self.citation_button = QtWidgets.QPushButton("Citation Lookup")
        self.similar_button = QtWidgets.QPushButton("Find Similar Cases")
        self.validate_button = QtWidgets.QPushButton("Validate Determined Case")
        self.save_button = QtWidgets.QPushButton("Save to Matter Notes")
        self.search_button.clicked.connect(self._search)
        self.citation_button.clicked.connect(self._lookup_citation)
        self.similar_button.clicked.connect(self._find_similar_cases)
        self.validate_button.clicked.connect(self._validate_determined_case)
        self.save_button.clicked.connect(self._save_selected)

        self.button_bar = QtWidgets.QHBoxLayout()
        self.button_bar.addWidget(self.search_button)
        self.button_bar.addWidget(self.citation_button)
        self.button_bar.addWidget(self.similar_button)
        self.button_bar.addWidget(self.validate_button)
        self.button_bar.addWidget(self.save_button)
        self.button_bar.addStretch(1)
        self.layout.addLayout(self.button_bar)

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setWordWrap(True)
        self.layout.addWidget(self.status_label)

        self.result_list = QtWidgets.QListWidget()
        self.result_list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.layout.addWidget(self.result_list)

        self._connect_query_preview_updates()
        self._refresh_query_preview()

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _search(self) -> None:
        query, notice = self._build_structured_search_query()
        if not query:
            self.status_label.setText("Enter a CourtListener research query first.")
            return
        search_type = self._selected_search_type()
        semantic = self._selected_semantic(search_type)
        self._run_query(
            lambda connector: connector.search_legal(query, search_type=search_type, semantic=semantic),
            query,
            notice=notice,
        )

    def _lookup_citation(self) -> None:
        text = self.query_input.toPlainText().strip()
        if not text:
            self.status_label.setText("Enter citation text first.")
            return
        self._run_query(lambda connector: connector.lookup_citation(text=text), text)

    def _find_similar_cases(self) -> None:
        query, notice = self._build_structured_search_query()
        if not query:
            self.status_label.setText("Enter a public-law query before searching for similar cases.")
            return
        self._run_access_query(lambda access: access.find_similar_cases(query), query, notice=notice)

    def _validate_determined_case(self) -> None:
        citation_or_title = self.query_input.toPlainText().strip()
        if not citation_or_title:
            self.status_label.setText("Enter a citation, docket number, or case title to validate.")
            return
        _court_filter, _extra_query, notice = self._court_filter_context()
        self._run_access_query(
            lambda access: access.validate_presented_case(citation=citation_or_title),
            citation_or_title,
            notice=notice,
        )

    def _run_query(self, callback: Any, query: str, *, notice: str = "") -> None:
        self.result_list.clear()
        self.results = []
        self.status_label.setText("Querying CourtListener...")
        QtWidgets.QApplication.processEvents()
        try:
            connector = CourtListenerConnector()
            response = callback(connector)
        except Exception as exc:
            self.status_label.setText(f"CourtListener request failed: {str(exc)[:200]}")
            self._add_response_summary(
                {
                    "ok": False,
                    "status": "exception",
                    "message": f"CourtListener request failed: {str(exc)[:200]}",
                },
                query,
                notice,
            )
            return

        if not response.get("ok"):
            self.status_label.setText(response.get("message", "CourtListener request did not complete."))
            self._add_response_summary(response, query, notice)
            return

        self.results = response.get("results", [])
        label = response.get("message") or f"{len(self.results)} CourtListener result(s) for: {query[:120]}"
        if notice:
            label = f"{label} {notice}"
        self.status_label.setText(label)
        if not self.results:
            self._add_response_summary(response, query, notice)
            return
        for result in self.results:
            item = QtWidgets.QListWidgetItem(self._format_result(result))
            item.setData(QtCore.Qt.UserRole, result)
            item.setSizeHint(QtCore.QSize(0, 118))
            self.result_list.addItem(item)

    def _run_access_query(self, callback: Any, query: str, *, notice: str = "") -> None:
        self.result_list.clear()
        self.results = []
        self.status_label.setText("Querying CourtListener guardrail...")
        QtWidgets.QApplication.processEvents()
        try:
            access = CourtListenerAccess(CourtListenerConnector())
            response = callback(access)
        except Exception as exc:
            self.status_label.setText(f"CourtListener guardrail failed: {str(exc)[:200]}")
            self._add_response_summary(
                {
                    "ok": False,
                    "status": "exception",
                    "message": f"CourtListener guardrail failed: {str(exc)[:200]}",
                },
                query,
                notice,
            )
            return
        if not response.get("ok"):
            self.status_label.setText(response.get("message", "CourtListener guardrail did not complete."))
            self._add_response_summary(response, query, notice)
            return
        self.results = response.get("results", [])
        scope = response.get("validation_scope", "")
        warning = response.get("accuracy_warning", "")
        detail = f"\n{scope}" if scope else ""
        warning_detail = f"\n{warning}" if warning else ""
        notice_detail = f"\n{notice}" if notice else ""
        self.status_label.setText(f"{response.get('message', '')}{detail}{warning_detail}{notice_detail}")
        if not self.results:
            self._add_response_summary(response, query, notice)
            return
        for result in self.results:
            item = QtWidgets.QListWidgetItem(self._format_result(result))
            item.setData(QtCore.Qt.UserRole, result)
            item.setSizeHint(QtCore.QSize(0, 140))
            self.result_list.addItem(item)

    def _save_selected(self) -> None:
        if not self.case_id:
            self.status_label.setText("Select an active case before saving to matter notes.")
            return
        item = self.result_list.currentItem()
        if not item:
            self.status_label.setText("Select a CourtListener result to save.")
            return
        result = item.data(QtCore.Qt.UserRole)
        if not isinstance(result, dict):
            self.status_label.setText("Selected item is not a saveable CourtListener result.")
            return
        query = self.query_input.toPlainText().strip()
        summary = self._summary_for_log(result)
        add_research_log(self.case_id, query, "CourtListener", summary, "[]", self.db_path)
        self._notify_case_data_changed(self.case_id)
        self.status_label.setText("CourtListener result saved to matter notes.")

    def _format_result(self, result: dict[str, Any]) -> str:
        citation = result.get("citation") or "No citation"
        court = result.get("court") or "Court unknown"
        date = result.get("date") or "Date unknown"
        reference = result.get("absolute_url") or result.get("resource_uri") or "No source reference"
        snippet = result.get("snippet") or ""
        title = result.get("title") or "Untitled CourtListener result"
        lookup_line = ""
        lookup_status = result.get("lookup_status")
        match_count = result.get("match_count")
        normalized = result.get("normalized_citations")
        if lookup_status is not None or match_count is not None:
            lookup_parts = []
            if lookup_status is not None:
                lookup_parts.append(f"status {lookup_status}")
            if match_count is not None:
                lookup_parts.append(f"{match_count} match(es)")
            if isinstance(normalized, list) and normalized:
                lookup_parts.append("normalized: " + "; ".join(str(item) for item in normalized[:3]))
            lookup_line = "\nCitation lookup: " + " | ".join(lookup_parts)
        determination = result.get("determination") if isinstance(result.get("determination"), dict) else {}
        determination_line = ""
        if determination:
            status = "determined" if determination.get("determined") else "not determined from metadata"
            determination_line = f"\nDetermination: {status} - {determination.get('reason', '')}"
        return f"{title}\n{citation} | {court} | {date}{lookup_line}\n{snippet[:220]}{determination_line}\n{reference}"

    def _connect_query_preview_updates(self) -> None:
        self.query_input.textChanged.connect(self._refresh_query_preview)
        for line_edit in [
            self.location_input,
            self.court_ids_input,
            self.statute_input,
            self.required_terms_input,
            self.exclude_terms_input,
            self.date_after_input,
            self.date_before_input,
        ]:
            line_edit.textChanged.connect(lambda _text: self._refresh_query_preview())
        self.location_preset_input.currentTextChanged.connect(self._apply_location_preset)
        self.status_input.currentTextChanged.connect(lambda _text: self._refresh_query_preview())
        self.search_type_input.currentTextChanged.connect(lambda _text: self._refresh_query_preview())
        self.search_mode_input.currentTextChanged.connect(lambda _text: self._refresh_query_preview())

    def _apply_location_preset(self, label: str) -> None:
        location, court_ids = COURTLISTENER_LOCATION_PRESETS.get(label, ("", ""))
        self.location_input.setText(location)
        self.court_ids_input.setText(court_ids)
        self._refresh_query_preview()

    def _refresh_query_preview(self) -> None:
        query, notice = self._build_structured_search_query()
        preview = query
        if notice:
            preview = f"{preview}\nNote: {notice}" if preview else f"Note: {notice}"
        self.query_preview.setPlainText(preview)

    def _build_structured_search_query(self) -> tuple[str, str]:
        query = self.query_input.toPlainText().strip()
        pieces: list[str] = []
        notices: list[str] = []
        if query:
            pieces.append(query)

        location_terms = self.location_input.text().strip()
        if location_terms:
            pieces.append(location_terms)

        statute_terms = self.statute_input.text().strip()
        if statute_terms:
            pieces.append(statute_terms)

        required_terms = [self._format_query_term(term) for term in self._split_entry_terms(self.required_terms_input.text())]
        if required_terms:
            if pieces:
                pieces.extend(f"AND {term}" for term in required_terms)
            else:
                pieces.extend(required_terms)

        excluded_terms = [self._format_query_term(term) for term in self._split_entry_terms(self.exclude_terms_input.text())]
        if excluded_terms:
            pieces.extend(f"-{term}" for term in excluded_terms)

        court_filter, extra_query, court_notice = self._court_filter_context()
        if court_filter:
            pieces.append(court_filter)
        if extra_query:
            pieces.append(extra_query)
        if court_notice:
            notices.append(court_notice)

        status = self._selected_status()
        if status:
            pieces.append(f"status:{status}")

        date_filter, date_notice = self._date_filter_context()
        if date_filter:
            pieces.append(date_filter)
        if date_notice:
            notices.append(date_notice)

        if self._has_strict_search_filters(court_filter, status, date_filter) and self.search_mode_input.currentText().startswith("Semantic"):
            notices.append("Court, date, and status filters are enforced with keyword/Boolean search; semantic mode will be disabled for this search.")

        return " ".join(piece for piece in pieces if piece).strip(), " ".join(notices)

    def _court_filter_context(self) -> tuple[str, str, str]:
        raw_value = self.court_input.text().strip()
        if not raw_value:
            return "", "", ""

        valid_ids: list[str] = []
        invalid_terms: list[str] = []
        for term in self._split_court_id_terms(raw_value):
            if COURTLISTENER_COURT_CODE_RE.fullmatch(term):
                valid_ids.append(term.lower())
            else:
                invalid_terms.append(term)

        court_filter = ""
        if len(valid_ids) == 1:
            court_filter = f"court_id:{valid_ids[0]}"
        elif valid_ids:
            court_filter = "court_id:(" + " OR ".join(valid_ids) + ")"

        if not invalid_terms:
            return court_filter, "", ""

        invalid_text = " ".join(invalid_terms)
        preview = invalid_text[:80]
        notice = (
            f'Ignored "{preview}" as a court code because CourtListener court filters use IDs like '
            "scotus, ca9, or caed. Included it in the search terms instead."
        )
        return court_filter, invalid_text, notice

    def _combine_query_terms(self, query: str, extra_query: str) -> str:
        terms = [query.strip()]
        if extra_query.strip():
            terms.append(extra_query.strip())
        return " ".join(term for term in terms if term)

    def _date_filter_context(self) -> tuple[str, str]:
        after = self.date_after_input.text().strip()
        before = self.date_before_input.text().strip()
        invalid = [value for value in (after, before) if value and not ISO_DATE_RE.fullmatch(value)]
        if invalid:
            return "", "Ignored filed-date filters because dates must use YYYY-MM-DD format."
        if not after and not before:
            return "", ""
        return f"dateFiled:[{after or '*'} TO {before or '*'}]", ""

    def _split_court_id_terms(self, value: str) -> list[str]:
        normalized = re.sub(r"[,;\n]+", " ", value)
        return [part.strip() for part in normalized.split() if part.strip()]

    def _split_entry_terms(self, value: str) -> list[str]:
        return [part.strip() for part in re.split(r"[,;\n]+", value) if part.strip()]

    def _format_query_term(self, value: str) -> str:
        if any(marker in value for marker in ['"', ":", "(", ")", "[", "]"]):
            return value
        if " " in value:
            return f'"{value}"'
        return value

    def _selected_status(self) -> str:
        return SEARCH_STATUSES.get(self.status_input.currentText(), "")

    def _selected_search_type(self) -> str:
        return SEARCH_TYPES.get(self.search_type_input.currentText(), "o")

    def _selected_semantic(self, search_type: str) -> bool:
        if search_type != "o" or not self.search_mode_input.currentText().startswith("Semantic"):
            return False
        court_filter, _extra_query, _notice = self._court_filter_context()
        date_filter, _date_notice = self._date_filter_context()
        return not self._has_strict_search_filters(court_filter, self._selected_status(), date_filter)

    def _has_strict_search_filters(self, court_filter: str, status: str, date_filter: str) -> bool:
        return bool(court_filter or status or date_filter)

    def _add_response_summary(self, response: dict[str, Any], query: str, notice: str = "") -> None:
        item = QtWidgets.QListWidgetItem(self._format_response_summary(response, query, notice))
        item.setSizeHint(QtCore.QSize(0, 150))
        self.result_list.addItem(item)

    def _format_response_summary(self, response: dict[str, Any], query: str, notice: str = "") -> str:
        status = response.get("status", "unknown")
        message = response.get("message") or "CourtListener did not return a detailed message."
        lines = [message, f"Status: {status}"]
        if notice:
            lines.append(notice)
        if query:
            lines.append(f"Submitted text: {query[:240]}")
        raw_count = response.get("raw_count")
        if raw_count is not None:
            lines.append(f"Raw result count: {raw_count}")
        endpoint = response.get("endpoint")
        if endpoint:
            lines.append(f"Endpoint: {endpoint}")
        request_params = response.get("request_params")
        if isinstance(request_params, dict) and request_params:
            safe_params = ", ".join(f"{key}={value}" for key, value in request_params.items())
            lines.append(f"Request params: {safe_params}")
        guidance = self._guidance_for_response(status)
        if guidance:
            lines.append(guidance)
        return "\n".join(lines)

    def _guidance_for_response(self, status: str) -> str:
        if status == "no_citations":
            return "Citation Lookup only validates formal legal citations found in text. Use Search CourtListener for natural-language research questions."
        if status == "unmatched_citations":
            return "CourtListener parsed a citation but did not find a database match. Check reporter spelling, page number, and jurisdiction."
        if status == "no_results":
            return "Try broadening the query, removing court restrictions, or moving statute/code terms into the query text."
        if status == "credentials_missing":
            return "Check that COURTLISTENER_API_TOKEN is present in .env and restart the GUI from the project launcher."
        if status == "disabled":
            return "Set COURTLISTENER_ENABLED=true in .env and restart the GUI."
        if status == "api_error":
            return "Check the CourtListener token, endpoint configuration, and rate limit status."
        return ""

    def _summary_for_log(self, result: dict[str, Any]) -> str:
        payload = {
            "title": result.get("title"),
            "citation": result.get("citation"),
            "court": result.get("court"),
            "date": result.get("date"),
            "docket_number": result.get("docket_number"),
            "source": result.get("source"),
            "absolute_url": result.get("absolute_url"),
            "resource_uri": result.get("resource_uri"),
            "snippet": result.get("snippet"),
            "result_type": result.get("result_type"),
            "determination": result.get("determination"),
        }
        return json.dumps(payload, indent=2)
