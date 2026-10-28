@echo off
rem Starts the Lamsa voice bot (its web interface is served at http://localhost:7860).
cd /d "%~dp0"
rem Open the browser about 15 seconds from now, once the bot has finished starting.
start "" cmd /c "ping -n 16 127.0.0.1 >nul & start http://localhost:7860"
".venv\Scripts\python.exe" demo_openai1.py
