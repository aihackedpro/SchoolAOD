"""คอมโพเนนต์เลือกภาษาประกาศ: ติ๊กภาษาที่จะอ่าน + จัดลำดับการอ่าน + จำนวนรอบทวน + แปลอัตโนมัติ

การแปลอัตโนมัติ:
- ช่องว่าง → แปลจากข้อความภาษาไทย (หรือชื่อคาบ)
- พิมพ์ภาษาไม่ตรงช่อง (เช่น พิมพ์ไทยในช่องจีน) → แปลเป็นภาษาของช่องทันทีเมื่อพิมพ์เสร็จ
- พิมพ์ภาษาตรงช่องอยู่แล้ว → ใช้ตามที่พิมพ์ ไม่แปลทับ
"""
import threading
from PySide6.QtWidgets import (
	QWidget, QFrame, QVBoxLayout, QHBoxLayout, QCheckBox, QLineEdit, QPlainTextEdit,
	QSpinBox, QPushButton, QLabel, QStyle
)
from PySide6.QtCore import Qt, Signal, QObject, QEvent, QSize, QLocale
from tts_engine import LANG_NAME, LANG_LABEL, MAX_REPEAT, normalize_langs
from translator import translate, detect_lang

_PLACEHOLDER = {
	"th": "ข้อความภาษาไทย",
	"en": "ว่างไว้ = แปลจากภาษาไทยให้อัตโนมัติ • พิมพ์ไทยได้ ระบบจะแปลเป็นอังกฤษ",
	"zh": "ว่างไว้ = แปลจากภาษาไทยให้อัตโนมัติ • พิมพ์ไทยได้ ระบบจะแปลเป็นจีน",
}


class _TranslateBridge(QObject):
	done = Signal(dict, str)   # {code: คำแปล}, ข้อความ error


class RepeatControl(QWidget):
	"""ตัวเลือกจำนวนรอบ [−] 2 [+] — ปุ่มใหญ่กดง่าย พิมพ์ตัวเลขได้
	บังคับใช้เลขอารบิก: Windows ภาษาไทยทำให้ช่องตัวเลขแสดงเลขไทย (๑) และพิมพ์เลข 1-9 ไม่ได้
	"""

	def __init__(self, value=1, parent=None):
		super().__init__(parent)
		row = QHBoxLayout(self)
		row.setContentsMargins(0, 0, 0, 0)
		row.setSpacing(4)

		self.spin = QSpinBox()
		self.spin.setLocale(QLocale.c())
		self.spin.setRange(1, MAX_REPEAT)
		self.spin.setValue(value)
		self.spin.setButtonSymbols(QSpinBox.NoButtons)
		self.spin.setAlignment(Qt.AlignCenter)
		self.spin.setFixedWidth(52)
		self.spin.setToolTip(f"จำนวนรอบที่อ่านภาษานี้ (1–{MAX_REPEAT}) พิมพ์ตัวเลขได้")

		self.btn_minus = self._step_button("−", -1)
		self.btn_plus = self._step_button("+", 1)
		lbl_pre, lbl_post = QLabel("อ่าน"), QLabel("รอบ")
		row.addWidget(lbl_pre)
		row.addWidget(self.btn_minus)
		row.addWidget(self.spin)
		row.addWidget(self.btn_plus)
		row.addWidget(lbl_post)

	def _step_button(self, text, delta):
		btn = QPushButton(text)
		btn.setFixedSize(34, 34)
		btn.setCursor(Qt.PointingHandCursor)
		btn.setStyleSheet("padding: 0px; font-size: 18px; font-weight: bold;")
		btn.clicked.connect(lambda: self.spin.setValue(self.spin.value() + delta))
		return btn

	def value(self):
		self.spin.interpretText()   # ใช้ค่าที่พิมพ์ค้างไว้ด้วย แม้ยังไม่กด Enter
		return self.spin.value()

	def setValue(self, value):
		self.spin.setValue(value)


