@echo off
REM ================================================================
REM  NSSM - Instalar servicio Formularios PVSA
REM  Ejecutar como Administrador
REM ================================================================

SET NSSM=C:\nssm-2.24\win64\nssm.exe
SET PROJECT_DIR=C:\www\ProyectosDjango\formularios_pvsa
SET VENV_PYTHON=C:\www\EntornosProyectos\Scripts\python.exe
SET LOG_DIR=%PROJECT_DIR%\logs

mkdir "%LOG_DIR%" 2>nul

%NSSM% install FormulariosPVSA "%VENV_PYTHON%"
%NSSM% set FormulariosPVSA AppParameters "%PROJECT_DIR%\script.py"
%NSSM% set FormulariosPVSA AppDirectory "%PROJECT_DIR%"
%NSSM% set FormulariosPVSA DisplayName "Formularios PVSA"
%NSSM% set FormulariosPVSA Description "Formularios PVSA (Django)"
%NSSM% set FormulariosPVSA Start SERVICE_AUTO_START
%NSSM% set FormulariosPVSA AppStdout "%LOG_DIR%\stdout.log"
%NSSM% set FormulariosPVSA AppStderr "%LOG_DIR%\stderr.log"
%NSSM% set FormulariosPVSA AppRotateFiles 1
%NSSM% set FormulariosPVSA AppRotateBytes 5242880

echo.
echo Iniciando servicio...
%NSSM% start FormulariosPVSA
%NSSM% status FormulariosPVSA

echo.
echo Servicio instalado. Logs en: %LOG_DIR%
pause
