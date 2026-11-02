"""ระบบเสียง AI สำหรับประกาศเสียงตามสายหลายภาษา (ไทย / อังกฤษ / จีน)

- เสียงหลัก: Microsoft Edge Neural TTS (ฟรี คุณภาพระดับผู้ประกาศ ต้องใช้อินเทอร์เน็ตตอนสร้างเสียง)
- ทุกประโยคที่สร้างแล้วจะถูกเก็บไว้ในเครื่อง (voice_cache) → เน็ตหลุดก็ยังเล่นได้
- สำรอง: gTTS (ออนไลน์) → คำสั่ง say ของ macOS (ออฟไลน์ เฉพาะภาษาไทยบน Mac)

โครงสร้างข้อมูลภาษาของประกาศ (เรียงตามลำดับการอ่าน):
	[{"code": "th", "enabled": True, "text": "...", "repeat": 1}, {"code": "en", ...}, {"code": "zh", ...}]
"""
import asyncio
import hashlib
import json
import os
import re
import sys
import threading
import time
from paths import data_path

# (รหัส, ชื่อที่แสดง, ธง)
LANGUAGES = [
	("th", "ไทย", "🇹🇭"),
	("en", "English", "🇬🇧"),
	("zh", "中文", "🇨🇳"),
]
LANG_NAME = {code: name for code, name, _ in LANGUAGES}
LANG_FLAG = {code: flag for code, _, flag in LANGUAGES}
# ป้ายสั้นสำหรับหน้าจอ Windows (Windows ไม่แสดงอีโมจิธงชาติ จะกลายเป็นตัวอักษร TH/GB/CN)
LANG_SHORT = {"th": "ไทย", "en": "EN", "zh": "中文"}
LANG_LABEL = {"th": "ไทย (TH)", "en": "English (EN)", "zh": "中文 (ZH)"}

VOICE_STYLES = [
	("female", "👩 เสียงผู้หญิง"),
	("male", "👨 เสียงผู้ชาย"),
	("girl", "👧 เสียงเด็กผู้หญิง"),
	("boy", "👦 เสียงเด็กผู้ชาย"),
]
STYLE_NAME = dict(VOICE_STYLES)

# ความเร็วการพูด (key, ชื่อที่แสดง, % ที่ส่งให้เสียง AI)
# ค่า 0% ของเสียง AI คือความเร็วการพูดคุยทั่วไป ซึ่งเร็วกว่าจังหวะผู้ประกาศเสียงตามสาย
# จึงตั้ง "ปกติ" ให้ช้าลงเล็กน้อยเพื่อให้ฟังชัดและเป็นธรรมชาติแบบการประกาศ
SPEEDS = [
	("slower", "🐢 ช้ามาก", -30),
	("slow", "ช้า", -20),
	("normal", "ปกติ (จังหวะผู้ประกาศ — แนะนำ)", -10),
	("fast", "เร็ว", 0),
	("faster", "🐇 เร็วมาก", 12),
]
SPEED_RATE = {key: rate for key, _, rate in SPEEDS}

MAX_REPEAT = 10

# จังหวะเว้นระหว่างเสียง (มิลลิวินาที) ให้ฟังเป็นธรรมชาติแบบผู้ประกาศ
GAP_AFTER_CHIME = 400
GAP_TIME_TO_TEXT = 450    # ขานเวลา → ข้อความ (ภาษาเดียวกัน)
GAP_BETWEEN_LANGS = 800   # เปลี่ยนภาษา
GAP_BETWEEN_ROUNDS = 1200 # ขึ้นรอบใหม่
GAP_BEFORE_SOUND = 800    # ก่อนเสียงต่อท้าย/ติ่งต่องปิดท้าย

