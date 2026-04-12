@echo off
setlocal

:: Define the name of the local environment folder
set VENV_DIR=.venv
set SCRIPT_NAME=batch-anki.py

:: Check if the virtual environment already exists
IF NOT EXIST "%VENV_DIR%\Scripts\activate.bat" (
    echo [Bootstrapper] No local environment found. Creating one now...
    python -m venv %VENV_DIR%
    
    echo [Bootstrapper] Installing required dependencies... ^(this might take a while depending on your internet connection^)
    call "%VENV_DIR%\Scripts\activate.bat"
    python -m pip install --upgrade pip -q
    pip install requests google-genai -q
) ELSE (
    :: If it exists, just activate it silently
    call "%VENV_DIR%\Scripts\activate.bat"
    pip show requests >nul 2>&1 || pip install requests -q
    pip show google-genai >nul 2>&1 || pip install google-genai -q
)

:run_script
echo.
echo --------------------------------------------------
echo [Bootstrapper] Running %SCRIPT_NAME%...
echo --------------------------------------------------

:: Run the actual Python script and pass all command-line arguments to it
python %SCRIPT_NAME% %*

echo --------------------------------------------------
:: Ask the user what to do next
choice /C YN /M "Would you like to rerun the script?"

:: Errorlevels are evaluated from highest to lowest based on the /C order (Y=1, N=2)
if errorlevel 2 goto :exit_script
if errorlevel 1 goto :run_script

:exit_script
echo [Bootstrapper] Exiting...
:: Exit the virtual environment when finished
deactivate
endlocal