"""ข้อมูลเวอร์ชันของโปรแกรม (แหล่งเดียวของทั้งระบบ)
ตอน build ผ่าน GitHub Actions ด้วย tag (เช่น v2.1.0) ค่า APP_VERSION จะถูกเขียนทับจาก tag อัตโนมัติ
"""

APP_NAME = "School AOD"
APP_VERSION = "2.0.0"

# repo ที่ใช้ตรวจสอบและดาวน์โหลดอัปเดต
GITHUB_REPO = "aihackedpro/SchoolAOD"
UPDATE_ASSET_NAME = "SchoolAOD-Windows.zip"


def parse_version(text: str) -> tuple:
	"""แปลง 'v2.1.0' / '2.1' / '1.4' เป็น tuple ตัวเลขสำหรับเปรียบเทียบ"""
	text = (text or "").strip().lstrip("vV")
	parts = []
	for piece in text.split("."):
		digits = "".join(ch for ch in piece if ch.isdigit())
		parts.append(int(digits) if digits else 0)
	while len(parts) < 3:
		parts.append(0)
	return tuple(parts[:3])


def is_newer(remote: str, local: str = APP_VERSION) -> bool:
	return parse_version(remote) > parse_version(local)
