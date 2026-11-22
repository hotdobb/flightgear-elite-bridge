@echo off
rem Schritt-Modus fuer die AP-3000-Anzeigen. Weitere Optionen werden durchgereicht, z.B.: schritt --ab I
py -3 "%~dp0elite_avionik.py" BR000000 schritt %*
