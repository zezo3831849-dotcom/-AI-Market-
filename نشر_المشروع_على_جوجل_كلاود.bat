@echo off
chcp 65001 > nul
title أداة النشر التلقائي على سحابة جوجل (Google Cloud Run)
color 0B

echo ======================================================================
echo          نشر مشروع AI-Powered Market Manager على سحابة جوجل
echo ======================================================================
echo.
echo هذه الأداة ستقوم بأتمتة كافة خطوات النشر على Google Cloud Run تلقائياً.
echo.

cd /d "%~dp0"

:: 1. التحقق من وجود gcloud CLI
where gcloud >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [1/4] جاري تثبيت Google Cloud CLI على جهازك عبر winget...
    winget install Google.CloudSDK --accept-source-agreements --accept-package-agreements --silent
    echo.
    echo تم التثبيت! يرجى إغلاق هذه النافذة وإعادة فتحها لتحديث مسارات النظام.
    pause
    exit /b
)

echo [1/4] أداة Google Cloud CLI متوفرة بنجاح!
echo.

:: 2. تسجيل الدخول إلى حساب جوجل
echo [2/4] جاري تسجيل الدخول بحسابك في Google Cloud...
echo سيتم فتح المتصفح لتأكيد الدخول، يرجى الموافقة.
call gcloud auth login
echo.

:: 3. اختيار أو إنشاء المشروع
echo [3/4] جاري إعداد مشروع Google Cloud...
call gcloud projects list
set /p GCP_PROJECT="اكتب اسم أو معرف المشروع (PROJECT_ID) من القائمة أعلاه واضغط Enter: "

if "%GCP_PROJECT%"=="" (
    echo لم يتم إدخال معرف المشروع.
    pause
    exit /b
)

call gcloud config set project %GCP_PROJECT%
call gcloud services enable run.googleapis.com cloudbuild.googleapis.com --quiet

:: 4. النشر التلقائي على Cloud Run
echo.
echo [4/4] جاري بناء ونشر المشروع على Google Cloud Run...
echo سيستغرق ذلك دقيقة أو دقيقتين...
call gcloud run deploy ai-market --source . --region us-central1 --allow-unauthenticated --quiet

echo.
echo ======================================================================
echo مبروك! تم نشر المشروع بنجاح على سحابة جوجل!
echo يمكنك نسخ الرابط الظاهر بالأعلى وإرساله للجميع في أي مكان في العالم.
echo ======================================================================
pause
