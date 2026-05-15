from __future__ import annotations
import json
from datetime import datetime, timezone

from PySide6 import QtWidgets

from legal_agent import db
from .widgets import BaseView


class AuditLogView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Audit Log / Verification History", "Review audit events and manually add a record of key case actions.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.log_list = QtWidgets.QListWidget()
        self.layout.addWidget(self.log_list)
        self.safe_check_list = QtWidgets.QListWidget()
        self.layout.addWidget(QtWidgets.QLabel("Safe Check Events"))
        self.layout.addWidget(self.safe_check_list)
        self.new_event_input = QtWidgets.QLineEdit()
        self.new_event_input.setPlaceholderText("New audit event description")
        self.add_button = QtWidgets.QPushButton("Add Audit Event")
        self.add_button.clicked.connect(self._add_event)
        self.refresh_button = QtWidgets.QPushButton("Refresh Audit Log")
        self.refresh_button.clicked.connect(self.refresh)
        button_bar = QtWidgets.QHBoxLayout()
        button_bar.addWidget(self.add_button)
        button_bar.addWidget(self.refresh_button)
        self.message_label = QtWidgets.QLabel("")
        self.layout.addWidget(self.new_event_input)
        self.layout.addLayout(button_bar)
        self.layout.addWidget(self.message_label)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _add_event(self) -> None:
        self.message_label.clear()
        if not self.case_id:
            self.message_label.setText("Select a case first.")
            return
        description = self.new_event_input.text().strip()
        if not description:
            description = "Untitled audit event"
        db.log_audit_event(self.case_id, "manual", description, datetime.now(timezone.utc).isoformat(), self.db_path)
        self.new_event_input.clear()
        self._notify_case_data_changed(self.case_id)
        self.message_label.setText("Audit event added.")

    def refresh(self) -> None:
        self.log_list.clear()
        self.safe_check_list.clear()
        self.message_label.clear()
        if not self.case_id:
            self.log_list.addItem("Select a case first to view audit events.")
        events = db.get_audit_events(db_path=self.db_path)
        if not events:
            self.log_list.addItem("No audit events recorded.")
        for event in events:
            if self.case_id and event["case_id"] == self.case_id:
                item = QtWidgets.QListWidgetItem(f"[{event['created_at']}] {event['event_type']}: {event['description']}")
                self.log_list.addItem(item)

        safe_events = db.get_safe_check_events(db_path=self.db_path)
        if not safe_events:
            self.safe_check_list.addItem("No safe check events recorded.")
            return
        for event in safe_events:
            if event["case_id"] not in {None, self.case_id}:
                continue
            details = event.get("details") if isinstance(event.get("details"), dict) else {}
            hint = details.get("improvement_hint", "")
            suffix = f" | Hint: {hint}" if hint else ""
            item = QtWidgets.QListWidgetItem(
                f"[{event['created_at']}] {event['severity']} {event['event_type']}: {event['message']}{suffix}"
            )
            item.setToolTip(json.dumps(details, indent=2, sort_keys=True))
            self.safe_check_list.addItem(item)
        if self.safe_check_list.count() == 0:
            self.safe_check_list.addItem("No safe check events recorded for this case.")