# เสียงที่จับคู่กับแต่ละสไตล์: (ชื่อเสียง Edge, ปรับระดับเสียง)
# เสียงเด็กของภาษาไทยไม่มีให้โดยตรง จึงจำลองด้วยการยกระดับเสียง
PRESETS = {
	"th": {
		"female": ("th-TH-PremwadeeNeural", "+0Hz"),
		"male": ("th-TH-NiwatNeural", "+0Hz"),
		"girl": ("th-TH-PremwadeeNeural", "+35Hz"),
		"boy": ("th-TH-NiwatNeural", "+60Hz"),
	},
	"en": {
		"female": ("en-US-AriaNeural", "+0Hz"),
		"male": ("en-US-ChristopherNeural", "+0Hz"),
		"girl": ("en-US-AnaNeural", "+0Hz"),
		"boy": ("en-US-AnaNeural", "-25Hz"),
	},
	"zh": {
		"female": ("zh-CN-XiaoxiaoNeural", "+0Hz"),
		"male": ("zh-CN-YunyangNeural", "+0Hz"),
		"girl": ("zh-CN-XiaoyiNeural", "+15Hz"),
		"boy": ("zh-CN-YunxiaNeural", "+0Hz"),
	},
}

_GTTS_LANG = {"th": "th", "en": "en", "zh": "zh-CN"}
_VOICE_LOCALE_PREFIX = {"th": "th-", "en": "en-", "zh": "zh-"}
_EDGE_TIMEOUT = 25


# ---------------------------------------------------------------- ข้อความประกาศ

def thai_number_to_words(number: int) -> str:
	thai_digits = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
	if number == 0:
		return "ศูนย์"
	if number < 10:
		return thai_digits[number]
	if number == 10:
		return "สิบ"
	if number < 20:
		return "สิบ" + ("เอ็ด" if number % 10 == 1 else thai_digits[number % 10])
	if number < 60:
		tens, units = divmod(number, 10)
		prefix = "ยี่" if tens == 2 else thai_digits[tens]
		unit_str = "เอ็ด" if units == 1 else (thai_digits[units] if units > 0 else "")
		return prefix + "สิบ" + unit_str
	return str(number)


def time_phrase(lang: str, hour: int, minute: int) -> str:
	"""ประโยคขานเวลาในแต่ละภาษา"""
	if lang == "en":
		h12 = hour % 12 or 12
		ampm = "AM" if hour < 12 else "PM"
		return f"The time is now {h12}:{minute:02d} {ampm}."
	if lang == "zh":
		return f"现在时间，{hour}点整。" if minute == 0 else f"现在时间，{hour}点{minute}分。"
	hour_word = thai_number_to_words(hour)
	if minute == 0:
		return f"ขณะนี้เวลา {hour_word}นาฬิกาตรง"
	return f"ขณะนี้เวลา {hour_word}นาฬิกา {thai_number_to_words(minute)}นาที"


def default_langs(th_enabled=True):
	return [
		{"code": "th", "enabled": th_enabled, "text": "", "repeat": 1},
		{"code": "en", "enabled": False, "text": "", "repeat": 1},
		{"code": "zh", "enabled": False, "text": "", "repeat": 1},
	]


def normalize_langs(langs):
	"""ทำให้รายการภาษาถูกต้องเสมอ: ครบ 3 ภาษา ไม่ซ้ำ คงลำดับที่ผู้ใช้จัดไว้"""
	if not isinstance(langs, list) or not langs:
		return default_langs()
	out, seen = [], set()
	for entry in langs:
		if not isinstance(entry, dict):
			continue
		code = entry.get("code")
		if code not in LANG_NAME or code in seen:
			continue
		seen.add(code)
		try:
			repeat = int(entry.get("repeat", 1) or 1)
		except (TypeError, ValueError):
			repeat = 1
		item = {
			"code": code,
			"enabled": bool(entry.get("enabled", False)),
			"text": str(entry.get("text", "") or ""),
			"repeat": max(1, min(MAX_REPEAT, repeat)),
		}
		if entry.get("speak_as") in LANG_NAME:
			item["speak_as"] = entry["speak_as"]   # ภาษาเสียงที่ใช้จริง (กรณีแปลไม่ได้ตอนออฟไลน์)
		out.append(item)
	for code, _, _ in LANGUAGES:
		if code not in seen:
			out.append({"code": code, "enabled": False, "text": "", "repeat": 1})
	return out


