from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class BaseView(QtWidgets.QWidget):
    def __init__(self, title: str, explanation: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.explanation = explanation

        self.root_layout = QtWidgets.QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)

        self.content_widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout(self.content_widget)
        self.layout.setContentsMargins(28, 24, 28, 24)
        self.layout.setSpacing(10)
        self.scroll_area.setWidget(self.content_widget)
        self.root_layout.addWidget(self.scroll_area)

        self.header = QtWidgets.QLabel(f"<h2>{title}</h2>")
        self.explanation_label = QtWidgets.QLabel(explanation)
        self.explanation_label.setWordWrap(True)
        self.layout.addWidget(self.header)
        self.layout.addWidget(self.explanation_label)

    def prepare_for_display(self) -> None:
        """Normalize common child widgets after a concrete view builds its controls."""
        has_form_inputs = bool(self.findChildren(QtWidgets.QLineEdit) or self.findChildren(QtWidgets.QTextEdit))
        for text_edit in self.findChildren(QtWidgets.QTextEdit):
            text_edit.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
            if text_edit.isReadOnly():
                text_edit.setMinimumHeight(max(text_edit.minimumHeight(), 220))
                text_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            else:
                text_edit.setMinimumHeight(max(text_edit.minimumHeight(), 96))
                text_edit.setMaximumHeight(180)
                text_edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        for list_widget in self.findChildren(QtWidgets.QListWidget):
            list_widget.setMinimumHeight(max(list_widget.minimumHeight(), 120))
            if has_form_inputs:
                list_widget.setMaximumHeight(220)
                list_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            else:
                list_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

    def refresh(self) -> None:
        pass

    def _notify_case_data_changed(self, select_case_id: int | None = None) -> None:
        window = self.window()
        if hasattr(window, "refresh_case_data"):
            window.refresh_case_data(select_case_id=select_case_id)


class StatusBadge(QtWidgets.QLabel):
    BADGE_STYLES = {
        "Verified": "background-color: #4caf50; color: white; padding: 4px 8px; border-radius: 10px;",
        "Unverified": "background-color: #f44336; color: white; padding: 4px 8px; border-radius: 10px;",
        "Needs Review": "background-color: #ff9800; color: white; padding: 4px 8px; border-radius: 10px;",
        "Missing Required Data": "background-color: #9c27b0; color: white; padding: 4px 8px; border-radius: 10px;",
        "Treatment Unknown": "background-color: #607d8b; color: white; padding: 4px 8px; border-radius: 10px;",
        "High Risk": "background-color: #d32f2f; color: white; padding: 4px 8px; border-radius: 10px;",
        "Medium Risk": "background-color: #ffa000; color: black; padding: 4px 8px; border-radius: 10px;",
        "Low Risk": "background-color: #388e3c; color: white; padding: 4px 8px; border-radius: 10px;",
        "Ready for Export": "background-color: #1976d2; color: white; padding: 4px 8px; border-radius: 10px;",
    }

    def __init__(self, label: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setStyleSheet(self.BADGE_STYLES.get(label, self.BADGE_STYLES["Needs Review"]))
        self.setMargin(4)
