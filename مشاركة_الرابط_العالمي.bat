@echo off
chcp 65001 > nul
title AI Market Manager - Live Public Link (Cloudflare Tunnel)

echo ======================================================================
echo       توليد رابط عالمي أونلاين لمشروع AI-Powered Market Manager
echo ======================================================================
echo.
echo تأكد من أن سيرفر المشروع يعمل محلياً على: http://127.0.0.1:8000
echo جاري إنشاء نفق سحابي مجاني ومؤمن (Cloudflare Tunnel)...
echo.
echo سيظهر الرابط العالمي الخاص بك بالأسفل بصيغة:
echo https://xxxx.trycloudflare.com
echo.
echo يمكنك نسخ الرابط وإرساله لأصدقائك لتجربة الموقع فوراً من أي هاتف أو جهاز!
echo (اترك هذه النافذة مفتوحة طالما ترغب في استمرار عمل الرابط)
echo ======================================================================
echo.

"%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8000
pause
