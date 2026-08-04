GLASS_GREEN_STYLESHEET = """
* {
	font-family: 'Noto Sans Thai', 'Sarabun', -apple-system, sans-serif;
}

QMainWindow {
	background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #022C22, stop:0.5 #064E3B, stop:1 #02381F);
}

QTabWidget::pane {
	border: 1px solid rgba(52, 211, 153, 0.25);
	background: rgba(6, 44, 27, 0.75);
	border-radius: 18px;
}

QTabBar::tab {
	padding: 12px 24px;
	font-size: 15px;
	font-weight: bold;
	color: #A7F3D0;
	background: rgba(255, 255, 255, 0.05);
	border-top-left-radius: 12px;
	border-top-right-radius: 12px;
	margin-right: 6px;
	border: 1px solid rgba(52, 211, 153, 0.15);
}

QTabBar::tab:selected {
	background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
	color: #FFFFFF;
	border: 1px solid rgba(110, 231, 183, 0.4);
}

QFrame.glass-card {
	background: rgba(6, 78, 59, 0.35);
	border: 1px solid rgba(52, 211, 153, 0.25);
	border-radius: 18px;
}

QLabel {
	color: #ECFDF5;
}

QPushButton.primary-btn {
	background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #047857);
	color: white;
	font-weight: bold;
	font-size: 15px;
	border-radius: 10px;
	padding: 12px 20px;
	border: 1px solid rgba(110, 231, 183, 0.3);
}

QPushButton.primary-btn:hover {
	background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #34D399, stop:1 #059669);
}

QPushButton.secondary-btn {
	background: rgba(255, 255, 255, 0.08);
	color: #A7F3D0;
	font-weight: bold;
	font-size: 14px;
	border-radius: 10px;
	padding: 10px 16px;
	border: 1px solid rgba(52, 211, 153, 0.3);
}

QPushButton.secondary-btn:hover {
	background: rgba(52, 211, 153, 0.2);
	color: #FFFFFF;
}

QPushButton.danger-btn {
	background: rgba(225, 29, 72, 0.85);
	color: white;
	font-weight: bold;
	border-radius: 8px;
	padding: 6px 12px;
	border: none;
}

QPushButton.danger-btn:hover {
	background: rgba(225, 29, 72, 1.0);
}

QTableWidget {
	background: rgba(2, 44, 34, 0.6);
	border: 1px solid rgba(52, 211, 153, 0.2);
	border-radius: 14px;
	color: #ECFDF5;
	gridline-color: rgba(52, 211, 153, 0.1);
}

QHeaderView::section {
	background: rgba(6, 78, 59, 0.9);
	color: #6EE7B7;
	font-weight: bold;
	font-size: 14px;
	padding: 12px;
	border: none;
}

QMessageBox, QDialog {
	background-color: #064E3B;
	border: 2px solid #34D399;
	border-radius: 14px;
}

QMessageBox QLabel, QDialog QLabel {
	color: #ECFDF5;
	font-size: 15px;
	font-weight: bold;
}

QMessageBox QPushButton {
	background: #10B981;
	color: white;
	font-weight: bold;
	border-radius: 8px;
	padding: 8px 20px;
	min-width: 80px;
}

QMessageBox QPushButton:hover {
	background: #34D399;
}
"""
