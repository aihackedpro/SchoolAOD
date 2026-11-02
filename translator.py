"""แปลข้อความประกาศ ไทย → อังกฤษ / จีน (ใช้อินเทอร์เน็ต)
ลองผู้ให้บริการหลายเจ้าตามลำดับ ถ้าเจ้าแรกล่มหรือถูกจำกัดจำนวนครั้ง จะสลับไปเจ้าถัดไปเอง
ผลการแปลถูกบันทึกไว้กับตารางเวลา จึงใช้งานแบบออฟไลน์ต่อได้
"""
import json
import re
import urllib.parse
import urllib.request

# รหัสภาษาในระบบ → รหัสของบริการแปล
_TARGET = {"th": "th", "en": "en", "zh": "zh-CN"}
_UA = {"User-Agent": "Mozilla/5.0 (SchoolAOD)"}
_THAI_RE = re.compile(r"[฀-๿]")
_CJK_RE = re.compile(r"[一-鿿]")


def detect_lang(text: str) -> str:
	if _THAI_RE.search(text or ""):
		return "th"
	if _CJK_RE.search(text or ""):
		return "zh"
	return "en"


def _get_json(url, timeout=10):
	req = urllib.request.Request(url, headers=_UA)
	with urllib.request.urlopen(req, timeout=timeout) as resp:
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


def translate(text: str, target_lang: str, source_lang: str = "") -> str:
	"""แปลข้อความเป็นภาษาเป้าหมาย ('en' / 'zh' / 'th') คืนค่า "" ถ้าแปลไม่สำเร็จ"""
	text = (text or "").strip()
	if not text or target_lang not in _TARGET:
		return ""
	source_lang = source_lang or detect_lang(text)
	if source_lang == target_lang:
		return text

	src, tgt = _TARGET.get(source_lang, "auto"), _TARGET[target_lang]
	for provider in _PROVIDERS:
		try:
			result = provider(text, src, tgt).strip()
			if result:
				return result
		except Exception as e:
			print(f"[Translator] {provider.__name__} ล้มเหลว: {e}")
	return ""
