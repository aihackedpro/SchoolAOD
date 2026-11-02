import os
import threading
import time
from datetime import datetime
from PySide6.QtCore import QUrl, QObject, Signal, QTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioSink, QAudioFormat
from paths import data_path
from config_manager import load_config
from tts_engine import (TTSEngine, build_segments, prepare_langs, default_langs, LANG_NAME,
						GAP_AFTER_CHIME, GAP_BEFORE_SOUND)


def parse_item_time(item):
	"""ดึงชั่วโมง/นาทีจากตารางเวลา (เช่น '08:05:00')"""
	parts = str(item.get("time", "")).split(":")
	try:
		hour = int(parts[0]) if parts and parts[0].strip().isdigit() else 0
		minute = int(parts[1]) if len(parts) > 1 and parts[1].strip().isdigit() else 0
		return hour, minute
	except Exception:
		now = datetime.now()
		return now.hour, now.minute


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
	# ---- ประกาศด้วยเสียง AI หลายภาษา ----
	announce_requested = Signal(dict)       # ขอประกาศ (รับได้จากทุกเธรด เช่น รีโมท)
	_chain_ready = Signal(object, str, object)  # เธรดเบื้องหลังสร้างเสียงเสร็จ → (ไฟล์, ชื่อ, จังหวะเว้น) มาเล่นบน main thread
	cache_progress = Signal(int, int)       # เตรียมเสียงล่วงหน้า: ทำไปแล้ว / ทั้งหมด
	cache_finished = Signal(int, int)       # เตรียมเสียงเสร็จ: สำเร็จ / ทั้งหมด

	def __init__(self, sounds_dir=None, config=None):
		super().__init__()
		self.sounds_dir = sounds_dir or data_path("sounds")
		os.makedirs(self.sounds_dir, exist_ok=True)
		self.config = config if config is not None else load_config()
		self.tts = TTSEngine(self.config)

		# เมื่อ signal ถูก emit จากเธรดอื่น Qt จะส่งเป็น queued connection มาทำงานบนเธรดของ AudioEngine (main thread)
		self.remote_bell_requested.connect(self._handle_remote_bell)
		self.play_item_requested.connect(self._handle_play_item)
		self.live_broadcast_requested.connect(self._handle_live_broadcast)
		self.announce_requested.connect(self.play_announcement)
		self._chain_ready.connect(self._on_chain_ready)

		# การเตรียมเสียงล่วงหน้า (ทำทีละชุด ถ้ามีคำขอใหม่ระหว่างทำ จะทำซ้ำอีกรอบด้วยข้อมูลล่าสุด)
		self._cache_lock = threading.Lock()
		self._cache_running = False
		self._cache_pending = None

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
		self.gaps = []
		self.current_index = 0
		self.is_playing = False
		self._seq_id = 0   # เลขชุดเสียงปัจจุบัน — กันตัวจับเวลาของชุดเก่าไปเล่นแทรกชุดใหม่
		self.player.mediaStatusChanged.connect(self._on_media_status_changed)

	def set_volume(self, volume_percent: int):
		vol = max(0, min(100, volume_percent)) / 100.0
		self.audio_output.setVolume(vol)

	def stop_all(self):
		"""หยุดเสียงที่กำลังเล่นทั้งหมดทันที (ไม่กระทบการพูดสดผ่านไมค์)"""
		self._seq_id += 1
		self.playlist = []
		self.current_index = 0
		if self.is_playing:
			self.is_playing = False
			self.player.stop()
			self.sequence_finished.emit()

	def play_sequence(self, sound_files: list, label="อ๊อดแจ้งเวลา", gaps=None):
		"""เล่นไฟล์ต่อกัน — gaps[i] = จังหวะเว้น (ms) ก่อนเล่นไฟล์ลำดับที่ i"""
		# ไมค์สดมาก่อนเสมอ: ถ้ากำลังพูดสดอยู่ ให้ Drop เสียงขาน/อ๊อดที่ชนช่วงนี้ทิ้ง
		if self.live_active:
			print(f"[AudioEngine] Drop เสียง '{label}' เพราะมีการพูดสดผ่านไมค์อยู่")
			return False

		valid_files, valid_gaps = [], []
		pending_gap = 0
		for i, file in enumerate(sound_files):
			gap = gaps[i] if gaps and i < len(gaps) else 100
			if not file:
				pending_gap = max(pending_gap, gap)
				continue
			path = file if os.path.isabs(file) else os.path.abspath(os.path.join(self.sounds_dir, file))
			if os.path.exists(path):
				valid_files.append(path)
				valid_gaps.append(max(gap, pending_gap))
				pending_gap = 0

		if valid_files:
			self._seq_id += 1
			self.playlist = valid_files
			self.gaps = valid_gaps
			self.current_index = 0
			self.is_playing = True
			self.sequence_started.emit(label)
			self._play_current()
			return True
		return False

	# ---------------------------------------------------------------- ประกาศเสียง AI หลายภาษา
	@staticmethod
	def spec_from_item(item, hour=None, minute=None):
		"""แปลงตารางเวลาเป็นคำสั่งประกาศ (ค่าเริ่มต้นใช้เวลาตามตาราง)"""
		if hour is None or minute is None:
			hour, minute = parse_item_time(item)
		return {
			"hour": hour,
			"minute": minute,
			"pre_chime": item.get("pre_chime", True),
			"voice_announce": item.get("voice_announce", True),
			"speak_text": item.get("speak_text", item.get("voice_announce", True)),
			"custom_sound": item.get("custom_sound", "ไม่มี"),
			"post_chime": item.get("post_chime", True),
			"label": item.get("label", "อ๊อดแจ้งเวลา"),
			"langs": item.get("langs"),
			"style": item.get("voice_style") or None,
		}

	def play_schedule_item(self, item, hour=None, minute=None, label=None):
		spec = self.spec_from_item(item, hour, minute)
		if label:
			spec["display_label"] = label
		return self.play_announcement(spec)

	def play_announcement(self, spec: dict):
		"""เริ่มประกาศ: สร้าง/ดึงเสียงทุกภาษาในเธรดเบื้องหลัง แล้วค่อยเล่นบน main thread (UI ไม่ค้าง)

		spec: hour, minute, pre_chime, voice_announce (ขานเวลา), speak_text (อ่านข้อความ),
		      custom_sound, post_chime, label, langs (ลำดับภาษา), style (สไตล์เสียง)
		"""
		label = spec.get("display_label") or spec.get("label") or "อ๊อดแจ้งเวลา"
		# ไมค์สดมาก่อน: ถ้ากำลังพูดสด ให้ข้ามการประกาศนี้ (Drop)
		if self.live_active:
			print(f"[AudioEngine] Drop การประกาศ '{label}' เพราะมีการพูดสดผ่านไมค์อยู่")
			return False
		threading.Thread(target=self._build_chain_worker, args=(dict(spec), label), daemon=True).start()
		return True

	def _build_chain_worker(self, spec, label):
		files, gaps = [], []
		if spec.get("pre_chime", True):
			files.append("chime.mp3")
			gaps.append(0)

		now = datetime.now()
		hour = spec.get("hour", now.hour)
		minute = spec.get("minute", now.minute)
		langs = prepare_langs(spec.get("langs"), spec.get("label", ""))

		segments = build_segments(
			langs,
			label=spec.get("label", ""),
			hour=hour,
			minute=minute,
			include_time=spec.get("voice_announce", True),
			include_text=spec.get("speak_text", True),
		)
		for i, (text, lang, gap) in enumerate(segments):
			path = self.tts.synthesize(text, lang, spec.get("style"))
			if not path:
				print(f"[AudioEngine] สร้างเสียง {LANG_NAME.get(lang, lang)} ไม่ได้ (ออฟไลน์และยังไม่เคยแคช): {text[:40]}")
			files.append(path)   # ไฟล์ว่าง = ข้าม แต่ยังรักษาจังหวะเว้นไว้
			gaps.append(GAP_AFTER_CHIME if i == 0 and files[:1] == ["chime.mp3"] else gap)

		# เสียงต่อท้ายและติ่งต่องปิดท้าย เล่นหลังพูดครบทุกรอบแล้วเท่านั้น
		custom = spec.get("custom_sound")
		if custom and custom != "ไม่มี":
			files.append(custom)
			gaps.append(GAP_BEFORE_SOUND)
		if spec.get("post_chime", True):
			files.append("chime.mp3")
			gaps.append(GAP_BEFORE_SOUND)

		self._chain_ready.emit(files, label, gaps)

	def _on_chain_ready(self, files, label, gaps):
		self.play_sequence(files, label=label, gaps=gaps)

	# ---------------------------------------------------------------- เตรียมเสียงล่วงหน้า (ใช้ออฟไลน์)
	def _schedule_jobs(self, schedules, allow_network=False):
		jobs, seen = [], set()
		for item in schedules or []:
			if not item.get("enabled", True):
				continue
			spec = self.spec_from_item(item)
			langs = prepare_langs(spec["langs"], spec["label"], allow_network=allow_network)
			segments = build_segments(
				langs, label=spec["label"], hour=spec["hour"], minute=spec["minute"],
				include_time=spec["voice_announce"], include_text=spec["speak_text"],
			)
			for text, lang, _gap in segments:
				key = (text, lang, spec["style"])
				if key not in seen:
					seen.add(key)
					jobs.append(key)
		return jobs

	def cache_status(self, schedules):
		"""คืน (พร้อมใช้ออฟไลน์, ทั้งหมด, เป็นเสียง AI คุณภาพสูงแล้ว) — ไม่ใช้เครือข่าย"""
		jobs = self._schedule_jobs(schedules)
		ready = sum(1 for text, lang, style in jobs if self.tts.is_cached(text, lang, style))
		ai_ready = sum(1 for text, lang, style in jobs if self.tts.has_ai_voice(text, lang, style))
		return ready, len(jobs), ai_ready

	def precache_schedules(self, schedules):
		"""ดาวน์โหลดเสียง AI ของทุกตารางมาเก็บไว้ในเครื่อง (ทำในเธรดเบื้องหลัง)"""
		snapshot = [dict(item) for item in schedules or []]
		with self._cache_lock:
			if self._cache_running:
				self._cache_pending = snapshot
				return
			self._cache_running = True
		threading.Thread(target=self._precache_worker, args=(snapshot,), daemon=True).start()

	def _precache_worker(self, schedules):
		while True:
			jobs = self._schedule_jobs(schedules, allow_network=True)
			ok = 0
			for i, (text, lang, style) in enumerate(jobs, start=1):
				needs_network = not self.tts.has_ai_voice(text, lang, style)
				if self.tts.synthesize(text, lang, style, upgrade=True):
					ok += 1
				self.cache_progress.emit(i, len(jobs))
				if needs_network:
					time.sleep(0.4)   # เว้นจังหวะระหว่างคำขอ ลดโอกาสโดนบริการจำกัดจำนวนครั้ง
			self.cache_finished.emit(ok, len(jobs))

			with self._cache_lock:
				if self._cache_pending is None:
					self._cache_running = False
					return
				schedules, self._cache_pending = self._cache_pending, None

	def _handle_remote_bell(self):
		"""ทำงานบน main thread เสมอ (ถูกเรียกผ่าน remote_bell_requested signal) — สั่งอ๊อดขานเวลาปัจจุบัน"""
		now = datetime.now()
		self.play_announcement({
			"hour": now.hour,
			"minute": now.minute,
			"pre_chime": True,
			"voice_announce": True,
			"speak_text": False,
			"post_chime": True,
			"label": "สั่งเปิดอ๊อดผ่าน Remote",
			"langs": default_langs(),
		})

	def _handle_play_item(self, item: dict):
		"""รีโมทสั่งเล่นตามรายการในตาราง (ทำงานบน main thread) — ขานเวลา 'ตามค่าในตาราง' ไม่ใช่เวลาปัจจุบัน"""
		self.play_schedule_item(item)

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
		self._seq_id += 1
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
				gap = self.gaps[self.current_index] if self.current_index < len(self.gaps) else 100
				seq = self._seq_id
				QTimer.singleShot(max(50, int(gap)), lambda: self._play_current() if seq == self._seq_id else None)
			else:
				self.is_playing = False
				self.sequence_finished.emit()
