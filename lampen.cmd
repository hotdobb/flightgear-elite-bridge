@echo off
rem Ordnet die Autopilot-Lampen des AP-3000 den Bits im Datensatz T zu (Tempo per Enter)
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%~dp0elite_avionik.py" BR000000 lampen
