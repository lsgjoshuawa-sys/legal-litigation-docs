"""Shared styles for the GUI application."""

APP_STYLE = """
QMainWindow {
    background-color: #f3f4f6;
}
QWidget {
    font-family: Segoe UI, Arial, sans-serif;
}
QLabel {
    color: #202124;
}
QPushButton {
    background-color: #1976d2;
    color: white;
    border: 1px solid #1565c0;
    padding: 8px 12px;
    border-radius: 4px;
}
QPushButton:hover {
    background-color: #1565c0;
}
QListWidget {
    background-color: white;
    border: 1px solid #ccc;
    color: #202124;
    outline: 0;
}
QListWidget::item, QListView::item, QTreeView::item, QTableView::item {
    color: #202124;
    background-color: transparent;
    padding: 6px 8px;
}
QListWidget::item:hover, QListView::item:hover, QTreeView::item:hover, QTableView::item:hover {
    color: #111827;
    background-color: #dbeafe;
}
QListWidget::item:selected, QListView::item:selected, QTreeView::item:selected, QTableView::item:selected {
    color: #ffffff;
    background-color: #1565c0;
}
QListWidget::item:selected:hover, QListView::item:selected:hover, QTreeView::item:selected:hover, QTableView::item:selected:hover {
    color: #ffffff;
    background-color: #0d47a1;
}
QListWidget::item:focus, QListView::item:focus, QTreeView::item:focus, QTableView::item:focus {
    color: #111827;
    background-color: #bfdbfe;
}
QListWidget::item:disabled, QListView::item:disabled, QTreeView::item:disabled, QTableView::item:disabled {
    color: #6b7280;
    background-color: #f3f4f6;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox {
    background-color: white;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 6px;
    color: #202124;
    selection-background-color: #1565c0;
    selection-color: #ffffff;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #202124;
    border: 1px solid #9ca3af;
    outline: 0;
    selection-background-color: #1565c0;
    selection-color: #ffffff;
}
QComboBox QAbstractItemView::item {
    color: #202124;
    background-color: #ffffff;
    min-height: 24px;
    padding: 6px 8px;
}
QComboBox QAbstractItemView::item:hover {
    color: #111827;
    background-color: #dbeafe;
}
QComboBox QAbstractItemView::item:selected {
    color: #ffffff;
    background-color: #1565c0;
}
QComboBox QAbstractItemView::item:selected:hover {
    color: #ffffff;
    background-color: #0d47a1;
}
QComboBox QAbstractItemView::item:focus {
    color: #111827;
    background-color: #bfdbfe;
}
QComboBox QAbstractItemView::item:disabled {
    color: #6b7280;
    background-color: #f3f4f6;
}
QMenu {
    background-color: #ffffff;
    color: #202124;
    border: 1px solid #9ca3af;
}
QMenu::item {
    color: #202124;
    background-color: transparent;
    padding: 6px 22px;
}
QMenu::item:selected {
    color: #ffffff;
    background-color: #1565c0;
}
QMenu::item:disabled {
    color: #6b7280;
    background-color: #f3f4f6;
}
"""
