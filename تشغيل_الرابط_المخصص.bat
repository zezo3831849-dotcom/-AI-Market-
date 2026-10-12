@echo off
chcp 65001 > nul
title AI Market Manager - Custom Link Runner
color 0B

echo ======================================================================
echo          تشغيل الرابط المخصص العالمي: ai-market-zzt
echo ======================================================================
echo.
echo الرابط الخاص بك:
echo https://ai-market-zzt.loca.lt
echo.
echo جاري ربط السيرفر بالرابط المخصص...
echo (اترك هذه النافذة مفتوحة طالما ترغب في استمرار عمل الرابط)
echo ======================================================================
echo.

set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%..\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

"%PYTHON_EXE%" "%PROJECT_DIR%localtunnel_bridge.py"
pause
