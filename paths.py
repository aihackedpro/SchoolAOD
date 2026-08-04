import os
import sys
import shutil

APP_NAME = "SchoolAOD"


def is_frozen() -> bool:
	"""กำลังรันแบบ .exe (แพ็กด้วย PyInstaller) หรือไม่"""
	return getattr(sys, "frozen", False)


def resource_dir() -> str:
	"""โฟลเดอร์ทรัพยากรที่ฝังมากับโปรแกรม (อ่านอย่างเดียว)
	- ตอนเป็น .exe: โฟลเดอร์ชั่วคราวที่ PyInstaller คลายไฟล์ไว้ (_MEIPASS)
	- ตอน dev: โฟลเดอร์โปรเจกต์
	"""
	if is_frozen():
		return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
	return os.path.dirname(os.path.abspath(__file__))


def exe_dir() -> str:
	"""โฟลเดอร์ที่ไฟล์ .exe วางอยู่จริง (ใช้หาไฟล์ข้าง ๆ เช่น cloudflared.exe)"""
	if is_frozen():
		return os.path.dirname(sys.executable)
	return os.path.dirname(os.path.abspath(__file__))


def data_dir() -> str:
	"""โฟลเดอร์เก็บข้อมูลที่เขียนได้ (ตั้งค่า/ตารางเวลา/ฐานข้อมูล/ไฟล์เสียง)
	- ตอนเป็น .exe: โฟลเดอร์ข้อมูลผู้ใช้ (เขียนได้เสมอ ไม่ติดสิทธิ์ Program Files)
	- ตอน dev: โฟลเดอร์โปรเจกต์ (พฤติกรรมเดิม ไม่เปลี่ยน)
	"""
	if not is_frozen():
		return os.path.dirname(os.path.abspath(__file__))

	if sys.platform == "win32":
		base = os.environ.get("APPDATA") or os.path.expanduser("~")
	elif sys.platform == "darwin":
		base = os.path.expanduser("~/Library/Application Support")
	else:
		base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")

	d = os.path.join(base, APP_NAME)
	os.makedirs(d, exist_ok=True)
	return d


DATA_DIR = data_dir()
RESOURCE_DIR = resource_dir()
EXE_DIR = exe_dir()


def data_path(*parts) -> str:
	return os.path.join(DATA_DIR, *parts)


def resource_path(*parts) -> str:
	return os.path.join(RESOURCE_DIR, *parts)


def ensure_default_assets():
	"""คัดลอกไฟล์เสียงเริ่มต้นที่ฝังมากับโปรแกรม ไปยังโฟลเดอร์ข้อมูลในการเปิดครั้งแรก"""
	src_sounds = resource_path("sounds")
	dst_sounds = data_path("sounds")
	os.makedirs(dst_sounds, exist_ok=True)

	# ตอน dev ต้นทาง=ปลายทาง จึงข้าม (ไม่ต้องคัดลอกทับ)
	if os.path.abspath(src_sounds) == os.path.abspath(dst_sounds):
		return

	if os.path.isdir(src_sounds):
		for f in os.listdir(src_sounds):
			dst = os.path.join(dst_sounds, f)
			if not os.path.exists(dst):
				try:
					shutil.copy(os.path.join(src_sounds, f), dst)
				except Exception:
					pass
