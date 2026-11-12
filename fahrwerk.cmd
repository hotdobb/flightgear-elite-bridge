@echo off
rem Testet die Fahrwerkslampen am Pro Panel II Schritt fuer Schritt
cd /d "%~dp0"
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%~dp0elite_avionik.py" BR200000 pro
