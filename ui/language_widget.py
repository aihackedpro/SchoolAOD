"""คอมโพเนนต์เลือกภาษาประกาศ: ติ๊กภาษาที่จะอ่าน + จัดลำดับการอ่าน (▲▼) + จำนวนรอบทวน + แปลอัตโนมัติ"""
import threading
from PySide6.QtWidgets import (
	QWidget, QFrame, QVBoxLayout, QHBoxLayout, QCheckBox, QLineEdit, QPlainTextEdit,
	QSpinBox, QPushButton, QLabel
)
from PySide6.QtCore import Qt, Signal, QObject
from tts_engine import LANG_NAME, LANG_FLAG, normalize_langs
from translator import translate

_PLACEHOLDER = {
	"th": "ข้อความภาษาไทย",
	"en": "English text (กด 'แปลอัตโนมัติ' เพื่อแปลจากภาษาไทย)",
	"zh": "中文内容（กด 'แปลอัตโนมัติ' เพื่อแปลจากภาษาไทย）",
}


class _TranslateBridge(QObject):
	done = Signal(dict, str)   # {code: คำแปล}, ข้อความ error


class LanguageRow(QFrame):
	move_requested = Signal(object, int)

	def __init__(self, entry, multiline=False, parent=None):
		super().__init__(parent)
		self.code = entry["code"]
		self.setProperty("class", "lang-row")

		row = QHBoxLayout(self)
		row.setContentsMargins(8, 4, 8, 4)
		row.setSpacing(8)

		self.chk = QCheckBox(f"{LANG_FLAG[self.code]}  {LANG_NAME[self.code]}")
		self.chk.setChecked(entry["enabled"])
		self.chk.setMinimumWidth(110)
		self.chk.setCursor(Qt.PointingHandCursor)

		if multiline:
			self.edit = QPlainTextEdit()
			self.edit.setFixedHeight(64)
			self.edit.setPlainText(entry["text"])
		else:
			self.edit = QLineEdit(entry["text"])
		self.edit.setPlaceholderText(_PLACEHOLDER[self.code])

		self.spin = QSpinBox()
		self.spin.setRange(1, 5)
		self.spin.setValue(entry["repeat"])
		self.spin.setPrefix("ทวน ")
		self.spin.setSuffix(" รอบ")
		self.spin.setToolTip("จำนวนรอบที่จะอ่านภาษานี้ (1 = ไม่ทวน)")

		self.btn_up = QPushButton("▲")
		self.btn_down = QPushButton("▼")
		for btn, delta, tip in ((self.btn_up, -1, "ย้ายขึ้น (อ่านก่อน)"), (self.btn_down, 1, "ย้ายลง (อ่านทีหลัง)")):
			btn.setFixedWidth(34)
			btn.setToolTip(tip)
			btn.setCursor(Qt.PointingHandCursor)
			btn.setProperty("class", "secondary-btn")
			btn.clicked.connect(lambda _, d=delta: self.move_requested.emit(self, d))

		self.chk.toggled.connect(self._sync_enabled)

		row.addWidget(self.chk)
		row.addWidget(self.edit, 1)
		row.addWidget(self.spin)
		row.addWidget(self.btn_up)
		row.addWidget(self.btn_down)
		self._sync_enabled(self.chk.isChecked())

	def _sync_enabled(self, on):
		self.edit.setEnabled(on)
		self.spin.setEnabled(on)

	def text(self):
		return self.edit.toPlainText() if isinstance(self.edit, QPlainTextEdit) else self.edit.text()

	def set_text(self, value):
		if isinstance(self.edit, QPlainTextEdit):
			self.edit.setPlainText(value)
		else:
			self.edit.setText(value)

	def entry(self):
		return {"code": self.code, "enabled": self.chk.isChecked(), "text": self.text().strip(), "repeat": self.spin.value()}


