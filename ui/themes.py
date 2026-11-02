"""ระบบธีมสีของ UI — เลือกได้ 4 แบบ: มาตรฐาน / สว่าง / เข้ม / ขาวดำ
ใช้วิธีสร้าง stylesheet จาก palette เดียว เพื่อให้ทุกธีมสอดคล้องกันและอ่านง่ายทุกโหมด
"""


def _build_stylesheet(p: dict) -> str:
	return f"""
* {{
	font-family: 'Noto Sans Thai', 'Sarabun', -apple-system, sans-serif;
}}

QMainWindow {{
	background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {p['bg1']}, stop:0.5 {p['bg2']}, stop:1 {p['bg3']});
}}

QWidget {{
	color: {p['text']};
}}

QTabWidget::pane {{
	border: 1px solid {p['border']};
	background: {p['pane']};
	border-radius: 18px;
}}

QTabBar::tab {{
	padding: 12px 24px;
	font-size: 15px;
	font-weight: bold;
	color: {p['text_dim']};
	background: {p['tab_bg']};
	border-top-left-radius: 12px;
	border-top-right-radius: 12px;
	margin-right: 6px;
	border: 1px solid {p['border']};
}}

QTabBar::tab:selected {{
	background: {p['accent']};
	color: {p['on_accent']};
	border: 1px solid {p['accent2']};
}}

QFrame.glass-card {{
	background: {p['panel']};
	border: 1px solid {p['border']};
	border-radius: 18px;
}}

QLabel {{
	color: {p['text']};
	background: transparent;
}}

/* ป้ายเฉพาะบนหน้า Dashboard — คุมสีตามธีมให้อ่านง่ายทุกโหมด */
QLabel[class="clock"]        {{ font-size: 72px; font-weight: bold; color: {p['accent2']}; }}
QLabel[class="clock-sm"]     {{ font-size: 26px; font-weight: bold; color: {p['accent2']}; }}
QLabel[class="title"]        {{ font-size: 18px; font-weight: bold; color: {p['text']}; }}
QLabel[class="muted"]        {{ font-size: 15px; color: {p['text_dim']}; }}
QLabel[class="muted-title"]  {{ font-size: 18px; font-weight: bold; color: {p['text_dim']}; }}
QLabel[class="accent-amber"] {{ font-size: 18px; font-weight: bold; color: {p['amber']}; }}
QLabel[class="accent-green"] {{ font-size: 14px; font-weight: bold; color: {p['accent2']}; }}

QPushButton.primary-btn {{
	background: {p['accent']};
	color: {p['on_accent']};
	font-weight: bold;
	font-size: 15px;
	border-radius: 10px;
	padding: 12px 20px;
	border: 1px solid {p['accent2']};
}}
QPushButton.primary-btn:hover {{ background: {p['accent2']}; }}

QPushButton.secondary-btn {{
	background: {p['secondary_bg']};
	color: {p['text']};
	font-weight: bold;
	font-size: 14px;
	border-radius: 10px;
	padding: 10px 16px;
	border: 1px solid {p['border']};
}}
QPushButton.secondary-btn:hover {{ background: {p['secondary_hover']}; color: {p['on_accent']}; }}

QPushButton.danger-btn {{
	background: {p['danger']};
	color: #FFFFFF;
	font-weight: bold;
	border-radius: 8px;
	padding: 6px 12px;
	border: none;
}}

QPushButton.theme-btn {{
	background: {p['secondary_bg']};
	color: {p['text']};
	font-weight: bold;
	font-size: 13px;
	border-radius: 8px;
	padding: 6px 12px;
	border: 1px solid {p['border']};
}}
QPushButton.theme-btn:checked {{
	background: {p['accent']};
	color: {p['on_accent']};
	border: 1px solid {p['accent2']};
}}

QTableWidget {{
	background: {p['table_bg']};
	border: 1px solid {p['border']};
	border-radius: 14px;
	color: {p['text']};
	gridline-color: {p['border']};
}}
QTableWidget::item:selected {{ background: {p['accent']}; color: {p['on_accent']}; }}

QHeaderView::section {{
	background: {p['header_bg']};
	color: {p['header_text']};
	font-weight: bold;
	font-size: 14px;
	padding: 12px;
	border: none;
}}

QLineEdit, QTimeEdit, QComboBox, QPlainTextEdit, QTextEdit, QTextBrowser, QSpinBox {{
	background: {p['input_bg']};
	color: {p['text']};
	border: 1px solid {p['border']};
	border-radius: 6px;
	padding: 5px 8px;
}}
QLineEdit:disabled, QPlainTextEdit:disabled, QSpinBox:disabled {{ color: {p['text_dim']}; }}

/* รายการที่กางออกของ QComboBox — กำหนดพื้น/อักษรเอง กันอักษรกลืนพื้นบน Windows */
QComboBox QAbstractItemView {{
	background-color: {p['dialog_bg']};
	color: {p['dialog_text']};
	selection-background-color: {p['accent']};
	selection-color: {p['on_accent']};
	border: 1px solid {p['border']};
}}

QProgressBar {{
	background: {p['input_bg']};
	border: 1px solid {p['border']};
	border-radius: 8px;
	text-align: center;
	color: {p['text']};
	min-height: 18px;
}}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 7px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QFrame.lang-row {{
	background: {p['panel']};
	border: 1px solid {p['border']};
	border-radius: 10px;
}}

QCheckBox, QGroupBox {{ color: {p['text']}; }}
QGroupBox {{ border: 1px solid {p['border']}; border-radius: 10px; margin-top: 8px; padding: 8px; }}

QMessageBox, QDialog {{
	background-color: {p['dialog_bg']};
	border: 2px solid {p['accent2']};
	border-radius: 14px;
}}
QMessageBox QLabel, QDialog QLabel {{
	color: {p['dialog_text']};
	font-size: 15px;
	font-weight: bold;
}}

/* เมนู (รวมเมนูคลิกขวาที่ System Tray) — กำหนดพื้น/อักษรให้อ่านออกทุกธีม */
QMenu {{
	background-color: {p['dialog_bg']};
	color: {p['dialog_text']};
	border: 1px solid {p['border']};
	padding: 4px;
}}
QMenu::item {{
	padding: 8px 22px;
	background: transparent;
}}
QMenu::item:selected {{
	background-color: {p['accent']};
	color: {p['on_accent']};
	border-radius: 6px;
}}
QMenu::separator {{
	height: 1px;
	background: {p['border']};
	margin: 4px 8px;
}}
"""


