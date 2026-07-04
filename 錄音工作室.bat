@echo off
rem Launch the 5-step audio cleaning wizard in the browser.
rem ASCII-only on purpose: cmd.exe mis-parses non-ASCII bat files on zh-TW systems.
chcp 65001 >nul
cd /d C:\Users\User\audio-studio
python -m streamlit run app.py --server.port 8601 --server.fileWatcherType none
