import json
import os
from datetime import datetime, timedelta
from PySide6.QtCore import QObject, Signal, QTimer
from paths import data_path
from tts_engine import normalize_schedule_item

DAY_MAP_SHORT = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

class SchoolScheduler(QObject):
	bell_triggered = Signal(dict)
	schedules_changed = Signal()   # บันทึกตารางแล้ว (ใช้สั่งเตรียมเสียง AI ล่วงหน้าใหม่)

	def __init__(self, audio_engine, json_path=None):
		super().__init__()
		self.audio_engine = audio_engine
		self.json_path = json_path or data_path("schedules.json")
		self.schedules = []
		self.operating_start = "00:00:00"
		self.operating_end = "23:59:59"
		self.last_triggered_key = ""

		self.load_schedules()

		self.watchdog_timer = QTimer(self)
		self.watchdog_timer.timeout.connect(self._check_schedule_watchdog)
		self.watchdog_timer.start(1000)

	def normalize_time_str(self, t_str):
		if not t_str:
			return "00:00:00"
		try:
			parts = [p.strip() for p in str(t_str).split(":")]
			h = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
			m = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
			s = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
			return f"{h:02d}:{m:02d}:{s:02d}"
		except Exception:
			return "00:00:00"

	def sort_schedules_by_time(self):
		for item in self.schedules:
			item["time"] = self.normalize_time_str(item.get("time", "00:00:00"))
			normalize_schedule_item(item)
		self.schedules.sort(key=lambda x: x.get("time", "00:00:00"))

	def load_schedules(self):
		if os.path.exists(self.json_path):
			try:
				with open(self.json_path, "r", encoding="utf-8") as f:
					data = json.load(f)
					if isinstance(data, dict):
						self.schedules = data.get("schedules", [])
					else:
						self.schedules = data
			except Exception:
				self.schedules = []

		if not self.schedules:
			self.load_default_school_template()

		self.sort_schedules_by_time()

	def load_default_school_template(self):
		self.schedules = [
			{"id": "1", "time": "07:00:00", "label": "ทำความสะอาดอาคารเรียนและเขตอภัยทาน", "pre_chime": True, "voice_announce": True, "custom_sound": "ไม่มี", "post_chime": False, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True},
			{"id": "2", "time": "08:00:00", "label": "เพลงชาติไทย / เคารพธงชาติ", "pre_chime": True, "voice_announce": True, "custom_sound": "national_anthem.mp3", "post_chime": True, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True},
			{"id": "3", "time": "08:05:00", "label": "เตรียมเข้าแถวเคารพธงชาติและโฮมรูม", "pre_chime": True, "voice_announce": True, "custom_sound": "ไม่มี", "post_chime": False, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True},
			{"id": "4", "time": "08:30:00", "label": "เข้าห้องเรียน คาบเรียนที่ 1", "pre_chime": True, "voice_announce": True, "custom_sound": "ไม่มี", "post_chime": False, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True},
			{"id": "5", "time": "09:30:00", "label": "เริ่มคาบเรียนที่ 2", "pre_chime": True, "voice_announce": True, "custom_sound": "ไม่มี", "post_chime": False, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True},
			{"id": "6", "time": "10:30:00", "label": "เริ่มคาบเรียนที่ 3", "pre_chime": True, "voice_announce": True, "custom_sound": "ไม่มี", "post_chime": False, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True},
			{"id": "7", "time": "11:30:00", "label": "พักรับประทานอาหารกลางวัน", "pre_chime": True, "voice_announce": True, "custom_sound": "ไม่มี", "post_chime": True, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True},
			{"id": "8", "time": "12:30:00", "label": "เข้าห้องเรียน คาบเรียนที่ 4", "pre_chime": True, "voice_announce": True, "custom_sound": "ไม่มี", "post_chime": False, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True},
			{"id": "9", "time": "13:30:00", "label": "เริ่มคาบเรียนที่ 5", "pre_chime": True, "voice_announce": True, "custom_sound": "ไม่มี", "post_chime": False, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True},
			{"id": "10", "time": "14:30:00", "label": "เริ่มคาบเรียนที่ 6", "pre_chime": True, "voice_announce": True, "custom_sound": "ไม่มี", "post_chime": False, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True},
			{"id": "11", "time": "15:25:00", "label": "ได้เวลาเข้าแถวเตรียมตัวกลับบ้าน", "pre_chime": True, "voice_announce": True, "custom_sound": "ไม่มี", "post_chime": False, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True},
			{"id": "12", "time": "15:30:00", "label": "เลิกเรียน / ทำกิจกรรมเลิกเรียน", "pre_chime": True, "voice_announce": True, "custom_sound": "ไม่มี", "post_chime": True, "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "enabled": True}
		]
		self.save_schedules()

	def save_schedules(self):
		try:
			self.sort_schedules_by_time()
			data = {
				"operating_start": self.operating_start,
				"operating_end": self.operating_end,
				"schedules": self.schedules
			}
			with open(self.json_path, "w", encoding="utf-8") as f:
				json.dump(data, f, ensure_ascii=False, indent=2)
			self.schedules_changed.emit()
		except Exception as e:
			print(f"[Scheduler] Error saving schedules.json: {e}")

	def start(self):
		print("[Scheduler] School Bell Scheduler Watchdog Started.")

	def stop(self):
		self.watchdog_timer.stop()

	def is_in_sleep_mode(self):
		return False  # ปลดล็อกให้ทำงานได้ตลอด 24 ชั่วโมงตามตารางที่ตั้งไว้

	def _check_schedule_watchdog(self):
		now = datetime.now()
		now_hms = now.strftime("%H:%M:%S")
		now_hm = now.strftime("%H:%M")
		today_code = DAY_MAP_SHORT[now.weekday()]

		for item in self.schedules:
			if not item.get("enabled", True):
				continue

			item_time = self.normalize_time_str(item.get("time", ""))
			item_hm = item_time[:5]
			item_days = item.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri"])

			current_trigger_key = f"{now.strftime('%Y-%m-%d')} {item_time}"

			if (item_time == now_hms or (now.second < 3 and item_hm == now_hm)) and today_code in item_days:
				if current_trigger_key != self.last_triggered_key:
					self.last_triggered_key = current_trigger_key
					print(f"[Watchdog] Triggering schedule: {item.get('label')} at {now_hms}")
					self._trigger_bell(item, now.hour, now.minute)
					break

	def _trigger_bell(self, item, hour, minute):
		# ไมค์สดมาก่อน: ถ้ากำลังพูดสดอยู่ ให้ Drop ตารางนี้ทั้งเสียงและป๊อปอัพ
		if getattr(self.audio_engine, "live_active", False):
			print(f"[Watchdog] Drop ตาราง '{item.get('label')}' เพราะกำลังพูดสดผ่านไมค์")
			return
		self.bell_triggered.emit(item)
		self.audio_engine.play_schedule_item(item, hour, minute)

	def get_next_schedule_display(self):
		"""เปรียบเทียบเวลาในเครื่องกับตารางเวลาจริงนับไปข้างหน้าแบบ Realtime"""
		now = datetime.now()
		now_hms = now.strftime("%H:%M:%S")
		now_hm = now.strftime("%H:%M")
		today_code = DAY_MAP_SHORT[now.weekday()]
		
		upcoming_today = []
		for s in self.schedules:
			if not s.get("enabled", True):
				continue
			days = s.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri"])
			if today_code not in days:
				continue
			slot_time = self.normalize_time_str(s.get("time", "00:00:00"))
			if slot_time >= now_hms or slot_time[:5] >= now_hm:
				upcoming_today.append((slot_time, s.get("label", "อ๊อดแจ้งเวลา")))

		if upcoming_today:
			upcoming_today.sort(key=lambda x: x[0])
			next_time, next_label = upcoming_today[0]
			return f"{next_time} น. ({next_label})"

		for day_offset in range(1, 8):
			next_day = now + timedelta(days=day_offset)
			next_day_code = DAY_MAP_SHORT[next_day.weekday()]
			
			upcoming_future = []
			for s in self.schedules:
				if not s.get("enabled", True):
					continue
				days = s.get("days", ["Mon", "Tue", "Wed", "Thu", "Fri"])
				if next_day_code in days:
					slot_time = self.normalize_time_str(s.get("time", "00:00:00"))
					upcoming_future.append((slot_time, s.get("label", "อ๊อดแจ้งเวลา")))

			if upcoming_future:
				upcoming_future.sort(key=lambda x: x[0])
				next_time, next_label = upcoming_future[0]
				return f"{next_time} น. ({next_label}) [รอบถัดไป]"

		return "ไม่มีรายการตารางเวลา"
