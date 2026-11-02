"""สังเคราะห์เสียงติ่งต่อง 10 แบบ × 3 ความยาว → sounds/chimes/*.wav
รันครั้งเดียวตอนพัฒนา: python generate_chimes.py (ใช้แค่ไลบรารีมาตรฐานของ Python)

ใช้ additive synthesis: แต่ละเครื่องดนตรีประกอบจาก partial (ความถี่ย่อย) ที่มีอัตราส่วน/ความดัง/การจางต่างกัน
"""
import math
import os
import wave
from array import array
from chimes import CHIME_DESIGNS, NOTES, LENGTH_TEMPO, CHIME_LENGTHS, chime_filename

SR = 22050          # พอสำหรับเสียงติ่งต่อง และทำให้ไฟล์เล็ก
NYQUIST_SAFE = 10000

# (อัตราส่วนความถี่, ความดัง, ตัวคูณความเร็วในการจาง)
TIMBRES = {
	"bar": [(1.0, 1.0, 1.0), (2.756, 0.45, 1.8), (5.404, 0.18, 3.0)],              # แท่งโลหะแบบกริ่งประตู
	"vibes": [(1.0, 1.0, 1.0), (4.0, 0.22, 2.5), (10.0, 0.05, 4.0)],               # ไวบราโฟน
	"marimba": [(1.0, 1.0, 1.0), (3.932, 0.35, 2.5), (9.538, 0.10, 4.0)],          # มาริมบา/ระนาด
	"bell": [(0.5, 0.30, 0.6), (1.0, 1.0, 1.0), (1.2, 0.45, 1.3), (1.5, 0.30, 1.6),
			 (2.0, 0.35, 1.8), (2.5, 0.18, 2.4), (3.0, 0.12, 3.0)],               # ระฆังหอนาฬิกา
	"handbell": [(1.0, 1.0, 1.0), (2.0, 0.22, 1.5), (3.0, 0.28, 2.0), (4.2, 0.14, 2.6)],
	"piano": [(1.0, 1.0, 1.0), (2.0, 0.50, 1.4), (3.0, 0.28, 1.9), (4.0, 0.15, 2.4), (5.0, 0.08, 3.0)],
	"crystal": [(1.0, 1.0, 1.0), (1.003, 0.6, 1.0), (2.0, 0.28, 1.3), (3.01, 0.14, 1.8)],  # คู่ความถี่เหลื่อมกันให้เสียงระยิบ
	"harp": [(1.0, 1.0, 1.0), (2.0, 0.45, 1.6), (3.0, 0.22, 2.2), (4.0, 0.10, 3.0)],
	"alert": [(1.0, 1.0, 1.0), (3.0, 0.22, 1.0), (5.0, 0.08, 1.0)],
}
ATTACK = {"marimba": 0.002, "harp": 0.003, "alert": 0.012}
TREMOLO = {"vibes": (5.5, 0.18)}   # ความถี่ (Hz), ความลึก


def render_note(buf, start, freq, kind, ring, sustain=None):
	partials = [(freq * r, a, d) for r, a, d in TIMBRES[kind] if freq * r < NYQUIST_SAFE]
	attack = ATTACK.get(kind, 0.005)
	k = 4.6 / ring   # ความดังลดเหลือ ~1% (-40 dB) เมื่อครบเวลา ring
	length = int((sustain + 0.06 if sustain else ring * 1.15) * SR)
	start_i = int(start * SR)
	trem = TREMOLO.get(kind)
	two_pi = 2 * math.pi
	for n in range(length):
		t = n / SR
		env_a = min(1.0, t / attack)
		if sustain:   # เสียงแจ้งเตือน: ดังคงที่แล้วค่อยปล่อย
			env_s = 1.0 if t < sustain else math.exp(-(t - sustain) / 0.02)
		s = 0.0
		for f, a, d in partials:
			env = env_s if sustain else math.exp(-k * d * t)
			s += a * env * math.sin(two_pi * f * t)
		if trem:
			s *= 1.0 - trem[1] * (0.5 + 0.5 * math.sin(two_pi * trem[0] * t))
		idx = start_i + n
		if idx >= len(buf):
			break
		buf[idx] += s * env_a


def render_chime(style, length):
	design = CHIME_DESIGNS[style]
	spacing_mult, ring_mult = LENGTH_TEMPO[length]
	notes = design[length]
	spacing = design["spacing"] * spacing_mult
	ring = design["ring"] * ring_mult
	kind = design["kind"]
	sustain = spacing * 0.85 if kind == "alert" else None

	total = spacing * (len(notes) - 1) + (sustain + 0.1 if sustain else ring * 1.15)
	buf = [0.0] * int(total * SR + 1)
	for i, name in enumerate(notes):
		render_note(buf, i * spacing, NOTES[name], kind, ring, sustain)

	# ปรับความดังสูงสุดให้เท่ากันทุกไฟล์ + เฟดท้าย 40ms กันเสียงคลิก
	peak = max(abs(x) for x in buf) or 1.0
	gain = 0.85 / peak
	fade = int(0.04 * SR)
	out = array("h")
	for i, x in enumerate(buf):
		if i >= len(buf) - fade:
			x *= (len(buf) - i) / fade
		out.append(int(max(-1.0, min(1.0, x * gain)) * 32767))
	return out


def main():
	out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds", "chimes")
	os.makedirs(out_dir, exist_ok=True)
	for style in CHIME_DESIGNS:
		for length, _ in CHIME_LENGTHS:
			samples = render_chime(style, length)
			path = os.path.join(out_dir, chime_filename(style, length))
			with wave.open(path, "wb") as w:
				w.setnchannels(1)
				w.setsampwidth(2)
				w.setframerate(SR)
				w.writeframes(samples.tobytes())
			print(f"  [OK] {chime_filename(style, length):24s} {len(samples) / SR:4.1f}s")


if __name__ == "__main__":
	main()
