@echo off
rem Testet die Fahrwerkslampen am Pro Panel II Schritt fuer Schritt
cd /d "%~dp0"
py -3 "%~dp0elite_avionik.py" BR200000 pro
