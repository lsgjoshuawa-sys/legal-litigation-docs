from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.evidence import evidence_review
from legal_agent.research import get_research_logs
from .widgets import BaseView


class DocumentStrategyView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Document Strategy", "Summarize evidence strengths, research leads, and strategy considerations for drafting.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.output = QtWidgets.QTextEdit(readOnly=True)
        self.output.setMinimumHeight(320)
        self.refresh_button = QtWidgets.QPushButton("Refresh Strategy Summary")
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
        research_logs = get_research_logs(self.case_id, self.db_path)
        lines: list[str] = ["Evidence review:"]
        if review.get("claim_reviews"):
            for claim in review["claim_reviews"]:
                lines.append(f"- {claim['claim_name']}: missing {claim['missing_elements']} and support {claim['supported_elements']}")
        else:
            lines.append("- No claim evidence review available.")
        lines.append("")
        lines.append("Research leads:")
        if research_logs:
            for log in research_logs:
                lines.append(f"- {log['query']} from {log['source']}")
        else:
            lines.append("- No research logs recorded.")
        self.output.setPlainText("\n".join(lines))
