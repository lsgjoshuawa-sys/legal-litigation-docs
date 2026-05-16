from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.authority_validation import get_verified_authorities
from legal_agent.drafting import get_document, save_document
from .widgets import BaseView


class DraftGeneratorView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Draft Generator", "Produce a document draft using verified authorities and case information.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.document_type_input = QtWidgets.QLineEdit()
        self.document_type_input.setPlaceholderText("complaint")
        self.generate_button = QtWidgets.QPushButton("Generate Draft")
        self.generate_button.clicked.connect(self._generate_draft)
        self.output = QtWidgets.QTextEdit(readOnly=True)
        self.output.setMinimumHeight(320)
        form = QtWidgets.QFormLayout()
        form.addRow("Document type:", self.document_type_input)
        self.layout.addLayout(form)
        self.layout.addWidget(self.generate_button)
        self.layout.addWidget(self.output)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _generate_draft(self) -> None:
        self.output.clear()
        if not self.case_id:
            self.output.setPlainText("Select a case first.")
            return
        doc_type = self.document_type_input.text().strip() or "complaint"
        verified = get_verified_authorities(self.case_id, self.db_path)
        messages: list[str] = []
        if not verified:
            messages.append("Warning: No verified authorities found. Draft will include placeholders and should not be submitted without verification.")
        result = save_document(self.case_id, doc_type, self.db_path)
        citation_validation = result.get("citation_validation", {})
        messages.append(result.get("draft_text", "Unable to generate draft."))
        if citation_validation:
            messages.append("## CourtListener Citation Guardrail\n" + citation_validation.get("message", "Citation guardrail status unavailable."))
        if "document_id" in result:
            self._notify_case_data_changed(self.case_id)
        self.output.setPlainText("\n\n".join(messages))

    def refresh(self) -> None:
        self.output.clear()

    def select_record(self, record_id: int) -> bool:
        document = get_document(record_id, self.db_path)
        if not document:
            return False
        self.document_type_input.setText(document.get("document_type", ""))
        self.output.setPlainText(document.get("draft_markdown", ""))
        return True
