import os
import re
import sys
import shutil
import subprocess
import threading
from PySide6.QtCore import QObject, Signal
from paths import exe_dir, resource_path

# จับลิงก์สาธารณะที่ cloudflared สร้างให้ (รูปแบบ https://xxxx.trycloudflare.com)
_TRYCF_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


def find_cloudflared():
	"""หา cloudflared: ข้าง ๆ ตัวโปรแกรม > ในทรัพยากรที่ฝังมา > ใน PATH ของระบบ"""
	exe = "cloudflared.exe" if sys.platform == "win32" else "cloudflared"
	for cand in (os.path.join(exe_dir(), exe), resource_path(exe)):
		if os.path.isfile(cand):
			return cand
	return shutil.which(exe) or shutil.which("cloudflared")


class TunnelManager(QObject):
	"""สร้างลิงก์ HTTPS สาธารณะอัตโนมัติด้วย Cloudflare Tunnel (ไม่ต้องมีบัญชี ไม่ต้องตั้งค่า)
	ทำให้เข้ารีโมทจากที่ไหนก็ได้ + ใช้ไมโครโฟนพูดสดได้ (ต้องเป็น HTTPS)
	"""
	url_ready = Signal(str)        # ได้ลิงก์สาธารณะแล้ว
	status_changed = Signal(str)   # สถานะ: connecting / connected / no-tool / error

	def __init__(self, port=8000):
		super().__init__()
		self.port = port
		self.process = None
		self.public_url = ""
		self._emitted = False

	@staticmethod
	def available():
		return find_cloudflared() is not None

	def start(self):
		self._bin = find_cloudflared()
		if not self._bin:
			self.status_changed.emit("no-tool")
			return
		threading.Thread(target=self._run, daemon=True).start()

	def _run(self):
		try:
			self.status_changed.emit("connecting")
			self.process = subprocess.Popen(
				# ใช้ 127.0.0.1 (IPv4) ไม่ใช่ localhost — กันปัญหาบน Windows ที่ localhost ชี้ไป IPv6 (::1) แล้วเซิร์ฟเวอร์ไม่ตอบ = 502
				[self._bin, "tunnel", "--url", f"http://127.0.0.1:{self.port}", "--no-autoupdate"],
				stdout=subprocess.PIPE,
				stderr=subprocess.STDOUT,
				text=True,
				bufsize=1,
			)
			# อ่าน output ต่อเนื่อง: จับ URL ครั้งแรก แล้วอ่านทิ้งต่อไปเรื่อย ๆ (กัน buffer เต็มจนค้าง)
			for line in self.process.stdout:
				if not self._emitted:
					m = _TRYCF_RE.search(line)
					if m:
						self.public_url = m.group(0)
						self._emitted = True
						self.url_ready.emit(self.public_url)
						self.status_changed.emit("connected")
			# ออกจากลูป = โปรเซสจบ/ตาย
			if not self._emitted:
				self.status_changed.emit("error")
		except Exception as e:
			print(f"[Tunnel] Error: {e}")
			self.status_changed.emit("error")

	def stop(self):
		if self.process:
			try:
				self.process.terminate()
			except Exception:
				pass
