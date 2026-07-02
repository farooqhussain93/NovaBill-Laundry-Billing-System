@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo   Building NovaBill Laundry EXE
echo ==========================================
echo.

if not exist venv (
    py -m venv venv
)

call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller==6.11.1

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name "NovaBill Laundry" ^
  --icon "assets\app_icon.ico" ^
  --add-data "assets;assets" ^
  --add-data "laundry_invoice_app\web;laundry_invoice_app\web" ^
  --collect-submodules webview ^
  --collect-submodules clr_loader ^
  --collect-submodules pythonnet ^
  --collect-all reportlab ^
  main.py

if errorlevel 1 (
    echo.
    echo Build failed. Please check the error above.
    pause
    exit /b 1
)

echo.
echo Build completed successfully.
echo.
echo EXE location:
echo dist\NovaBill Laundry\NovaBill Laundry.exe
echo.
echo To share the app, zip this complete folder:
echo dist\NovaBill Laundry
echo.
pause
