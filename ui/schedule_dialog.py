import os
import shutil
from PySide6.QtWidgets import (
	QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTimeEdit,
	QLineEdit, QCheckBox, QComboBox, QGroupBox, QFileDialog, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, QTime
from tts_engine import VOICE_STYLES, normalize_langs
from ui.language_widget import LanguageSequenceWidget


def _save_with_translation(dialog):
	"""บันทึกหลังแปลภาษาเสร็จ: ภาษาที่ติ๊กไว้แต่ยังว่าง/พิมพ์ผิดภาษา จะถูกแปลก่อนบันทึก (เพื่อใช้ออฟไลน์ได้)
	ถ้าแปลไม่สำเร็จ (ไม่มีเน็ต) ก็ยังบันทึกได้ ระบบจะแปลให้อีกครั้งตอนเล่นเมื่อมีเน็ต
	dialog ต้องมี: lang_widget, btn_save, lbl_save_status, _saving, _translate_attempted
	"""
	widget = dialog.lang_widget
	if widget.is_busy() or (widget.needs_translation() and not dialog._translate_attempted):
		dialog._saving = True
		dialog.btn_save.setEnabled(False)
		dialog.lbl_save_status.setText("⏳ กำลังแปลภาษาก่อนบันทึก...")
		if not widget.is_busy():
			dialog._translate_attempted = True
			widget.translate_from_thai()
		return
	dialog.accept()


def _on_save_translation_finished(dialog):
	if dialog._saving:
		dialog._saving = False
		dialog.btn_save.setEnabled(True)
		dialog.lbl_save_status.setText("")
		_save_with_translation(dialog)


def parse_hms(time_str: str):
	"""แยกชั่วโมง นาที วินาที อย่างปลอดภัย 100%"""
	try:
		parts = str(time_str).split(":")
		h = int(parts[0]) if len(parts) > 0 else 0
		m = int(parts[1]) if len(parts) > 1 else 0
		s = int(parts[2]) if len(parts) > 2 else 0
		return h, m, s
	except Exception:
		return 0, 0, 0


class ScheduleFormDialog(QDialog):
	def __init__(self, sounds_dir, item_data=None, parent=None, preview_callback=None):
		super().__init__(parent)
		self.sounds_dir = sounds_dir
		self.item_data = item_data or {}
		self.preview_callback = preview_callback
		self._saving = False
		self._translate_attempted = False
		self.setWindowTitle("⚙️ กำหนดรายละเอียดตารางเวลาอ๊อด")
		self.resize(780, 820)

		outer = QVBoxLayout(self)
		scroll = QScrollArea()
		scroll.setWidgetResizable(True)
		scroll.setFrameShape(QScrollArea.NoFrame)
		content = QWidget()
		layout = QVBoxLayout(content)
		scroll.setWidget(content)
		outer.addWidget(scroll)

		group_time = QGroupBox("🕒 เวลาและรายละเอียดคาบเรียน")
		layout_time = QVBoxLayout(group_time)

		row1 = QHBoxLayout()
		row1.addWidget(QLabel("เลือกเวลา (ชั่วโมง:นาที:วินาที):"))
		self.time_edit = QTimeEdit()
		self.time_edit.setDisplayFormat("HH:mm:ss")
		if "time" in self.item_data and self.item_data["time"]:
			h, m, s = parse_hms(self.item_data["time"])
			self.time_edit.setTime(QTime(h, m, s))
		else:
			self.time_edit.setTime(QTime.currentTime())
		row1.addWidget(self.time_edit)
		layout_time.addLayout(row1)

		row2 = QHBoxLayout()
		row2.addWidget(QLabel("ชื่อคาบ / รายละเอียด:"))
		self.txt_label = QLineEdit(self.item_data.get("label", ""))
		self.txt_label.setPlaceholderText("เช่น เข้าแถวเคารพธงชาติ / เริ่มคาบที่ 1")
		row2.addWidget(self.txt_label)
		layout_time.addLayout(row2)
		layout.addWidget(group_time)

		group_days = QGroupBox("📅 วันที่เปิดใช้งาน")
		layout_days = QHBoxLayout(group_days)
		self.day_checkboxes = {}
		days_map = [("Mon", "จ"), ("Tue", "อ"), ("Wed", "พ"), ("Thu", "พฤ"), ("Fri", "ศ"), ("Sat", "ส"), ("Sun", "อา")]
		selected_days = self.item_data.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri"])
		for code, label in days_map:
			chk = QCheckBox(label)
			chk.setChecked(code in selected_days)
			self.day_checkboxes[code] = chk
			layout_days.addWidget(chk)
		layout.addWidget(group_days)

		group_audio = QGroupBox("🔊 กำหนดลำดับเสียง (Audio Sequence)")
		layout_audio = QVBoxLayout(group_audio)

		self.chk_pre_chime = QCheckBox("1️⃣ เล่นเสียงติ่งต่องนำหน้า (Pre-Chime)")
		self.chk_pre_chime.setChecked(self.item_data.get("pre_chime", True))

		self.chk_voice = QCheckBox("2️⃣ ขานเวลาอัตโนมัติ (ขานในทุกภาษาที่เลือก)")
		self.chk_voice.setChecked(self.item_data.get("voice_announce", True))

		self.chk_speak_text = QCheckBox("3️⃣ อ่านข้อความประกาศ (ตามภาษาและลำดับด้านล่าง)")
		self.chk_speak_text.setChecked(self.item_data.get("speak_text", self.item_data.get("voice_announce", True)))

		row_sound = QHBoxLayout()
		row_sound.addWidget(QLabel("4️⃣ เสียงต่อท้าย / เพลงชาติ:"))
		self.combo_custom_sound = QComboBox()
		self.combo_custom_sound.setMinimumWidth(200)
		btn_upload_sound = QPushButton("📤 อัปโหลดไฟล์ใหม่...")
		btn_upload_sound.setProperty("class", "secondary-btn")
		btn_upload_sound.clicked.connect(self.upload_new_sound_file)
		row_sound.addWidget(self.combo_custom_sound)
		row_sound.addWidget(btn_upload_sound)

		self.chk_post_chime = QCheckBox("5️⃣ เล่นเสียงติ่งต่องปิดท้าย (Post-Chime)")
		self.chk_post_chime.setChecked(self.item_data.get("post_chime", True))

		layout_audio.addWidget(self.chk_pre_chime)
		layout_audio.addWidget(self.chk_voice)
		layout_audio.addWidget(self.chk_speak_text)
		layout_audio.addLayout(row_sound)
		layout_audio.addWidget(self.chk_post_chime)
		layout.addWidget(group_audio)

		group_lang = QGroupBox("🌐 ภาษาประกาศ & เสียง AI (เสียงตามสายแบบสากล)")
		layout_lang = QVBoxLayout(group_lang)
		self.lang_widget = LanguageSequenceWidget(
			self.item_data.get("langs"),
			multiline=False,
			thai_source=lambda: self.txt_label.text(),
		)
		self.txt_label.textChanged.connect(self.lang_widget.set_thai_placeholder)
		self.lang_widget.set_thai_placeholder(self.txt_label.text())
		self.lang_widget.translation_finished.connect(self._on_translation_finished)
		layout_lang.addWidget(self.lang_widget)

		row_style = QHBoxLayout()
		row_style.addWidget(QLabel("🎙️ สไตล์เสียงผู้ประกาศ:"))
		self.combo_style = QComboBox()
		self.combo_style.addItem("⚙️ ตามค่าเริ่มต้นของระบบ", "")
		for key, name in VOICE_STYLES:
			self.combo_style.addItem(name, key)
		idx = self.combo_style.findData(self.item_data.get("voice_style", ""))
		self.combo_style.setCurrentIndex(max(0, idx))
		row_style.addWidget(self.combo_style)
		row_style.addStretch()
		if self.preview_callback:
			btn_preview = QPushButton("▶️ ทดลองฟังประกาศนี้")
			btn_preview.setProperty("class", "secondary-btn")
			btn_preview.clicked.connect(lambda: self.preview_callback(self.get_data()))
			row_style.addWidget(btn_preview)
		layout_lang.addLayout(row_style)
		layout.addWidget(group_lang)
		layout.addStretch()

		self.refresh_sound_dropdown(self.item_data.get("custom_sound", "ไม่มี"))

		btn_box = QHBoxLayout()
		self.lbl_save_status = QLabel("")
		self.lbl_save_status.setProperty("class", "muted")
		btn_cancel = QPushButton("ยกเลิก")
		btn_cancel.setProperty("class", "secondary-btn")
		btn_cancel.clicked.connect(self.reject)
		self.btn_save = QPushButton("💾 บันทึกข้อมูล")
		self.btn_save.setProperty("class", "primary-btn")
		self.btn_save.clicked.connect(self.save)
		btn_box.addWidget(self.lbl_save_status, 1)
		btn_box.addWidget(btn_cancel)
		btn_box.addWidget(self.btn_save)
		outer.addLayout(btn_box)

	def refresh_sound_dropdown(self, selected_filename="ไม่มี"):
		self.combo_custom_sound.clear()
		self.combo_custom_sound.addItem("ไม่มี")
		if os.path.exists(self.sounds_dir):
			files = sorted([f for f in os.listdir(self.sounds_dir) if f.lower().endswith(('.mp3', '.wav'))])
			for f in files:
				if f not in ["chime.mp3", "chime.wav", "voice_now_is.mp3", "voice_oclock.mp3"] and not f.startswith("temp_"):
					self.combo_custom_sound.addItem(f)
		idx = self.combo_custom_sound.findText(selected_filename)
		self.combo_custom_sound.setCurrentIndex(idx if idx >= 0 else 0)

	def upload_new_sound_file(self):
		file_path, _ = QFileDialog.getOpenFileName(self, "เลือกไฟล์เสียงต่อท้าย (MP3 หรือ WAV)", "", "Audio Files (*.mp3 *.wav)")
		if file_path:
			file_name = os.path.basename(file_path)
			shutil.copy(file_path, os.path.join(self.sounds_dir, file_name))
			self.refresh_sound_dropdown(selected_filename=file_name)

	def save(self):
		_save_with_translation(self)

	def _on_translation_finished(self, ok, error):
		_on_save_translation_finished(self)

	def get_data(self):
		active_days = [code for code, chk in self.day_checkboxes.items() if chk.isChecked()]
		return {
			"id": self.item_data.get("id", ""),
			"time": self.time_edit.time().toString("HH:mm:ss"),
			"label": self.txt_label.text() or "อ๊อดแจ้งเวลา",
			"pre_chime": self.chk_pre_chime.isChecked(),
			"voice_announce": self.chk_voice.isChecked(),
			"speak_text": self.chk_speak_text.isChecked(),
			"custom_sound": self.combo_custom_sound.currentText(),
			"post_chime": self.chk_post_chime.isChecked(),
			"days": active_days if active_days else ["Mon", "Tue", "Wed", "Thu", "Fri"],
			"enabled": self.item_data.get("enabled", True),
			"langs": normalize_langs(self.lang_widget.get_langs()),
			"voice_style": self.combo_style.currentData() or "",
		}


class LanguageEditDialog(QDialog):
	"""แก้ภาษาของรายการในตารางแบบเร็ว: ติ๊กภาษา / สลับลำดับ / จำนวนรอบ / สไตล์เสียง (เปิดจากคอลัมน์ภาษา)"""

	def __init__(self, item, parent=None, preview_callback=None):
		super().__init__(parent)
		self.item = dict(item)
		self.preview_callback = preview_callback
		self._saving = False
		self._translate_attempted = False
		self.setWindowTitle(f"🌐 ภาษาประกาศ — {item.get('time', '')} {item.get('label', '')}")
		self.resize(820, 420)

		layout = QVBoxLayout(self)
		title = QLabel(f"⏰ {item.get('time', '')}   {item.get('label', '')}")
		title.setProperty("class", "title")
		layout.addWidget(title)

		self.lang_widget = LanguageSequenceWidget(
			item.get("langs"),
			multiline=False,
			thai_source=lambda: self.item.get("label", ""),
		)
		self.lang_widget.set_thai_placeholder(item.get("label", ""))
		self.lang_widget.translation_finished.connect(lambda ok, err: _on_save_translation_finished(self))
		layout.addWidget(self.lang_widget)

		row_style = QHBoxLayout()
		row_style.addWidget(QLabel("🎙️ สไตล์เสียงผู้ประกาศ:"))
		self.combo_style = QComboBox()
		self.combo_style.addItem("⚙️ ตามค่าเริ่มต้นของระบบ", "")
		for key, name in VOICE_STYLES:
			self.combo_style.addItem(name, key)
		self.combo_style.setCurrentIndex(max(0, self.combo_style.findData(item.get("voice_style", ""))))
		row_style.addWidget(self.combo_style)
		row_style.addStretch()
		layout.addLayout(row_style)
		layout.addStretch()

		btn_box = QHBoxLayout()
		self.lbl_save_status = QLabel("")
		self.lbl_save_status.setProperty("class", "muted")
		btn_box.addWidget(self.lbl_save_status, 1)
		if preview_callback:
			btn_preview = QPushButton("▶️ ทดลองฟัง")
			btn_preview.setProperty("class", "secondary-btn")
			btn_preview.clicked.connect(lambda: self.preview_callback(self.get_item()))
			btn_box.addWidget(btn_preview)
		btn_cancel = QPushButton("ยกเลิก")
		btn_cancel.setProperty("class", "secondary-btn")
		btn_cancel.clicked.connect(self.reject)
		self.btn_save = QPushButton("💾 บันทึก")
		self.btn_save.setProperty("class", "primary-btn")
		self.btn_save.clicked.connect(lambda: _save_with_translation(self))
		btn_box.addWidget(btn_cancel)
		btn_box.addWidget(self.btn_save)
		layout.addLayout(btn_box)

	def get_item(self):
		data = dict(self.item)
		data["langs"] = normalize_langs(self.lang_widget.get_langs())
		data["voice_style"] = self.combo_style.currentData() or ""
		return data
