@echo off
REM ============================================================
REM sincronizar.bat - Sandbox NT8 <-> Repo CAOS
REM ============================================================
REM
REM Sincroniza arquivos *.cs entre:
REM   REPO    = e:\CAOS\04_CODIGO\ninjascript\
REM   SANDBOX = %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\caos\
REM
REM Cobertura: freio humano #1 escopado em 25/mai/2026 (steering
REM protocolo-debate-no-chat.md). Toda escrita na sandbox exige
REM cópia espelho no repo - este script existe para garantir isso.
REM
REM Modos:
REM   sincronizar.bat caos-para-repo   Sandbox -> Repo (puxar do NT8)
REM   sincronizar.bat repo-para-caos   Repo -> Sandbox (empurrar pro NT8)
REM   sincronizar.bat verificar        Compara hashes; nao copia
REM
REM Filtros:
REM   - Apenas *.cs sao sincronizados.
REM   - README*.md, *.bat e reference_hydra\ ficam de fora.
REM
REM Idioma: pt-BR. Plataforma: Windows + cmd.
REM ============================================================

setlocal enabledelayedexpansion

set "REPO=e:\CAOS\04_CODIGO\ninjascript"
set "SANDBOX=%USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Strategies\caos"

if "%~1"=="" goto :uso
if /I "%~1"=="caos-para-repo" goto :sandbox_para_repo
if /I "%~1"=="repo-para-caos" goto :repo_para_sandbox
if /I "%~1"=="verificar" goto :verificar
goto :uso

:uso
echo.
echo Uso:
echo   sincronizar.bat caos-para-repo    Sandbox NT8 -^> Repo CAOS
echo   sincronizar.bat repo-para-caos    Repo CAOS -^> Sandbox NT8
echo   sincronizar.bat verificar         Compara, nao copia
echo.
echo Caminhos:
echo   REPO    = %REPO%
echo   SANDBOX = %SANDBOX%
echo.
exit /b 2

:sandbox_para_repo
echo.
echo === Sincronizando Sandbox NT8 -^> Repo CAOS ===
echo Origem:  %SANDBOX%
echo Destino: %REPO%
echo.
if not exist "%SANDBOX%\" (
    echo ERRO: sandbox nao existe em %SANDBOX%
    exit /b 1
)
set "_count=0"
for %%F in ("%SANDBOX%\*.cs") do (
    copy /Y "%%F" "%REPO%\%%~nxF" >nul
    if errorlevel 1 (
        echo   FALHA: %%~nxF
    ) else (
        echo   OK:    %%~nxF
        set /a _count+=1
    )
)
echo.
echo !_count! arquivo(s) .cs sincronizado(s) Sandbox -^> Repo.
echo Lembrete: rode 'git add' + 'git commit' no repo para versionar.
exit /b 0

:repo_para_sandbox
echo.
echo === Sincronizando Repo CAOS -^> Sandbox NT8 ===
echo Origem:  %REPO%
echo Destino: %SANDBOX%
echo.
if not exist "%REPO%\" (
    echo ERRO: repo nao existe em %REPO%
    exit /b 1
)
if not exist "%SANDBOX%\" (
    echo Criando sandbox em %SANDBOX%
    mkdir "%SANDBOX%"
    if errorlevel 1 (
        echo ERRO: nao foi possivel criar sandbox.
        exit /b 1
    )
)
set "_count=0"
for %%F in ("%REPO%\*.cs") do (
    copy /Y "%%F" "%SANDBOX%\%%~nxF" >nul
    if errorlevel 1 (
        echo   FALHA: %%~nxF
    ) else (
        echo   OK:    %%~nxF
        set /a _count+=1
    )
)
echo.
echo !_count! arquivo(s) .cs sincronizado(s) Repo -^> Sandbox.
echo Lembrete: abra NT8 e pressione F5 em Edit NinjaScript para recompilar.
exit /b 0

:verificar
echo.
echo === Verificando paridade Sandbox ^<-^> Repo ===
echo REPO    = %REPO%
echo SANDBOX = %SANDBOX%
echo.
if not exist "%SANDBOX%\" (
    echo ERRO: sandbox nao existe em %SANDBOX%
    exit /b 1
)
set "_div=0"
set "_so_repo=0"
set "_so_sandbox=0"
set "_iguais=0"

REM Repo -> Sandbox: arquivos no repo, conferir contra sandbox
for %%F in ("%REPO%\*.cs") do (
    set "_nome=%%~nxF"
    if exist "%SANDBOX%\!_nome!" (
        fc /B "%%F" "%SANDBOX%\!_nome!" >nul 2>&1
        if errorlevel 1 (
            echo   DIVERGE:  !_nome!
            set /a _div+=1
        ) else (
            set /a _iguais+=1
        )
    ) else (
        echo   SO_REPO:  !_nome!
        set /a _so_repo+=1
    )
)

REM Sandbox -> Repo: arquivos so na sandbox
for %%F in ("%SANDBOX%\*.cs") do (
    set "_nome=%%~nxF"
    if not exist "%REPO%\!_nome!" (
        echo   SO_SBOX:  !_nome!
        set /a _so_sandbox+=1
    )
)

echo.
echo Resumo:
echo   iguais       : !_iguais!
echo   divergem     : !_div!
echo   so no repo   : !_so_repo!
echo   so na sandbox: !_so_sandbox!
echo.
if !_div! GTR 0 (
    echo ATENCAO: ha divergencias. Use 'caos-para-repo' ou 'repo-para-caos'.
    exit /b 1
)
if !_so_repo! GTR 0 (
    echo Repo tem arquivos que faltam na sandbox. Use 'repo-para-caos'.
    exit /b 1
)
if !_so_sandbox! GTR 0 (
    echo Sandbox tem arquivos novos que faltam no repo. Use 'caos-para-repo'.
    exit /b 1
)
echo Tudo em paridade.
exit /b 0
