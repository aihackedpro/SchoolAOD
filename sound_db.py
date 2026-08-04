import os
import sqlite3
from datetime import datetime
from paths import data_path

# Local database (SQLite) สำหรับจัดการรายการไฟล์เสียงในระบบ
# เก็บ metadata ของไฟล์เสียง และคอยซิงก์ให้ตรงกับไฟล์จริงในโฟลเดอร์ sounds/

DB_FILE = data_path("sounds.db")

# ไฟล์ระบบที่ห้ามลบ/แก้ (ใช้ภายในเครื่องเสียง)
PROTECTED_FILES = {"chime.mp3", "chime.wav", "temp_live_voice.mp3", "temp_label_voice.mp3"}


class SoundDatabase:
	def __init__(self, sounds_dir=None, db_path=None):
		self.sounds_dir = sounds_dir or data_path("sounds")
		self.db_path = db_path or DB_FILE
		os.makedirs(self.sounds_dir, exist_ok=True)
		self._purge_temp_broadcasts()
		self._init_db()
		self.sync_with_folder()

	def _purge_temp_broadcasts(self):
		"""ลบไฟล์เสียงพูดสดชั่วคราวเก่า ๆ ที่ค้างไว้ กันไม่ให้รกโฟลเดอร์"""
		try:
			for f in os.listdir(self.sounds_dir):
				if f.startswith("temp_live_broadcast_"):
					os.remove(os.path.join(self.sounds_dir, f))
		except Exception:
			pass

	def _connect(self):
		conn = sqlite3.connect(self.db_path)
		conn.row_factory = sqlite3.Row
		return conn

	def _init_db(self):
		with self._connect() as conn:
			conn.execute("""
				CREATE TABLE IF NOT EXISTS sounds (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					filename TEXT UNIQUE NOT NULL,
					display_name TEXT NOT NULL,
					created_at TEXT NOT NULL
				)
			""")
			conn.commit()

	def sync_with_folder(self):
		"""ทำให้ฐานข้อมูลตรงกับไฟล์จริงในโฟลเดอร์เสมอ (ไฟล์หาย = ลบออกจาก DB, ไฟล์ใหม่ = เพิ่มเข้า DB)"""
		disk_files = set()
		if os.path.exists(self.sounds_dir):
			for f in os.listdir(self.sounds_dir):
				# ข้ามไฟล์ระบบและไฟล์ชั่วคราว (ขึ้นต้นด้วย temp_) ไม่ให้โผล่ในตัวจัดการไฟล์เสียง
				if f.lower().endswith((".mp3", ".wav")) and f not in PROTECTED_FILES and not f.startswith("temp_"):
					disk_files.add(f)

		with self._connect() as conn:
			db_files = {row["filename"] for row in conn.execute("SELECT filename FROM sounds")}

			# เพิ่มไฟล์ใหม่ที่มีในดิสก์แต่ยังไม่มีใน DB
			for f in disk_files - db_files:
				conn.execute(
					"INSERT OR IGNORE INTO sounds (filename, display_name, created_at) VALUES (?, ?, ?)",
					(f, os.path.splitext(f)[0], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
				)

			# ลบรายการที่ไฟล์จริงหายไปแล้ว
			for f in db_files - disk_files:
				conn.execute("DELETE FROM sounds WHERE filename = ?", (f,))

			conn.commit()

	def list_sounds(self):
		self.sync_with_folder()
		with self._connect() as conn:
			rows = conn.execute("SELECT id, filename, display_name, created_at FROM sounds ORDER BY display_name COLLATE NOCASE").fetchall()
			return [dict(r) for r in rows]

	def add_sound(self, src_path):
		"""คัดลอกไฟล์เสียงเข้าระบบ + บันทึกลง DB คืนค่าชื่อไฟล์ปลายทาง"""
		import shutil
		filename = os.path.basename(src_path)
		dest_path = os.path.join(self.sounds_dir, filename)
		shutil.copy(src_path, dest_path)
		with self._connect() as conn:
			conn.execute(
				"INSERT OR REPLACE INTO sounds (filename, display_name, created_at) VALUES (?, ?, ?)",
				(filename, os.path.splitext(filename)[0], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
			)
			conn.commit()
		return filename

	def rename_display(self, sound_id, new_display_name):
		"""แก้ชื่อที่แสดง (ไม่แตะชื่อไฟล์จริง เพื่อไม่ให้ตารางเวลาที่อ้างชื่อไฟล์พัง)"""
		new_display_name = (new_display_name or "").strip()
		if not new_display_name:
			return False
		with self._connect() as conn:
			conn.execute("UPDATE sounds SET display_name = ? WHERE id = ?", (new_display_name, sound_id))
			conn.commit()
		return True

	def delete_sound(self, sound_id):
		"""ลบทั้งไฟล์จริงและระเบียนใน DB คืนค่าชื่อไฟล์ที่ลบ (หรือ None)"""
		with self._connect() as conn:
			row = conn.execute("SELECT filename FROM sounds WHERE id = ?", (sound_id,)).fetchone()
			if not row:
				return None
			filename = row["filename"]
			if filename in PROTECTED_FILES:
				return None
			conn.execute("DELETE FROM sounds WHERE id = ?", (sound_id,))
			conn.commit()

		file_path = os.path.join(self.sounds_dir, filename)
		try:
			if os.path.exists(file_path):
				os.remove(file_path)
		except Exception as e:
			print(f"[SoundDB] ลบไฟล์ไม่สำเร็จ: {e}")
		return filename

	def get_filename(self, sound_id):
		with self._connect() as conn:
			row = conn.execute("SELECT filename FROM sounds WHERE id = ?", (sound_id,)).fetchone()
			return row["filename"] if row else None
