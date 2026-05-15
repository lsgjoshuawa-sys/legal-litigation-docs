from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.evidence import evidence_review
from .widgets import BaseView


class EvidenceReviewView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Evidence Sufficiency Review", "Review evidence support for each claim and identify missing elements.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.output = QtWidgets.QTextEdit(readOnly=True)
        self.output.setMinimumHeight(320)
        self.refresh_button = QtWidgets.QPushButton("Refresh Evidence Review")
        self.refresh_button.clicked.connect(self.refresh)
        self.layout.addWidget(self.output)
        self.layout.addWidget(self.refresh_button)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def refresh(self) -> None:
        self.output.clear()
        if not self.case_id:
            self.output.setPlainText("Select a case first.")
            return
        review = evidence_review(self.case_id, self.db_path)
        if not review.get("claim_reviews"):
            self.output.setPlainText("No claims or evidence available for review.")
            return
        lines: list[str] = []
        for claim in review["claim_reviews"]:
            lines.append(f"Claim: {claim['claim_name']}")
            lines.append(f"Required elements: {claim['required_elements']}")
            lines.append(f"Supported: {claim['supported_elements']}")
            lines.append(f"Missing: {claim['missing_elements']}")
            if claim["supplemental_items"]:
                lines.append("Supplemental evidence:")
                lines.extend([f"  - {item}" for item in claim["supplemental_items"]])
            if claim["weaknesses"]:
                lines.append("Weaknesses:")
                lines.extend([f"  - {weakness}" for weakness in claim["weaknesses"]])
            lines.append("")
        self.output.setPlainText("\n".join(lines))
