import os
import shutil
from datetime import datetime
import threading
from PySide6.QtWidgets import (
	QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
	QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
	QFrame, QMessageBox, QGraphicsOpacityEffect, QDialog, QSystemTrayIcon, QMenu,
	QInputDialog, QButtonGroup, QApplication, QComboBox, QCheckBox, QGroupBox,
	QProgressBar, QProgressDialog, QTextBrowser, QScrollArea, QGridLayout
)
from PySide6.QtCore import Qt, QTimer, QUrl, QPropertyAnimation, QEasingCurve, QObject, Signal
from PySide6.QtGui import QGuiApplication, QDesktopServices, QIcon, QAction
from ui.themes import get_stylesheet, normalize_theme_key, THEME_ORDER, BUTTON_COLORS
from ui.components import AnimatedToggle, ToastNotification
from ui.schedule_dialog import ScheduleFormDialog, LanguageEditDialog, build_chime_picker
from ui.language_widget import LanguageSequenceWidget
from sound_db import SoundDatabase
from config_manager import load_config, save_config
from remote_server import set_allow_voice
from win_system import prevent_sleep
from paths import resource_path
from tts_engine import VOICE_STYLES, LANGUAGES, SPEEDS, langs_summary, default_langs
from updater import UpdateManager, can_self_update
from version import APP_VERSION

# ข้อความสำเร็จรูปสำหรับประกาศเสียงตามสาย (ผู้ใช้บันทึกเพิ่มเองได้)
BUILTIN_TEMPLATES = [
	("เชิญประชุมคณะครู", "ขอเชิญคณะครูทุกท่าน เข้าร่วมประชุมที่ห้องประชุมโรงเรียน ในอีกสิบนาที"),
	("เรียกผู้ปกครอง", "ขอเชิญผู้ปกครองที่มารับนักเรียน ติดต่อที่ห้องธุรการของโรงเรียน"),
	("ฝนตก เข้าแถวในอาคาร", "เนื่องจากมีฝนตก ขอให้นักเรียนทุกคนเข้าแถวภายในอาคารเรียน"),
	("ซ้อมหนีไฟ", "ขณะนี้เป็นการซ้อมอพยพหนีไฟ ขอให้นักเรียนและบุคลากรทุกคนเดินออกจากอาคารอย่างเป็นระเบียบ"),
]

VOICE_SAMPLES = {
	"th": "สวัสดี นี่คือเสียงทดสอบจากระบบประกาศเสียงตามสายของโรงเรียน",
	"en": "Hello, this is a test of the school public announcement system.",
	"zh": "大家好，这是学校广播系统的测试。",
}


class _MainThreadInvoker(QObject):
	"""ให้เธรดเบื้องหลังสั่งอัปเดตหน้าจอได้อย่างปลอดภัย (ฟังก์ชันจะไปรันบน main thread)"""
	invoke = Signal(object)

	def __init__(self):
		super().__init__()
		self.invoke.connect(lambda fn: fn())


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


class UpdateDialog(QDialog):
	"""แจ้งเวอร์ชันใหม่ + รายละเอียดการเปลี่ยนแปลง ให้ผู้ใช้เลือก อัปเดตเลย / อัปเดตทีหลัง"""

	def __init__(self, info, self_update, parent=None):
		super().__init__(parent)
		self.choice = "later"
		self.setWindowTitle("🆕 มีเวอร์ชันใหม่ของ School AOD")
		self.resize(620, 520)

		layout = QVBoxLayout(self)
		title = QLabel(f"🎉 มีเวอร์ชันใหม่พร้อมให้อัปเดต: v{info['version']}")
		title.setProperty("class", "accent-amber")
		layout.addWidget(title)

		meta = QLabel(f"เวอร์ชันที่ใช้อยู่: v{APP_VERSION}   →   เวอร์ชันใหม่: v{info['version']}"
					  + (f"   (เผยแพร่ {info['published_at']})" if info.get("published_at") else ""))
		meta.setProperty("class", "muted")
		layout.addWidget(meta)

		notes = QTextBrowser()
		notes.setOpenExternalLinks(True)
		notes.setMarkdown(info.get("notes") or "_ไม่มีรายละเอียดการเปลี่ยนแปลง_")
		layout.addWidget(notes, 1)

		hint_text = ("ระบบจะดาวน์โหลดและติดตั้งให้อัตโนมัติ แล้วเปิดโปรแกรมใหม่เอง\n"
					 "ตารางเวลา ไฟล์เสียง และการตั้งค่าเดิมจะอยู่ครบทุกอย่าง")
		if not self_update:
			hint_text = "จะเปิดหน้าดาวน์โหลดเวอร์ชันใหม่ในเบราว์เซอร์ (การติดตั้งอัตโนมัติรองรับเฉพาะโปรแกรม .exe บน Windows)"
		hint = QLabel(hint_text)
		hint.setWordWrap(True)
		hint.setProperty("class", "muted")
		layout.addWidget(hint)

		row = QHBoxLayout()
		for text, choice, color in (
			("⏰ อัปเดตทีหลัง", "later", BUTTON_COLORS["cancel"]),
			("⬇️ อัปเดตเลย", "update", BUTTON_COLORS["yes"]),
		):
			btn = QPushButton(text)
			btn.setCursor(Qt.PointingHandCursor)
			btn.setStyleSheet(f"background:{color}; color:#FFFFFF; font-weight:bold; border-radius:8px; padding:10px 22px;")
			btn.clicked.connect(lambda _, c=choice: self._choose(c))
			row.addWidget(btn)
		layout.addLayout(row)

	def _choose(self, choice):
		self.choice = choice
		self.accept()


