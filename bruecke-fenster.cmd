@echo off
rem Elite-Bruecke mit Bedienfenster (ohne schwarzes Konsolenfenster)
cd /d "%~dp0"
start "" "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe" "%~dp0elite_gui.py"
