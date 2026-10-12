@echo off
title Push AI Market Manager to GitHub
color 0A

echo ======================================================================
echo               Pushing AI-Market Manager to GitHub
echo ======================================================================
echo.
echo Target Repository:
echo https://github.com/zezo3831849-dotcom/-AI-Market-.git
echo.

cd /d "%~dp0"

echo [1/3] Setting git remote...
git remote remove origin 2>nul
git remote add origin https://github.com/zezo3831849-dotcom/-AI-Market-.git
git branch -M main

echo.
echo [2/3] Uploading code to GitHub...
echo If a GitHub login window appears, click "Sign in with your browser".
echo.

git push -u origin main

echo.
echo ======================================================================
if %ERRORLEVEL% equ 0 (
    echo [SUCCESS] Your project has been uploaded to GitHub successfully!
    echo Visit: https://github.com/zezo3831849-dotcom/-AI-Market-
) else (
    echo [NOTICE] If sign-in failed, you can generate a Personal Access Token
    echo from: https://github.com/settings/tokens/new
)
echo ======================================================================
echo.
pause
