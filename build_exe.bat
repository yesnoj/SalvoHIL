@echo off
echo ================================
echo   Creazione EXE con PyInstaller
echo ================================
echo.

python -m PyInstaller ^
--onefile ^
--windowed ^
--add-data "alarm_can_sender.py;." ^
--hidden-import "can.interfaces.vector" ^
--hidden-import "can.interfaces.socketcan" ^
--hidden-import "can.interfaces.pcan" ^
--hidden-import "can.interfaces.usb2can" ^
--hidden-import "can.interfaces.ixxat" ^
--hidden-import "can.interfaces.nican" ^
--hidden-import "can.interfaces.slcan" ^
--hidden-import "can.interfaces.kvaser" ^
--hidden-import "can" ^
webcam_capture_server.py

echo.
echo ================================
echo   Build completata
echo ================================
pause