from PySide6.QtWidgets import QWidget, QLabel
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush

class AnimatedToggle(QWidget):
	state_changed = Signal(bool)

	def __init__(self, checked=False, parent=None):
		super().__init__(parent)
		self._checked = checked
		self._thumb_position = 1.0 if checked else 0.0
		self.setFixedSize(50, 26)
		self.setCursor(Qt.PointingHandCursor)

		self.anim = QPropertyAnimation(self, b"thumb_position", self)
		self.anim.setDuration(180)
		self.anim.setEasingCurve(QEasingCurve.InOutQuad)

	@Property(float)
	def thumb_position(self):
		return self._thumb_position

	@thumb_position.setter
	def thumb_position(self, pos):
		self._thumb_position = pos
		self.update()

	def isChecked(self):
		return self._checked

	def setChecked(self, checked):
		if self._checked != checked:
			self._checked = checked
			self.anim.stop()
			self.anim.setEndValue(1.0 if checked else 0.0)
			self.anim.start()
			self.state_changed.emit(self._checked)

	def mousePressEvent(self, event):
		if event.button() == Qt.LeftButton:
			self.setChecked(not self._checked)

	def paintEvent(self, event):
		painter = QPainter(self)
		painter.setRenderHint(QPainter.Antialiasing)

		bg_color = QColor("#10B981") if self._checked else QColor("#475569")
		painter.setBrush(QBrush(bg_color))
		painter.setPen(Qt.NoPen)
		painter.drawRoundedRect(0, 0, self.width(), self.height(), 13, 13)

		thumb_x = 3 + self._thumb_position * (self.width() - 26)
		painter.setBrush(QBrush(QColor("#FFFFFF")))
		painter.drawEllipse(int(thumb_x), 3, 20, 20)


class ToastNotification(QLabel):
	def __init__(self, text, parent=None):
		super().__init__(text, parent)
		self.setStyleSheet("""
			background: rgba(16, 185, 129, 0.95);
			color: white; font-weight: bold; font-size: 14px;
			padding: 10px 24px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.4);
		""")
		self.setAlignment(Qt.AlignCenter)
		self.adjustSize()
		self.hide()

	def show_toast(self):
		if self.parent():
			p_rect = self.parent().rect()
			self.move((p_rect.width() - self.width()) // 2, p_rect.height() - self.height() - 40)
		self.show()
		self.raise_()
		QTimer.singleShot(2000, self.hide)
