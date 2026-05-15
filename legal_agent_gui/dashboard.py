from __future__ import annotations
from datetime import datetime
from typing import Any

from PySide6 import QtCore, QtWidgets

from legal_agent.intake import list_cases, list_action_items
from legal_agent.authority_validation import get_unverified_authorities
from legal_agent.vulnerability import get_vulnerability_checks
from .widgets import BaseView


class DashboardView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Dashboard", "View active case highlights, upcoming due dates, and verification status.")
        self.db_path = db_path
        self.summary = QtWidgets.QTextEdit(readOnly=True)
        self.summary.setMinimumHeight(600)
        self.layout.addWidget(self.summary)

    def refresh(self) -> None:
        cases = list_cases(self.db_path)
        upcoming = []
        unverified = []
        vulnerabilities = []
        for case in cases:
            action_items = list_action_items(case["id"], self.db_path)
            for item in action_items:
                if not item["due_date"] or item["due_date"] in ["", "unknown"]:
                    upcoming.append(f"Case {case['id']} missing due date: {item['action_text']}")
                else:
                    upcoming.append(f"Case {case['id']} due {item['due_date']}: {item['action_text']}")
            unverified.extend([f"Case {case['id']} authority {auth['title']}" for auth in get_unverified_authorities(case["id"], self.db_path)])
            vulnerabilities.extend([f"Case {case['id']} issue {issue['issue_type']}" for issue in get_vulnerability_checks(case["id"], self.db_path)])
        lines = ["Active Cases:", *[f"- {case['id']}: {case['title']}" for case in cases], "", "Upcoming or Missing Deadlines:", *[f"- {line}" for line in upcoming[:10]], "", "Unverified Authorities:", *[f"- {line}" for line in unverified[:10]], "", "Vulnerabilities:", *[f"- {line}" for line in vulnerabilities[:10]]]
        self.summary.setPlainText("\n".join(lines))