class LanguageSequenceWidget(QWidget):
	"""รายการภาษาตามลำดับการอ่าน — แถวบนสุดอ่านก่อน"""
	translation_finished = Signal(bool, str)

	def __init__(self, langs=None, multiline=False, thai_source=None, parent=None):
		"""thai_source: ฟังก์ชันคืนข้อความไทยสำรอง (เช่น ชื่อคาบ) เมื่อช่องภาษาไทยว่าง"""
		super().__init__(parent)
		self.multiline = multiline
		self.thai_source = thai_source
		self.rows = []

		self._bridge = _TranslateBridge()
		self._bridge.done.connect(self._on_translated)

		outer = QVBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		outer.setSpacing(4)

		hint = QLabel("ติ๊กภาษาที่ต้องการให้อ่าน • ระบบอ่านจากแถวบนลงล่าง ใช้ ▲▼ สลับลำดับ")
		hint.setProperty("class", "muted")
		hint.setStyleSheet("font-size: 12px;")
		outer.addWidget(hint)

		self.rows_box = QVBoxLayout()
		self.rows_box.setSpacing(4)
		outer.addLayout(self.rows_box)

		tool = QHBoxLayout()
		self.btn_translate = QPushButton("🌐 แปลอัตโนมัติจากภาษาไทย → English / 中文")
		self.btn_translate.setProperty("class", "secondary-btn")
		self.btn_translate.setCursor(Qt.PointingHandCursor)
		self.btn_translate.clicked.connect(self.translate_from_thai)
		self.lbl_status = QLabel("")
		self.lbl_status.setProperty("class", "muted")
		self.lbl_status.setStyleSheet("font-size: 12px;")
		tool.addWidget(self.btn_translate)
		tool.addWidget(self.lbl_status, 1)
		outer.addLayout(tool)

		self.set_langs(langs)

	# ---- ข้อมูล ----
	def set_langs(self, langs):
		for row in self.rows:
			self.rows_box.removeWidget(row)
			row.deleteLater()
		self.rows = []
		for entry in normalize_langs(langs):
			row = LanguageRow(entry, self.multiline)
			row.move_requested.connect(self._move_row)
			self.rows.append(row)
			self.rows_box.addWidget(row)
		self._refresh_arrows()

	def get_langs(self):
		return [row.entry() for row in self.rows]

	def row_for(self, code):
		return next((r for r in self.rows if r.code == code), None)

	def set_thai_placeholder(self, text):
		row = self.row_for("th")
		if row and text:
			row.edit.setPlaceholderText(f"ว่างไว้ = อ่าน \"{text}\"")

	def thai_text(self):
		row = self.row_for("th")
		text = row.text().strip() if row else ""
		if not text and self.thai_source:
			text = (self.thai_source() or "").strip()
		return text

	# ---- จัดลำดับ ----
	def _move_row(self, row, delta):
		idx = self.rows.index(row)
		new_idx = idx + delta
		if not (0 <= new_idx < len(self.rows)):
			return
		self.rows[idx], self.rows[new_idx] = self.rows[new_idx], self.rows[idx]
		for r in self.rows:
			self.rows_box.removeWidget(r)
		for r in self.rows:
			self.rows_box.addWidget(r)
		self._refresh_arrows()

	def _refresh_arrows(self):
		for i, row in enumerate(self.rows):
			row.btn_up.setEnabled(i > 0)
			row.btn_down.setEnabled(i < len(self.rows) - 1)

	# ---- แปลภาษา ----
	def translate_from_thai(self):
		source = self.thai_text()
		if not source:
			self.lbl_status.setText("⚠️ กรุณาพิมพ์ข้อความภาษาไทยก่อน")
			return
		self.btn_translate.setEnabled(False)
		self.lbl_status.setText("⏳ กำลังแปล...")

		def worker():
			results, errors = {}, []
			for code in ("en", "zh"):
				out = translate(source, code, "th")
				if out:
					results[code] = out
				else:
					errors.append(LANG_NAME[code])
			msg = ("แปลไม่สำเร็จ: " + ", ".join(errors) + " (ตรวจสอบอินเทอร์เน็ต)") if errors else ""
			self._bridge.done.emit(results, msg)

		threading.Thread(target=worker, daemon=True).start()

	def _on_translated(self, results, error):
		for code, text in results.items():
			row = self.row_for(code)
			if row:
				row.set_text(text)
		self.btn_translate.setEnabled(True)
		ok = bool(results) and not error
		self.lbl_status.setText("✅ แปลเรียบร้อย (แก้ไขคำแปลได้)" if ok else f"⚠️ {error}")
		self.translation_finished.emit(ok, error)
