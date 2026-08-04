import os
import wave
import math
import struct

try:
	from gtts import gTTS
	HAS_GTTS = True
except ImportError:
	HAS_GTTS = False

def generate_dingdong_wav(filepath):
	sample_rate = 44100
	duration = 1.2
	n_samples = int(sample_rate * duration)
	
	with wave.open(filepath, 'w') as wave_file:
		wave_file.setnchannels(1)
		wave_file.setsampwidth(2)
		wave_file.setframerate(sample_rate)
		
		for i in range(n_samples):
			t = i / sample_rate
			if t < 0.5:
				freq = 523.25
				decay = math.exp(-t * 5)
			else:
				freq = 659.25
				decay = math.exp(-(t - 0.5) * 4)
				
			sample = math.sin(2 * math.pi * freq * t) * decay * 32767 * 0.7
			data = struct.pack('<h', int(sample))
			wave_file.writeframes(data)

def generate_all_sounds():
	os.makedirs("sounds", exist_ok=True)
	print("🔔 กำลังสร้างไฟล์เสียงตัวอย่างเข้าสู่โฟลเดอร์ sounds/...")
	
	chime_path = os.path.join("sounds", "chime.wav")
	generate_dingdong_wav(chime_path)
	print("  [OK] Created chime.wav")

	chime_mp3_path = os.path.join("sounds", "chime.mp3")
	generate_dingdong_wav(chime_mp3_path)
	print("  [OK] Created chime.mp3")

	if HAS_GTTS:
		voice_items = {
			"voice_now_is.mp3": "ขณะนี้เวลา",
			"voice_oclock.mp3": "ตรง",
			"voice_8.mp3": "แปดนาฬิกา",
			"voice_12.mp3": "สิบสองนาฬิกา",
			"voice_16.mp3": "สิบหกนาฬิกา",
			"national_anthem.mp3": "เพลงชาติไทย"
		}
		for filename, text in voice_items.items():
			try:
				tts = gTTS(text=text, lang='th')
				tts.save(os.path.join("sounds", filename))
				print(f"  [OK] Generated {filename} ({text})")
			except Exception as e:
				print(f"  [Error] Could not generate {filename}: {e}")
	else:
		print("  [Notice] ติดตั้ง gTTS เพิ่มเติมได้ด้วยคำสั่ง: pip install gTTS")

if __name__ == "__main__":
	generate_all_sounds()
