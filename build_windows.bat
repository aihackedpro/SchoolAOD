@echo off
REM ===== สคริปต์ build โปรแกรมเป็น .exe บนเครื่อง Windows =====
REM ต้องมี Python 3.10-3.12 ติดตั้งก่อน (Windows 10/11 เท่านั้น)

echo [1/4] สร้าง virtual environment...
python -m venv venv
call venv\Scripts\activate

echo [2/4] ติดตั้ง dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

echo [3/4] ดาวน์โหลด cloudflared.exe (ถ้ายังไม่มี)...
if not exist cloudflared.exe (
	curl -L -o cloudflared.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
)

echo [4/4] Build...
pyinstaller SchoolAOD.spec --noconfirm

echo.
echo ========================================================
echo  เสร็จแล้ว! ไฟล์อยู่ที่  dist\SchoolAOD.exe
echo  ให้ก็อป dist\SchoolAOD.exe กับ cloudflared.exe ไว้โฟลเดอร์เดียวกันเวลานำไปใช้
echo ========================================================
pause
