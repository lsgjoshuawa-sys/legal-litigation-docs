from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.ai_analysis import generate_argument_analysis
from legal_agent.case_profile import build_case_profile
from legal_agent.resource_throttle import get_throttling_agent
from .widgets import BaseView


class AIAnalysisView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__(
            "AI Argument Analysis",
            "Generate an argument and defense workup from the saved case profile and verified authorities.",
        )
        self.db_path = db_path
        self.case_id: int | None = None

        self.generate_button = QtWidgets.QPushButton("Generate AI Analysis")
        self.refresh_profile_button = QtWidgets.QPushButton("Refresh Case Profile")
        self.generate_button.clicked.connect(self._generate)
        self.refresh_profile_button.clicked.connect(self.refresh)

        button_bar = QtWidgets.QHBoxLayout()
        button_bar.addWidget(self.generate_button)
        button_bar.addWidget(self.refresh_profile_button)
        button_bar.addStretch(1)
        self.layout.addLayout(button_bar)

        self.profile_list = QtWidgets.QListWidget()
        self.output = QtWidgets.QTextEdit(readOnly=True)
        self.output.setMinimumHeight(320)
        self.throttle_label = QtWidgets.QLabel("")
        self.throttle_label.setWordWrap(True)
        self.layout.addWidget(self.throttle_label)
        self.layout.addWidget(QtWidgets.QLabel("Case profile items available to the AI layer:"))
        self.layout.addWidget(self.profile_list)
        self.layout.addWidget(self.output)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def refresh(self) -> None:
        self.profile_list.clear()
        self._refresh_throttle_label()
        if not self.case_id:
            self.profile_list.addItem("Select a case first.")
            self.output.clear()
            return
        profile = build_case_profile(self.case_id, self.db_path)
        if profile.get("error"):
            self.profile_list.addItem(profile["error"])
            return
        for item in profile.get("items", []):
            self.profile_list.addItem(f"{item['item_type']}: {item['title']}")

    def _generate(self) -> None:
        self.output.clear()
        if not self.case_id:
            self.output.setPlainText("Select a case first.")
            return
        result = generate_argument_analysis(self.case_id, self.db_path)
        self.output.setPlainText(result.get("analysis", "Unable to generate analysis."))
        self.refresh()

    def _refresh_throttle_label(self) -> None:
        budget = get_throttling_agent().report().get("budget", {})
        self.throttle_label.setText(
            "Throttle: "
            f"enabled={budget.get('enabled', True)}; "
            f"AI={budget.get('ai_requests_per_minute', '?')}/min; "
            f"HTTP={budget.get('http_requests_per_minute', '?')}/min; "
            f"context={budget.get('ai_max_context_chars', '?')} chars; "
            f"citations/run={budget.get('citation_checks_per_run', '?')}"
        )
