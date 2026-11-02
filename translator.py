"""แปลข้อความประกาศระหว่าง ไทย / อังกฤษ / จีน

- ลองผู้ให้บริการหลายเจ้าตามลำดับ ถ้าเจ้าแรกล่มหรือถูกจำกัดจำนวนครั้ง จะสลับไปเจ้าถัดไปเอง
- คำแปลทุกรายการถูกจำไว้ในเครื่อง (translations.json) → ข้อความเดิมแปลได้แม้ไม่มีอินเทอร์เน็ต
"""
import json
import os
import re
import threading
import urllib.parse
import urllib.request
from net import urlopen
from paths import data_path

# รหัสภาษาในระบบ → รหัสของบริการแปล
_TARGET = {"th": "th", "en": "en", "zh": "zh-CN"}
_UA = {"User-Agent": "Mozilla/5.0 (SchoolAOD)"}
_THAI_RE = re.compile(r"[฀-๿]")
_CJK_RE = re.compile(r"[一-鿿]")

_CACHE_FILE = data_path("translations.json")
_cache = None
_cache_lock = threading.Lock()


def detect_lang(text: str) -> str:
	"""เดาภาษาของข้อความ: มีอักษรไทย → th, มีอักษรจีน → zh, นอกนั้น → en"""
	if _THAI_RE.search(text or ""):
		return "th"
	if _CJK_RE.search(text or ""):
		return "zh"
	return "en"


# ---------------------------------------------------------------- คำแปลที่จำไว้
def _load_cache():
	global _cache
	if _cache is None:
		try:
			with open(_CACHE_FILE, "r", encoding="utf-8") as f:
				_cache = json.load(f)
		except Exception:
			_cache = {}
	return _cache


def _cache_key(text, target):
	return f"{target}␟{text}"


def _cache_get(text, target):
	with _cache_lock:
		return _load_cache().get(_cache_key(text, target), "")


def _cache_put(text, target, result):
	with _cache_lock:
		cache = _load_cache()
		cache[_cache_key(text, target)] = result
		try:
			tmp = _CACHE_FILE + ".tmp"
			with open(tmp, "w", encoding="utf-8") as f:
				json.dump(cache, f, ensure_ascii=False, indent=0)
			os.replace(tmp, _CACHE_FILE)
		except Exception as e:
			print(f"[Translator] บันทึกคำแปลไม่สำเร็จ: {e}")


# ---------------------------------------------------------------- ผู้ให้บริการแปล
def _get_json(url, timeout=10):
	with urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout) as resp:
		return json.loads(resp.read().decode("utf-8"))


def _google_clients5(text, source, target):
	url = "https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=%s&tl=%s&q=%s" % (
		source, target, urllib.parse.quote(text))
	data = _get_json(url)
	out = []
	for seg in data if isinstance(data, list) else []:
		out.append(seg[0] if isinstance(seg, list) else str(seg))
	return "".join(out)


def _google_gtx(text, source, target):
	url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=%s&tl=%s&dt=t&q=%s" % (
		source, target, urllib.parse.quote(text))
	data = _get_json(url)
	return "".join(seg[0] for seg in data[0] if seg and seg[0])


def _mymemory(text, source, target):
	url = "https://api.mymemory.translated.net/get?q=%s&langpair=%s|%s" % (
		urllib.parse.quote(text), source, target)
	data = _get_json(url)
	result = (data.get("responseData") or {}).get("translatedText") or ""
	# MyMemory ส่งข้อความเตือนกลับมาแทนคำแปลเมื่อเกินโควตา
	if "MYMEMORY WARNING" in result.upper():
		return ""
	return result


_PROVIDERS = [_google_clients5, _google_gtx, _mymemory]


def translate(text: str, target_lang: str, source_lang: str = "", allow_network: bool = True) -> str:
	"""แปลข้อความเป็นภาษาเป้าหมาย ('th' / 'en' / 'zh') คืนค่า "" ถ้าแปลไม่สำเร็จ
	allow_network=False → ใช้เฉพาะคำแปลที่เคยจำไว้ (เร็ว ไม่รอเครือข่าย)
	"""
	text = (text or "").strip()
	if not text or target_lang not in _TARGET:
		return ""
	source_lang = source_lang or detect_lang(text)
	if source_lang == target_lang:
		return text

	cached = _cache_get(text, target_lang)
	if cached or not allow_network:
		return cached

	src, tgt = _TARGET.get(source_lang, "auto"), _TARGET[target_lang]
	for provider in _PROVIDERS:
		try:
			result = provider(text, src, tgt).strip()
			if result:
				_cache_put(text, target_lang, result)
				return result
		except Exception as e:
			print(f"[Translator] {provider.__name__} ล้มเหลว: {e}")
	return ""
