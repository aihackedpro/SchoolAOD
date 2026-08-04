import os
import shutil
from datetime import datetime
from PySide6.QtWidgets import (
	QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
	QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
	QFrame, QMessageBox, QGraphicsOpacityEffect, QDialog, QSystemTrayIcon, QMenu,
	QInputDialog, QButtonGroup, QApplication
)
from PySide6.QtCore import Qt, QTimer, QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QGuiApplication, QDesktopServices, QIcon, QAction
from ui.themes import get_stylesheet, normalize_theme_key, THEME_ORDER, BUTTON_COLORS
from ui.components import AnimatedToggle, ToastNotification
from ui.schedule_dialog import ScheduleFormDialog, parse_hms
from sound_db import SoundDatabase
from config_manager import load_config, save_config
from remote_server import set_allow_voice
from paths import resource_path


def styled_message(parent, title, text, buttons, icon=QMessageBox.Question):
	"""กล่องข้อความที่ปุ่ม Yes/No/Cancel มีสีต่างกันชัดเจน (เขียว/แดง/เทา)"""
	box = QMessageBox(parent)
	box.setWindowTitle(title)
	box.setText(text)
	box.setIcon(icon)
	box.setStandardButtons(buttons)
	color_map = {
		QMessageBox.Yes: BUTTON_COLORS["yes"],
		QMessageBox.Ok: BUTTON_COLORS["yes"],
		QMessageBox.No: BUTTON_COLORS["no"],
		QMessageBox.Cancel: BUTTON_COLORS["cancel"],
	}
	for std_btn, color in color_map.items():
		btn = box.button(std_btn)
		if btn:
			btn.setStyleSheet(f"background:{color}; color:#FFFFFF; font-weight:bold; border-radius:8px; padding:8px 22px; min-width:90px;")
	return box.exec()


class DragDropArea(QFrame):
	def __init__(self, sounds_dir, refresh_callback):
		super().__init__()
		self.sounds_dir = sounds_dir
		self.refresh_callback = refresh_callback
		self.setAcceptDrops(True)
		self.setStyleSheet("""
			QFrame {
				border: 2px dashed #34D399;
				border-radius: 16px;
				background-color: rgba(52, 211, 153, 0.08);
				padding: 24px;
			}
		""")

		layout = QVBoxLayout()
		self.label = QLabel("📥 ลากไฟล์เสียง (MP3 หรือ WAV) มาวางที่นี่เพื่ออัปโหลดอัตโนมัติ")
		self.label.setAlignment(Qt.AlignCenter)
		self.label.setStyleSheet("font-size: 15px; font-weight: bold; color: #34D399;")
		layout.addWidget(self.label)
		self.setLayout(layout)

	def dragEnterEvent(self, event):
		if event.mimeData().hasUrls():
			event.acceptProposedAction()

	def dropEvent(self, event):
		for url in event.mimeData().urls():
			file_path = url.toLocalFile()
			if file_path.lower().endswith(('.mp3', '.wav')):
				file_name = os.path.basename(file_path)
				dest_path = os.path.join(self.sounds_dir, file_name)
				shutil.copy(file_path, dest_path)
		self.refresh_callback()


class BellTriggerDialog(QDialog):
	def __init__(self, item_data, parent=None):
		super().__init__(parent)
		self.setWindowTitle("🔔 สัญญาณอ๊อดกำลังทำงาน!")
		self.resize(450, 250)
		self.setStyleSheet("""
			QDialog {
				background: linear-gradient(135deg, #022c22, #064e3b);
				border-radius: 16px;
				border: 2px solid #34D399;
			}
			QLabel { color: white; font-family: 'Noto Sans Thai', sans-serif; }
		""")

		layout = QVBoxLayout(self)
		
		lbl_icon = QLabel("🔔")
		lbl_icon.setAlignment(Qt.AlignCenter)
		lbl_icon.setStyleSheet("font-size: 52px; margin-top: 10px;")

		lbl_time = QLabel(f"⏰ เวลา {item_data.get('time', '')} น.")
		lbl_time.setAlignment(Qt.AlignCenter)
		lbl_time.setStyleSheet("font-size: 24px; font-weight: bold; color: #FBBF24;")

		lbl_label = QLabel(item_data.get('label', 'อ๊อดแจ้งเวลา'))
		lbl_label.setAlignment(Qt.AlignCenter)
		lbl_label.setStyleSheet("font-size: 18px; color: #34D399; font-weight: bold;")

		lbl_info = QLabel("🔊 กำลังเล่นเสียงอ๊อดระบบ (หน้าต่างนี้จะปิดเองอัตโนมัติ)...")
		lbl_info.setAlignment(Qt.AlignCenter)
		lbl_info.setStyleSheet("font-size: 12px; color: #A7F3D0; margin-top: 8px;")

		layout.addWidget(lbl_icon)
		layout.addWidget(lbl_time)
		layout.addWidget(lbl_label)
		layout.addWidget(lbl_info)