def normalize_schedule_item(item: dict) -> dict:
	"""เติมฟิลด์ใหม่ให้ตารางเวลาเดิม (เวอร์ชันก่อน 2.0) โดยพฤติกรรมเหมือนเดิมทุกอย่าง"""
	item["langs"] = normalize_langs(item.get("langs"))
	# เดิม: ปิด "ขานเวลา" = ไม่พูดอะไรเลย → คงพฤติกรรมนั้นไว้สำหรับรายการเก่า
	if "speak_text" not in item:
		item["speak_text"] = bool(item.get("voice_announce", True))
	item.setdefault("voice_style", "")
	return item


def langs_summary(langs) -> str:
	"""สรุปลำดับภาษาสำหรับแสดงในตาราง เช่น 'ไทย → EN ×2 → 中文'"""
	parts = []
	for e in normalize_langs(langs):
		if e["enabled"]:
			parts.append(LANG_SHORT[e["code"]] + (f" ×{e['repeat']}" if e["repeat"] > 1 else ""))
	return " → ".join(parts) if parts else "— ไม่อ่านข้อความ —"


def prepare_langs(langs, label="", allow_network=True):
	"""เตรียมข้อความแต่ละภาษาให้พร้อมพูด
	- ช่องว่าง → ใช้ข้อความไทย/ชื่อคาบ แล้วแปลเป็นภาษาของช่องนั้น
	- พิมพ์ภาษาไม่ตรงช่อง (เช่น พิมพ์ไทยในช่องจีน) → แปลเป็นภาษาของช่องให้อัตโนมัติ
	- พิมพ์ภาษาตรงช่องอยู่แล้ว → อ่านตามที่พิมพ์ ไม่แปล
	- แปลไม่ได้ (ออฟไลน์และไม่เคยแปลไว้) → พูดด้วยเสียงของภาษาที่พิมพ์มาจริง
	allow_network=False → ใช้เฉพาะคำแปลที่จำไว้ในเครื่อง (ใช้ตอนคำนวณสถานะบนหน้าจอ)
	"""
	from translator import translate, detect_lang

	out = normalize_langs(langs)
	th_entry = next(e for e in out if e["code"] == "th")
	source = th_entry["text"].strip() or (label or "").strip()

	for entry in out:
		entry.pop("speak_as", None)
		if not entry["enabled"]:
			continue
		code = entry["code"]
		text = entry["text"].strip()
		if not text:
			text = source
		if text and detect_lang(text) != code:
			text = translate(text, code, allow_network=allow_network) or text
		entry["text"] = text
		if text and detect_lang(text) != code:
			entry["speak_as"] = detect_lang(text)
	return out


def build_segments(langs, label="", hour=None, minute=None, include_time=False, include_text=True):
	"""สร้างลำดับเสียงพูด [(ข้อความ, ภาษา, เว้นก่อนพูด ms), ...]

	อ่านเป็นรอบ: แต่ละรอบอ่านทุกภาษาที่ยังเหลือรอบ ตามลำดับที่จัดไว้ เช่น
	ไทย×2, อังกฤษ×1, จีน×2 → รอบ 1: ไทย → อังกฤษ → จีน, รอบ 2: ไทย → จีน
	ขานเวลากับข้อความแยกเป็นคนละท่อน เพื่อเว้นจังหวะหายใจแบบผู้ประกาศ
	"""
	entries = []
	for entry in normalize_langs(langs):
		if not entry["enabled"]:
			continue
		lang = entry.get("speak_as") or entry["code"]
		text = entry["text"].strip()
		if not text and entry["code"] == "th":
			text = (label or "").strip()
		parts = []
		if include_time and hour is not None:
			parts.append(time_phrase(lang, hour, minute or 0))
		if include_text and text:
			parts.append(text)
		if parts:
			entries.append((parts, lang, entry["repeat"]))

	segments = []
	rounds = max((repeat for _, _, repeat in entries), default=0)
	for round_no in range(rounds):
		first_in_round = True
		for parts, lang, repeat in entries:
			if repeat <= round_no:
				continue
			for i, part in enumerate(parts):
				if not segments:
					gap = 0
				elif i > 0:
					gap = GAP_TIME_TO_TEXT
				elif first_in_round:
					gap = GAP_BETWEEN_ROUNDS
				else:
					gap = GAP_BETWEEN_LANGS
				segments.append((part, lang, gap))
			first_in_round = False
	return segments


