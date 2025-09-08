@echo off
setlocal enabledelayedexpansion

echo.

echo        'cccc:cc::c::::ccccccccc;.      
echo      ,dd:'...................';ox:     
echo     'xl.                  .'.   :k;    
echo     ;x'              'olcldOl   .dl    
echo     ;x'              .xd,..cx:. .dl    
echo     ;x'              :kl.  ;x0l..dl    
echo     ;x'             .cdclloxc.  .dl    
echo     ;x'                 .:d:    .dl    
echo     ;x'       ,l:.              .dl    
echo     ;x'      ,Oxxx'             .dl    
echo     ;x'     .dx..lkdl::::,.     .dl    
echo     ;x'.;clldo'   '::c:lO0;     .dl    
echo     ;x,:KOc'.         'ox;      .dl    
echo     ;x' ,ldo;        .kx.       .dl    
echo     ;x'   .oO,       .dx.       .dl    
echo     ;x'    cO,.;ooool;l0o       .dl    
echo     ,k;    l0xdo;..';lod;       .xc    
echo     .ox;.  .;:.                'dd.    
echo       ;oolc:::::::::::::::::ccoo:.     
echo         .,;;;;;;;:;;;;;;;;;;;;.        
echo.
echo Welcome to EnglishAI.
echo.

set "CONFIG_FILE=config.ini"
set "DEFAULT_DECK=EnglishAI"
set "DEFAULT_MODEL=EnglishAI"

:: Check if Python is installed
where python >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Attempting to install Python using winget...
    winget install Python.Python.3.11
    if errorlevel 1 (
        echo Failed to install Python. Please install Python manually from python.org
        pause
        exit /b 1
    )
    echo Python installed successfully. Please restart this script.
    pause
    exit /b 0
)

:run_script
if not exist "%CONFIG_FILE%" (
    echo Configuration not found. Please enter the following details:
    echo Press Enter to use default values where applicable.
    
    set /p "DECK=Enter deck name [%DEFAULT_DECK%]: "
    set /p "MODEL=Enter model name [%DEFAULT_MODEL%]: "
    :api
    set /p "API_KEY=Enter API Key (required): "
    
    if "!DECK!"=="" set "DECK=%DEFAULT_DECK%"
    if "!MODEL!"=="" set "MODEL=%DEFAULT_MODEL%"
    if "!API_KEY!"=="" (
        echo API Key is required.
        goto api
    )
    
    (
        echo DECK=!DECK!
        echo MODEL=!MODEL!
        echo API_KEY=!API_KEY!
    ) > "%CONFIG_FILE%"
) else (
    echo Configuration found. Loading settings...
    echo.
    for /f "tokens=1,* delims==" %%a in (%CONFIG_FILE%) do (
        set "%%a=%%b"
    )
)

python learnEnglish.py words.csv --deck "%DECK%" --model "%MODEL%" --api-key "%API_KEY%"
if errorlevel 1 (
    echo API Key appears to be invalid. Please enter a new API Key:
    set /p "API_KEY=Enter API Key (required): "
    if "!API_KEY!"=="" (
        echo API Key is required.
        pause
        exit /b 1
    )
    (
        echo DECK=!DECK!
        echo MODEL=!MODEL!
        echo API_KEY=!API_KEY!
    ) > "%CONFIG_FILE%"
    goto run_script
) else (
    echo Script executed successfully.
    echo You may close this window now.
    pause
)