@echo off
setlocal EnableDelayedExpansion

echo.
echo  ================================================
echo   DataScheduler — Build executable Windows
echo  ================================================
echo.

set "ROOT=%~dp0"
set "VENV=%ROOT%envfs"
set "PYTHON=%VENV%\Scripts\python.exe"
set "PIP=%VENV%\Scripts\pip.exe"
set "PYINSTALLER=%VENV%\Scripts\pyinstaller.exe"

REM ── Vérifications préalables ───────────────────
if not exist "%PYTHON%" (
    echo [ERREUR] Environnement virtuel introuvable : %VENV%
    echo          Creer avec : python -m venv envfs
    echo          Puis       : envfs\Scripts\pip install -r requirements.txt
    pause & exit /b 1
)

if not exist "%ROOT%DataScheduler.spec" (
    echo [ERREUR] Fichier DataScheduler.spec introuvable dans %ROOT%
    pause & exit /b 1
)

REM ── Installation / mise à jour de PyInstaller ──
echo [1/4] Verification de PyInstaller...
"%PYTHON%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo       Installation de pyinstaller==6.11.1...
    "%PIP%" install pyinstaller==6.11.1 --quiet
    if errorlevel 1 (
        echo [ERREUR] Impossible d'installer PyInstaller.
        pause & exit /b 1
    )
)
echo       OK.

REM ── Nettoyage ──────────────────────────────────
echo [2/4] Nettoyage des builds precedents...
if exist "%ROOT%build" rmdir /s /q "%ROOT%build"
if exist "%ROOT%dist"  rmdir /s /q "%ROOT%dist"
echo       OK.

REM ── Compilation ────────────────────────────────
echo [3/4] Compilation (peut prendre 2-5 minutes)...
echo.
"%PYTHON%" -m PyInstaller "%ROOT%DataScheduler.spec" --noconfirm --log-level WARN
if errorlevel 1 (
    echo.
    echo [ERREUR] La compilation a echoue. Relancer avec --log-level DEBUG pour plus de details.
    pause & exit /b 1
)

REM ── Résultat ───────────────────────────────────
echo.
echo [4/4] Verification du resultat...
set "EXE=%ROOT%dist\DataScheduler\DataScheduler.exe"
if exist "%EXE%" (
    echo.
    echo  ================================================
    echo   BUILD REUSSI^^!
    echo  ================================================
    echo.
    echo   Executable  : dist\DataScheduler\DataScheduler.exe
    echo   Dossier     : dist\DataScheduler\
    echo.
    echo   Pour partager : zipper le dossier dist\DataScheduler\
    echo   Clic droit -^> Envoyer vers -^> Dossier compresse
    echo.
) else (
    echo [ERREUR] L'executable n'a pas ete genere.
    echo          Verifier les erreurs ci-dessus.
)

pause
endlocal
