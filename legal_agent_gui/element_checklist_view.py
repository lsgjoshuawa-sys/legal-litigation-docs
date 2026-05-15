from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.evidence import element_checklist
from legal_agent.intake import list_claims
from .widgets import BaseView


class ElementChecklistView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Claim Element Checklist", "Review claim required elements and evidence support for each claim.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.claim_selector = QtWidgets.QComboBox()
        self.claim_selector.currentIndexChanged.connect(self.refresh)
        self.checklist_output = QtWidgets.QTextEdit(readOnly=True)
        self.checklist_output.setMinimumHeight(240)
        self.layout.addWidget(self.claim_selector)
        self.layout.addWidget(self.checklist_output)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def refresh(self) -> None:
        self.claim_selector.blockSignals(True)
        self.claim_selector.clear()
        self.checklist_output.clear()
        if not self.case_id:
            self.claim_selector.addItem("Select a case first.")
            self.claim_selector.blockSignals(False)
            return
        claims = list_claims(self.case_id, self.db_path)
        if not claims:
            self.claim_selector.addItem("No claims available.")
            self.claim_selector.blockSignals(False)
            return
        self.claim_selector.addItem("Select a claim", None)
        for claim in claims:
            self.claim_selector.addItem(claim["claim_name"], claim["id"])
        self.claim_selector.blockSignals(False)
        if self.claim_selector.currentIndex() > 0:
            claim_id = self.claim_selector.currentData()
            if claim_id:
                self._display_checklist(claim_id)

    def _display_checklist(self, claim_id: int) -> None:
        result = element_checklist(self.case_id, claim_id, self.db_path)
        if "error" in result:
            self.checklist_output.setPlainText(result["error"])
            return
        lines = [f"Claim: {result['claim_name']}", "", "Required elements:", *[f"- {element}" for element in result['required_elements']], "", "Supported elements:", *[f"- {element}" for element in result['supported_elements']], "", "Missing elements:", *[f"- {element}" for element in result['missing_elements']], "", "Weaknesses:", *[f"- {weakness}" for weakness in result['weaknesses']]]
        self.checklist_output.setPlainText("\n".join(lines))
