@echo off
REM ================================================================
REM  %NSSM% - Instalar servicios Stock API en servidor PVSA
REM  Ejecutar como Administrador
REM ================================================================
REM
REM  Estructura del servidor:
REM    C:\www\ProyectosDjango\stock\          (código)
REM    C:\www\EntornosProyectos\stock\.venv\  (virtualenv)
REM    C:\www\ProyectosDjango\stock\logs\     (logs)
REM
REM  Redis: DB 8 (broker), DB 9 (results)
REM ================================================================

SET NSSM=C:\nssm-2.24\win64\nssm.exe
SET PROJECT_DIR=C:\www\ProyectosDjango\stock
SET VENV_PYTHON=C:\www\EntornosProyectos\stock\.venv\Scripts\python.exe
SET VENV_CELERY=C:\www\EntornosProyectos\stock\.venv\Scripts\celery.exe
SET LOG_DIR=%PROJECT_DIR%\logs

REM Crear carpeta de logs
mkdir "%LOG_DIR%" 2>nul

REM ================================================================
REM  1) Stock API (Waitress en puerto 777)
REM ================================================================
%NSSM% install StockAPI "%VENV_PYTHON%"
%NSSM% set StockAPI AppParameters "-m waitress --host=0.0.0.0 --port=777 --threads=4 stock.wsgi:application"
%NSSM% set StockAPI AppDirectory "%PROJECT_DIR%"
%NSSM% set StockAPI AppEnvironmentExtra "DJANGO_SETTINGS_MODULE=stock.settings" "CELERY_BROKER_URL=redis://127.0.0.1:6379/8" "CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/9"
%NSSM% set StockAPI DisplayName "Stock API"
%NSSM% set StockAPI Description "API Stock y Camiones (Django + Waitress :777)"
%NSSM% set StockAPI Start SERVICE_AUTO_START
%NSSM% set StockAPI AppStdout "%LOG_DIR%\api_stdout.log"
%NSSM% set StockAPI AppStderr "%LOG_DIR%\api_stderr.log"
%NSSM% set StockAPI AppRotateFiles 1
%NSSM% set StockAPI AppRotateBytes 5242880

REM ================================================================
REM  2) Stock Celery Worker
REM ================================================================
%NSSM% install StockCeleryWorker "%VENV_CELERY%"
%NSSM% set StockCeleryWorker AppParameters "-A stock worker --loglevel=info --pool=solo -n stock-worker@%%h"
%NSSM% set StockCeleryWorker AppDirectory "%PROJECT_DIR%"
%NSSM% set StockCeleryWorker AppEnvironmentExtra "DJANGO_SETTINGS_MODULE=stock.settings" "CELERY_BROKER_URL=redis://127.0.0.1:6379/8" "CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/9"
%NSSM% set StockCeleryWorker DisplayName "Stock Celery Worker"
%NSSM% set StockCeleryWorker Description "Worker Celery para Stock (Redis DB 8)"
%NSSM% set StockCeleryWorker Start SERVICE_AUTO_START
%NSSM% set StockCeleryWorker AppStdout "%LOG_DIR%\celery_worker_stdout.log"
%NSSM% set StockCeleryWorker AppStderr "%LOG_DIR%\celery_worker_stderr.log"
%NSSM% set StockCeleryWorker AppRotateFiles 1
%NSSM% set StockCeleryWorker AppRotateBytes 5242880

REM ================================================================
REM  3) Stock Celery Beat
REM ================================================================
%NSSM% install StockCeleryBeat "%VENV_CELERY%"
%NSSM% set StockCeleryBeat AppParameters "-A stock beat --loglevel=info"
%NSSM% set StockCeleryBeat AppDirectory "%PROJECT_DIR%"
%NSSM% set StockCeleryBeat AppEnvironmentExtra "DJANGO_SETTINGS_MODULE=stock.settings" "CELERY_BROKER_URL=redis://127.0.0.1:6379/8" "CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/9"
%NSSM% set StockCeleryBeat DisplayName "Stock Celery Beat"
%NSSM% set StockCeleryBeat Description "Scheduler Celery Beat para Stock"
%NSSM% set StockCeleryBeat Start SERVICE_AUTO_START
%NSSM% set StockCeleryBeat AppStdout "%LOG_DIR%\celery_beat_stdout.log"
%NSSM% set StockCeleryBeat AppStderr "%LOG_DIR%\celery_beat_stderr.log"
%NSSM% set StockCeleryBeat AppRotateFiles 1
%NSSM% set StockCeleryBeat AppRotateBytes 5242880

REM ================================================================
REM  Iniciar los 3 servicios
REM ================================================================
echo.
echo Iniciando servicios...
%NSSM% start StockAPI
%NSSM% start StockCeleryWorker
%NSSM% start StockCeleryBeat

echo.
echo Verificando estado...
%NSSM% status StockAPI
%NSSM% status StockCeleryWorker
%NSSM% status StockCeleryBeat

echo.
echo ========================================
echo  Servicios instalados e iniciados.
echo  Logs en: %LOG_DIR%
echo  API en:  http://localhost:777/api/
echo  Admin:   http://localhost:777/admin/
echo ========================================
pause
