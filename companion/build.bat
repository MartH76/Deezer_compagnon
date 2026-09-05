@echo off
setlocal
cd /d "%~dp0"

echo === Installation des dependances (build) ===
python -m pip install --upgrade pip
python -m pip install pyinstaller winsdk pycaw comtypes pyserial pillow psutil pystray || goto :err

echo.
echo === Compilation de l'executable ===
python -m PyInstaller --noconfirm --clean --onefile --noconsole ^
  --name DeezerCompanion ^
  --icon app.ico ^
  --collect-all winsdk ^
  --collect-submodules comtypes ^
  --collect-submodules pycaw ^
  --hidden-import pystray._win32 ^
  deezer_companion.py || goto :err

echo.
echo ============================================================
echo   OK : executable genere dans  dist\DeezerCompanion.exe
echo   A distribuer tel quel (aucun Python requis chez l'utilisateur).
echo ============================================================
pause
exit /b 0

:err
echo.
echo *** Echec du build. Verifie que "python" fonctionne dans ce terminal.
echo *** (sinon remplace "python" par "python3.10" dans build.bat)
pause
exit /b 1
