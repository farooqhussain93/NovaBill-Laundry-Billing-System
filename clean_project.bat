@echo off
setlocal
cd /d "%~dp0"

echo Cleaning generated development files...

if exist venv rmdir /s /q venv
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
del /s /q *.pyc >nul 2>nul

if exist data\laundry_invoice.db del /q data\laundry_invoice.db
if exist data\laundry_invoice.db-wal del /q data\laundry_invoice.db-wal
if exist data\laundry_invoice.db-shm del /q data\laundry_invoice.db-shm

echo Done.
pause
