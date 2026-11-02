"""การเชื่อมต่ออินเทอร์เน็ตแบบ HTTPS ที่ใช้ร่วมกันทั้งโปรแกรม

ปัญหาที่แก้: ใน .exe บน Windows (เครื่องลงใหม่ / VM / เน็ตโรงเรียนที่มี proxy) Python มักหาใบรับรอง
ไม่เจอ → CERTIFICATE_VERIFY_FAILED จึงรวมใบรับรอง 2 แหล่ง:
- certifi: ชุดใบรับรองมาตรฐานที่แพ็กมากับโปรแกรม (ใช้ได้แม้ Windows ยังไม่มีใบรับรองนั้น)
- ใบรับรองของระบบ: รวมใบรับรองของ proxy/ไฟร์วอลล์ที่โรงเรียนติดตั้งไว้
"""
import ssl
import urllib.request

_CONTEXT = None


def ssl_context():
	global _CONTEXT
	if _CONTEXT is None:
		try:
			import certifi
			ctx = ssl.create_default_context(cafile=certifi.where())
		except Exception:
			ctx = ssl.create_default_context()
		try:
			ctx.load_default_certs()
		except Exception:
			pass
		_CONTEXT = ctx
	return _CONTEXT


def urlopen(request, timeout=10):
	return urllib.request.urlopen(request, timeout=timeout, context=ssl_context())