# ---- นิยาม palette ของแต่ละธีม ----
_PALETTES = {
	"standard": {
		"bg1": "#022C22", "bg2": "#064E3B", "bg3": "#02381F",
		"pane": "rgba(6, 44, 27, 0.75)", "panel": "rgba(6, 78, 59, 0.35)",
		"border": "rgba(52, 211, 153, 0.25)", "accent": "#10B981", "accent2": "#34D399",
		"on_accent": "#FFFFFF", "text": "#ECFDF5", "text_dim": "#A7F3D0", "amber": "#FBBF24",
		"tab_bg": "rgba(255, 255, 255, 0.05)", "secondary_bg": "rgba(255,255,255,0.08)",
		"secondary_hover": "rgba(52,211,153,0.2)", "table_bg": "rgba(2, 44, 34, 0.6)",
		"header_bg": "rgba(6, 78, 59, 0.9)", "header_text": "#6EE7B7", "input_bg": "rgba(2,44,34,0.6)",
		"danger": "rgba(225, 29, 72, 0.9)", "dialog_bg": "#064E3B", "dialog_text": "#ECFDF5",
	},
	"light": {
		"bg1": "#F8FAFC", "bg2": "#EEF2F6", "bg3": "#E7ECF1",
		"pane": "#FFFFFF", "panel": "#FFFFFF",
		"border": "#CBD5E1", "accent": "#059669", "accent2": "#10B981",
		"on_accent": "#FFFFFF", "text": "#0F172A", "text_dim": "#475569", "amber": "#B45309",
		"tab_bg": "#E2E8F0", "secondary_bg": "#EEF2F6",
		"secondary_hover": "#10B981", "table_bg": "#FFFFFF",
		"header_bg": "#E2E8F0", "header_text": "#065F46", "input_bg": "#FFFFFF",
		"danger": "#DC2626", "dialog_bg": "#FFFFFF", "dialog_text": "#0F172A",
	},
	"dark": {
		"bg1": "#0B0F14", "bg2": "#111827", "bg3": "#0B0F14",
		"pane": "#111827", "panel": "#1F2937",
		"border": "#374151", "accent": "#3B82F6", "accent2": "#60A5FA",
		"on_accent": "#FFFFFF", "text": "#F3F4F6", "text_dim": "#9CA3AF", "amber": "#FBBF24",
		"tab_bg": "rgba(255,255,255,0.05)", "secondary_bg": "#374151",
		"secondary_hover": "#3B82F6", "table_bg": "#111827",
		"header_bg": "#1F2937", "header_text": "#93C5FD", "input_bg": "#1F2937",
		"danger": "#EF4444", "dialog_bg": "#1F2937", "dialog_text": "#F3F4F6",
	},
	"mono": {
		"bg1": "#FFFFFF", "bg2": "#F2F2F2", "bg3": "#E8E8E8",
		"pane": "#FFFFFF", "panel": "#FFFFFF",
		"border": "#222222", "accent": "#111111", "accent2": "#000000",
		"on_accent": "#FFFFFF", "text": "#111111", "text_dim": "#555555", "amber": "#000000",
		"tab_bg": "#E8E8E8", "secondary_bg": "#F2F2F2",
		"secondary_hover": "#111111", "table_bg": "#FFFFFF",
		"header_bg": "#111111", "header_text": "#FFFFFF", "input_bg": "#FFFFFF",
		"danger": "#000000", "dialog_bg": "#FFFFFF", "dialog_text": "#111111",
	},
}

# รายชื่อธีมสำหรับปุ่มเลือก (key, ชื่อไทย)
THEME_ORDER = [
	("standard", "🟢 มาตรฐาน"),
	("light", "☀️ สว่าง"),
	("dark", "🌙 เข้ม"),
	("mono", "⚫ ขาวดำ"),
]

# dialog สีปุ่ม Yes/No/Cancel ให้แยกกันชัด (ใช้ร่วมกับ themed message box)
BUTTON_COLORS = {
	"yes": "#16A34A",     # เขียว = ตกลง
	"no": "#DC2626",      # แดง = ไม่/ปิด
	"cancel": "#6B7280",  # เทา = ยกเลิก
}


def get_stylesheet(theme_key: str) -> str:
	palette = _PALETTES.get(theme_key, _PALETTES["standard"])
	return _build_stylesheet(palette)


def normalize_theme_key(value: str) -> str:
	return value if value in _PALETTES else "standard"
