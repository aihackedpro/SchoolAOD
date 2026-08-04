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
	"allow_remote_voice": True
}

def load_config():
	if os.path.exists(CONFIG_FILE):
		try:
			with open(CONFIG_FILE, "r", encoding="utf-8") as f:
				config = json.load(f)
				for k, v in DEFAULT_CONFIG.items():
					if k not in config:
						config[k] = v
				return config
		except Exception:
			pass
	save_config(DEFAULT_CONFIG)
	return DEFAULT_CONFIG

def save_config(config_data):
	try:
		with open(CONFIG_FILE, "w", encoding="utf-8") as f:
			json.dump(config_data, f, ensure_ascii=False, indent=2)
	except Exception as e:
		print(f"[Config] Error saving config.json: {e}")
