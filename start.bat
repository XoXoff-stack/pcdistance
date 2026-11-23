@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 goto failed
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto failed
python -m pip install -r requirements.txt
if errorlevel 1 goto failed
python app.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Une erreur est survenue pendant l'installation ou le lancement.
echo Verifie que Python 3 est installe et que la connexion Internet fonctionne.
pause
exit /b 1