class MainWindow(QMainWindow):
	def __init__(self, audio_engine, scheduler_engine, pin_code, lan_url, public_url="", tunnel=None):
		super().__init__()
		self.audio = audio_engine
		self.scheduler = scheduler_engine
		self.pin_code = pin_code
		self.lan_url = lan_url
		self.public_url = public_url          # โดเมนสาธารณะ (ว่าง = ยังไม่มี/รอ tunnel)
		self.remote_url = public_url or lan_url
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

		# เตรียมเสียง AI ของตารางไว้ล่วงหน้า (ใช้งานออฟไลน์ได้) — รอ 3 วิหลังแก้ตารางแล้วค่อยทำ
		self._ui = _MainThreadInvoker()
		self._precache_timer = QTimer(self)
		self._precache_timer.setSingleShot(True)
		self._precache_timer.setInterval(3000)
		self._precache_timer.timeout.connect(self.start_precache)
		self.scheduler.schedules_changed.connect(self._precache_timer.start)
		self.audio.cache_progress.connect(self.on_cache_progress)
		self.audio.cache_finished.connect(self.on_cache_finished)

		# ระบบอัปเดต
		self.updater = UpdateManager(self)
		self.updater.check_finished.connect(self.on_update_checked)
		self.updater.download_progress.connect(self.on_update_download_progress)
		self.updater.install_ready.connect(self.on_update_install_ready)
		self._latest_release = None
		self._update_manual = False
		self._update_progress = None

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
		self.init_announce_tab()
		self.init_schedule_tab()
		self.init_audio_tab()
		self.init_settings_tab()

		footer_frame = QFrame()
		footer_layout = QVBoxLayout(footer_frame)
		footer_layout.setContentsMargins(0, 8, 0, 4)

		lbl_credits = QLabel('<a href="https://www.facebook.com/suebsing" style="color: #34D399; text-decoration: none; font-weight: bold; font-size: 13px;">Develop by hAcKEdpRO | Pongwattana Suebsing</a>')
		lbl_credits.setOpenExternalLinks(True)
		lbl_credits.setAlignment(Qt.AlignCenter)

		version_row = QHBoxLayout()
		version_row.setAlignment(Qt.AlignCenter)
		lbl_version = QLabel(f"Version {APP_VERSION} © 2026-2027 All Rights Reserved")
		lbl_version.setProperty("class", "muted")
		lbl_version.setStyleSheet("font-size: 11px;")
		self.btn_update = QPushButton("🔄 ตรวจสอบอัปเดต")
		self.btn_update.setProperty("class", "theme-btn")
		self.btn_update.setCursor(Qt.PointingHandCursor)
		self.btn_update.clicked.connect(self.on_update_button)
		version_row.addWidget(lbl_version)
		version_row.addSpacing(10)
		version_row.addWidget(self.btn_update)

		footer_layout.addWidget(lbl_credits)
		footer_layout.addLayout(version_row)
		main_layout.addWidget(footer_frame)

		self.setCentralWidget(central_widget)

		self.update_dashboard_clock()

		self.timer = QTimer(self)
		self.timer.timeout.connect(self.update_dashboard_clock)
		self.timer.start(1000)

		# ย้ำคำสั่งกันเครื่องหลับเป็นระยะ (เผื่อ Windows รีเซ็ตสถานะพลังงาน)
		self.keepawake_timer = QTimer(self)
		self.keepawake_timer.timeout.connect(prevent_sleep)
		self.keepawake_timer.start(240000)  # ทุก 4 นาที

		# เมื่อ Cloudflare Tunnel สร้างลิงก์สาธารณะเสร็จ ให้อัปเดตลิงก์ในหน้าจอทันที
		if self.tunnel:
			self.tunnel.url_ready.connect(self.on_public_url_ready)
			self.tunnel.status_changed.connect(self.on_tunnel_status)

		# เริ่มเตรียมเสียง AI หลังเปิดโปรแกรม และลองใหม่ทุก 15 นาทีถ้ายังไม่ครบ (เผื่อตอนนั้นเน็ตหลุด)
		self.refresh_voice_status()
		QTimer.singleShot(3000, self.start_precache)
		self._cache_retry_timer = QTimer(self)
		self._cache_retry_timer.timeout.connect(self._retry_precache_if_incomplete)
		self._cache_retry_timer.start(15 * 60 * 1000)

		# ตรวจสอบเวอร์ชันใหม่อัตโนมัติหลังเปิดโปรแกรม และทุก 6 ชม. (โปรแกรมเปิดค้างทั้งวัน)
		self._prompted_versions = set()
		self._update_check_timer = QTimer(self)
		self._update_check_timer.timeout.connect(self._auto_check_updates)
		self._update_check_timer.start(6 * 60 * 60 * 1000)
		QTimer.singleShot(8000, self._auto_check_updates)

	def on_public_url_ready(self, public_url):
		self.public_url = public_url
		self.remote_url = public_url
		self.lbl_public_url.setText(public_url)
		self.btn_copy_public.setEnabled(True)
		self.tray_icon.showMessage(
			"ลิงก์รีโมทพร้อมใช้งาน",
			f"สร้างโดเมนสาธารณะสำเร็จ:\n{public_url}",
			QSystemTrayIcon.Information,
			5000
		)

	def on_tunnel_status(self, status):
		if status in ("no-tool", "error"):
			# สร้างลิงก์สาธารณะไม่ได้ → แจ้งให้ใช้ไอพีวง LAN แทน
			self.lbl_public_url.setText("— (สร้างลิงก์สาธารณะไม่สำเร็จ ใช้ไอพีวง LAN แทน)")

	def copy_text(self, text):
		if text:
			QGuiApplication.clipboard().setText(text)
			self.toast.show_toast()

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

		# กระดิ่งแจ้งเตือนเวอร์ชันใหม่ — แสดงเฉพาะตอนมีอัปเดตที่ยังไม่ได้ติดตั้ง
		self.btn_update_badge = QPushButton("🔔 มีอัปเดตใหม่")
		self.btn_update_badge.setCursor(Qt.PointingHandCursor)
		self.btn_update_badge.setToolTip("มีเวอร์ชันใหม่ กดเพื่อดูรายละเอียดและอัปเดต")
		self.btn_update_badge.setStyleSheet(
			"QPushButton { background: #F59E0B; color: #1F2937; font-weight: bold; font-size: 13px;"
			" border-radius: 8px; padding: 6px 14px; border: 1px solid #FBBF24; }"
			"QPushButton:hover { background: #FBBF24; }")
		self.btn_update_badge.clicked.connect(self.on_update_button)
		self.btn_update_badge.hide()
		row.addWidget(self.btn_update_badge)
		row.addSpacing(8)

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

		self.lbl_status = QLabel("🟢 สถานะระบบ: พร้อมทำงาน 24 ชม. (กันเครื่องหลับอัตโนมัติ)")
		self.lbl_status.setAlignment(Qt.AlignCenter)
		self.lbl_status.setProperty("class", "accent-green")

		self.lbl_voice_status = QLabel("🎙️ เสียง AI: กำลังตรวจสอบ...")
		self.lbl_voice_status.setAlignment(Qt.AlignCenter)
		self.lbl_voice_status.setProperty("class", "muted")
		self.lbl_voice_status.setStyleSheet("font-size: 13px;")

		clock_layout.addWidget(lbl_title_now)
		clock_layout.addWidget(self.lbl_clock_big)
		clock_layout.addWidget(self.lbl_next_bell)
		clock_layout.addWidget(self.lbl_status)
		clock_layout.addWidget(self.lbl_voice_status)
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

		# ---- ลิงก์เชื่อมต่อ 2 แบบ: ไอพีในวง LAN และ โดเมนสาธารณะ (จัดกึ่งกลาง + ปุ่มคัดลอกแยกกัน) ----
		def make_link_row(desc, url_text, url_class="accent-green"):
			row = QHBoxLayout()
			row.setContentsMargins(0, 4, 0, 4)
			lbl_desc = QLabel(desc)
			lbl_desc.setProperty("class", "muted")
			lbl_val = QLabel(url_text)
			lbl_val.setProperty("class", url_class)
			lbl_val.setTextInteractionFlags(Qt.TextSelectableByMouse)
			btn = QPushButton("📋 คัดลอก")
			btn.setProperty("class", "secondary-btn")
			btn.setFixedWidth(120)
			btn.setCursor(Qt.PointingHandCursor)
			# จัดกลุ่มคำอธิบาย+ลิงก์+ปุ่ม ให้อยู่กึ่งกลางแนวนอน
			row.addStretch()
			row.addWidget(lbl_desc)
			row.addSpacing(6)
			row.addWidget(lbl_val)
			row.addSpacing(14)
			row.addWidget(btn)
			row.addStretch()
			return row, lbl_val, btn

		# แถวที่ 1: ไอพีในวง LAN (สำหรับเข้าจากเครื่องในวงเดียวกัน)
		lan_row, self.lbl_lan_url, btn_copy_lan = make_link_row("🌐 ไอพีในวง LAN:", self.lan_url, "accent-green")
		btn_copy_lan.clicked.connect(lambda: self.copy_text(self.lan_url))

		# แถวที่ 2: โดเมนสาธารณะ (สำหรับเข้าจากที่ไหนก็ได้)
		if self.public_url:
			pub_text = self.public_url
		elif self.tunnel:
			pub_text = "⏳ กำลังสร้างลิงก์สาธารณะ HTTPS..."
		else:
			pub_text = "— (ไม่ได้เปิดใช้ลิงก์สาธารณะ)"
		pub_row, self.lbl_public_url, self.btn_copy_public = make_link_row("🌍 โดเมนสาธารณะ:", pub_text, "accent-amber")
		self.btn_copy_public.clicked.connect(lambda: self.copy_text(self.public_url))
		self.btn_copy_public.setEnabled(bool(self.public_url))

		# ปุ่มเปิดลิงก์ทดสอบ: มีทั้งภายใน (LAN) และภายนอก (โดเมน)
		open_row = QHBoxLayout()
		open_row.setAlignment(Qt.AlignCenter)
		btn_open_lan = QPushButton("🌐 เปิดลิงก์ภายใน (LAN)")
		btn_open_lan.setProperty("class", "secondary-btn")
		btn_open_lan.setCursor(Qt.PointingHandCursor)
		btn_open_lan.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.lan_url)))
		btn_open_pub = QPushButton("🌍 เปิดลิงก์ภายนอก (โดเมน)")
		btn_open_pub.setProperty("class", "secondary-btn")
		btn_open_pub.setCursor(Qt.PointingHandCursor)
		btn_open_pub.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.public_url or self.lan_url)))
		open_row.addWidget(btn_open_lan)
		open_row.addSpacing(10)
		open_row.addWidget(btn_open_pub)

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
		remote_layout.addLayout(lan_row)
		remote_layout.addLayout(pub_row)
		remote_layout.addLayout(open_row)
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
		self.audio.play_announcement({
			"hour": now.hour,
			"minute": now.minute,
			"pre_chime": True,
			"voice_announce": True,
			"speak_text": False,
			"post_chime": True,
			"label": f"ทดสอบขานเวลาปัจจุบัน ({now.strftime('%H:%M:%S')} น.)",
			"langs": default_langs(),
		})

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
		self.table.setColumnCount(9)
		self.table.setHorizontalHeaderLabels(["เวลา (HH:mm:ss)", "รายละเอียด", "ติ่งต่องหน้า", "ขานเวลา", "เสียงต่อท้าย", "ติ่งต่องท้าย", "เปิด/ปิด", "ภาษา (ลำดับอ่าน)", "จัดการ"])
		
		self.table.verticalHeader().setDefaultSectionSize(42)
		self.table.verticalHeader().setStyleSheet("QHeaderView::section { background: #064E3B; color: #6EE7B7; font-weight: bold; font-size: 12px; border: none; padding: 4px; }")

		header = self.table.horizontalHeader()
		header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
		header.setSectionResizeMode(1, QHeaderView.Stretch)
		for col in range(2, 9):
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

			# คอลัมน์ภาษา: กดเพื่อเลือกภาษา / สลับลำดับ / จำนวนรอบ ของรายการนี้ได้ทันที
			btn_lang = QPushButton(f"🌐 {langs_summary(item.get('langs'))}")
			btn_lang.setProperty("class", "secondary-btn")
			btn_lang.setCursor(Qt.PointingHandCursor)
			btn_lang.setToolTip("กดเพื่อเลือกภาษาที่จะพูด สลับลำดับ และจำนวนรอบที่อ่าน")
			btn_lang.setStyleSheet("padding: 6px 12px; font-size: 13px;")
			btn_lang.clicked.connect(lambda _, idx=row: self.edit_schedule_languages(idx))
			self.table.setCellWidget(row, 7, btn_lang)

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
			self.table.setCellWidget(row, 8, btn_container)

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
			self.audio.play_schedule_item(item, label=f"ทดลองฟัง ({item.get('label')})")

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

	def _preview_dialog_item(self, data):
		self.audio.play_schedule_item(data, label=f"ทดลองฟัง ({data.get('label')})")

	def edit_schedule_languages(self, index):
		if not (0 <= index < len(self.scheduler.schedules)):
			return
		item = self.scheduler.schedules[index]
		dialog = LanguageEditDialog(item, parent=self, preview_callback=self._preview_dialog_item)
		if dialog.exec() == QDialog.Accepted:
			updated = dialog.get_item()
			item["langs"] = updated["langs"]
			item["voice_style"] = updated["voice_style"]
			self.scheduler.save_schedules()
			self.refresh_schedule_table()

	def add_schedule_dialog(self):
		try:
			dialog = ScheduleFormDialog(self.audio.sounds_dir, parent=self, preview_callback=self._preview_dialog_item,
										chime_preview=self.audio.play_chime_preview)
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
				dialog = ScheduleFormDialog(self.audio.sounds_dir, item_data=current_data, parent=self,
											preview_callback=self._preview_dialog_item,
											chime_preview=self.audio.play_chime_preview)
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

	# ================================================================ แท็บประกาศเสียงตามสาย
	def init_announce_tab(self):
		tab = QWidget()
		layout = QVBoxLayout(tab)
		layout.setContentsMargins(20, 16, 20, 16)

		title = QLabel("📢 ศูนย์ประกาศเสียงตามสาย — พิมพ์ข้อความ แล้วให้เสียง AI ประกาศหลายภาษา")
		title.setProperty("class", "title")
		layout.addWidget(title)

		tpl_row = QHBoxLayout()
		tpl_row.addWidget(QLabel("📋 ข้อความสำเร็จรูป:"))
		self.combo_templates = QComboBox()
		self.combo_templates.setMinimumWidth(280)
		self.combo_templates.activated.connect(self.load_announce_template)
		btn_save_tpl = QPushButton("💾 บันทึกเป็นข้อความสำเร็จรูป")
		btn_save_tpl.setProperty("class", "secondary-btn")
		btn_save_tpl.clicked.connect(self.save_announce_template)
		btn_del_tpl = QPushButton("🗑️ ลบ")
		btn_del_tpl.setProperty("class", "secondary-btn")
		btn_del_tpl.clicked.connect(self.delete_announce_template)
		tpl_row.addWidget(self.combo_templates, 1)
		tpl_row.addWidget(btn_save_tpl)
		tpl_row.addWidget(btn_del_tpl)
		layout.addLayout(tpl_row)
		self.refresh_announce_templates()

		box = QGroupBox("🌐 ข้อความประกาศ & ลำดับภาษา")
		box_layout = QVBoxLayout(box)
		self.announce_langs = LanguageSequenceWidget(default_langs(), multiline=True, reorderable=False)
		box_layout.addWidget(self.announce_langs)
		layout.addWidget(box, 1)

		opt = QHBoxLayout()
		self.chk_ann_pre = QCheckBox("🔔 ติ่งต่องนำหน้า")
		self.chk_ann_pre.setChecked(True)
		self.chk_ann_post = QCheckBox("🔔 ติ่งต่องปิดท้าย")
		self.chk_ann_post.setChecked(True)
		self.chk_ann_time = QCheckBox("🕒 ขานเวลาปัจจุบันด้วย")
		self.combo_ann_style = QComboBox()
		self.combo_ann_style.addItem("⚙️ สไตล์เสียงตามค่าเริ่มต้น", "")
		for key, name in VOICE_STYLES:
			self.combo_ann_style.addItem(name, key)
		for w in (self.chk_ann_pre, self.chk_ann_post, self.chk_ann_time):
			opt.addWidget(w)
		opt.addStretch()
		opt.addWidget(QLabel("🎙️ เสียง:"))
		opt.addWidget(self.combo_ann_style)
		layout.addLayout(opt)

		chime_row, self.combo_ann_chime, self.combo_ann_chime_len = build_chime_picker(
			preview=self.audio.play_chime_preview)
		chime_row.insertWidget(0, QLabel("🎵 เสียงติ่งต่อง:"))
		layout.addLayout(chime_row)

		act = QHBoxLayout()
		btn_announce = QPushButton("📢 ประกาศทันที")
		btn_announce.setProperty("class", "primary-btn")
		btn_announce.setStyleSheet("font-size: 17px; padding: 14px;")
		btn_announce.setCursor(Qt.PointingHandCursor)
		btn_announce.clicked.connect(self.announce_now)
		btn_stop = QPushButton("⏹️ หยุดเสียง")
		btn_stop.setProperty("class", "danger-btn")
		btn_stop.setStyleSheet("font-size: 15px; padding: 12px 20px;")
		btn_stop.setCursor(Qt.PointingHandCursor)
		btn_stop.clicked.connect(self.audio.stop_all)
		act.addWidget(btn_announce, 1)
		act.addWidget(btn_stop)
		layout.addLayout(act)

		self.lbl_announce_status = QLabel("💡 พิมพ์ภาษาไทย แล้วกด 'แปลอัตโนมัติ' เพื่อเติมภาษาอังกฤษ/จีน • ใช้ไมค์บนคีย์บอร์ดพิมพ์ด้วยเสียงได้")
		self.lbl_announce_status.setProperty("class", "muted")
		self.lbl_announce_status.setWordWrap(True)
		layout.addWidget(self.lbl_announce_status)

		self.tabs.addTab(tab, "📢 ประกาศเสียงตามสาย")

	def announce_now(self):
		langs = self.announce_langs.get_langs()
		if not any(e["enabled"] and e["text"] for e in langs) and not self.chk_ann_time.isChecked():
			self.lbl_announce_status.setText("⚠️ กรุณาพิมพ์ข้อความ และติ๊กอย่างน้อย 1 ภาษา")
			return
		if self.audio.live_active:
			self.lbl_announce_status.setText("🎙️ กำลังมีการพูดสดผ่านไมค์อยู่ — ระบบให้ไมค์มาก่อน กรุณารอวางสาย")
			return
		now = datetime.now()
		self.audio.play_announcement({
			"hour": now.hour,
			"minute": now.minute,
			"pre_chime": self.chk_ann_pre.isChecked(),
			"post_chime": self.chk_ann_post.isChecked(),
			"voice_announce": self.chk_ann_time.isChecked(),
			"speak_text": True,
			"label": "📢 ประกาศเสียงตามสาย",
			"langs": langs,
			"style": self.combo_ann_style.currentData() or None,
			"chime_style": self.combo_ann_chime.currentData() or "",
			"chime_length": self.combo_ann_chime_len.currentData() or "",
		})
		order = " → ".join(f"{e['code'].upper()}" + (f"×{e['repeat']}" if e["repeat"] > 1 else "")
						   for e in langs if e["enabled"])
		self.lbl_announce_status.setText(f"📢 กำลังประกาศ ({order}) — ประโยคใหม่อาจใช้เวลาสร้างเสียงสักครู่")

	def refresh_announce_templates(self):
		self.combo_templates.clear()
		self.combo_templates.addItem("— เลือกข้อความสำเร็จรูป —", None)
		for name, text in BUILTIN_TEMPLATES:
			langs = default_langs()
			langs[0]["text"] = text
			self.combo_templates.addItem(f"⭐ {name}", {"name": name, "langs": langs, "builtin": True})
		for tpl in self.config.get("announce_templates", []):
			self.combo_templates.addItem(f"📝 {tpl.get('name', '')}", dict(tpl, builtin=False))

	def load_announce_template(self, index):
		data = self.combo_templates.itemData(index)
		if data:
			self.announce_langs.set_langs(data.get("langs"))
			self.lbl_announce_status.setText(f"📋 โหลดข้อความ '{data.get('name')}' แล้ว — ตรวจสอบแล้วกดประกาศได้เลย")

	def save_announce_template(self):
		langs = self.announce_langs.get_langs()
		if not any(e["text"] for e in langs):
			self.lbl_announce_status.setText("⚠️ ยังไม่มีข้อความให้บันทึก")
			return
		name, ok = QInputDialog.getText(self, "บันทึกข้อความสำเร็จรูป", "ตั้งชื่อข้อความ:")
		if ok and name.strip():
			templates = [t for t in self.config.get("announce_templates", []) if t.get("name") != name.strip()]
			templates.append({"name": name.strip(), "langs": langs})
			self.config["announce_templates"] = templates
			save_config(self.config)
			self.refresh_announce_templates()
			self.lbl_announce_status.setText(f"💾 บันทึก '{name.strip()}' แล้ว")

	def delete_announce_template(self):
		data = self.combo_templates.currentData()
		if not data or data.get("builtin"):
			self.lbl_announce_status.setText("⚠️ เลือกข้อความที่บันทึกเอง (📝) ก่อนกดลบ")
			return
		self.config["announce_templates"] = [t for t in self.config.get("announce_templates", [])
											 if t.get("name") != data.get("name")]
		save_config(self.config)
		self.refresh_announce_templates()

	# ================================================================ แท็บตั้งค่า
	def init_settings_tab(self):
		tab = QWidget()
		outer = QVBoxLayout(tab)
		scroll = QScrollArea()
		scroll.setWidgetResizable(True)
		content = QWidget()
		layout = QVBoxLayout(content)
		layout.setContentsMargins(20, 16, 20, 16)
		scroll.setWidget(content)
		outer.addWidget(scroll)

		# ---- เสียงติ่งต่องเริ่มต้น ----
		chime_box = QGroupBox("🎵 เสียงติ่งต่องเริ่มต้น (10 แบบ × 3 ความยาว)")
		chime_layout = QVBoxLayout(chime_box)
		chime_row, self.combo_chime_style, self.combo_chime_length = build_chime_picker(
			self.config.get("chime_style", "classic"), self.config.get("chime_length", "medium"),
			preview=self.audio.play_chime_preview, allow_default=False)
		self.combo_chime_style.currentIndexChanged.connect(self.on_default_chime_changed)
		self.combo_chime_length.currentIndexChanged.connect(self.on_default_chime_changed)
		chime_layout.addLayout(chime_row)
		chime_note = QLabel("ใช้กับทุกรายการที่ตั้งเป็น 'ตามค่าเริ่มต้น' • เลือกแบบเฉพาะของแต่ละคาบได้ที่ปุ่ม ✏️ ในแท็บจัดการตารางเวลา")
		chime_note.setProperty("class", "muted")
		chime_note.setWordWrap(True)
		chime_layout.addWidget(chime_note)
		layout.addWidget(chime_box)

		# ---- ระบบเสียง AI ----
		voice_box = QGroupBox("🎙️ ระบบเสียง AI (Neural Voice) — ใช้ประกาศทุกภาษา")
		grid = QGridLayout(voice_box)
		grid.setHorizontalSpacing(12)

		grid.addWidget(QLabel("สไตล์เสียงเริ่มต้น:"), 0, 0)
		self.combo_style = QComboBox()
		for key, name in VOICE_STYLES:
			self.combo_style.addItem(name, key)
		self.combo_style.setCurrentIndex(max(0, self.combo_style.findData(self.config.get("tts_style", "female"))))
		self.combo_style.currentIndexChanged.connect(self.on_voice_style_changed)
		grid.addWidget(self.combo_style, 0, 1)

		grid.addWidget(QLabel("ความเร็วการพูด:"), 1, 0)
		self.combo_speed = QComboBox()
		for key, name, _rate in SPEEDS:
			self.combo_speed.addItem(name, key)
		self.combo_speed.setCurrentIndex(max(0, self.combo_speed.findData(self.config.get("tts_speed", "normal"))))
		self.combo_speed.currentIndexChanged.connect(self.on_voice_speed_changed)
		grid.addWidget(self.combo_speed, 1, 1)

		self.voice_combos = {}
		for row, (code, name, flag) in enumerate(LANGUAGES, start=2):
			grid.addWidget(QLabel(f"{flag} เสียงภาษา{name}:"), row, 0)
			combo = QComboBox()
			combo.setMinimumWidth(360)
			combo.currentIndexChanged.connect(lambda _, c=code: self.on_voice_override_changed(c))
			self.voice_combos[code] = combo
			grid.addWidget(combo, row, 1)
			btn_test = QPushButton("🔊 ทดสอบ")
			btn_test.setProperty("class", "secondary-btn")
			btn_test.clicked.connect(lambda _, c=code: self.test_voice(c))
			grid.addWidget(btn_test, row, 2)
		self.populate_voice_combos()

		btn_row = QHBoxLayout()
		self.btn_refresh_voices = QPushButton("🔄 โหลดรายชื่อเสียงทั้งหมดจากอินเทอร์เน็ต")
		self.btn_refresh_voices.setProperty("class", "secondary-btn")
		self.btn_refresh_voices.clicked.connect(self.refresh_voice_list)
		btn_precache = QPushButton("⬇️ ดาวน์โหลดเสียงทุกตารางเก็บไว้ (ใช้ออฟไลน์)")
		btn_precache.setProperty("class", "primary-btn")
		btn_precache.clicked.connect(self.start_precache)
		btn_clear = QPushButton("🗑️ ล้างแคชเสียง")
		btn_clear.setProperty("class", "secondary-btn")
		btn_clear.clicked.connect(self.clear_voice_cache)
		btn_row.addWidget(self.btn_refresh_voices)
		btn_row.addWidget(btn_precache)
		btn_row.addWidget(btn_clear)
		grid.addLayout(btn_row, 5, 0, 1, 3)

		self.cache_bar = QProgressBar()
		self.cache_bar.setRange(0, 1)
		self.cache_bar.setValue(0)
		grid.addWidget(self.cache_bar, 6, 0, 1, 3)
		self.lbl_cache_status = QLabel("")
		self.lbl_cache_status.setProperty("class", "muted")
		self.lbl_cache_status.setWordWrap(True)
		grid.addWidget(self.lbl_cache_status, 7, 0, 1, 3)

		note = QLabel("ℹ️ เสียงที่ดาวน์โหลดแล้วจะเก็บไว้ในเครื่อง ถึงเวลาออดจะเล่นได้ทันทีแม้ไม่มีอินเทอร์เน็ต "
					  "• เสียงเด็กของภาษาไทยจำลองจากการปรับระดับเสียง • เลือก 'เสียงอื่น ๆ' รายภาษาได้ในช่องด้านบน")
		note.setProperty("class", "muted")
		note.setWordWrap(True)
		grid.addWidget(note, 8, 0, 1, 3)
		layout.addWidget(voice_box)

		# ---- อัปเดตโปรแกรม ----
		upd_box = QGroupBox("🔄 อัปเดตโปรแกรม")
		upd = QVBoxLayout(upd_box)
		lbl_ver = QLabel(f"เวอร์ชันที่ใช้อยู่: v{APP_VERSION}")
		lbl_ver.setProperty("class", "title")
		upd.addWidget(lbl_ver)
		self.chk_auto_update = QCheckBox("ตรวจสอบเวอร์ชันใหม่อัตโนมัติทุกครั้งที่เปิดโปรแกรม")
		self.chk_auto_update.setChecked(self.config.get("auto_check_update", True))
		self.chk_auto_update.toggled.connect(self.on_auto_update_toggled)
		upd.addWidget(self.chk_auto_update)
		row = QHBoxLayout()
		btn_check = QPushButton("🔍 ตรวจสอบอัปเดตตอนนี้")
		btn_check.setProperty("class", "primary-btn")
		btn_check.clicked.connect(lambda: self.check_for_updates(manual=True))
		self.lbl_update_status = QLabel("")
		self.lbl_update_status.setProperty("class", "muted")
		row.addWidget(btn_check)
		row.addWidget(self.lbl_update_status, 1)
		upd.addLayout(row)
		layout.addWidget(upd_box)
		layout.addStretch()

		self.tabs.addTab(tab, "⚙️ ตั้งค่า")

	# ---- ตั้งค่าเสียง ----
	def populate_voice_combos(self):
		overrides = self.config.get("tts_voice_overrides") or {}
		for code, combo in self.voice_combos.items():
			combo.blockSignals(True)
			combo.clear()
			combo.addItem("✨ อัตโนมัติ (ตามสไตล์เสียงเริ่มต้น)", "")
			for name, desc in self.audio.tts.list_voices(code):
				combo.addItem(f"{name}" + (f"  —  {desc}" if desc else ""), name)
			current = overrides.get(code, "")
			idx = combo.findData(current)
			if idx < 0 and current:
				combo.addItem(current, current)
				idx = combo.count() - 1
			combo.setCurrentIndex(max(0, idx))
			combo.blockSignals(False)

	def _voice_settings_changed(self):
		save_config(self.config)
		self.refresh_voice_status()
		self._precache_timer.start()

	def on_default_chime_changed(self, _):
		self.config["chime_style"] = self.combo_chime_style.currentData()
		self.config["chime_length"] = self.combo_chime_length.currentData()
		save_config(self.config)

	def on_voice_style_changed(self, _):
		self.config["tts_style"] = self.combo_style.currentData()
		self._voice_settings_changed()

	def on_voice_speed_changed(self, _):
		self.config["tts_speed"] = self.combo_speed.currentData()
		self._voice_settings_changed()

	def on_voice_override_changed(self, code):
		overrides = dict(self.config.get("tts_voice_overrides") or {})
		overrides[code] = self.voice_combos[code].currentData() or ""
		self.config["tts_voice_overrides"] = overrides
		self._voice_settings_changed()

	def test_voice(self, code):
		self.audio.play_announcement({
			"pre_chime": False,
			"post_chime": False,
			"voice_announce": False,
			"speak_text": True,
			"label": f"ทดสอบเสียง {code.upper()}",
			"langs": [{"code": code, "enabled": True, "text": VOICE_SAMPLES[code], "repeat": 1}],
		})

	def refresh_voice_list(self):
		self.btn_refresh_voices.setEnabled(False)
		self.lbl_cache_status.setText("⏳ กำลังโหลดรายชื่อเสียงจากอินเทอร์เน็ต...")

		def worker():
			count = self.audio.tts.refresh_voices()

			def done():
				self.btn_refresh_voices.setEnabled(True)
				self.populate_voice_combos()
				self.lbl_cache_status.setText(f"✅ โหลดรายชื่อเสียงแล้ว {count} เสียง" if count
											  else "⚠️ โหลดไม่สำเร็จ (ตรวจสอบอินเทอร์เน็ต)")
			self._ui.invoke.emit(done)

		threading.Thread(target=worker, daemon=True).start()

	def clear_voice_cache(self):
		confirm = styled_message(self, "ล้างแคชเสียง",
								 "ลบไฟล์เสียง AI ที่ดาวน์โหลดเก็บไว้ทั้งหมด?\n(ระบบจะดาวน์โหลดใหม่อัตโนมัติเมื่อมีอินเทอร์เน็ต)",
								 QMessageBox.Yes | QMessageBox.No)
		if confirm == QMessageBox.Yes:
			self.audio.tts.clear_cache()
			self.refresh_voice_status()
			self._precache_timer.start()

	# ---- เตรียมเสียงล่วงหน้า ----
	def start_precache(self):
		self.audio.precache_schedules(self.scheduler.schedules)

	def _retry_precache_if_incomplete(self):
		"""ยังมีประโยคที่ไม่มีเสียงเลย หรือยังเป็นแค่เสียงสำรอง → ลองดาวน์โหลดเสียง AI ใหม่"""
		ready, total, ai_ready = self.audio.cache_status(self.scheduler.schedules)
		if ready < total or ai_ready < total:
			self.start_precache()

	def on_cache_progress(self, done, total):
		self.cache_bar.setRange(0, max(1, total))
		self.cache_bar.setValue(done)
		self.lbl_voice_status.setText(f"🎙️ เสียง AI: กำลังเตรียมเสียงประกาศ {done}/{total}")

	def on_cache_finished(self, ok, total):
		self.refresh_voice_status()

	def refresh_voice_status(self):
		ready, total, ai_ready = self.audio.cache_status(self.scheduler.schedules)
		size_mb = self.audio.tts.cache_size_bytes() / (1024 * 1024)
		if total == 0:
			text = "🎙️ เสียง AI: พร้อมใช้งาน (ยังไม่มีประโยคที่ต้องเตรียม)"
		elif ready < total:
			text = f"🎙️ เสียง AI: ⚠️ พร้อมออฟไลน์ {ready}/{total} ประโยค — เชื่อมอินเทอร์เน็ตเพื่อดาวน์โหลดส่วนที่เหลือ"
		elif ai_ready < total:
			text = (f"🎙️ เสียง AI: ✅ พร้อมใช้งานออฟไลน์ครบ {total} ประโยค "
					f"(เสียง AI {ai_ready} • เสียงสำรอง {total - ai_ready} จะอัปเกรดเป็นเสียง AI อัตโนมัติ)")
		else:
			text = f"🎙️ เสียง AI: ✅ พร้อมใช้งานออฟไลน์ครบ {total}/{total} ประโยค"
		self.lbl_voice_status.setText(text)
		if hasattr(self, "lbl_cache_status"):
			self.lbl_cache_status.setText(f"{text}  •  พื้นที่แคช {size_mb:.1f} MB")
			self.cache_bar.setRange(0, max(1, total))
			self.cache_bar.setValue(ready)

	# ================================================================ อัปเดตโปรแกรม
	def on_auto_update_toggled(self, on):
		self.config["auto_check_update"] = bool(on)
		save_config(self.config)

	def on_update_button(self):
		if self._latest_release and self._latest_release.get("is_newer"):
			self.show_update_dialog(self._latest_release)
		else:
			self.check_for_updates(manual=True)

	def _auto_check_updates(self):
		if self.config.get("auto_check_update", True):
			self.check_for_updates(manual=False)

	def check_for_updates(self, manual=False):
		self._update_manual = manual
		if manual:
			self.btn_update.setText("⏳ กำลังตรวจสอบ...")
			self.lbl_update_status.setText("⏳ กำลังตรวจสอบเวอร์ชันล่าสุด...")
		self.updater.check_async()

	def _set_update_available(self, info):
		"""แสดง/ซ่อนกระดิ่งแจ้งเตือน: มีเฉพาะตอนมีเวอร์ชันใหม่ที่ยังไม่ได้อัปเดต"""
		if info and info.get("is_newer"):
			text = f"🔔 มีอัปเดตใหม่ v{info['version']}"
			self.btn_update_badge.setText(text)
			self.btn_update_badge.show()
			self.btn_update.setText(f"🔔 อัปเดตเป็น v{info['version']}")
			self.lbl_update_status.setText(f"🔔 มีเวอร์ชันใหม่ v{info['version']} — กดเพื่ออัปเดต")
			self.tray_icon.setToolTip(f"School AOD v{APP_VERSION} — มีอัปเดต v{info['version']}")
		else:
			self.btn_update_badge.hide()
			self.btn_update.setText(f"✅ เวอร์ชันล่าสุด v{APP_VERSION}")
			self.lbl_update_status.setText(f"✅ คุณใช้เวอร์ชันล่าสุดแล้ว (v{APP_VERSION})")
			self.tray_icon.setToolTip(f"School AOD v{APP_VERSION}")

	def on_update_checked(self, info, error):
		manual = self._update_manual
		if error or not info:
			if not (self._latest_release and self._latest_release.get("is_newer")):
				self.btn_update.setText("🔄 ตรวจสอบอัปเดต")
			self.lbl_update_status.setText("⚠️ ตรวจสอบไม่สำเร็จ (ตรวจสอบอินเทอร์เน็ต)")
			if manual:
				styled_message(self, "ตรวจสอบอัปเดตไม่สำเร็จ",
							   f"เชื่อมต่อ GitHub ไม่ได้ กรุณาตรวจสอบอินเทอร์เน็ตแล้วลองใหม่\n\n{error}",
							   QMessageBox.Ok, icon=QMessageBox.Warning)
			return

		self._latest_release = info
		self._set_update_available(info)

		if not info["is_newer"]:
			if manual:
				styled_message(self, "เป็นเวอร์ชันล่าสุดแล้ว",
							   f"✅ คุณใช้เวอร์ชันล่าสุดแล้ว (v{APP_VERSION})\nไม่มีอัปเดตใหม่ในตอนนี้",
							   QMessageBox.Ok, icon=QMessageBox.Information)
			return

		if manual:
			self.show_update_dialog(info)
		elif info["version"] not in self._prompted_versions:
			# ตรวจอัตโนมัติ: แจ้งครั้งเดียวต่อเวอร์ชัน (กดทีหลังแล้ว กระดิ่งยังค้างไว้ให้กดได้ตลอด)
			self._prompted_versions.add(info["version"])
			self.tray_icon.showMessage("🔔 มีเวอร์ชันใหม่ของ School AOD",
									   f"v{info['version']} พร้อมให้อัปเดตแล้ว", QSystemTrayIcon.Information, 6000)
			if self.isVisible():
				self.show_update_dialog(info)

	def show_update_dialog(self, info):
		self.show_window()
		dialog = UpdateDialog(info, can_self_update(), self)
		dialog.exec()
		if dialog.choice == "update":
			if can_self_update() and info.get("asset_url"):
				self._update_progress = QProgressDialog("⬇️ กำลังดาวน์โหลดเวอร์ชันใหม่...", None, 0, 100, self)
				self._update_progress.setWindowTitle(f"อัปเดตเป็น v{info['version']}")
				self._update_progress.setWindowModality(Qt.WindowModal)
				self._update_progress.setMinimumDuration(0)
				self._update_progress.setValue(0)
				self._update_progress.show()
				self.updater.download_async(info)
			else:
				QDesktopServices.openUrl(QUrl(info.get("html_url")))

	def on_update_download_progress(self, done, total):
		if self._update_progress:
			if total:
				self._update_progress.setValue(int(done * 100 / total))
			self._update_progress.setLabelText(f"⬇️ กำลังดาวน์โหลด... {done / 1048576:.1f} / {total / 1048576:.1f} MB")

	def on_update_install_ready(self, ok, result):
		if self._update_progress:
			self._update_progress.close()
			self._update_progress = None
		if not ok:
			styled_message(self, "อัปเดตไม่สำเร็จ", f"ดาวน์โหลด/เตรียมติดตั้งไม่สำเร็จ:\n{result}",
						   QMessageBox.Ok, icon=QMessageBox.Warning)
			return
		styled_message(self, "พร้อมติดตั้ง",
					   "ดาวน์โหลดเรียบร้อย ✅\nโปรแกรมจะปิดตัวและเปิดเวอร์ชันใหม่ให้อัตโนมัติภายในไม่กี่วินาที",
					   QMessageBox.Ok, icon=QMessageBox.Information)
		try:
			UpdateManager.launch_installer(result)
		except Exception as e:
			styled_message(self, "อัปเดตไม่สำเร็จ", f"เริ่มตัวติดตั้งไม่ได้: {e}", QMessageBox.Ok, icon=QMessageBox.Warning)
			return
		QGuiApplication.quit()
