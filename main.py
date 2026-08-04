import sys
import os

# สำคัญ: ตอนเป็น .exe แบบ windowed จะไม่มี console → sys.stdout/stderr เป็น None
# ทำให้ไลบรารีที่เรียก sys.stdout.isatty() (เช่น uvicorn logging) พัง แล้วเซิร์ฟเวอร์ไม่สตาร์ท
# ต้องคืนค่าให้เป็นสตรีมจริงก่อน import อย่างอื่น
if sys.stdout is None:
	sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
	sys.stderr = open(os.devnull, "w", encoding="utf-8")

import time
import socket
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QSharedMemory


def wait_server_ready(port, timeout=15):
	"""รอจนเว็บเซิร์ฟเวอร์ในตัวโปรแกรมพร้อมรับการเชื่อมต่อจริง ก่อนเปิด tunnel (กัน 502)"""
	deadline = time.time() + timeout
	while time.time() < deadline:
		try:
			with socket.create_connection(("127.0.0.1", port), timeout=1):
				return True
		except OSError:
			time.sleep(0.25)
	return False
from audio_engine import AudioEngine
from scheduler_engine import SchoolScheduler
from remote_server import start_remote_server_async
from tunnel_manager import TunnelManager
from config_manager import load_config
from ui.main_window import MainWindow
from win_system import prevent_sleep, allow_sleep
import paths

def main():
	app = QApplication(sys.argv)
	app.setQuitOnLastWindowClosed(False)  # ไม่ปิดโปรแกรมเมื่อปิดหน้าต่าง ให้ย่อลง System Tray

	# ป้องกันการเปิดโปรแกรมซ้ำ
	shared_mem = QSharedMemory("SchoolAOD_Single_Instance_Lock_v1")
	if not shared_mem.create(1):
		QMessageBox.warning(None, "เตือนระบบ", "โปรแกรมระบบอ๊อดโรงเรียนกำลังเปิดทำงานอยู่อีกหน้าต่างหนึ่งแล้ว!")
		sys.exit(0)

	# เปิดครั้งแรก: เตรียมไฟล์เสียงเริ่มต้นไปยังโฟลเดอร์ข้อมูล (สำคัญตอนเป็น .exe)
	paths.ensure_default_assets()

	# กันเครื่องหลับ/Hibernate เพื่อให้ระบบอ๊อดทำงานต่อเนื่อง 24 ชม.
	prevent_sleep()
	app.aboutToQuit.connect(allow_sleep)

	config = load_config()
	port = config.get("remote_port", 8000)

	audio = AudioEngine()
	scheduler = SchoolScheduler(audio)
	scheduler.start()

	pin_code, lan_url, public_url = start_remote_server_async(audio, scheduler, port=port)

	# รอให้เว็บเซิร์ฟเวอร์พร้อมก่อน แล้วค่อยเปิด tunnel (กันปัญหา 502 ตอนต่อ)
	server_ok = wait_server_ready(port)
	print(f"[Main] เว็บเซิร์ฟเวอร์ {'พร้อม' if server_ok else 'ยังไม่ตอบสนอง'} ที่พอร์ต {port}")

	# จัดการลิงก์สาธารณะ: ถ้าตั้งโดเมนถาวรไว้ ใช้เลย / ไม่งั้นสร้างอัตโนมัติด้วย Cloudflare Tunnel
	tunnel = None
	if not public_url and config.get("tunnel_enabled", True) and TunnelManager.available():
		tunnel = TunnelManager(port)
		tunnel.start()
		app.aboutToQuit.connect(tunnel.stop)

	window = MainWindow(audio, scheduler, pin_code, lan_url, public_url, tunnel=tunnel)
	window.show()

	sys.exit(app.exec())

if __name__ == "__main__":
	main()
