"""ระบบอัปเดตโปรแกรมอัตโนมัติจาก GitHub Releases

ขั้นตอน: ตรวจเวอร์ชันล่าสุด → ผู้ใช้ยืนยัน → ดาวน์โหลด zip → แตกไฟล์ →
สคริปต์ติดตั้งรอโปรแกรมเดิมปิด → คัดลอกไฟล์ใหม่ทับ → เปิดโปรแกรมใหม่เอง
ข้อมูลผู้ใช้ (ตาราง/เสียง/ตั้งค่า) อยู่ใน %APPDATA%\\SchoolAOD จึงไม่หายเมื่ออัปเดต
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from PySide6.QtCore import QObject, Signal
from paths import is_frozen
from version import APP_VERSION, GITHUB_REPO, UPDATE_ASSET_NAME, is_newer

_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": f"SchoolAOD-Updater/{APP_VERSION}"}


def fetch_latest_release(timeout=12):
	"""ข้อมูล Release ล่าสุดบน GitHub (โยน exception ถ้าเชื่อมต่อไม่ได้)"""
	req = urllib.request.Request(_API_LATEST, headers=_HEADERS)
	with urllib.request.urlopen(req, timeout=timeout) as resp:
		data = json.loads(resp.read().decode("utf-8"))

	asset = next((a for a in data.get("assets", []) if a.get("name") == UPDATE_ASSET_NAME), None)
	tag = data.get("tag_name", "")
	return {
		"tag": tag,
		"version": tag.lstrip("vV"),
		"name": data.get("name") or tag,
		"notes": data.get("body") or "",
		"html_url": data.get("html_url") or RELEASES_PAGE,
		"published_at": (data.get("published_at") or "")[:10],
		"asset_url": asset.get("browser_download_url") if asset else "",
		"asset_size": asset.get("size", 0) if asset else 0,
		"is_newer": is_newer(tag),
	}


def can_self_update():
	"""ติดตั้งทับเองได้เฉพาะตัวโปรแกรม .exe บน Windows (ตอน dev จะเปิดหน้า Releases แทน)"""
	return is_frozen() and sys.platform == "win32"


def _ps_quote(path):
	return "'" + str(path).replace("'", "''") + "'"


class UpdateManager(QObject):
	check_finished = Signal(object, str)     # (ข้อมูล release หรือ None, ข้อความ error)
	download_progress = Signal(int, int)     # ดาวน์โหลดแล้ว / ทั้งหมด (bytes)
	install_ready = Signal(bool, str)        # (พร้อมติดตั้ง, path สคริปต์ หรือข้อความ error)

	def __init__(self, parent=None):
		super().__init__(parent)
		self._busy = False

	def check_async(self):
		if self._busy:
			return
		self._busy = True
		threading.Thread(target=self._check_worker, daemon=True).start()

	def _check_worker(self):
		try:
			info = fetch_latest_release()
			self.check_finished.emit(info, "")
		except Exception as e:
			self.check_finished.emit(None, str(e))
		finally:
			self._busy = False

	def download_async(self, info):
		threading.Thread(target=self._download_worker, args=(info,), daemon=True).start()

	def _download_worker(self, info):
		try:
			if not info.get("asset_url"):
				raise RuntimeError(f"Release นี้ไม่มีไฟล์ {UPDATE_ASSET_NAME}")

			work_dir = tempfile.mkdtemp(prefix="SchoolAOD_update_")
			zip_path = os.path.join(work_dir, UPDATE_ASSET_NAME)
			req = urllib.request.Request(info["asset_url"], headers={"User-Agent": _HEADERS["User-Agent"]})
			with urllib.request.urlopen(req, timeout=30) as resp, open(zip_path, "wb") as out:
				total = int(resp.headers.get("Content-Length") or info.get("asset_size") or 0)
				done = 0
				while True:
					chunk = resp.read(256 * 1024)
					if not chunk:
						break
					out.write(chunk)
					done += len(chunk)
					self.download_progress.emit(done, total)

			extract_dir = os.path.join(work_dir, "new")
			with zipfile.ZipFile(zip_path) as zf:
				zf.extractall(extract_dir)

			new_exe = self._find_file(extract_dir, "SchoolAOD.exe")
			if not new_exe:
				raise RuntimeError("ไม่พบไฟล์ SchoolAOD.exe ในไฟล์อัปเดต")

			script = self._write_install_script(os.path.dirname(new_exe), work_dir)
			self.install_ready.emit(True, script)
		except Exception as e:
			self.install_ready.emit(False, str(e))

	@staticmethod
	def _find_file(root, name):
		for dirpath, _, files in os.walk(root):
			if name in files:
				return os.path.join(dirpath, name)
		return ""

	@staticmethod
	def _write_install_script(src_dir, work_dir):
		"""สคริปต์ PowerShell: รอโปรแกรมเดิมปิด → คัดลอกไฟล์ใหม่ทับ (ลองซ้ำถ้าไฟล์ยังถูกล็อก) → เปิดใหม่"""
		exe_path = sys.executable
		app_dir = os.path.dirname(exe_path)
		# .exe แบบไฟล์เดียว (PyInstaller onefile) มี 2 โปรเซส: ตัวเปิด (parent) ที่ล็อกไฟล์ .exe ไว้ + ตัวโปรแกรม (เรา)
		# ต้องรอให้ทั้งคู่ปิดก่อน จึงจะคัดลอกไฟล์ใหม่ทับได้
		script = f"""$ErrorActionPreference = 'SilentlyContinue'
