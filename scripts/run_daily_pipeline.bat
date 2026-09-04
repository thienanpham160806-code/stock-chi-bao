@echo off
REM Wrapper chay run_pipeline.py tu dong hang ngay qua Windows Task Scheduler.
REM Duong dan python duoc ghi tuyet doi de khong phu thuoc PATH cua Task
REM Scheduler (thuong khac PATH cua shell dang dung).

set "PROJECT_DIR=%~dp0.."
set "PYTHON_EXE=C:\Users\Dell\AppData\Local\Programs\Python\Python312\python.exe"
set "LOG_FILE=%PROJECT_DIR%\data\processed\pipeline_scheduled.log"

cd /d "%PROJECT_DIR%"

echo. >> "%LOG_FILE%"
echo ===== %DATE% %TIME% ===== >> "%LOG_FILE%"
"%PYTHON_EXE%" run_pipeline.py >> "%LOG_FILE%" 2>&1

exit /b %ERRORLEVEL%
