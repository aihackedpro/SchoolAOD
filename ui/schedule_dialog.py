import os
import shutil
from PySide6.QtWidgets import (
	QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTimeEdit,
	QLineEdit, QCheckBox, QComboBox, QGroupBox, QFileDialog
)
from PySide6.QtCore import Qt, QTime


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
	def __init__(self, sounds_dir, item_data=None, parent=None):
		super().__init__(parent)
		self.sounds_dir = sounds_dir
		self.item_data = item_data or {}
		self.setWindowTitle("⚙️ กำหนดรายละเอียดตารางเวลาอ๊อด")
		self.resize(560, 540)

		layout = QVBoxLayout(self)

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

		self.chk_voice = QCheckBox("2️⃣ ขานเวลาอัตโนมัติ (ขานเฉพาะชั่วโมงและนาที)")
		self.chk_voice.setChecked(self.item_data.get("voice_announce", True))

		row_sound = QHBoxLayout()
		row_sound.addWidget(QLabel("3️⃣ เสียงต่อท้าย / เพลงชาติ:"))
		self.combo_custom_sound = QComboBox()
		self.combo_custom_sound.setMinimumWidth(200)

		btn_upload_sound = QPushButton("📤 อัปโหลดไฟล์ใหม่...")
		btn_upload_sound.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 5px 12px; border-radius: 6px;")
		btn_upload_sound.clicked.connect(self.upload_new_sound_file)

		row_sound.addWidget(self.combo_custom_sound)
		row_sound.addWidget(btn_upload_sound)

		self.chk_post_chime = QCheckBox("4️⃣ เล่นเสียงติ่งต่องปิดท้าย (Post-Chime)")
		self.chk_post_chime.setChecked(self.item_data.get("post_chime", True))

		layout_audio.addWidget(self.chk_pre_chime)
		layout_audio.addWidget(self.chk_voice)
		layout_audio.addLayout(row_sound)
		layout_audio.addWidget(self.chk_post_chime)

		layout.addWidget(group_audio)

		self.refresh_sound_dropdown(self.item_data.get("custom_sound", "ไม่มี"))

		btn_box = QHBoxLayout()
		btn_cancel = QPushButton("ยกเลิก")
		btn_cancel.clicked.connect(self.reject)

		btn_save = QPushButton("💾 บันทึกข้อมูล")
		btn_save.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 10px;")
		btn_save.clicked.connect(self.accept)

		btn_box.addWidget(btn_cancel)
		btn_box.addWidget(btn_save)
		layout.addLayout(btn_box)

	def refresh_sound_dropdown(self, selected_filename="ไม่มี"):
		self.combo_custom_sound.clear()
		self.combo_custom_sound.addItem("ไม่มี")

		if os.path.exists(self.sounds_dir):
			files = sorted([f for f in os.listdir(self.sounds_dir) if f.lower().endswith(('.mp3', '.wav'))])
			for f in files:
				if f not in ["chime.mp3", "chime.wav", "voice_now_is.mp3", "voice_oclock.mp3"] and not f.startswith("temp_"):
					self.combo_custom_sound.addItem(f)

		idx = self.combo_custom_sound.findText(selected_filename)
		if idx >= 0:
			self.combo_custom_sound.setCurrentIndex(idx)
		else:
			self.combo_custom_sound.setCurrentIndex(0)

	def upload_new_sound_file(self):
		file_path, _ = QFileDialog.getOpenFileName(self, "เลือกไฟล์เสียงต่อท้าย (MP3 หรือ WAV)", "", "Audio Files (*.mp3 *.wav)")
		if file_path:
			file_name = os.path.basename(file_path)
			dest_path = os.path.join(self.sounds_dir, file_name)
			shutil.copy(file_path, dest_path)
			self.refresh_sound_dropdown(selected_filename=file_name)

	def get_data(self):
		active_days = [code for code, chk in self.day_checkboxes.items() if chk.isChecked()]
		return {
			"id": self.item_data.get("id", ""),
			"time": self.time_edit.time().toString("HH:mm:ss"),
			"label": self.txt_label.text() or "อ๊อดแจ้งเวลา",
			"pre_chime": self.chk_pre_chime.isChecked(),
			"voice_announce": self.chk_voice.isChecked(),
			"custom_sound": self.combo_custom_sound.currentText(),
			"post_chime": self.chk_post_chime.isChecked(),
			"days": active_days if active_days else ["Mon", "Tue", "Wed", "Thu", "Fri"],
			"enabled": self.item_data.get("enabled", True)
		}
