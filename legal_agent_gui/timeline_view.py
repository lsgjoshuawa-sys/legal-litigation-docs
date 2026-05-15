from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.intake import generate_timeline
from .widgets import BaseView


class TimelineView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Litigation Timeline", "Review the case timeline and upcoming deadlines.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.timeline_list = QtWidgets.QListWidget()
        self.timeline_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.layout.addWidget(self.timeline_list)
        self.refresh_button = QtWidgets.QPushButton("Refresh Timeline")
        self.refresh_button.clicked.connect(self.refresh)
        self.layout.addWidget(self.refresh_button)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def refresh(self) -> None:
        self.timeline_list.clear()
        if not self.case_id:
            self.timeline_list.addItem("Select a case first.")
            return
        items = generate_timeline(self.case_id, self.db_path)
        if not items:
            self.timeline_list.addItem("No timeline items found for this case.")
            return
        for item in items:
            label = f"{item.get('due_date') or 'Unknown due date'}: {item.get('action_text')} ({item.get('status')})"
            self.timeline_list.addItem(label)
