import sys
import subprocess

# ค่าธงของ Windows SetThreadExecutionState (กันเครื่องหลับ)
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_AWAYMODE_REQUIRED = 0x00000040


def prevent_sleep():
	"""กันไม่ให้ Windows เข้าสู่โหมด Sleep/Hibernate อัตโนมัติ ขณะโปรแกรมทำงาน
	(หน้าจอยังดับได้ตามปกติ แต่ระบบจะไม่หลับ อ๊อดจึงทำงานต่อ 24 ชม.)
	"""
	if sys.platform == "win32":
		try:
			import ctypes
			ctypes.windll.kernel32.SetThreadExecutionState(
				ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
			)
			print("[Windows] เปิดโหมดกันเครื่องหลับ (ระบบอ๊อดจะทำงานต่อเนื่อง)")
			return True
		except Exception as e:
			print(f"[Windows] ตั้งค่ากันเครื่องหลับไม่สำเร็จ: {e}")
			return False
	return False


def allow_sleep():
	"""คืนค่าให้เครื่องหลับได้ตามปกติ (เรียกตอนปิดโปรแกรม)"""
	if sys.platform == "win32":
		try:
			import ctypes
			ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
		except Exception:
			pass


def config_windows_firewall(port: int = 8000):
	if sys.platform == "win32":
		try:
			cmd = f'netsh advfirewall firewall add rule name="SchoolAOD_Remote" dir=in action=allow protocol=TCP localport={port}'
			subprocess.run(cmd, shell=True, check=True)
			print(f"[Windows] Firewall opened for port {port}")
			return True
		except Exception as e:
			print(f"[Windows] Firewall Config Error: {e}")
			return False
	else:
		print(f"[{sys.platform}] Skipping Firewall config in dev mode.")
		return True
