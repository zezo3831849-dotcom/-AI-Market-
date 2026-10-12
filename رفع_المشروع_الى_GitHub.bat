@echo off
chcp 65001 > nul
title AI Market Manager - GitHub Push Helper

echo ======================================================================
echo             رفع مشروع AI Market Manager إلى GitHub
echo ======================================================================
echo.
echo تم تهيئة مستودع Git للمشروع وعمل أول Commit بنجاح محلياً!
echo.
echo لربط المشروع بحسابك على GitHub:
echo 1. افتح https://github.com/new وأنشئ مستودعاً جديداً (New Repository) فارغاً.
echo 2. انسخ رابط المستودع (مثال: https://github.com/YourUsername/market-manager.git)
echo.
set /p REPO_URL="الصق رابط مستودع GitHub هنا واضغط Enter: "

if "%REPO_URL%"=="" (
    echo لم يتم إدخال رابط. تم إلغاء العملية.
    pause
    exit /b
)

echo.
echo جاري ربط المستودع ورفع الملفات إلى فرع main...
git remote remove origin 2>nul
git remote add origin %REPO_URL%
git branch -M main
git push -u origin main

echo.
echo تم الانتهاء! تحقق من صفحة GitHub للتأكد من رفع المشروع بنجاح.
pause
