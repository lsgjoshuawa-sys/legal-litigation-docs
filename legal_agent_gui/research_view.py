from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from legal_agent.research import add_research_log, get_research_logs
from .plain_text_lists import json_list_from_identifier_text, plain_text_from_list_storage
from .widgets import BaseView


class ResearchView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Legal Research", "Track research queries, sources, and research leads tied to each case.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.log_list = QtWidgets.QListWidget()
        self.log_list.currentItemChanged.connect(self._load_log)
        self.layout.addWidget(self.log_list)

        self.query_input = QtWidgets.QLineEdit()
        self.source_input = QtWidgets.QLineEdit()
        self.result_input = QtWidgets.QTextEdit()
        self.authority_ids_input = QtWidgets.QLineEdit()
        self.authority_ids_input.setPlaceholderText("Authority IDs separated by commas or spaces, e.g. 1, 2, 5")
        self.save_button = QtWidgets.QPushButton("Add Research Log")
        self.save_button.clicked.connect(self._save_log)
        self.warning_label = QtWidgets.QLabel("")
        self.current_log_id: int | None = None

        form = QtWidgets.QFormLayout()
        form.addRow("Query:", self.query_input)
        form.addRow("Source:", self.source_input)
        form.addRow("Result summary:", self.result_input)
        form.addRow("Authority IDs:", self.authority_ids_input)
        self.layout.addLayout(form)
        self.layout.addWidget(self.save_button)
        self.layout.addWidget(self.warning_label)

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _load_log(self, current: QtWidgets.QListWidgetItem | None) -> None:
        if not current:
            return
        log = current.data(QtCore.Qt.UserRole)
        self.current_log_id = log["id"]
        self.query_input.setText(log["query"])
        self.source_input.setText(log["source"])
        self.result_input.setPlainText(log["result_summary"])
        self.authority_ids_input.setText(", ".join(plain_text_from_list_storage(log["authority_ids_json"]).splitlines()))

    def _save_log(self) -> None:
        if not self.case_id:
            self.warning_label.setText("Select a case first.")
            return
        query = self.query_input.text().strip()
        source = self.source_input.text().strip()
        summary = self.result_input.toPlainText().strip()
        add_research_log(self.case_id, query, source, summary, json_list_from_identifier_text(self.authority_ids_input.text()), self.db_path)
        self._notify_case_data_changed(self.case_id)
        self.warning_label.setText("Research log saved.")

    def refresh(self) -> None:
        selected_id = self.current_log_id
        self.log_list.clear()
        self.query_input.clear()
        self.source_input.clear()
        self.result_input.clear()
        self.authority_ids_input.clear()
        self.warning_label.clear()
        if not self.case_id:
            return
        for log in get_research_logs(self.case_id, self.db_path):
            item = QtWidgets.QListWidgetItem(f"{log['query']} ({log['source']})")
            item.setData(QtCore.Qt.UserRole, log)
            self.log_list.addItem(item)
            if selected_id and log["id"] == selected_id:
                self.log_list.setCurrentItem(item)

    def select_record(self, record_id: int) -> bool:
        for index in range(self.log_list.count()):
            item = self.log_list.item(index)
            log = item.data(QtCore.Qt.UserRole)
            if log and log["id"] == record_id:
                self.log_list.setCurrentItem(item)
                self._load_log(item)
                return True
        return False
