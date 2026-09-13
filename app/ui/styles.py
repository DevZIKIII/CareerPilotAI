APP_QSS = """
* {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
    color: #e8ecf5;
}
QMainWindow, QWidget {
    background: #0f131d;
}
QFrame#Sidebar {
    background: #0a0d14;
    border-right: 1px solid #20283a;
}
QLabel#AppTitle {
    font-size: 22px;
    font-weight: 700;
}
QLabel#HeaderTitle {
    font-size: 24px;
    font-weight: 700;
}
QLabel#Muted {
    color: #99a5ba;
}
QPushButton {
    background: #1b2232;
    border: 1px solid #344058;
    border-radius: 6px;
    padding: 8px 12px;
    min-height: 20px;
}
QPushButton:hover {
    background: #263047;
}
QPushButton#PrimaryButton {
    background: #4f7cff;
    border: 0;
    font-weight: 700;
}
QPushButton#NavButton {
    border: 0;
    text-align: left;
    padding: 11px 14px;
    background: transparent;
    color: #aeb7c9;
}
QPushButton#NavButton:hover, QPushButton#NavButton:checked {
    background: #171f30;
    color: #ffffff;
}
QFrame#Card {
    background: #151b28;
    border: 1px solid #2b354b;
    border-radius: 8px;
}
QLabel#CardValue {
    font-size: 24px;
    font-weight: 800;
}
QLabel#CardTitle {
    color: #aeb7c9;
    font-weight: 600;
}
QTableWidget, QListWidget, QTextEdit, QLineEdit, QComboBox {
    background: #121824;
    border: 1px solid #2b354b;
    border-radius: 7px;
    padding: 6px;
    selection-background-color: #33415f;
}
QHeaderView::section {
    background: #1a2232;
    color: #c8d0df;
    border: 0;
    padding: 8px 10px;
}
QComboBox::drop-down {
    border: 0;
}
QTextEdit {
    line-height: 1.3;
}
QTableWidget {
    gridline-color: #263149;
    alternate-background-color: #151c2a;
}
QDialog {
    background: #0f131d;
}
"""


def channel_badge(channel: str) -> str:
    colors = {
        "email_auto": "#22c55e",
        "sensitive_platform": "#facc15",
        "manual_review": "#38bdf8",
        "blocked_sensitive_platform": "#ef4444",
    }
    color = colors.get(channel, "#94a3b8")
    text_color = "#111827" if channel == "sensitive_platform" else "#ffffff"
    return (
        f"<span style='background:{color};color:{text_color};"
        "padding:4px 8px;border-radius:8px;font-weight:700;'>"
        f"{channel}</span>"
    )