# ---------------------------------------------------------------- ตัวสร้างเสียง

_PHRASE_SPLIT_RE = re.compile(r"(?<=[\s。，,.!?！？;；])")


def _import_edge_tts():
	"""โหลด edge-tts และให้ใช้ชุดใบรับรองเดียวกับทั้งโปรแกรม (certifi + ใบรับรองของ Windows/proxy โรงเรียน)"""
	import edge_tts
	from net import ssl_context
	for module_name in ("communicate", "voices"):
		module = getattr(edge_tts, module_name, None)
		if module is not None and hasattr(module, "_SSL_CTX"):
			module._SSL_CTX = ssl_context()
	return edge_tts


def _split_phrases(text):
	"""แยกประโยคเป็นท่อนตามช่องว่าง/เครื่องหมายวรรคตอน (ภาษาไทยเว้นวรรค = จุดหยุดหายใจ)"""
	return [p.strip() for p in _PHRASE_SPLIT_RE.split(text) if p.strip()]


def _run_coroutine(factory):
	"""รัน coroutine ให้จบ ไม่ว่าจะเรียกจากเธรดที่มี event loop อยู่แล้วหรือไม่"""
	try:
		asyncio.get_running_loop()
	except RuntimeError:
		return asyncio.run(factory())

	result = {}

	def runner():
		try:
			result["value"] = asyncio.run(factory())
		except Exception as e:
			result["error"] = e

	t = threading.Thread(target=runner, daemon=True)
	t.start()
	t.join()
	if "error" in result:
		raise result["error"]
	return result.get("value")


