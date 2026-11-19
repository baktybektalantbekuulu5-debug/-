@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================================
echo   BeamNG YouTube Factory - установка
echo ============================================================

where py >nul 2>nul
if %errorlevel%==0 ( set PY=py -3 ) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo [ОШИБКА] Python не найден. Установите Python 3.11+ с https://www.python.org/downloads/
    echo          При установке поставьте галочку "Add python.exe to PATH".
    pause & exit /b 1
  )
  set PY=python
)
%PY% -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)"
if errorlevel 1 (
  echo [ОШИБКА] Нужен Python 3.10 или новее.
  pause & exit /b 1
)

echo [1/4] Создаю виртуальное окружение .venv ...
if not exist .venv ( %PY% -m venv .venv )
if errorlevel 1 ( echo [ОШИБКА] Не удалось создать .venv & pause & exit /b 1 )

echo [2/4] Устанавливаю зависимости ...
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 ( echo [ОШИБКА] Не удалось установить зависимости & pause & exit /b 1 )

echo [3/4] Проверяю FFmpeg ...
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo FFmpeg не найден. Пробую установить через winget ...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo [ВНИМАНИЕ] winget недоступен. Скачайте FFmpeg: https://www.gyan.dev/ffmpeg/builds/ и добавьте папку bin в PATH
    echo            либо укажите путь к ffmpeg.exe в Настройках программы.
  ) else (
    winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    echo Если FFmpeg установился, перезапустите это окно/программу, чтобы обновился PATH.
  )
)

echo [4/4] Проверка системы ...
call .venv\Scripts\python.exe main.py --check

echo.
echo Установка завершена. Запуск: start.bat
echo Не забудьте: OBS Studio (https://obsproject.com) и BeamNG.drive должны быть установлены.
echo Подробности: README.md
pause