class LanguageRow(QFrame):
	move_requested = Signal(object, int)
	text_committed = Signal(object)   # พิมพ์เสร็จ (ออกจากช่อง/กด Enter)

	def __init__(self, entry, multiline=False, reorderable=True, parent=None):
		super().__init__(parent)
		self.code = entry["code"]
		self.setProperty("class", "lang-row")

		row = QHBoxLayout(self)
		row.setContentsMargins(8, 4, 8, 4)
		row.setSpacing(8)

		self.chk = QCheckBox(LANG_LABEL[self.code])
		self.chk.setChecked(entry["enabled"])
		self.chk.setMinimumWidth(130)
		self.chk.setCursor(Qt.PointingHandCursor)

		if multiline:
			self.edit = QPlainTextEdit()
			self.edit.setFixedHeight(64)
			self.edit.setPlainText(entry["text"])
			self.edit.installEventFilter(self)
		else:
			self.edit = QLineEdit(entry["text"])
			self.edit.editingFinished.connect(lambda: self.text_committed.emit(self))
		self.edit.setPlaceholderText(_PLACEHOLDER[self.code])

		self.spin = RepeatControl(entry["repeat"])

		row.addWidget(self.chk)
		row.addWidget(self.edit, 1)
		row.addWidget(self.spin)

		self.btn_up = self.btn_down = None
		if reorderable:
			style = self.style()
			self.btn_up = self._arrow_button(style.standardIcon(QStyle.SP_ArrowUp), "ย้ายขึ้น (อ่านก่อน)", -1)
			self.btn_down = self._arrow_button(style.standardIcon(QStyle.SP_ArrowDown), "ย้ายลง (อ่านทีหลัง)", 1)
			row.addWidget(self.btn_up)
			row.addWidget(self.btn_down)

		self.chk.toggled.connect(self._sync_enabled)
		self._sync_enabled(self.chk.isChecked())

	def _arrow_button(self, icon, tip, delta):
		btn = QPushButton()
		btn.setIcon(icon)
		btn.setIconSize(QSize(18, 18))
		btn.setFixedSize(38, 34)
		btn.setToolTip(tip)
		btn.setCursor(Qt.PointingHandCursor)
		btn.setStyleSheet("padding: 2px;")
		btn.clicked.connect(lambda: self.move_requested.emit(self, delta))
		return btn

	def eventFilter(self, obj, event):
		if obj is self.edit and event.type() == QEvent.FocusOut:
			self.text_committed.emit(self)
		return super().eventFilter(obj, event)

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

	def __init__(self, langs=None, multiline=False, thai_source=None, reorderable=True, parent=None):
		"""thai_source: ฟังก์ชันคืนข้อความไทยสำรอง (เช่น ชื่อคาบ) เมื่อช่องภาษาไทยว่าง"""
		super().__init__(parent)
		self.multiline = multiline
		self.reorderable = reorderable
		self.thai_source = thai_source
		self.rows = []
		self._busy = False

		self._bridge = _TranslateBridge()
		self._bridge.done.connect(self._on_translated)

		outer = QVBoxLayout(self)
		outer.setContentsMargins(0, 0, 0, 0)
		outer.setSpacing(4)

		hint_text = "ติ๊กภาษาที่ต้องการให้อ่าน • พิมพ์ภาษาไทยลงช่องไหนก็ได้ ระบบแปลเป็นภาษาของช่องนั้นให้เอง"
		if reorderable:
			hint_text += " • อ่านจากแถวบนลงล่าง ใช้ปุ่มลูกศรสลับลำดับ"
		hint_text += " • อ่านเป็นรอบ: รอบแรกอ่านครบทุกภาษาก่อน แล้วค่อยวนรอบถัดไปเฉพาะภาษาที่ตั้งไว้หลายรอบ"
		hint = QLabel(hint_text)
		hint.setProperty("class", "muted")
		hint.setWordWrap(True)
		hint.setStyleSheet("font-size: 12px;")
		outer.addWidget(hint)

		self.rows_box = QVBoxLayout()
		self.rows_box.setSpacing(4)
		outer.addLayout(self.rows_box)

		tool = QHBoxLayout()
		self.btn_translate = QPushButton("🌐 แปลอัตโนมัติ (เติมช่องที่ว่าง / แปลงช่องที่พิมพ์ผิดภาษา)")
		self.btn_translate.setProperty("class", "secondary-btn")
		self.btn_translate.setCursor(Qt.PointingHandCursor)
		self.btn_translate.setToolTip("ช่องที่พิมพ์ถูกภาษาอยู่แล้วจะไม่ถูกแปลทับ • ลบข้อความในช่องออกถ้าต้องการให้แปลใหม่")
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
			row = LanguageRow(entry, self.multiline, self.reorderable)
			row.move_requested.connect(self._move_row)
			row.text_committed.connect(self._on_row_committed)
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

	def is_busy(self):
		return self._busy

	def needs_translation(self):
		"""มีภาษาที่ติ๊กไว้แต่ยังว่าง หรือพิมพ์ไม่ตรงภาษาของช่อง"""
		for row in self.rows:
			e = row.entry()
			if not e["enabled"]:
				continue
			if (not e["text"] and e["code"] != "th") or (e["text"] and detect_lang(e["text"]) != e["code"]):
				return True
		return False

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
			if row.btn_up:
				row.btn_up.setEnabled(i > 0)
				row.btn_down.setEnabled(i < len(self.rows) - 1)

	# ---- แปลภาษา ----
	def _on_row_committed(self, row):
		"""พิมพ์เสร็จในช่องใด แล้วภาษาไม่ตรงกับช่อง → แปลเฉพาะช่องนั้นให้ทันที"""
		text = row.text().strip()
		if text and detect_lang(text) != row.code and not self._busy:
			self._start_translation({row.code: text})

	def translate_from_thai(self):
		"""เติมช่องที่ว่าง (แปลจากภาษาไทย) และแปลงช่องที่พิมพ์ผิดภาษา — ช่องที่ถูกภาษาอยู่แล้วไม่แตะ"""
		source = self.thai_text()
		jobs = {}
		for row in self.rows:
			e = row.entry()
			if not e["enabled"]:
				continue
			if e["text"]:
				if detect_lang(e["text"]) != e["code"]:
					jobs[e["code"]] = e["text"]
			elif e["code"] != "th" and source:
				jobs[e["code"]] = source
		if not jobs:
			self.lbl_status.setText("✅ ทุกภาษาที่เลือกพร้อมแล้ว" if source else "⚠️ กรุณาพิมพ์ข้อความภาษาไทยก่อน")
			self.translation_finished.emit(bool(source), "" if source else "ไม่มีข้อความ")
			return
		self._start_translation(jobs)

	def _start_translation(self, jobs):
		"""jobs: {รหัสภาษาปลายทาง: ข้อความต้นฉบับ}"""
		self._busy = True
		self.btn_translate.setEnabled(False)
		self.lbl_status.setText("⏳ กำลังแปล...")

		def worker():
			results, errors = {}, []
			for code, text in jobs.items():
				out = translate(text, code)
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
		self._busy = False
		self.btn_translate.setEnabled(True)
		ok = bool(results) and not error
		names = ", ".join(LANG_NAME[c] for c in results)
		self.lbl_status.setText(f"✅ แปลเป็น {names} แล้ว (แก้ไขคำแปลได้)" if ok else f"⚠️ {error}")
		self.translation_finished.emit(ok, error)
