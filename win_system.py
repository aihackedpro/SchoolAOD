import sys
import subprocess

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
