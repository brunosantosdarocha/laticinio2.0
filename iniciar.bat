@echo off
REM ============================================================
REM  iniciar.bat - clique duas vezes para ligar o sistema.
REM  Procura o Python: .venv -> py -3 -> python (ignora o atalho
REM  falso da Microsoft Store). Sem Python, abre o python.org.
REM ============================================================
chcp 65001 >NUL
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" iniciar.py %*
    goto fim
)

where py >NUL 2>NUL
if %errorlevel%==0 (
    py -3 iniciar.py %*
    goto fim
)

for /f "delims=" %%P in ('where python 2^>NUL') do (
    echo %%P | find /i "WindowsApps" >NUL
    if errorlevel 1 (
        "%%P" iniciar.py %*
        goto fim
    )
)

echo.
echo Python nao foi encontrado neste computador.
echo Instale o Python 3.12 (marque "Add python.exe to PATH") e rode de novo.
start "" https://www.python.org/downloads/
pause
exit /b 1

:fim
pause