class TTSEngine:
	def __init__(self, config, cache_dir=None):
		self.config = config
		self.cache_dir = cache_dir or data_path("voice_cache")
		os.makedirs(self.cache_dir, exist_ok=True)
		self.voices_file = os.path.join(self.cache_dir, "voices.json")

	# ---- การเลือกเสียง ----
	def default_style(self):
		style = self.config.get("tts_style", "female")
		return style if style in STYLE_NAME else "female"

	def rate_str(self):
		rate = SPEED_RATE.get(self.config.get("tts_speed", "normal"), SPEED_RATE["normal"])
		return f"{rate:+d}%"

	def resolve_voice(self, lang, style=None):
		"""คืน (ชื่อเสียง, pitch) ที่จะใช้จริง — ค่าเสียงเฉพาะภาษาที่ผู้ใช้เลือกมาก่อนสไตล์"""
		overrides = self.config.get("tts_voice_overrides") or {}
		override = (overrides.get(lang) or "").strip()
		if override:
			return override, "+0Hz"
		style = style if style in STYLE_NAME else self.default_style()
		presets = PRESETS.get(lang, PRESETS["th"])
		return presets.get(style) or presets["female"]

	# ---- แคช ----
	def _edge_cache_path(self, text, lang, style):
		voice, pitch = self.resolve_voice(lang, style)
		key = hashlib.sha1(f"{voice}|{pitch}|{self.rate_str()}|{text}".encode("utf-8")).hexdigest()
		return os.path.join(self.cache_dir, f"{lang}_{key}.mp3")

	def _fallback_cache_path(self, text, lang):
		key = hashlib.sha1(f"fallback|{lang}|{text}".encode("utf-8")).hexdigest()
		return os.path.join(self.cache_dir, f"{lang}_fb_{key}.mp3")

	@staticmethod
	def _valid(path):
		return os.path.exists(path) and os.path.getsize(path) > 0

	def is_cached(self, text, lang, style=None):
		"""ประโยคนี้เล่นได้แบบออฟไลน์หรือยัง (มีเสียง AI หรือเสียงสำรองเก็บไว้แล้ว)"""
		text = (text or "").strip()
		return bool(text) and (self._valid(self._edge_cache_path(text, lang, style))
							   or self._valid(self._fallback_cache_path(text, lang)))

	def has_ai_voice(self, text, lang, style=None):
		"""มีเสียง AI คุณภาพสูงแล้ว (ไม่ใช่แค่เสียงสำรอง)"""
		text = (text or "").strip()
		return bool(text) and self._valid(self._edge_cache_path(text, lang, style))

	def cache_size_bytes(self):
		total = 0
		for f in os.listdir(self.cache_dir):
			if f.endswith(".mp3"):
				total += os.path.getsize(os.path.join(self.cache_dir, f))
		return total

	def clear_cache(self):
		for f in os.listdir(self.cache_dir):
			if f.endswith((".mp3", ".part")):
				try:
					os.remove(os.path.join(self.cache_dir, f))
				except OSError:
					pass

	# ---- สร้างเสียง ----
	def synthesize(self, text, lang, style=None, allow_network=True, upgrade=False):
		"""คืน path ไฟล์เสียงของประโยค (ใช้แคชก่อน) หรือ "" ถ้าสร้างไม่ได้
		ต้องเรียกจากเธรดเบื้องหลังเท่านั้น เพราะอาจรอเครือข่ายหลายวินาที

		upgrade=False (ตอนเล่นจริง): มีเสียงสำรองเก็บไว้ก็ใช้ทันที ไม่รอเน็ต → ออดตรงเวลา
		upgrade=True  (ตอนเตรียมเสียงเบื้องหลัง): พยายามสร้างเสียง AI คุณภาพสูงแทนเสียงสำรอง
		"""
		text = (text or "").strip()
		if not text:
			return ""

		edge_path = self._edge_cache_path(text, lang, style)
		if self._valid(edge_path):
			return edge_path

		fb_path = self._fallback_cache_path(text, lang)
		if not upgrade and self._valid(fb_path):
			return fb_path

		if allow_network:
			voice, pitch = self.resolve_voice(lang, style)
			if self._edge_save(text, voice, pitch, edge_path):
				return edge_path

		# เสียงสำรอง (ใช้ได้เมื่อเคยสร้างไว้ หรือยังมีอินเทอร์เน็ต)
		if self._valid(fb_path):
			return fb_path
		if allow_network and self._gtts_save(text, lang, fb_path):
			return fb_path
		if lang == "th" and sys.platform == "darwin" and self._say_save(text, fb_path):
			return fb_path
		return ""

	def _edge_save(self, text, voice, pitch, out_path, attempts=2):
		"""สร้างเสียงด้วย Edge TTS
		- บริการบางครั้งตอบว่างเมื่อถูกเรียกถี่ ๆ → ลองซ้ำพร้อมเว้นระยะ
		- บางประโยคบริการปฏิเสธทั้งประโยค แต่รับได้เมื่อแยกเป็นท่อน → สร้างทีละท่อนด้วยเสียงเดิมแล้วต่อกัน
		- เชื่อมต่อไม่ได้ (เน็ตหลุด) → เลิกทันที ให้ระบบใช้เสียงสำรอง ออดจะได้ไม่ช้า
		"""
		tmp = out_path + ".part"
		try:
			edge_tts = _import_edge_tts()
			from edge_tts.exceptions import NoAudioReceived
		except ImportError:
			return False

		async def synth_bytes(chunks):
			data = bytearray()
			for chunk in chunks:
				comm = edge_tts.Communicate(chunk, voice, rate=self.rate_str(), pitch=pitch)
				async for msg in comm.stream():
					if msg.get("type") == "audio":
						data.extend(msg["data"])
			return bytes(data)

		def write(chunks):
			data = _run_coroutine(lambda: asyncio.wait_for(synth_bytes(chunks), timeout=_EDGE_TIMEOUT * len(chunks)))
			if data:
				with open(tmp, "wb") as f:
					f.write(data)
				os.replace(tmp, out_path)
				return True
			return False

		plans = [[text]] * attempts
		chunks = _split_phrases(text)
		if len(chunks) > 1:
			plans.append(chunks)

		for attempt, plan in enumerate(plans, start=1):
			try:
				if write(plan):
					return True
			except NoAudioReceived as e:
				print(f"[TTS] Edge TTS ตอบว่าง ครั้งที่ {attempt} ({voice}, {len(plan)} ท่อน): {e}")
			except Exception as e:
				print(f"[TTS] Edge TTS เชื่อมต่อไม่ได้ ({voice}): {e}")
				self._remove(tmp)
				return False
			self._remove(tmp)
			if attempt < attempts:
				time.sleep(1.5 * attempt)
		return False

	def _gtts_save(self, text, lang, out_path):
		tmp = out_path + ".part"
		try:
			from gtts import gTTS
			gTTS(text=text, lang=_GTTS_LANG.get(lang, "th")).save(tmp)
			if self._valid(tmp):
				os.replace(tmp, out_path)
				return True
		except Exception as e:
			print(f"[TTS] gTTS ล้มเหลว: {e}")
		self._remove(tmp)
		return False

	def _say_save(self, text, out_path):
		tmp = out_path + ".aiff"
		safe = text.replace('"', "")
		if os.system(f'say -v Kanya "{safe}" -o "{tmp}" 2>/dev/null') == 0 and self._valid(tmp):
			os.replace(tmp, out_path)
			return True
		self._remove(tmp)
		return False

	@staticmethod
	def _remove(path):
		try:
			if os.path.exists(path):
				os.remove(path)
		except OSError:
			pass

	# ---- รายชื่อเสียงทั้งหมด (สำหรับเลือก "เสียงอื่น ๆ") ----
	def list_voices(self, lang):
		"""คืน [(ชื่อเสียง, คำอธิบาย)] ของภาษา จากไฟล์ที่เคยดาวน์โหลดไว้ (ออฟไลน์ได้)"""
		voices = []
		if os.path.exists(self.voices_file):
			try:
				with open(self.voices_file, "r", encoding="utf-8") as f:
					voices = json.load(f)
			except Exception:
				voices = []
		if not voices:
			voices = [{"ShortName": v, "Gender": "", "Personalities": []}
					  for presets in PRESETS.values() for v, _ in presets.values()]

		prefix = _VOICE_LOCALE_PREFIX.get(lang, "th-")
		out, seen = [], set()
		for v in voices:
			name = v.get("ShortName", "")
			if not name.startswith(prefix) or name in seen:
				continue
			seen.add(name)
			gender = {"Female": "หญิง", "Male": "ชาย"}.get(v.get("Gender", ""), "")
			traits = ", ".join(v.get("Personalities") or [])
			desc = " · ".join(x for x in (gender, traits) if x)
			out.append((name, desc))
		return sorted(out)

	def refresh_voices(self):
		"""ดาวน์โหลดรายชื่อเสียงทั้งหมดจากอินเทอร์เน็ตมาเก็บไว้ (เรียกจากเธรดเบื้องหลัง)"""
		try:
			edge_tts = _import_edge_tts()
			raw = _run_coroutine(edge_tts.list_voices)
			keep = []
			for v in raw:
				name = v.get("ShortName", "")
				if name.startswith(tuple(_VOICE_LOCALE_PREFIX.values())):
					keep.append({
						"ShortName": name,
						"Gender": v.get("Gender", ""),
						"Personalities": (v.get("VoiceTag") or {}).get("VoicePersonalities", []),
					})
			with open(self.voices_file, "w", encoding="utf-8") as f:
				json.dump(keep, f, ensure_ascii=False, indent=1)
			return len(keep)
		except Exception as e:
			print(f"[TTS] โหลดรายชื่อเสียงไม่สำเร็จ: {e}")
			return 0
