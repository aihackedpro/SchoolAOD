import os
import json
import socket
import threading
from datetime import datetime
from fastapi import FastAPI, HTTPException, Header, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response, JSONResponse
import uvicorn
from win_system import config_windows_firewall
from config_manager import load_config
from paths import resource_path

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
				<small class="text-muted">Version 1.0 &copy; 2026-2027 All Rights Reserved</small>
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
	return HTML_TEMPLATE

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
	config_windows_firewall(port)
	uvicorn.run(app, host="0.0.0.0", port=port, log_level="error")

def start_remote_server_async(audio_engine, scheduler_engine, port=8000):
	global GLOBAL_AUDIO_ENGINE, GLOBAL_SCHEDULER_ENGINE
	GLOBAL_AUDIO_ENGINE = audio_engine
	GLOBAL_SCHEDULER_ENGINE = scheduler_engine

	thread = threading.Thread(target=run_server, args=(port,), daemon=True)
	thread.start()

	local_ip = get_local_ip()
	lan_url = f"http://{local_ip}:{port}"

	# ถ้าตั้งโดเมนถาวรไว้ใน config จะใช้โดเมนนั้นเป็นลิงก์หลัก (ฝังไว้ใช้ได้ตลอด)
	domain = (CONFIG.get("remote_domain") or "").strip()
	display_url = domain if domain else lan_url

	print(f"[Remote] LAN URL : {lan_url}")
	if domain:
		print(f"[Remote] Domain  : {domain}")
	return REMOTE_PIN, display_url
