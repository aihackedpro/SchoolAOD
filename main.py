import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QSharedMemory
from audio_engine import AudioEngine
from scheduler_engine import SchoolScheduler
from remote_server import start_remote_server_async
from tunnel_manager import TunnelManager
from config_manager import load_config
from ui.main_window import MainWindow
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

	config = load_config()
	port = config.get("remote_port", 8000)

	audio = AudioEngine()
	scheduler = SchoolScheduler(audio)
	scheduler.start()

	pin_code, remote_url = start_remote_server_async(audio, scheduler, port=port)

	# จัดการลิงก์รีโมท: ถ้าตั้งโดเมนถาวรไว้ ใช้เลย / ไม่งั้นสร้างลิงก์สาธารณะอัตโนมัติด้วย Cloudflare Tunnel
	tunnel = None
	domain = (config.get("remote_domain") or "").strip()
	if domain:
		remote_url = domain
	elif config.get("tunnel_enabled", True) and TunnelManager.available():
		tunnel = TunnelManager(port)
		tunnel.start()
		app.aboutToQuit.connect(tunnel.stop)

	window = MainWindow(audio, scheduler, pin_code, remote_url, tunnel=tunnel)
	window.show()

	sys.exit(app.exec())

if __name__ == "__main__":
	main()
