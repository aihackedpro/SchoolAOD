import os
import sys
from datetime import datetime
from PySide6.QtCore import QUrl, QObject, Signal, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioSink, QAudioFormat
from paths import data_path

try:
	from gtts import gTTS
	HAS_GTTS = True
except ImportError:
	HAS_GTTS = False


def thai_number_to_words(number: int) -> str:
	thai_digits = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
	if number == 0:
		return "ศูนย์"
	elif number < 10:
		return thai_digits[number]
	elif number == 10:
		return "สิบ"
	elif number < 20:
		return "สิบ" + ("เอ็ด" if number % 10 == 1 else thai_digits[number % 10])
	elif number < 60:
		tens = number // 10
		units = number % 10
		prefix = "ยี่" if tens == 2 else thai_digits[tens]
		unit_str = "เอ็ด" if units == 1 else (thai_digits[units] if units > 0 else "")
		return prefix + "สิบ" + unit_str
	return str(number)


class AudioEngine(QObject):
	sequence_started = Signal(str)
	sequence_finished = Signal()
	# ใช้รับคำสั่งเล่นเสียงข้ามเธรด (เช่น จาก Remote Server) ให้ไปทำงานบน main thread ของ Qt อย่างปลอดภัย
	remote_bell_requested = Signal()
	play_item_requested = Signal(dict)     # รีโมทสั่งเล่นตามรายการในตาราง
	live_broadcast_requested = Signal(str)  # (แบบเก่า) รีโมทพูดสด → ส่ง path ไฟล์เสียงมาเล่น
	live_broadcast_started = Signal(str)    # แจ้ง UI ให้แสดงว่ากำลังออกอากาศสด
	# ---- สตรีมเสียงสดแบบเรียลไทม์ (walkie-talkie) ----
	live_stream_started = Signal(int)       # เริ่มสตรีม (ส่ง sample rate มาด้วย)
	live_pcm_received = Signal(object)      # ก้อนข้อมูลเสียง PCM (bytes) เข้ามาแบบต่อเนื่อง
	live_stream_stopped = Signal()          # วางสาย/จบสตรีม

	def __init__(self, sounds_dir=None):
		super().__init__()
		self.sounds_dir = sounds_dir or data_path("sounds")
		os.makedirs(self.sounds_dir, exist_ok=True)

		# เมื่อ signal ถูก emit จากเธรดอื่น Qt จะส่งเป็น queued connection มาทำงานบนเธรดของ AudioEngine (main thread)
		self.remote_bell_requested.connect(self._handle_remote_bell)
		self.play_item_requested.connect(self._handle_play_item)
		self.live_broadcast_requested.connect(self._handle_live_broadcast)

		# สถานะสตรีมสด + ตัวเล่นเสียงสตรีม (QAudioSink)
		self.live_active = False
		self.audio_sink = None
		self.sink_io = None
		self.live_stream_started.connect(self._on_live_stream_started)
		self.live_pcm_received.connect(self._on_live_pcm)
		self.live_stream_stopped.connect(self._on_live_stream_stopped)

		self.audio_output = QAudioOutput()
		self.player = QMediaPlayer()
		self.player.setAudioOutput(self.audio_output)
		self.audio_output.setVolume(1.0)

		self.playlist = []
		self.current_index = 0
		self.is_playing = False
		self.player.mediaStatusChanged.connect(self._on_media_status_changed)

	def set_volume(self, volume_percent: int):
		vol = max(0, min(100, volume_percent)) / 100.0
		self.audio_output.setVolume(vol)

	def generate_tts_voice(self, text: str, filename: str) -> str:
		"""สร้างไฟล์เสียงพูดภาษาไทยจากข้อความใด ๆ (ใช้ซ้ำได้ทั้งขานเวลาและอ่านรายละเอียด)"""
		text = (text or "").strip()
		if not text:
			return ""

		temp_path = os.path.abspath(os.path.join(self.sounds_dir, filename))

		if HAS_GTTS:
			try:
				tts = gTTS(text=text, lang='th')
				tts.save(temp_path)
				return temp_path
			except Exception as e:
				print(f"[AudioEngine] gTTS Error: {e}")

		# fallback: ใช้คำสั่ง say ของ macOS เท่านั้น (Windows/Linux ไม่มีคำสั่งนี้)
		if sys.platform == "darwin":
			safe_text = text.replace('"', "")
			if os.system(f'say -v Kanya "{safe_text}" -o "{temp_path}" 2>/dev/null') == 0:
				return temp_path

		return ""

	def generate_live_time_voice(self, hour: int, minute: int) -> str:
		hour_word = thai_number_to_words(hour)
		if minute == 0:
			text = f"ขณะนี้เวลา {hour_word}นาฬิกาตรง"
		else:
			min_word = thai_number_to_words(minute)
			text = f"ขณะนี้เวลา {hour_word}นาฬิกา {min_word}นาที"

		# ใช้ไฟล์ชั่วคราวเฉพาะของเสียงขานเวลา (แยกจากไฟล์อ่านรายละเอียด)
		return self.generate_tts_voice(text, "temp_live_voice.mp3")

	def play_sequence(self, sound_files: list, label="อ๊อดแจ้งเวลา"):
		# ไมค์สดมาก่อนเสมอ: ถ้ากำลังพูดสดอยู่ ให้ Drop เสียงขาน/อ๊อดที่ชนช่วงนี้ทิ้ง
		if self.live_active:
			print(f"[AudioEngine] Drop เสียง '{label}' เพราะมีการพูดสดผ่านไมค์อยู่")
			return False

		valid_files = []
		for file in sound_files:
			if not file:
				continue
			path = file if os.path.isabs(file) else os.path.abspath(os.path.join(self.sounds_dir, file))
			if os.path.exists(path):
				valid_files.append(path)

		if valid_files:
			self.playlist = valid_files
			self.current_index = 0
			self.is_playing = True
			self.sequence_started.emit(label)
			self._play_current()
			return True
		return False

	def play_chime_chain(self, hour: int, minute: int, pre_chime: bool = True, voice_announce: bool = True, custom_sound: str = "", post_chime: bool = True, label="อ๊อดแจ้งเวลา", announce_label: str = ""):
		# ไมค์สดมาก่อน: ถ้ากำลังพูดสด ให้ข้ามการขาน/อ๊อดนี้ไปเลย (ไม่ต้องเสียเวลาสร้างเสียง)
		if self.live_active:
			print(f"[AudioEngine] Drop การขาน '{label}' เพราะมีการพูดสดผ่านไมค์อยู่")
			return False

		chain = []

		if pre_chime:
			chain.append("chime.mp3")

		if voice_announce:
			# 1) ขานเวลา
			live_voice_file = self.generate_live_time_voice(hour, minute)
			if live_voice_file:
				chain.append(live_voice_file)

			# 2) อ่านข้อความในช่อง "รายละเอียด" เป็นเสียงภาษาไทย (แยกไฟล์ชั่วคราวออกจากเสียงขานเวลา)
			if announce_label and announce_label.strip():
				label_voice_file = self.generate_tts_voice(announce_label, "temp_label_voice.mp3")
				if label_voice_file:
					chain.append(label_voice_file)

		if custom_sound and custom_sound != "ไม่มี":
			chain.append(custom_sound)

		if post_chime:
			chain.append("chime.mp3")

		return self.play_sequence(chain, label=label)

	def _handle_remote_bell(self):
		"""ทำงานบน main thread เสมอ (ถูกเรียกผ่าน remote_bell_requested signal) — สั่งอ๊อดขานเวลาปัจจุบัน"""
		now = datetime.now()
		self.play_chime_chain(
			hour=now.hour,
			minute=now.minute,
			pre_chime=True,
			voice_announce=True,
			custom_sound="ไม่มี",
			post_chime=True,
			label="สั่งเปิดอ๊อดผ่าน Remote"
		)

	def _handle_play_item(self, item: dict):
		"""รีโมทสั่งเล่นตามรายการในตาราง (ทำงานบน main thread) — ขานเวลา 'ตามค่าในตาราง' ไม่ใช่เวลาปัจจุบัน"""
		parts = str(item.get("time", "")).split(":")
		try:
			hour = int(parts[0]) if len(parts) > 0 and parts[0].strip().isdigit() else 0
			minute = int(parts[1]) if len(parts) > 1 and parts[1].strip().isdigit() else 0
		except Exception:
			now = datetime.now()
			hour, minute = now.hour, now.minute
		self.play_chime_chain(
			hour=hour,
			minute=minute,
			pre_chime=item.get("pre_chime", True),
			voice_announce=item.get("voice_announce", True),
			custom_sound=item.get("custom_sound", "ไม่มี"),
			post_chime=item.get("post_chime", True),
			label=item.get("label", "อ๊อดแจ้งเวลา"),
			announce_label=item.get("label", "")
		)

	def _handle_live_broadcast(self, path: str):
		"""รีโมทพูดสด → เล่นไฟล์เสียงที่อัดมาทันที + แจ้ง UI ให้แสดงสถานะออกอากาศ (main thread)"""
		if path and os.path.exists(path):
			self.live_broadcast_started.emit(os.path.basename(path))
			self.play_sequence([path], label="📢 ประชาสัมพันธ์สด (Live)")

	# ---- สตรีมเสียงสดแบบเรียลไทม์ (ทั้งหมดทำงานบน main thread ผ่าน queued signal) ----
	def _on_live_stream_started(self, sample_rate: int):
		"""เริ่มพูดสด: ไมค์มาก่อน → หยุดเสียงที่กำลังเล่นทันที แล้วเปิดช่องเล่นเสียงสตรีม"""
		self.live_active = True
		self.is_playing = False
		self.playlist = []
		self.player.stop()  # Drop เสียงขาน/อ๊อดที่กำลังเล่นอยู่

		fmt = QAudioFormat()
		fmt.setSampleRate(int(sample_rate) if sample_rate else 48000)
		fmt.setChannelCount(1)
		fmt.setSampleFormat(QAudioFormat.Int16)
		self.audio_sink = QAudioSink(fmt)
		self.sink_io = self.audio_sink.start()  # push mode: เขียน PCM เข้าไปเล่นต่อเนื่อง

		self.live_broadcast_started.emit("สตรีมเสียงสด")

	def _on_live_pcm(self, data):
		"""ได้ก้อนเสียง PCM มา → เล่นออกลำโพงทันที (เรียลไทม์)"""
		if self.live_active and self.sink_io is not None and data:
			try:
				self.sink_io.write(bytes(data))
			except Exception as e:
				print(f"[AudioEngine] live pcm write error: {e}")

	def _on_live_stream_stopped(self):
		"""วางสาย: ปิดช่องสตรีม แล้วคืนระบบให้ขาน/อ๊อดตามปกติได้"""
		self.live_active = False
		if self.audio_sink is not None:
			try:
				self.audio_sink.stop()
			except Exception:
				pass
		self.audio_sink = None
		self.sink_io = None
		self.sequence_finished.emit()  # ปิดป๊อปอัพสถานะพูดสด

	def _play_current(self):
		if 0 <= self.current_index < len(self.playlist):
			path = self.playlist[self.current_index]
			self.player.setSource(QUrl.fromLocalFile(path))
			self.player.play()
		else:
			self.is_playing = False
			self.sequence_finished.emit()

	def _on_media_status_changed(self, status):
		if status == QMediaPlayer.MediaStatus.EndOfMedia:
			self.current_index += 1
			if self.current_index < len(self.playlist):
				QTimer.singleShot(100, self._play_current)
			else:
				self.is_playing = False
				self.sequence_finished.emit()
