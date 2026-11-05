@echo off
rem Copie la base du projet dans le serveur PostgreSQL deja installe sur ce poste (port 5432).
rem Double-cliquer sur ce fichier : le mot de passe du serveur est demande a l'ecran, sans etre affiche.
rem Options possibles depuis un terminal : --port 5433, --compte moi, --remplacer
chcp 65001 >nul
python "%~dp0scripts\12_copier_base.py" %*
pause
