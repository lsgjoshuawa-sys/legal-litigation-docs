from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from legal_agent.intake import add_action_item, delete_action_item, list_action_items, update_action_item
from .widgets import BaseView


class ActionItemsView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Action Items & Due Dates", "Track tasks, due dates, dependencies, and missing deadline information.")
        self.db_path = db_path
        self.case_id: int | None = None
        self.action_list = QtWidgets.QListWidget()
        self.action_list.currentItemChanged.connect(self._load_action)
        self.layout.addWidget(self.action_list)
        self.action_input = QtWidgets.QTextEdit()
        self.category_input = QtWidgets.QLineEdit()
        self.due_date_input = QtWidgets.QLineEdit()
        self.dependency_input = QtWidgets.QLineEdit()
        self.status_input = QtWidgets.QComboBox()
        self.status_input.addItems(["open", "in progress", "complete"])
        self.notes_input = QtWidgets.QTextEdit()
        self.save_button = QtWidgets.QPushButton("Save Action")
        self.delete_button = QtWidgets.QPushButton("Delete Action")
        self.save_button.clicked.connect(self._save_action)
        self.delete_button.clicked.connect(self._delete_action)
        form = QtWidgets.QFormLayout()
        form.addRow("Action text:", self.action_input)
        form.addRow("Category:", self.category_input)
        form.addRow("Due date:", self.due_date_input)
        form.addRow("Dependency:", self.dependency_input)
        form.addRow("Status:", self.status_input)
        form.addRow("Notes:", self.notes_input)
        self.layout.addLayout(form)
        self.layout.addWidget(self.save_button)
        self.layout.addWidget(self.delete_button)
        self.current_action_id: int | None = None

    def set_case_id(self, case_id: int | None) -> None:
        self.case_id = case_id

    def _load_action(self, current: QtWidgets.QListWidgetItem | None) -> None:
        if not current:
            return
        action = current.data(QtCore.Qt.UserRole)
        self.current_action_id = action["id"]
        self.action_input.setPlainText(action["action_text"])
        self.category_input.setText(action["category"])
        self.due_date_input.setText(action["due_date"] or "")
        self.dependency_input.setText(action["dependency"])
        self.status_input.setCurrentText(action["status"])
        self.notes_input.setPlainText(action["notes"])

    def _save_action(self) -> None:
        if not self.case_id:
            return
        payload = {
            "action_text": self.action_input.toPlainText().strip(),
            "category": self.category_input.text().strip(),
            "due_date": self.due_date_input.text().strip(),
            "dependency": self.dependency_input.text().strip(),
            "status": self.status_input.currentText(),
            "notes": self.notes_input.toPlainText().strip(),
        }
        if self.current_action_id:
            update_action_item(self.current_action_id, **payload, db_path=self.db_path)
        else:
            add_action_item(self.case_id, **payload, db_path=self.db_path)
        self._notify_case_data_changed(self.case_id)

    def _delete_action(self) -> None:
        if self.current_action_id:
            delete_action_item(self.current_action_id, self.db_path)
            self.current_action_id = None
            self._notify_case_data_changed(self.case_id)

    def refresh(self) -> None:
        self.action_list.clear()
        if not self.case_id:
            return
        for action in list_action_items(self.case_id, self.db_path):
            label = f"{action['due_date'] or 'Unknown'} | {action['status']} | {action['action_text'][:70]}"
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.UserRole, action)
            self.action_list.addItem(item)
