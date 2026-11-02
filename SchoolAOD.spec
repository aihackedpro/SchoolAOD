# -*- mode: python ; coding: utf-8 -*-
# ไฟล์กำหนดค่าการแพ็กเป็นโปรแกรมเดียว (PyInstaller)
# ใช้ได้ทั้ง Windows (.exe) และ macOS — build บนระบบปฏิบัติการปลายทางเท่านั้น
from PyInstaller.utils.hooks import collect_all

datas = [('sounds', 'sounds'), ('assets', 'assets')]
binaries = []
hiddenimports = []

# รวมไฟล์/ซับโมดูลของไลบรารีที่ PyInstaller มักตรวจไม่เจอเอง
for pkg in [
	'uvicorn', 'websockets', 'wsproto', 'fastapi', 'starlette',
	'gtts', 'anyio', 'sniffio', 'click', 'h11',
	'pydantic', 'pydantic_core', 'requests', 'certifi', 'idna', 'urllib3', 'charset_normalizer',
	# เสียง AI (Edge Neural TTS) และไลบรารีเครือข่ายที่ใช้
	'edge_tts', 'aiohttp', 'aiohappyeyeballs', 'aiosignal', 'attr', 'attrs', 'frozenlist',
	'multidict', 'propcache', 'yarl', 'tabulate', 'typing_extensions',
]:
	try:
		d, b, h = collect_all(pkg)
		datas += d
		binaries += b
		hiddenimports += h
	except Exception:
		pass

a = Analysis(
	['main.py'],
	pathex=[],
	binaries=binaries,
	datas=datas,
	hiddenimports=hiddenimports,
	hookspath=[],
	hooksconfig={},
	runtime_hooks=[],
	excludes=[],
	noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
	pyz,
	a.scripts,
	a.binaries,
	a.datas,
	[],
	name='SchoolAOD',
	debug=False,
	bootloader_ignore_signals=False,
	strip=False,
	upx=False,
	runtime_tmpdir=None,
	console=False,
	disable_windowed_traceback=False,
	icon='assets/icon.ico',
)