$oldPid = {os.getpid()}
$parentPid = {os.getppid()}
$src = {_ps_quote(src_dir)}
$exe = {_ps_quote(exe_path)}
$appDir = {_ps_quote(app_dir)}
$work = {_ps_quote(work_dir)}

while (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {{ Start-Sleep -Milliseconds 500 }}
$parent = Get-Process -Id $parentPid -ErrorAction SilentlyContinue
if ($parent -and $parent.Path -eq $exe) {{
	for ($i = 0; $i -lt 60 -and (Get-Process -Id $parentPid -ErrorAction SilentlyContinue); $i++) {{ Start-Sleep -Milliseconds 500 }}
}}
Start-Sleep -Seconds 1

for ($i = 0; $i -lt 30; $i++) {{
	try {{ Copy-Item -LiteralPath (Join-Path $src 'SchoolAOD.exe') -Destination $exe -Force -ErrorAction Stop; break }}
	catch {{ Start-Sleep -Seconds 1 }}
}}
foreach ($f in @('cloudflared.exe', 'README_USER.txt')) {{
	$p = Join-Path $src $f
	if (Test-Path -LiteralPath $p) {{
		for ($i = 0; $i -lt 10; $i++) {{
			try {{ Copy-Item -LiteralPath $p -Destination (Join-Path $appDir $f) -Force -ErrorAction Stop; break }}
			catch {{ Start-Sleep -Seconds 1 }}
		}}
	}}
}}

Start-Process -FilePath $exe -WorkingDirectory $appDir
Start-Sleep -Seconds 3
Remove-Item -LiteralPath $work -Recurse -Force
"""
		path = os.path.join(work_dir, "install_update.ps1")
		# UTF-8 แบบมี BOM เพื่อให้ Windows PowerShell อ่านชื่อโฟลเดอร์ภาษาไทยได้ถูกต้อง
		with open(path, "w", encoding="utf-8-sig") as f:
			f.write(script)
		return path

	@staticmethod
	def launch_installer(script_path):
		"""เปิดสคริปต์ติดตั้งแบบแยกโปรเซส (ทำงานต่อหลังโปรแกรมนี้ปิดตัวลง)"""
		flags = 0
		if sys.platform == "win32":
			flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
		powershell = shutil.which("powershell") or "powershell"
		subprocess.Popen(
			[powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script_path],
			creationflags=flags,
			close_fds=True,
		)
