from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.jurisdiction import classify_case, get_procedural_rules
from .widgets import BaseView


class JurisdictionView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Jurisdiction Classifier", "Classify the case jurisdiction and review the jurisdictional recommendation.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.classify_button = QtWidgets.QPushButton("Classify Jurisdiction")
        self.classify_button.clicked.connect(self._classify)
        self.result_area = QtWidgets.QTextEdit(readOnly=True)
        self.result_area.setMinimumHeight(200)
        self.layout.addWidget(self.classify_button)
        self.layout.addWidget(self.result_area)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _classify(self) -> None:
        if not self.case_id:
            self.result_area.setPlainText("Select a case first.")
            return
        result = classify_case(self.case_id, self.db_path)
        self.result_area.setPlainText(f"Classification: {result.get('classification')}\nReason: {result.get('reason')}")

    def refresh(self) -> None:
        self.result_area.clear()
