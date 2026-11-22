@echo off
rem Elite-Bruecke mit Bedienfenster (ohne schwarzes Konsolenfenster)
cd /d "%~dp0"
start "" pyw -3 "%~dp0elite_gui.py"
