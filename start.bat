@echo off
"%~dp0.venv\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt" --quiet
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0speechskin.py" %*

