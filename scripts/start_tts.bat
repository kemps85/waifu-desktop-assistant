@echo off
cd /d "%~dp0..\vendor\Style-Bert-VITS2"
rem Model caches go under vendor\ because ~/.cache is not writable on this machine
set "HF_HOME=%~dp0..\vendor\hf-cache"
set "TORCH_HOME=%~dp0..\vendor\torch-cache"
set "PYANNOTE_CACHE=%~dp0..\vendor\pyannote-cache"
venv\Scripts\python server_fastapi.py
