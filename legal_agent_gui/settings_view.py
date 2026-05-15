from __future__ import annotations

from PySide6 import QtWidgets

from legal_agent.openai_client import ConfigManager, save_api_key
from .widgets import BaseView


class SettingsView(BaseView):
    def __init__(self, db_path: str | None = None) -> None:
        super().__init__("Settings", "Configure OpenAI integration, export options, and application behavior.")
        self.db_path = db_path
        self.form = QtWidgets.QFormLayout()
        self.api_key_input = QtWidgets.QLineEdit()
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.model_input = QtWidgets.QComboBox()
        self.model_input.addItems(["gpt-4o-mini", "gpt-4o", "gpt-4o-large"])
        self.temperature_input = QtWidgets.QLineEdit("0.0")
        self.citation_strictness = QtWidgets.QComboBox()
        self.citation_strictness.addItems(["High", "Medium", "Low"])
        self.verification_strictness = QtWidgets.QComboBox()
        self.verification_strictness.addItems(["High", "Medium", "Low"])
        self.database_location = QtWidgets.QLineEdit()
        self.export_folder = QtWidgets.QLineEdit()
        self.save_button = QtWidgets.QPushButton("Save Settings")
        self.save_button.clicked.connect(self._save_settings)
        self.form.addRow("OpenAI API key:", self.api_key_input)
        self.form.addRow("Model selection:", self.model_input)
        self.form.addRow("Temperature:", self.temperature_input)
        self.form.addRow("Citation strictness:", self.citation_strictness)
        self.form.addRow("Verification strictness:", self.verification_strictness)
        self.form.addRow("Database location:", self.database_location)
        self.form.addRow("Export folder:", self.export_folder)
        self.layout.addLayout(self.form)
        self.layout.addWidget(self.save_button)
        self.message_label = QtWidgets.QLabel("")
        self.layout.addWidget(self.message_label)
        self.config = ConfigManager()

    def _save_settings(self) -> None:
        try:
            api_key = self.api_key_input.text().strip()
            if api_key:
                save_api_key(api_key, self.db_path)
                self.config.set_api_key(api_key)
            self.config.set_setting("model", self.model_input.currentText())
            self.config.set_setting("temperature", self.temperature_input.text().strip())
            self.config.set_setting("citation_strictness", self.citation_strictness.currentText())
            self.config.set_setting("verification_strictness", self.verification_strictness.currentText())
            self.config.set_setting("export_folder", self.export_folder.text().strip())
            self.message_label.setText("Settings saved locally. OpenAI key stored for local use only.")
        except ValueError as exc:
            self.message_label.setText(str(exc))

    def refresh(self) -> None:
        api_key = self.config.get_api_key() or ""
        self.api_key_input.setText(api_key)
        self.model_input.setCurrentText(self.config.get_setting("model", "gpt-4o-mini"))
        self.temperature_input.setText(str(self.config.get_setting("temperature", "0.0")))
        self.citation_strictness.setCurrentText(self.config.get_setting("citation_strictness", "High"))
        self.verification_strictness.setCurrentText(self.config.get_setting("verification_strictness", "High"))
        self.export_folder.setText(self.config.get_setting("export_folder", ""))
