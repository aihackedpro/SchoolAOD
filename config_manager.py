import copy
import json
import os
import secrets
from paths import data_path

CONFIG_FILE = data_path("config.json")

DEFAULT_CONFIG = {
	"remote_pin": str(secrets.randbelow(900000) + 100000),
	"remote_port": 8000,
	"volume": 80,
	"theme": "standard",
	"auto_start": False,
	# โดเมน/URL ถาวรสำหรับรีโมท (เช่นจาก ngrok/Cloudflare) — ตั้งครั้งเดียวใช้ตลอด ปล่อยว่าง = สร้างลิงก์อัตโนมัติ
	"remote_domain": "",
	# สร้างลิงก์สาธารณะอัตโนมัติด้วย Cloudflare Tunnel เมื่อไม่ได้ตั้ง remote_domain ไว้
	"tunnel_enabled": True,
	# อนุญาตให้พูดประชาสัมพันธ์สดผ่านรีโมทหรือไม่ (เครื่องแม่ควบคุมได้)
	"allow_remote_voice": True,
	# ---- ระบบเสียง AI ----
	"tts_style": "female",                                   # female / male / girl / boy
	"tts_speed": "normal",                                   # slower / slow / normal / fast / faster
	"tts_voice_overrides": {"th": "", "en": "", "zh": ""},   # เลือกเสียงเฉพาะภาษา (ว่าง = ตามสไตล์)
	"announce_templates": [],                                # ข้อความประกาศสำเร็จรูปที่ผู้ใช้บันทึกไว้
	# ---- ระบบอัปเดต ----
	"auto_check_update": True,
}

# config ชุดเดียวที่ทุกส่วนของโปรแกรมใช้ร่วมกัน (แก้ที่หนึ่ง ที่อื่นเห็นทันที)
_CONFIG = None


def load_config():
	global _CONFIG
	if _CONFIG is not None:
		return _CONFIG

	config = None
	if os.path.exists(CONFIG_FILE):
		try:
			with open(CONFIG_FILE, "r", encoding="utf-8") as f:
				config = json.load(f)
		except Exception:
			config = None
	if not isinstance(config, dict):
		config = {}

	changed = not os.path.exists(CONFIG_FILE)
	for k, v in DEFAULT_CONFIG.items():
		if k not in config:
			config[k] = copy.deepcopy(v)
			changed = True

	_CONFIG = config
	if changed:
		save_config(config)
	return _CONFIG


def save_config(config_data=None):
	data = config_data if config_data is not None else _CONFIG
	if data is None:
		return
	try:
		with open(CONFIG_FILE, "w", encoding="utf-8") as f:
			json.dump(data, f, ensure_ascii=False, indent=2)
	except Exception as e:
		print(f"[Config] Error saving config.json: {e}")
