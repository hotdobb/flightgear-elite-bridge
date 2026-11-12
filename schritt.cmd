@echo off
rem Schritt-Modus fuer die AP-3000-Anzeigen. Weitere Optionen werden durchgereicht, z.B.: schritt --ab I
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%~dp0elite_avionik.py" BR000000 schritt %*
