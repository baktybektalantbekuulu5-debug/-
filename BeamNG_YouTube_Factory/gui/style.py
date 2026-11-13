DARK_QSS = """
* { font-family: 'Segoe UI', 'Noto Sans', sans-serif; font-size: 13px; }
QMainWindow, QWidget { background: #14161a; color: #e6e8eb; }
QTabWidget::pane { border: 1px solid #2a2e35; border-radius: 6px; }
QTabBar::tab { background: #1c1f25; padding: 9px 18px; margin-right: 2px; border-top-left-radius: 6px; border-top-right-radius: 6px; color: #9aa3ad; }
QTabBar::tab:selected { background: #262b33; color: #ffffff; }
QGroupBox { border: 1px solid #2a2e35; border-radius: 8px; margin-top: 12px; padding: 12px 8px 8px 8px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #ff8a3d; }
QPlainTextEdit, QTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTableWidget {
  background: #1b1e24; border: 1px solid #2f343c; border-radius: 6px; padding: 5px; selection-background-color: #ff6a00; }
QComboBox QAbstractItemView { background: #1b1e24; selection-background-color: #ff6a00; }
QPushButton { background: #2a2f38; border: 1px solid #3a404a; border-radius: 6px; padding: 7px 14px; }
QPushButton:hover { background: #343b46; }
QPushButton:disabled { color: #666c75; background: #20242a; }
QPushButton#generate { background: #ff6a00; border: none; color: #fff; font-size: 16px; font-weight: 700; padding: 12px; }
QPushButton#generate:hover { background: #ff8329; }
QPushButton#stop { background: #b3261e; border: none; color: #fff; font-weight: 700; padding: 12px; }
QPushButton#stop:disabled { background: #3a2220; color: #7a5a58; }
QProgressBar { background: #1b1e24; border: 1px solid #2f343c; border-radius: 6px; text-align: center; height: 20px; }
QProgressBar::chunk { background: #ff6a00; border-radius: 5px; }
QHeaderView::section { background: #20242a; padding: 5px; border: none; color: #9aa3ad; }
QLabel#hint { color: #8d96a0; }
QCheckBox { spacing: 8px; }
"""
