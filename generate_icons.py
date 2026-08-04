"""สร้างไอคอนแอป (PNG หลายขนาด + ICO) ลงโฟลเดอร์ assets/
รันครั้งเดียวตอน dev: python generate_icons.py
"""
import os
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QPainter, QColor, QLinearGradient, QBrush, QPainterPath
from PySide6.QtCore import Qt, QRectF


def make_icon(size: int) -> QPixmap:
	S = float(size)
	pm = QPixmap(size, size)
	pm.fill(Qt.transparent)
	p = QPainter(pm)
	p.setRenderHint(QPainter.Antialiasing)

	# พื้นหลังเขียวมรกตไล่เฉด มุมมน
	grad = QLinearGradient(0, 0, S, S)
	grad.setColorAt(0.0, QColor("#10B981"))
	grad.setColorAt(1.0, QColor("#047857"))
	p.setBrush(QBrush(grad))
	p.setPen(Qt.NoPen)
	p.drawRoundedRect(QRectF(0, 0, S, S), S * 0.22, S * 0.22)

	# กระดิ่งสีขาว (วาดเป็นเวกเตอร์ เรนเดอร์ได้ทุกที่)
	cx = S / 2
	white = QColor("#FFFFFF")
	p.setBrush(QBrush(white))

	# หูจับด้านบน
	p.drawEllipse(QRectF(cx - S * 0.05, S * 0.16, S * 0.10, S * 0.10))

	# ตัวระฆัง
	body = QPainterPath()
	body.moveTo(cx, S * 0.22)
	body.cubicTo(cx - S * 0.06, S * 0.24, cx - S * 0.30, S * 0.34, cx - S * 0.30, S * 0.60)
	body.lineTo(cx - S * 0.34, S * 0.66)
	body.lineTo(cx + S * 0.34, S * 0.66)
	body.lineTo(cx + S * 0.30, S * 0.60)
	body.cubicTo(cx + S * 0.30, S * 0.34, cx + S * 0.06, S * 0.24, cx, S * 0.22)
	p.drawPath(body)

	# ขอบล่างระฆัง
	p.drawRoundedRect(QRectF(cx - S * 0.36, S * 0.655, S * 0.72, S * 0.075), S * 0.03, S * 0.03)

	# ลูกกระดิ่ง
	p.drawEllipse(QRectF(cx - S * 0.055, S * 0.745, S * 0.11, S * 0.11))
	p.end()
	return pm


def main():
	app = QApplication(sys.argv)
	os.makedirs("assets", exist_ok=True)

	targets = {
		"assets/icon-192.png": 192,
		"assets/icon-512.png": 512,
		"assets/apple-touch-icon.png": 180,
		"assets/icon.png": 256,
	}
	for path, size in targets.items():
		make_icon(size).save(path, "PNG")
		print(f"  [OK] {path} ({size}x{size})")

	# ICO สำหรับไอคอนไฟล์ .exe บน Windows (หลายขนาดในไฟล์เดียว)
	try:
		make_icon(256).save("assets/icon.ico", "ICO")
		print("  [OK] assets/icon.ico")
	except Exception as e:
		print(f"  [Warn] สร้าง .ico ไม่สำเร็จ: {e}")


if __name__ == "__main__":
	main()
