@echo off
rem Testet die DME-Anzeige (Reihe 4) des AP-3000 Schritt fuer Schritt
cd /d "%~dp0"
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%~dp0elite_avionik.py" BR000000 dme
