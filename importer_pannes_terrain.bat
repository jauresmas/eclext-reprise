@echo off
chcp 65001 >nul
rem Glisser sur ce fichier le dossier ou le .zip renvoye par le telephone, ou double-cliquer.
python "%~dp0scripts\13_importer_terrain.py" %*
pause
