import os
import sys
import json
import socket
import threading
import traceback
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response, JSONResponse
import uvicorn
from win_system import config_windows_firewall
from config_manager import load_config
from paths import resource_path, data_path
from tts_engine import normalize_langs
from translator import translate, detect_lang
from version import APP_VERSION

app = FastAPI(title="School AOD Remote Dashboard")

GLOBAL_AUDIO_ENGINE = None
GLOBAL_SCHEDULER_ENGINE = None
CONFIG = load_config()
REMOTE_PIN = CONFIG.get("remote_pin", "853325")

# เครื่องแม่ควบคุมได้ว่าจะอนุญาตให้พูดผ่านรีโมทหรือไม่
ALLOW_REMOTE_VOICE = CONFIG.get("allow_remote_voice", True)

def set_allow_voice(value: bool):
	global ALLOW_REMOTE_VOICE
	ALLOW_REMOTE_VOICE = bool(value)

def get_local_ip():
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.connect(("8.8.8.8", 80))
		ip = s.getsockname()[0]
		s.close()
		return ip
	except Exception:
		return "127.0.0.1"

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="th">
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
	<title>School AOD Remote</title>
	<!-- PWA: ติดตั้งลงจอโฮมได้เหมือนแอป ทั้ง Android และ iOS -->
	<link rel="manifest" href="/manifest.webmanifest">
	<meta name="theme-color" content="#064e3b">
	<meta name="mobile-web-app-capable" content="yes">
	<meta name="apple-mobile-web-app-capable" content="yes">
	<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
	<meta name="apple-mobile-web-app-title" content="AOD Remote">
	<link rel="apple-touch-icon" href="/apple-touch-icon.png">
	<link rel="icon" href="/icon-192.png">
	<script>if ('serviceWorker' in navigator) { window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(()=>{})); }</script>
	<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
	<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Thai:wght@400;600;700&display=swap" rel="stylesheet">
	<style>
		body {
			background: linear-gradient(135deg, #022c22 0%, #064e3b 50%, #02381f 100%);
			min-height: 100vh;
			color: #ecfdf5;
			font-family: 'Noto Sans Thai', sans-serif;
		}
		.glass-card {
			background: rgba(6, 78, 59, 0.4);
			backdrop-filter: blur(14px);
			border: 1px solid rgba(52, 211, 153, 0.25);
			border-radius: 20px;
			box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
		}
		.btn-glow {
			background: linear-gradient(90deg, #10b981, #047857);
			border: none; color: white; font-weight: bold;
		}
		#talk-btn.recording { background: #dc2626 !important; animation: pulse 1s infinite; }
		@keyframes pulse { 0%{transform:scale(1)} 50%{transform:scale(1.04)} 100%{transform:scale(1)} }
	</style>
</head>
<body class="py-4">
	<div class="container" style="max-width: 560px;">
		<div class="glass-card p-4 text-center">
			<h2 class="fw-bold text-success mb-1">🔔 School AOD Remote</h2>
			<p class="text-light opacity-75 mb-4">ระบบควบคุมอ๊อดโรงเรียนระยะไกล</p>

			<div id="auth-section">
				<div class="mb-3">
					<input type="password" id="pin-input" class="form-control form-control-lg text-center fs-3 fw-bold bg-dark text-white border-success" placeholder="กรอก PIN Code">
				</div>
				<button onclick="login()" class="btn btn-glow w-100 py-3 fs-5">🔓 เข้าสู่ระบบ Remote</button>
			</div>

			<div id="control-section" class="d-none">
				<div class="alert alert-success bg-opacity-25 border-0 text-success fw-bold mb-3">✅ เชื่อมต่อสำเร็จ</div>

				<button onclick="triggerBell()" class="btn btn-warning w-100 py-3 fs-4 fw-bold mb-3">🔔 สั่งเปิดอ๊อด (ขานเวลาปัจจุบัน)</button>

				<div class="glass-card p-3 mb-3">
					<h5 class="fw-bold text-info mb-2">📢 ประชาสัมพันธ์สด (พูดออกที่เครื่องแม่)</h5>
					<button id="talk-btn" class="btn btn-glow w-100 py-3 fs-5">🎙️ กดเพื่อพูดสด</button>
					<div id="talk-status" class="small text-light opacity-75 mt-2">กดปุ่มแล้วพูดออกที่โรงเรียนทันที (เรียลไทม์) — กดอีกครั้งเพื่อวางสาย</div>
				</div>

				<div class="glass-card p-3 mb-3 text-start">
					<h5 class="fw-bold text-info mb-2 text-center">📝 ประกาศด้วยข้อความ (เสียง AI หลายภาษา)</h5>
					<textarea id="ann-text" class="form-control bg-dark text-white border-success mb-2" rows="3" maxlength="500"
						placeholder="พิมพ์ข้อความประกาศ หรือกดไมค์บนคีย์บอร์ดเพื่อพูดเป็นข้อความ"></textarea>
					<div class="small text-light opacity-75 mb-1">ติ๊กภาษาที่จะอ่าน • อ่านจากบนลงล่าง (▲▼ สลับลำดับ)</div>
					<div id="ann-langs" class="mb-2"></div>
					<div class="d-flex gap-2 mb-2">
						<select id="ann-style" class="form-select form-select-sm bg-dark text-white border-success">
							<option value="">🎙️ เสียงตามค่าเริ่มต้น</option>
							<option value="female">👩 เสียงผู้หญิง</option>
							<option value="male">👨 เสียงผู้ชาย</option>
							<option value="girl">👧 เสียงเด็กผู้หญิง</option>
							<option value="boy">👦 เสียงเด็กผู้ชาย</option>
						</select>
					</div>
					<div class="d-flex gap-3 small mb-2">
						<label><input type="checkbox" id="ann-chime" checked> 🔔 ติ่งต่องหน้า-ท้าย</label>
						<label><input type="checkbox" id="ann-time"> 🕒 ขานเวลาด้วย</label>
					</div>
					<button onclick="sendAnnounce()" id="ann-btn" class="btn btn-glow w-100 py-2 fs-5">📢 ประกาศ</button>
					<div id="ann-status" class="small text-light opacity-75 mt-2"></div>
				</div>

				<div class="text-start">
					<h5 class="fw-bold mb-3 text-info">📅 ตารางเวลา (กดเพื่อสั่งเล่นทันที):</h5>
					<div id="schedule-list" class="list-group list-group-flush rounded-3"></div>
				</div>
			</div>

			<footer class="mt-4 pt-3 border-top border-success text-center">
				<p class="mb-1 fw-bold">
					<a href="https://www.facebook.com/suebsing" target="_blank" class="text-info text-decoration-none">
						Develop by hAcKEdpRO | Pongwattana Suebsing
					</a>
				</p>
				<small class="text-muted">Version {{APP_VERSION}} &copy; 2026-2027 All Rights Reserved</small>
			</footer>
		</div>
	</div>

	<script>
		let pin = localStorage.getItem('school_aod_pin') || "";
		if (pin) { document.getElementById('pin-input').value = pin; login(); }

		async function login() {
			pin = document.getElementById('pin-input').value;
			const res = await fetch('/api/schedules', { headers: { 'access-code': pin } });
			if (res.ok) {
				localStorage.setItem('school_aod_pin', pin);
				document.getElementById('auth-section').classList.add('d-none');
				document.getElementById('control-section').classList.remove('d-none');
				renderSchedules(await res.json());
			} else {
				alert("PIN Code ไม่ถูกต้อง!");
			}
		}

		async function triggerBell() {
			const res = await fetch('/api/test-bell', { method: 'POST', headers: { 'access-code': pin } });
			if (res.ok) toast("ส่งสัญญาณเปิดอ๊อดแล้ว!");
		}

		async function playSchedule(id) {
			const res = await fetch('/api/play-schedule', {
				method: 'POST',
				headers: { 'access-code': pin, 'Content-Type': 'application/json' },
				body: JSON.stringify({ id: id })
			});
			if (res.ok) toast("กำลังเล่นตามตารางที่เลือก");
		}

		function renderSchedules(items) {
			const list = document.getElementById('schedule-list');
			list.innerHTML = items.map(i => `<div class="list-group-item bg-dark bg-opacity-50 text-white d-flex justify-content-between align-items-center border-secondary">
				<div><span class="fs-6 fw-bold text-warning">${i.time}</span> - ${i.label}</div>
				<button onclick="playSchedule('${i.id}')" class="btn btn-sm btn-outline-success">▶️ เล่น</button>
			</div>`).join('');
		}

		function toast(msg) {
			const t = document.getElementById('talk-status');
			const old = t.innerText; t.innerText = "✅ " + msg;
			setTimeout(() => t.innerText = old, 2500);
		}

		// ---- ประกาศด้วยข้อความ: เลือกภาษา + จัดลำดับ + จำนวนรอบทวน ----
		let annLangs = [
			{ code: 'th', name: '🇹🇭 ไทย', enabled: true, repeat: 1 },
			{ code: 'en', name: '🇬🇧 English', enabled: false, repeat: 1 },
			{ code: 'zh', name: '🇨🇳 中文', enabled: false, repeat: 1 },
		];
		try { const saved = JSON.parse(localStorage.getItem('school_aod_langs')); if (Array.isArray(saved) && saved.length === 3) annLangs = saved; } catch (e) {}

		function renderLangs() {
			localStorage.setItem('school_aod_langs', JSON.stringify(annLangs));
			document.getElementById('ann-langs').innerHTML = annLangs.map((l, i) => `
				<div class="d-flex align-items-center gap-2 mb-1 p-1 rounded" style="background:rgba(0,0,0,.25)">
					<input type="checkbox" class="form-check-input m-0" ${l.enabled ? 'checked' : ''} onchange="annLangs[${i}].enabled=this.checked;renderLangs()">
					<span class="flex-grow-1">${l.name}</span>
					<select class="form-select form-select-sm bg-dark text-white" style="width:auto" onchange="annLangs[${i}].repeat=+this.value;renderLangs()">
						${[1,2,3].map(n => `<option value="${n}" ${l.repeat === n ? 'selected' : ''}>${n === 1 ? 'อ่าน 1 รอบ' : 'ทวน ' + n + ' รอบ'}</option>`).join('')}
					</select>
					<button class="btn btn-sm btn-outline-light py-0" ${i === 0 ? 'disabled' : ''} onclick="moveLang(${i},-1)">▲</button>
					<button class="btn btn-sm btn-outline-light py-0" ${i === annLangs.length - 1 ? 'disabled' : ''} onclick="moveLang(${i},1)">▼</button>
				</div>`).join('');
		}
		function moveLang(i, d) {
			const j = i + d;
			if (j < 0 || j >= annLangs.length) return;
			[annLangs[i], annLangs[j]] = [annLangs[j], annLangs[i]];
			renderLangs();
		}
		renderLangs();

		async function sendAnnounce() {
			const text = document.getElementById('ann-text').value.trim();
			const status = document.getElementById('ann-status');
			if (!text) { status.innerText = "⚠️ กรุณาพิมพ์ข้อความก่อน"; return; }
			if (!annLangs.some(l => l.enabled)) { status.innerText = "⚠️ เลือกอย่างน้อย 1 ภาษา"; return; }
			const btn = document.getElementById('ann-btn');
			btn.disabled = true;
			status.innerText = "⏳ กำลังแปลภาษาและส่งประกาศ...";
			try {
				const chime = document.getElementById('ann-chime').checked;
				const res = await fetch('/api/announce', {
					method: 'POST',
					headers: { 'access-code': pin, 'Content-Type': 'application/json' },
					body: JSON.stringify({
						text: text, langs: annLangs, chime: chime,
						time: document.getElementById('ann-time').checked,
						style: document.getElementById('ann-style').value
					})
				});
				if (res.ok) {
					const data = await res.json();
					const tr = Object.entries(data.translations || {}).map(([k, v]) => `${k.toUpperCase()}: ${v || '(แปลไม่สำเร็จ)'}`).join('\\n');
					status.innerText = "✅ ส่งประกาศแล้ว" + (tr ? "\\n" + tr : "");
				} else if (res.status === 403) {
					status.innerText = "🚫 ผู้ดูแลปิดการประกาศผ่านรีโมทอยู่";
				} else {
					status.innerText = "❌ ส่งไม่สำเร็จ (HTTP " + res.status + ")";
				}
			} catch (e) {
				status.innerText = "❌ ส่งไม่สำเร็จ: " + e.message;
			}
			btn.disabled = false;
		}

		// ---- ประชาสัมพันธ์สดแบบเรียลไทม์ (walkie-talkie): สตรีม PCM ผ่าน WebSocket ออกทันที ----
		let audioCtx, mediaStream, processor, srcNode, zeroGain, ws, streaming = false;
		const talkBtn = document.getElementById('talk-btn');
		function setTalkStatus(msg) { document.getElementById('talk-status').innerText = msg; }

		async function startTalk() {
			if (streaming) return;
			if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.isSecureContext) {
				setTalkStatus("⚠️ ใช้ไมค์ไม่ได้: ต้องเปิดผ่านลิงก์ HTTPS ด้วย Safari หรือ Chrome โดยตรง (ไม่ใช่แอปในตัว)");
				return;
			}
			try {
				mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
				audioCtx = new (window.AudioContext || window.webkitAudioContext)();
				await audioCtx.resume();   // สำคัญมากสำหรับ iOS
				const sr = audioCtx.sampleRate;

				const proto = location.protocol === 'https:' ? 'wss' : 'ws';
				ws = new WebSocket(`${proto}://${location.host}/ws/live-voice`);
				ws.binaryType = 'arraybuffer';

				ws.onopen = () => {
					ws.send(JSON.stringify({ pin: pin, sampleRate: sr, channels: 1 }));
					beginCapture();
					streaming = true;
					talkBtn.classList.add('recording');
					talkBtn.innerText = "⏹️ กำลังพูดสด... กดเพื่อวางสาย";
					setTalkStatus("🔴 กำลังออกอากาศสดที่โรงเรียน (พูดได้เลย)");
				};
				ws.onmessage = (e) => {
					try { const m = JSON.parse(e.data); if (m.error) { setTalkStatus("🚫 " + m.error); hangUp(); } } catch (_) {}
				};
				ws.onclose = () => { if (streaming) { setTalkStatus("⏹️ วางสายแล้ว"); } cleanupMic(); streaming = false; resetBtn(); };
				ws.onerror = () => { setTalkStatus("❌ เชื่อมต่อสตรีมไม่สำเร็จ"); };
			} catch (err) {
				setTalkStatus("⚠️ ไม่ได้รับสิทธิ์ไมโครโฟน หรือเบราว์เซอร์ไม่รองรับ (" + (err.name || err) + ")");
			}
		}

		function beginCapture() {
			srcNode = audioCtx.createMediaStreamSource(mediaStream);
			processor = audioCtx.createScriptProcessor(2048, 1, 1);  // บัฟเฟอร์เล็ก = หน่วงต่ำ
			zeroGain = audioCtx.createGain(); zeroGain.gain.value = 0;  // กันเสียงย้อนที่มือถือ
			processor.onaudioprocess = (e) => {
				if (!ws || ws.readyState !== 1) return;
				const f = e.inputBuffer.getChannelData(0);
				const pcm = new Int16Array(f.length);
				for (let i = 0; i < f.length; i++) {
					let s = Math.max(-1, Math.min(1, f[i]));
					pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
				}
				ws.send(pcm.buffer);   // ส่งออกทันทีแบบเรียลไทม์
			};
			srcNode.connect(processor);
			processor.connect(zeroGain);
			zeroGain.connect(audioCtx.destination);
		}

		function hangUp() {
			if (ws && (ws.readyState === 1 || ws.readyState === 0)) { try { ws.close(); } catch (e) {} }
			cleanupMic();
			streaming = false;
			resetBtn();
		}

		function cleanupMic() {
			try { processor && processor.disconnect(); } catch (e) {}
			try { srcNode && srcNode.disconnect(); } catch (e) {}
			try { zeroGain && zeroGain.disconnect(); } catch (e) {}
			try { mediaStream && mediaStream.getTracks().forEach(t => t.stop()); } catch (e) {}
			try { audioCtx && audioCtx.close(); } catch (e) {}
			processor = srcNode = zeroGain = mediaStream = audioCtx = null;
		}

		function resetBtn() {
			talkBtn.classList.remove('recording');
			talkBtn.innerText = "🎙️ กดเพื่อพูดสด";
		}

		// กดครั้งเดียวเริ่มพูดทันที / กดอีกครั้งวางสาย (ไม่ต้องกดค้าง)
		talkBtn.addEventListener('click', () => { if (streaming) hangUp(); else startTalk(); });
	</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
	return HTML_TEMPLATE.replace("{{APP_VERSION}}", APP_VERSION)

# ---- PWA: ทำให้ติดตั้งลงจอโฮมได้เหมือนแอป (Android/iOS) ----
_PWA_MANIFEST = {
	"name": "School AOD Remote",
	"short_name": "AOD Remote",
	"description": "ระบบควบคุมอ๊อดโรงเรียนระยะไกล",
	"start_url": "/",
	"scope": "/",
	"display": "standalone",
	"orientation": "portrait",
	"background_color": "#022c22",
	"theme_color": "#064e3b",
	"icons": [
		{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
		{"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
	],
}

_SERVICE_WORKER = (
	"self.addEventListener('install', e => self.skipWaiting());\n"
	"self.addEventListener('activate', e => self.clients.claim());\n"
	"self.addEventListener('fetch', e => {});\n"
)

@app.get("/manifest.webmanifest")
def manifest():
	return JSONResponse(_PWA_MANIFEST, media_type="application/manifest+json")

@app.get("/sw.js")
def service_worker():
	return Response(_SERVICE_WORKER, media_type="application/javascript")

def _serve_icon(filename: str):
	path = resource_path("assets", filename)
	if os.path.exists(path):
		with open(path, "rb") as f:
			return Response(f.read(), media_type="image/png")
	raise HTTPException(status_code=404, detail="icon not found")

@app.get("/icon-192.png")
def icon_192():
	return _serve_icon("icon-192.png")

@app.get("/icon-512.png")
def icon_512():
	return _serve_icon("icon-512.png")

@app.get("/apple-touch-icon.png")
def apple_icon():
	return _serve_icon("apple-touch-icon.png")

def _check_pin(access_code: str):
	if access_code != REMOTE_PIN:
		raise HTTPException(status_code=401, detail="Invalid Access Code")

@app.get("/api/schedules")
def get_schedules(access_code: str = Header(...)):
	_check_pin(access_code)
	if GLOBAL_SCHEDULER_ENGINE:
		return GLOBAL_SCHEDULER_ENGINE.schedules
	return []

@app.post("/api/test-bell")
def trigger_bell(access_code: str = Header(...)):
	_check_pin(access_code)
	if GLOBAL_AUDIO_ENGINE:
		# ส่ง signal ให้ไปเล่นบน main thread ของ Qt (ห้ามเรียก QMediaPlayer ตรง ๆ จากเธรด uvicorn)
		GLOBAL_AUDIO_ENGINE.remote_bell_requested.emit()
	return {"status": "success"}

@app.post("/api/play-schedule")
async def play_schedule(request: Request, access_code: str = Header(...)):
	_check_pin(access_code)
	data = await request.json()
	target_id = str(data.get("id", ""))
	if GLOBAL_SCHEDULER_ENGINE and GLOBAL_AUDIO_ENGINE:
		for item in GLOBAL_SCHEDULER_ENGINE.schedules:
			if str(item.get("id")) == target_id:
				GLOBAL_AUDIO_ENGINE.play_item_requested.emit(item)
				return {"status": "success", "label": item.get("label")}
	raise HTTPException(status_code=404, detail="Schedule not found")

@app.post("/api/announce")
def announce(payload: dict, access_code: str = Header(...)):
	"""ประกาศข้อความด้วยเสียง AI หลายภาษาจากรีโมท
	เป็นฟังก์ชันแบบ sync → FastAPI รันใน thread pool จึงรอการแปลภาษาได้โดยไม่บล็อกเซิร์ฟเวอร์
	"""
	_check_pin(access_code)
	if not ALLOW_REMOTE_VOICE:
		raise HTTPException(status_code=403, detail="ผู้ดูแลปิดการประกาศผ่านรีโมท")
	if not GLOBAL_AUDIO_ENGINE:
		raise HTTPException(status_code=503, detail="Audio engine not ready")

	text = str(payload.get("text", "")).strip()[:500]
	if not text:
		raise HTTPException(status_code=422, detail="ไม่มีข้อความประกาศ")

	source = detect_lang(text)
	langs, translations = [], {}
	for entry in normalize_langs(payload.get("langs")):
		if entry["enabled"]:
			if entry["code"] == source:
				entry["text"] = text
			else:
				entry["text"] = translate(text, entry["code"], source)
				translations[entry["code"]] = entry["text"]
		langs.append(entry)

	now = datetime.now()
	chime = bool(payload.get("chime", True))
	GLOBAL_AUDIO_ENGINE.announce_requested.emit({
		"hour": now.hour,
		"minute": now.minute,
		"pre_chime": chime,
		"post_chime": chime,
		"voice_announce": bool(payload.get("time", False)),
		"speak_text": True,
		"label": "📢 ประกาศจากรีโมท",
		"langs": langs,
		"style": payload.get("style") or None,
	})
	return {"status": "success", "translations": translations}

@app.get("/api/voice-allowed")
def voice_allowed(access_code: str = Header(...)):
	_check_pin(access_code)
	return {"allowed": ALLOW_REMOTE_VOICE}

@app.post("/api/live-voice")
async def live_voice(request: Request, access_code: str = Header(...)):
	_check_pin(access_code)
	if not ALLOW_REMOTE_VOICE:
		raise HTTPException(status_code=403, detail="ผู้ดูแลปิดการพูดผ่านรีโมท")
	if not GLOBAL_AUDIO_ENGINE:
		raise HTTPException(status_code=503, detail="Audio engine not ready")
	audio_bytes = await request.body()
	# ต้องมีข้อมูลเสียงจริง (มากกว่าแค่ WAV header 44 ไบต์) มิฉะนั้นแปลว่าไมค์ไม่ได้เสียง
	if not audio_bytes or len(audio_bytes) <= 44:
		raise HTTPException(status_code=422, detail="ไม่ได้รับเสียงจากไมโครโฟน")

	sounds_dir = GLOBAL_AUDIO_ENGINE.sounds_dir
	ts = datetime.now().strftime("%H%M%S")
	path = os.path.abspath(os.path.join(sounds_dir, f"temp_live_broadcast_{ts}.wav"))
	with open(path, "wb") as f:
		f.write(audio_bytes)

	GLOBAL_AUDIO_ENGINE.live_broadcast_requested.emit(path)
	return {"status": "success", "bytes": len(audio_bytes)}

@app.websocket("/ws/live-voice")
async def ws_live_voice(websocket: WebSocket):
	"""สตรีมเสียงไมค์สดแบบเรียลไทม์ (walkie-talkie): รับ PCM ต่อเนื่องแล้วส่งให้เครื่องแม่เล่นทันที"""
	await websocket.accept()
	started = False
	try:
		# ข้อความแรกเป็น JSON: {pin, sampleRate} เพื่อตรวจสิทธิ์ (ไม่ส่ง PIN ผ่าน URL)
		first = await websocket.receive_text()
		info = json.loads(first)
		if info.get("pin") != REMOTE_PIN:
			await websocket.send_text(json.dumps({"error": "PIN ไม่ถูกต้อง"}))
			await websocket.close()
			return
		if not ALLOW_REMOTE_VOICE:
			await websocket.send_text(json.dumps({"error": "ผู้ดูแลปิดการพูดผ่านรีโมท"}))
			await websocket.close()
			return

		sample_rate = int(info.get("sampleRate", 48000))
		if GLOBAL_AUDIO_ENGINE:
			GLOBAL_AUDIO_ENGINE.live_stream_started.emit(sample_rate)
			started = True
		await websocket.send_text(json.dumps({"ok": True}))

		# รับก้อนเสียง PCM (binary) ต่อเนื่อง ส่งให้เครื่องแม่เล่นทันที
		while True:
			msg = await websocket.receive()
			if msg.get("type") == "websocket.disconnect":
				break
			data = msg.get("bytes")
			if data and GLOBAL_AUDIO_ENGINE:
				GLOBAL_AUDIO_ENGINE.live_pcm_received.emit(data)
	except WebSocketDisconnect:
		pass
	except Exception as e:
		print(f"[WS] live-voice error: {e}")
	finally:
		# วางสาย: คืนระบบให้ขาน/อ๊อดตามปกติ
		if started and GLOBAL_AUDIO_ENGINE:
			GLOBAL_AUDIO_ENGINE.live_stream_stopped.emit()

def run_server(port=8000):
	"""รันเว็บเซิร์ฟเวอร์ในเธรดเบื้องหลังให้ทนบน Windows
	- ใช้ SelectorEventLoop (ProactorEventLoop รันในเธรดไม่ได้บน Windows)
	- ปิด signal handler (ใช้ได้เฉพาะ main thread)
	- ถ้าล้มเหลว เขียน error ลงไฟล์ server_error.log เพื่อวินิจฉัย
	"""
	import asyncio
	try:
		config_windows_firewall(port)

		# สำคัญบน Windows: ต้องใช้ SelectorEventLoop จึงจะรันในเธรดเบื้องหลังได้
		if sys.platform == "win32":
			asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

		loop = asyncio.new_event_loop()
		asyncio.set_event_loop(loop)

		# log_config=None: ไม่ให้ uvicorn ตั้งค่า logging (กันพังจาก sys.stdout เป็น None ในโหมด windowed)
		config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="error", loop="asyncio", log_config=None)
		server = uvicorn.Server(config)
		server.install_signal_handlers = lambda: None
		loop.run_until_complete(server.serve())
	except Exception:
		err = traceback.format_exc()
		print(f"[Remote] เซิร์ฟเวอร์ล้มเหลว:\n{err}")
		try:
			with open(data_path("server_error.log"), "w", encoding="utf-8") as f:
				f.write(err)
		except Exception:
			pass

def _port_available(port):
	"""พอร์ตว่างจริงไหม: ต้องไม่มีโปรแกรมอื่นรับการเชื่อมต่ออยู่ และต้องจองพอร์ตได้"""
	try:
		with socket.create_connection(("127.0.0.1", port), timeout=0.3):
			return False   # มีโปรแกรมอื่นตอบอยู่แล้ว (เช่น เว็บเซิร์ฟเวอร์ตัวอื่นในเครื่อง)
	except OSError:
		pass
	with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
		try:
			s.bind(("0.0.0.0", port))
			return True
		except OSError:
			return False


def find_free_port(preferred, tries=20):
	for port in range(preferred, preferred + tries):
		if _port_available(port):
			return port
	return preferred


def start_remote_server_async(audio_engine, scheduler_engine, port=8000):
	global GLOBAL_AUDIO_ENGINE, GLOBAL_SCHEDULER_ENGINE
	GLOBAL_AUDIO_ENGINE = audio_engine
	GLOBAL_SCHEDULER_ENGINE = scheduler_engine

	# ถ้าพอร์ตที่ตั้งไว้ถูกโปรแกรมอื่นใช้อยู่ ให้ขยับไปพอร์ตว่างถัดไปเอง (รีโมทจะได้ใช้งานได้เสมอ)
	actual_port = find_free_port(port)
	if actual_port != port:
		print(f"[Remote] พอร์ต {port} ถูกโปรแกรมอื่นใช้อยู่ → เปลี่ยนไปใช้พอร์ต {actual_port}")

	thread = threading.Thread(target=run_server, args=(actual_port,), daemon=True)
	thread.start()

	local_ip = get_local_ip()
	lan_url = f"http://{local_ip}:{actual_port}"

	# ถ้าตั้งโดเมนถาวรไว้ใน config จะใช้เป็นลิงก์สาธารณะ (ฝังไว้ใช้ได้ตลอด)
	domain = (CONFIG.get("remote_domain") or "").strip()

	print(f"[Remote] LAN URL : {lan_url}")
	if domain:
		print(f"[Remote] Domain  : {domain}")
	# คืนค่า: PIN, ลิงก์วง LAN, ลิงก์สาธารณะ (ว่าง = จะได้จาก Cloudflare Tunnel ทีหลัง), พอร์ตที่ใช้จริง
	return REMOTE_PIN, lan_url, domain, actual_port
