"""เสียงติ่งต่อง 10 แบบ × 3 ความยาว (สั้นกระชับ / ปานกลาง / ยาว)

ไฟล์เสียงสังเคราะห์ขึ้นเองทั้งหมดด้วย generate_chimes.py (ไม่มีลิขสิทธิ์ผู้อื่น)
และฝังมากับโปรแกรมที่ sounds/chimes/<แบบ>_<ความยาว>.wav
"""
import os
from paths import resource_path, data_path

CHIME_STYLES = [
	("classic", "🔔 ติ๊ง-ต่อง คลาสสิก"),
	("airport", "✈️ สนามบิน (3 โน้ตขึ้น)"),
	("station", "🚉 สถานีรถไฟ"),
	("westminster", "🏛️ หอนาฬิกาเวสต์มินสเตอร์"),
	("school", "🛎️ กระดิ่งโรงเรียน"),
	("xylophone", "🎶 ระนาด / ไซโลโฟน"),
	("piano", "🎹 เปียโนนุ่มนวล"),
	("crystal", "💎 กระดิ่งแก้วคริสตัล"),
	("harp", "🎵 ฮาร์ปไล่โน้ต"),
	("alert", "📣 ประกาศด่วน (สองโทน)"),
]
CHIME_LENGTHS = [
	("short", "⚡ สั้นกระชับ"),
	("medium", "⏺️ ปานกลาง"),
	("long", "🎼 ยาว"),
]
STYLE_KEYS = {k for k, _ in CHIME_STYLES}
LENGTH_KEYS = {k for k, _ in CHIME_LENGTHS}

# ---- การออกแบบเสียง (ใช้โดย generate_chimes.py) ----
# kind = ลักษณะเสียงเครื่องดนตรี, spacing = ระยะห่างโน้ต (วินาที), ring = เวลาเสียงก้องจนเงียบ (วินาที)
NOTES = {
	"G4": 392.00, "A4": 440.00, "B4": 493.88, "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46,
	"G5": 783.99, "A5": 880.00, "B5": 987.77, "C6": 1046.50, "D6": 1174.66, "E6": 1318.51, "G6": 1567.98,
}
CHIME_DESIGNS = {
	"classic": {"kind": "bar", "spacing": 0.55, "ring": 1.6,
				"short": ["E5", "C5"], "medium": ["E5", "C5"], "long": ["E5", "C5", "E5", "C5"]},
	"airport": {"kind": "vibes", "spacing": 0.42, "ring": 1.8,
				"short": ["C5", "G5"], "medium": ["C5", "E5", "G5"], "long": ["C5", "E5", "G5", "C6"]},
	"station": {"kind": "marimba", "spacing": 0.22, "ring": 0.8,
				"short": ["G5", "C6"], "medium": ["G4", "C5", "E5", "G5"], "long": ["G4", "C5", "E5", "G5", "E5", "C5", "G4"]},
	"westminster": {"kind": "bell", "spacing": 0.55, "ring": 2.0,
					"short": ["E5", "C5"], "medium": ["E5", "C5", "D5", "G4"], "long": ["E5", "C5", "D5", "G4", "G4", "D5", "E5", "C5"]},
	"school": {"kind": "handbell", "spacing": 0.28, "ring": 1.2,
			   "short": ["D6", "D6"], "medium": ["D6", "D6", "D6"], "long": ["D6", "D6", "D6", "D6", "D6", "D6"]},
	"xylophone": {"kind": "marimba", "spacing": 0.14, "ring": 0.55,
				  "short": ["C5", "G5"], "medium": ["C5", "E5", "G5", "C6"], "long": ["C5", "E5", "G5", "C6", "G5", "E5", "C5"]},
	"piano": {"kind": "piano", "spacing": 0.38, "ring": 2.0,
			  "short": ["E5", "C5"], "medium": ["G4", "C5", "E5"], "long": ["G4", "C5", "E5", "G5", "C6"]},
	"crystal": {"kind": "crystal", "spacing": 0.30, "ring": 2.2,
				"short": ["G5", "D6"], "medium": ["G5", "D6", "G6"], "long": ["G5", "D6", "G6", "D6", "G6"]},
	"harp": {"kind": "harp", "spacing": 0.10, "ring": 1.6,
			 "short": ["C5", "E5", "G5"], "medium": ["C5", "E5", "G5", "B5", "C6"], "long": ["C5", "E5", "G5", "B5", "C6", "E6", "G6"]},
	"alert": {"kind": "alert", "spacing": 0.32, "ring": 0.30,
			  "short": ["A5", "E5"], "medium": ["A5", "E5", "A5", "E5"], "long": ["A5", "E5", "A5", "E5", "A5", "E5"]},
}
# ปรับจังหวะตามความยาว: สั้น = โน้ตชิดกันและก้องสั้น, ยาว = ก้องยาวขึ้น
LENGTH_TEMPO = {"short": (0.75, 0.6), "medium": (1.0, 1.0), "long": (1.0, 1.25)}


def chime_filename(style, length):
	return f"{style}_{length}.wav"


def chime_path(style, length):
	"""path ไฟล์ติ่งต่องที่จะเล่นจริง — ถ้าหาไม่เจอ ใช้เสียงติ่งต่องเดิมของระบบแทน"""
	style = style if style in STYLE_KEYS else "classic"
	length = length if length in LENGTH_KEYS else "medium"
	path = resource_path("sounds", "chimes", chime_filename(style, length))
	if os.path.exists(path):
		return path
	return data_path("sounds", "chime.mp3")