class MainWindow(QMainWindow):
	def __init__(self, audio_engine, scheduler_engine, pin_code, remote_url, tunnel=None):
		super().__init__()
		self.audio = audio_engine
		self.scheduler = scheduler_engine
		self.pin_code = pin_code
		self.remote_url = remote_url
		self.tunnel = tunnel
		self.active_alert_dialog = None

		self.setWindowTitle("ระบบอ๊อดโรงเรียนอัตโนมัติ - School AOD Masterpiece Pro")
		self.resize(1150, 750)
		self.setMinimumSize(900, 600)

		self.app_icon = QIcon(resource_path("assets", "icon.png"))
		if not self.app_icon.isNull():
			self.setWindowIcon(self.app_icon)

		# ฐานข้อมูลไฟล์เสียง (Local SQLite) + ธีมสี
		self.sound_db = SoundDatabase(self.audio.sounds_dir)
		self.config = load_config()
		self.current_theme = normalize_theme_key(self.config.get("theme", "standard"))
		self.apply_theme(self.current_theme)

		self.scheduler.bell_triggered.connect(self.show_bell_popup)
		self.audio.sequence_finished.connect(self.close_bell_popup)
		self.audio.live_broadcast_started.connect(self.show_live_popup)

		self.setup_system_tray()

		self.opacity_effect = QGraphicsOpacityEffect(self)
		self.setGraphicsEffect(self.opacity_effect)
		self.anim_fade = QPropertyAnimation(self.opacity_effect, b"opacity")
		self.anim_fade.setDuration(600)
		self.anim_fade.setStartValue(0.0)
		self.anim_fade.setEndValue(1.0)
		self.anim_fade.setEasingCurve(QEasingCurve.InOutQuad)
		self.anim_fade.start()

		self.toast = ToastNotification("📋 คัดลอกเรียบร้อย!", self)

		central_widget = QWidget()
		main_layout = QVBoxLayout(central_widget)

		self.tabs = QTabWidget()
		self.tabs.setCornerWidget(self.build_theme_switcher(), Qt.TopRightCorner)
		main_layout.addWidget(self.tabs)

		self.init_dashboard_tab()
		self.init_schedule_tab()
		self.init_audio_tab()

		footer_frame = QFrame()
		footer_layout = QVBoxLayout(footer_frame)
		footer_layout.setContentsMargins(0, 8, 0, 4)

		lbl_credits = QLabel('<a href="https://www.facebook.com/suebsing" style="color: #34D399; text-decoration: none; font-weight: bold; font-size: 13px;">Develop by hAcKEdpRO | Pongwattana Suebsing</a>')
		lbl_credits.setOpenExternalLinks(True)
		lbl_credits.setAlignment(Qt.AlignCenter)

		lbl_version = QLabel("Version 1.0 © 2026-2027 All Rights Reserved")
		lbl_version.setStyleSheet("color: #A7F3D0; font-size: 11px;")
		lbl_version.setAlignment(Qt.AlignCenter)

		footer_layout.addWidget(lbl_credits)
		footer_layout.addWidget(lbl_version)
		main_layout.addWidget(footer_frame)

		self.setCentralWidget(central_widget)

		self.update_dashboard_clock()

		self.timer = QTimer(self)
		self.timer.timeout.connect(self.update_dashboard_clock)
		self.timer.start(1000)

		# เมื่อ Cloudflare Tunnel สร้างลิงก์สาธารณะเสร็จ ให้อัปเดตลิงก์ในหน้าจอทันที
		if self.tunnel:
			self.tunnel.url_ready.connect(self.on_public_url_ready)
			self.tunnel.status_changed.connect(self.on_tunnel_status)

	def on_public_url_ready(self, public_url):
		self.remote_url = public_url
		self.lbl_url.setText(f"🌐 ลิงก์สาธารณะ (ใช้ได้ทุกที่): {public_url}")
		self.tray_icon.showMessage(
			"ลิงก์รีโมทพร้อมใช้งาน",
			f"สร้างลิงก์สาธารณะสำเร็จ:\n{public_url}",
			QSystemTrayIcon.Information,
			5000
		)

	def on_tunnel_status(self, status):
		if status in ("no-tool", "error"):
			# กลับไปแสดง IP ในวง LAN ถ้าสร้างลิงก์สาธารณะไม่ได้
			self.lbl_url.setText(f"🌐 ลิงก์เชื่อมต่อ (เฉพาะวง LAN): {self.remote_url}")

	def setup_system_tray(self):
		self.tray_icon = QSystemTrayIcon(self)
		tray_ic = self.app_icon if not self.app_icon.isNull() else QIcon.fromTheme("notifications")
		self.tray_icon.setIcon(tray_ic)
		
		tray_menu = QMenu()
		show_action = QAction("เปิดหน้าต่างหลัก", self)
		show_action.triggered.connect(self.show_window)
		exit_action = QAction("ออกจากโปรแกรมแบบสมบูรณ์", self)
		exit_action.triggered.connect(QGuiApplication.quit)

		tray_menu.addAction(show_action)
		tray_menu.addSeparator()
		tray_menu.addAction(exit_action)

		self.tray_icon.setContextMenu(tray_menu)
		self.tray_icon.show()

	def build_theme_switcher(self):
		"""ปุ่มเลือกธีมสี มุมขวาบน — มาตรฐาน / สว่าง / เข้ม / ขาวดำ"""
		container = QWidget()
		row = QHBoxLayout(container)
		row.setContentsMargins(4, 4, 10, 4)
		row.setSpacing(6)
		self.theme_group = QButtonGroup(self)
		self.theme_group.setExclusive(True)

		for key, name in THEME_ORDER:
			btn = QPushButton(name)
			btn.setProperty("class", "theme-btn")
			btn.setCheckable(True)
			btn.setCursor(Qt.PointingHandCursor)
			btn.setChecked(key == self.current_theme)
			btn.clicked.connect(lambda _, k=key: self.change_theme(k))
			self.theme_group.addButton(btn)
			row.addWidget(btn)

		return container

	def apply_theme(self, theme_key):
		"""ใช้ธีมกับทั้งแอป (รวมกล่องข้อความและหน้าต่างย่อย)"""
		self.current_theme = normalize_theme_key(theme_key)
		app = QApplication.instance()
		if app:
			app.setStyleSheet(get_stylesheet(self.current_theme))

	def change_theme(self, theme_key):
		self.apply_theme(theme_key)
		# บันทึกลง config ให้จำค่าไว้ครั้งถัดไป
		self.config["theme"] = self.current_theme
		save_config(self.config)

	def on_toggle_voice_permission(self, allowed):
		"""เครื่องแม่เปิด/ปิดสิทธิ์การพูดผ่านรีโมท — มีผลกับเซิร์ฟเวอร์ทันที + จำค่าไว้"""
		self.config["allow_remote_voice"] = allowed
		save_config(self.config)
		set_allow_voice(allowed)

	def show_live_popup(self, name):
		"""แสดงสถานะเมื่อมีการพูดประชาสัมพันธ์สดเข้ามาจากรีโมท"""
		self.show_bell_popup({
			"time": datetime.now().strftime("%H:%M:%S"),
			"label": "📢 ประชาสัมพันธ์สด (Live Broadcast)"
		})

	def closeEvent(self, event):
		""" Alert ป้องกันการปิดโปรแกรมโดยไม่ตั้งใจ """
		reply = styled_message(
			self,
			"⚠️ ยืนยันการปิดระบบอ๊อดโรงเรียน",
			"โปรแกรมระบบอ๊อดต้องเปิดรันไว้ตลอดเวลาเพื่อส่งสัญญาณเสียง\nคุณต้องการ 'ย่อลง System Tray' เพื่อรันต่อ หรือ 'ปิดโปรแกรมสมบูรณ์'?",
			QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
		)

		if reply == QMessageBox.Yes:
			event.ignore()
			self.hide()
			self.tray_icon.showMessage(
				"ระบบอ๊อดโรงเรียนยังทำงานอยู่",
				"โปรแกรมย่อมาทำงานเบื้องหลังตรงนี้เพื่อส่งสัญญาณอ๊อดต่อตลอดเวลา",
				QSystemTrayIcon.Information,
				3000
			)
		elif reply == QMessageBox.No:
			event.accept()
			QGuiApplication.quit()
		else:
			event.ignore()

	def show_window(self):
		self.show()
		self.raise_()
		self.activateWindow()

	def show_bell_popup(self, item_data):
		if self.active_alert_dialog:
			self.active_alert_dialog.close()
		self.active_alert_dialog = BellTriggerDialog(item_data, self)
		self.active_alert_dialog.show()

	def close_bell_popup(self):
		if self.active_alert_dialog:
			self.active_alert_dialog.accept()
			self.active_alert_dialog = None

	def init_dashboard_tab(self):
		tab = QWidget()
		layout = QVBoxLayout()
		layout.setContentsMargins(20, 20, 20, 20)

		clock_card = QFrame()
		clock_card.setProperty("class", "glass-card")
		clock_card.setMinimumHeight(200)
		clock_layout = QVBoxLayout()
		clock_layout.setAlignment(Qt.AlignCenter)

		lbl_title_now = QLabel("🕒 เวลาปัจจุบัน")
		lbl_title_now.setAlignment(Qt.AlignCenter)
		lbl_title_now.setProperty("class", "muted-title")

		self.lbl_clock_big = QLabel("00:00:00")
		self.lbl_clock_big.setAlignment(Qt.AlignCenter)
		self.lbl_clock_big.setProperty("class", "clock")

		self.lbl_next_bell = QLabel("🔔 อ๊อดรอบถัดไป: -")
		self.lbl_next_bell.setAlignment(Qt.AlignCenter)
		self.lbl_next_bell.setProperty("class", "accent-amber")

		self.lbl_status = QLabel("🟢 สถานะระบบ: พร้อมทำงานเต็มรูปแบบ 24 ชม.")
		self.lbl_status.setAlignment(Qt.AlignCenter)
		self.lbl_status.setProperty("class", "accent-green")

		clock_layout.addWidget(lbl_title_now)
		clock_layout.addWidget(self.lbl_clock_big)
		clock_layout.addWidget(self.lbl_next_bell)
		clock_layout.addWidget(self.lbl_status)
		clock_card.setLayout(clock_layout)

		remote_card = QFrame()
		remote_card.setProperty("class", "glass-card")
		remote_layout = QVBoxLayout()
		remote_layout.setAlignment(Qt.AlignCenter)
		
		lbl_remote_title = QLabel("🔑 ระบบ Remote Management")
		lbl_remote_title.setAlignment(Qt.AlignCenter)
		lbl_remote_title.setProperty("class", "accent-amber")

		row_pin = QHBoxLayout()
		row_pin.setAlignment(Qt.AlignCenter)
		lbl_pin = QLabel(f"PIN Code: {self.pin_code}")
		lbl_pin.setProperty("class", "clock-sm")
		
		btn_copy_pin = QPushButton("📋 คัดลอก PIN")
		btn_copy_pin.setProperty("class", "secondary-btn")
		btn_copy_pin.clicked.connect(self.copy_pin_code)
		
		row_pin.addWidget(lbl_pin)
		row_pin.addWidget(btn_copy_pin)

		initial_url = self.remote_url
		if self.tunnel:
			initial_url = f"{self.remote_url}  (กำลังสร้างลิงก์สาธารณะ HTTPS อัตโนมัติ...)"
		self.lbl_url = QLabel(f"🌐 ลิงก์เชื่อมต่อ: {initial_url}")
		self.lbl_url.setAlignment(Qt.AlignCenter)
		self.lbl_url.setProperty("class", "muted")
		self.lbl_url.setWordWrap(True)

		btn_row = QHBoxLayout()
		btn_row.setAlignment(Qt.AlignCenter)
		
		btn_copy_link = QPushButton("📋 คัดลอกลิงก์ Remote")
		btn_copy_link.setProperty("class", "secondary-btn")
		btn_copy_link.clicked.connect(self.copy_remote_link)

		btn_open = QPushButton("🌐 เปิดลิงก์ในเบราว์เซอร์")
		btn_open.setProperty("class", "secondary-btn")
		btn_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.remote_url)))

		btn_row.addWidget(btn_copy_link)
		btn_row.addWidget(btn_open)

		voice_perm_row = QHBoxLayout()
		voice_perm_row.setAlignment(Qt.AlignCenter)
		lbl_voice_perm = QLabel("🎙️ อนุญาตให้พูดประชาสัมพันธ์ผ่านรีโมท")
		lbl_voice_perm.setProperty("class", "muted")
		self.toggle_voice_perm = AnimatedToggle(checked=self.config.get("allow_remote_voice", True))
		self.toggle_voice_perm.state_changed.connect(self.on_toggle_voice_permission)
		voice_perm_row.addWidget(lbl_voice_perm)
		voice_perm_row.addWidget(self.toggle_voice_perm)

		remote_layout.addWidget(lbl_remote_title)
		remote_layout.addLayout(row_pin)
		remote_layout.addWidget(self.lbl_url)
		remote_layout.addLayout(btn_row)
		remote_layout.addLayout(voice_perm_row)
		remote_card.setLayout(remote_layout)

		btn_test = QPushButton("🔊 ทดสอบขานอ๊อดตามเวลาปัจจุบันจริงๆ (Live Time Test)")
		btn_test.setProperty("class", "primary-btn")
		btn_test.setStyleSheet("font-size: 16px; padding: 14px;")
		btn_test.clicked.connect(self.test_live_time_bell)

		layout.addWidget(clock_card)
		layout.addWidget(remote_card)
		layout.addWidget(btn_test)
		layout.addStretch()

		tab.setLayout(layout)
		self.tabs.addTab(tab, "🏠 หน้าหลัก (Dashboard)")

	def copy_pin_code(self):
		QGuiApplication.clipboard().setText(self.pin_code)
		self.toast.show_toast()

	def test_live_time_bell(self):
		now = datetime.now()
		self.audio.play_chime_chain(
			hour=now.hour,
			minute=now.minute,
			pre_chime=True,
			voice_announce=True,
			custom_sound="ไม่มี",
			post_chime=True,
			label=f"ทดสอบขานเวลาปัจจุบัน ({now.strftime('%H:%M:%S')} น.)"
		)

	def copy_remote_link(self):
		QGuiApplication.clipboard().setText(self.remote_url)
		self.toast.show_toast()

	def update_dashboard_clock(self):
		try:
			now_str = datetime.now().strftime("%H:%M:%S")
			next_display = self.scheduler.get_next_schedule_display()
			self.lbl_clock_big.setText(now_str)
			self.lbl_next_bell.setText(f"🔔 อ๊อดรอบถัดไป: {next_display}")
		except Exception as e:
			print(f"[MainWindow] Clock update error: {e}")

	def init_schedule_tab(self):
		tab = QWidget()
		layout = QVBoxLayout()
		layout.setContentsMargins(20, 20, 20, 20)

		toolbar = QHBoxLayout()
		btn_add = QPushButton("➕ เพิ่มตารางเวลาใหม่")
		btn_add.setProperty("class", "primary-btn")
		btn_add.clicked.connect(self.add_schedule_dialog)

		btn_sort = QPushButton("↕️ เรียงตามเวลาอัตโนมัติ")
		btn_sort.setProperty("class", "secondary-btn")
		btn_sort.clicked.connect(self.sort_schedules_auto)

		btn_template = QPushButton("🏫 ใช้ตารางมาตรฐานโรงเรียน")
		btn_template.setProperty("class", "secondary-btn")
		btn_template.clicked.connect(self.load_school_template)

		toolbar.addWidget(btn_add)
		toolbar.addWidget(btn_sort)
		toolbar.addWidget(btn_template)
		toolbar.addStretch()
		layout.addLayout(toolbar)

		self.table = QTableWidget()
		self.table.setColumnCount(8)
		self.table.setHorizontalHeaderLabels(["เวลา (HH:mm:ss)", "รายละเอียด", "ติ่งต่องหน้า", "ขานเวลา", "เสียงต่อท้าย", "ติ่งต่องท้าย", "เปิด/ปิด", "จัดการ"])
		
		self.table.verticalHeader().setDefaultSectionSize(42)
		self.table.verticalHeader().setStyleSheet("QHeaderView::section { background: #064E3B; color: #6EE7B7; font-weight: bold; font-size: 12px; border: none; padding: 4px; }")

		header = self.table.horizontalHeader()
		header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
		header.setSectionResizeMode(1, QHeaderView.Stretch)
		for col in range(2, 8):
			header.setSectionResizeMode(col, QHeaderView.ResizeToContents)

		# อ่านค่าจริงที่ผู้ใช้พิมพ์ในช่องเวลา/รายละเอียด แล้วมีผลทันที
		self._is_refreshing = False
		self.table.itemChanged.connect(self.on_schedule_item_changed)

		layout.addWidget(self.table)

		self.refresh_schedule_table()
		tab.setLayout(layout)
		self.tabs.addTab(tab, "📅 จัดการตารางเวลา")

	def sort_schedules_auto(self):
		self.scheduler.save_schedules()
		self.refresh_schedule_table()

	def load_school_template(self):
		confirm = styled_message(self, "ยืนยันการโหลดแม่แบบ", "ต้องการโหลดตารางเวลามาตรฐานโรงเรียนใช่หรือไม่?", QMessageBox.Yes | QMessageBox.No)
		if confirm == QMessageBox.Yes:
			self.scheduler.load_default_school_template()
			self.refresh_schedule_table()

	def refresh_schedule_table(self):
		self._is_refreshing = True
		self.table.setRowCount(0)
		for row, item in enumerate(self.scheduler.schedules):
			self.table.insertRow(row)
			self.table.setItem(row, 0, QTableWidgetItem(item.get("time", "")))
			self.table.setItem(row, 1, QTableWidgetItem(item.get("label", "")))

			toggle_pre = AnimatedToggle(checked=item.get("pre_chime", True))
			toggle_pre.state_changed.connect(lambda checked, idx=row: self.toggle_pre_chime_realtime(idx, checked))
			self.table.setCellWidget(row, 2, self._wrap_toggle(toggle_pre))

			toggle_voice = AnimatedToggle(checked=item.get("voice_announce", True))
			toggle_voice.state_changed.connect(lambda checked, idx=row: self.toggle_voice_realtime(idx, checked))
			self.table.setCellWidget(row, 3, self._wrap_toggle(toggle_voice))

			clean_sound_name = os.path.basename(item.get("custom_sound", "ไม่มี"))
			sound_item = QTableWidgetItem(clean_sound_name)
			# แก้ชื่อไฟล์เสียงต่อท้ายผ่านหน้าต่างแก้ไข (ปุ่ม ✏️) เท่านั้น กันพิมพ์ชื่อไฟล์มั่ว
			sound_item.setFlags(sound_item.flags() & ~Qt.ItemIsEditable)
			self.table.setItem(row, 4, sound_item)

			toggle_post = AnimatedToggle(checked=item.get("post_chime", True))
			toggle_post.state_changed.connect(lambda checked, idx=row: self.toggle_post_chime_realtime(idx, checked))
			self.table.setCellWidget(row, 5, self._wrap_toggle(toggle_post))

			toggle_enabled = AnimatedToggle(checked=item.get("enabled", True))
			toggle_enabled.state_changed.connect(lambda checked, idx=row: self.toggle_enabled_realtime(idx, checked))
			self.table.setCellWidget(row, 6, self._wrap_toggle(toggle_enabled))

			btn_box = QHBoxLayout()
			
			btn_play = QPushButton("▶️ ลองฟัง")
			btn_play.setProperty("class", "secondary-btn")
			btn_play.clicked.connect(lambda _, idx=row: self.preview_schedule_sound(idx))

			btn_up = QPushButton("⬆️")
			btn_up.setFixedWidth(28)
			btn_up.clicked.connect(lambda _, idx=row: self.move_schedule(idx, -1))

			btn_down = QPushButton("⬇️")
			btn_down.setFixedWidth(28)
			btn_down.clicked.connect(lambda _, idx=row: self.move_schedule(idx, 1))

			btn_edit = QPushButton("✏️")
			btn_edit.setFixedWidth(32)
			btn_edit.clicked.connect(lambda _, idx=row: self.edit_schedule_dialog(idx))

			btn_delete = QPushButton("🗑️")
			btn_delete.setFixedWidth(32)
			btn_delete.setProperty("class", "danger-btn")
			btn_delete.clicked.connect(lambda _, idx=row: self.delete_schedule(idx))

			btn_box.addWidget(btn_play)
			btn_box.addWidget(btn_up)
			btn_box.addWidget(btn_down)
			btn_box.addWidget(btn_edit)
			btn_box.addWidget(btn_delete)
			btn_box.setContentsMargins(0, 0, 0, 0)

			btn_container = QWidget()
			btn_container.setLayout(btn_box)
			self.table.setCellWidget(row, 7, btn_container)

		self._is_refreshing = False

	def on_schedule_item_changed(self, item):
		"""ผู้ใช้แก้ค่าในเซลล์ (เวลา/รายละเอียด) → อ่านค่าจริงที่พิมพ์ แล้วบันทึกมีผลทันที"""
		if getattr(self, "_is_refreshing", False):
			return
		row = item.row()
		col = item.column()
		if not (0 <= row < len(self.scheduler.schedules)):
			return

		if col == 0:  # เวลา — ใช้ค่าจริงที่พิมพ์ จัดรูปแบบเป็น HH:mm:ss แล้วเรียงใหม่ตามเวลา
			new_time = self.scheduler.normalize_time_str(item.text())
			self.scheduler.schedules[row]["time"] = new_time
			self.scheduler.save_schedules()
			self.refresh_schedule_table()
		elif col == 1:  # รายละเอียด
			self.scheduler.schedules[row]["label"] = item.text().strip() or "อ๊อดแจ้งเวลา"
			self.scheduler.save_schedules()

	def preview_schedule_sound(self, index):
		if 0 <= index < len(self.scheduler.schedules):
			item = self.scheduler.schedules[index]
			h, m, _ = parse_hms(item.get("time", "08:00:00"))
			self.audio.play_chime_chain(
				hour=h,
				minute=m,
				pre_chime=item.get("pre_chime", True),
				voice_announce=item.get("voice_announce", True),
				custom_sound=item.get("custom_sound", "ไม่มี"),
				post_chime=item.get("post_chime", True),
				label=f"ทดลองฟัง ({item.get('label')})",
				announce_label=item.get("label", "")
			)

	def _wrap_toggle(self, toggle_widget):
		container = QWidget()
		layout = QHBoxLayout(container)
		layout.addWidget(toggle_widget)
		layout.setAlignment(Qt.AlignCenter)
		layout.setContentsMargins(0, 0, 0, 0)
		return container

	def toggle_pre_chime_realtime(self, index, checked):
		if 0 <= index < len(self.scheduler.schedules):
			self.scheduler.schedules[index]["pre_chime"] = checked
			self.scheduler.save_schedules()

	def toggle_voice_realtime(self, index, checked):
		if 0 <= index < len(self.scheduler.schedules):
			self.scheduler.schedules[index]["voice_announce"] = checked
			self.scheduler.save_schedules()

	def toggle_post_chime_realtime(self, index, checked):
		if 0 <= index < len(self.scheduler.schedules):
			self.scheduler.schedules[index]["post_chime"] = checked
			self.scheduler.save_schedules()

	def toggle_enabled_realtime(self, index, checked):
		if 0 <= index < len(self.scheduler.schedules):
			self.scheduler.schedules[index]["enabled"] = checked
			self.scheduler.save_schedules()

	def move_schedule(self, index, direction):
		new_index = index + direction
		if 0 <= new_index < len(self.scheduler.schedules):
			self.scheduler.schedules[index], self.scheduler.schedules[new_index] = self.scheduler.schedules[new_index], self.scheduler.schedules[index]
			self.scheduler.save_schedules()
			self.refresh_schedule_table()

	def delete_schedule(self, index):
		if 0 <= index < len(self.scheduler.schedules):
			confirm = styled_message(self, "ยืนยันการลบ", "คุณต้องการลบตารางเวลานี้ใช่หรือไม่?", QMessageBox.Yes | QMessageBox.No)
			if confirm == QMessageBox.Yes:
				self.scheduler.schedules.pop(index)
				self.scheduler.save_schedules()
				self.refresh_schedule_table()

	def add_schedule_dialog(self):
		try:
			dialog = ScheduleFormDialog(self.audio.sounds_dir, parent=self)
			if dialog.exec() == QDialog.Accepted:
				new_data = dialog.get_data()
				new_data["id"] = str(len(self.scheduler.schedules) + 1)
				self.scheduler.schedules.append(new_data)
				self.scheduler.save_schedules()
				self.refresh_schedule_table()
		except Exception as e:
			print(f"[MainWindow] add_schedule_dialog error: {e}")

	def edit_schedule_dialog(self, index):
		try:
			if 0 <= index < len(self.scheduler.schedules):
				current_data = self.scheduler.schedules[index]
				dialog = ScheduleFormDialog(self.audio.sounds_dir, item_data=current_data, parent=self)
				if dialog.exec() == QDialog.Accepted:
					updated_data = dialog.get_data()
					updated_data["id"] = current_data.get("id", str(index + 1))
					self.scheduler.schedules[index] = updated_data
					self.scheduler.save_schedules()
					self.refresh_schedule_table()
		except Exception as e:
			print(f"[MainWindow] edit_schedule_dialog error: {e}")

	def init_audio_tab(self):
		tab = QWidget()
		layout = QVBoxLayout()
		layout.setContentsMargins(20, 20, 20, 20)

		top_upload_row = QHBoxLayout()
		btn_upload = QPushButton("📤 เลือกอัปโหลดไฟล์เสียงจากเครื่อง (Browse Files)")
		btn_upload.setProperty("class", "primary-btn")
		btn_upload.clicked.connect(self.browse_and_upload_sound)
		top_upload_row.addWidget(btn_upload)
		top_upload_row.addStretch()
		layout.addLayout(top_upload_row)

		drag_area = DragDropArea(self.audio.sounds_dir, self.refresh_audio_list)
		layout.addWidget(drag_area)

		layout.addWidget(QLabel("📁 ไฟล์เสียงในระบบ (บันทึกใน Local Database):"))

		self.audio_table = QTableWidget()
		self.audio_table.setColumnCount(4)
		self.audio_table.setHorizontalHeaderLabels(["ชื่อที่แสดง", "ชื่อไฟล์จริง", "เพิ่มเมื่อ", "จัดการ"])
		self.audio_table.verticalHeader().setDefaultSectionSize(44)
		ah = self.audio_table.horizontalHeader()
		ah.setSectionResizeMode(0, QHeaderView.Stretch)
		ah.setSectionResizeMode(1, QHeaderView.ResizeToContents)
		ah.setSectionResizeMode(2, QHeaderView.ResizeToContents)
		ah.setSectionResizeMode(3, QHeaderView.ResizeToContents)
		self.audio_table.setEditTriggers(QTableWidget.NoEditTriggers)
		layout.addWidget(self.audio_table)

		self.refresh_audio_list()
		tab.setLayout(layout)
		self.tabs.addTab(tab, "🎵 จัดการไฟล์เสียง")

	def browse_and_upload_sound(self):
		files, _ = QFileDialog.getOpenFileNames(self, "เลือกไฟล์เสียง (MP3 หรือ WAV)", "", "Audio Files (*.mp3 *.wav)")
		if files:
			for f in files:
				self.sound_db.add_sound(f)
			self.refresh_audio_list()

	def refresh_audio_list(self):
		if not hasattr(self, "audio_table"):
			return
		sounds = self.sound_db.list_sounds()
		self.audio_table.setRowCount(0)
		for row, snd in enumerate(sounds):
			self.audio_table.insertRow(row)
			self.audio_table.setItem(row, 0, QTableWidgetItem(snd["display_name"]))
			self.audio_table.setItem(row, 1, QTableWidgetItem(snd["filename"]))
			self.audio_table.setItem(row, 2, QTableWidgetItem(snd.get("created_at", "")))

			box = QHBoxLayout()
			btn_play = QPushButton("▶️ ฟัง")
			btn_play.setProperty("class", "secondary-btn")
			btn_play.clicked.connect(lambda _, fn=snd["filename"]: self.play_sound_file(fn))

			btn_rename = QPushButton("✏️ เปลี่ยนชื่อ")
			btn_rename.setProperty("class", "secondary-btn")
			btn_rename.clicked.connect(lambda _, sid=snd["id"], cur=snd["display_name"]: self.rename_sound(sid, cur))

			btn_del = QPushButton("🗑️ ลบ")
			btn_del.setProperty("class", "danger-btn")
			btn_del.clicked.connect(lambda _, sid=snd["id"], fn=snd["filename"]: self.delete_sound(sid, fn))

			box.addWidget(btn_play)
			box.addWidget(btn_rename)
			box.addWidget(btn_del)
			box.setContentsMargins(0, 0, 0, 0)
			container = QWidget()
			container.setLayout(box)
			self.audio_table.setCellWidget(row, 3, container)

	def play_sound_file(self, filename):
		self.audio.play_sequence([filename], label=f"ลองฟัง ({filename})")

	def rename_sound(self, sound_id, current_name):
		new_name, ok = QInputDialog.getText(self, "เปลี่ยนชื่อที่แสดง", "ชื่อใหม่:", text=current_name)
		if ok and new_name.strip():
			self.sound_db.rename_display(sound_id, new_name.strip())
			self.refresh_audio_list()

	def delete_sound(self, sound_id, filename):
		confirm = styled_message(self, "ยืนยันการลบไฟล์เสียง", f"ต้องการลบไฟล์เสียงนี้ออกจากระบบถาวรใช่หรือไม่?\n\n{filename}", QMessageBox.Yes | QMessageBox.No)
		if confirm == QMessageBox.Yes:
			result = self.sound_db.delete_sound(sound_id)
			if result is None:
				styled_message(self, "ลบไม่ได้", "ไฟล์นี้เป็นไฟล์ระบบ ไม่สามารถลบได้", QMessageBox.Ok, icon=QMessageBox.Warning)
			self.refresh_audio_list()
