import urllib.request
import urllib.parse
import http.cookiejar
import re

cookie_jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

# 1. Open login page
resp = opener.open('http://127.0.0.1:8000/accounts/login/')
print('1. Login Page Status:', resp.status)
html = resp.read().decode('utf-8')

match = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', html)
csrf = match.group(1) if match else ''
print('CSRF token found:', bool(csrf))

# 2. Login as admin
login_data = urllib.parse.urlencode({
    'username': 'admin',
    'password': 'admin1234',
    'csrfmiddlewaretoken': csrf
}).encode('utf-8')

req = urllib.request.Request(
    'http://127.0.0.1:8000/accounts/login/',
    data=login_data,
    headers={'Referer': 'http://127.0.0.1:8000/accounts/login/'}
)
resp = opener.open(req)
print('2. Authenticated, redirected to:', resp.geturl())

# 3. Test Core Pages
pages = [
    ('/', 'لوحة التحكم والتحليلات'),
    ('/financial-report/', 'القوائم المالية وحساب الأرباح'),
    ('/sales/pos/', 'نقطة البيع'),
    ('/sales/invoices/', 'سجل فواتير المبيعات'),
    ('/sales/returns/', 'سجل مرتجعات العملاء'),
    ('/sales/sync-history/', 'سجل عمليات مزامنة الأوفلاين'),
    ('/inventory/products/', 'دليل المنتجات والمخزون'),
    ('/inventory/batches/', 'دفعات الشراء وتواريخ الصلاحية'),
    ('/inventory/movements/', 'سجل حركات المخزون'),
    ('/inventory/counts/', 'جلسات الجرد الفعلي'),
    ('/inventory/barcodes/', 'سجل مراقبة نشاط الباركود'),
    ('/inventory/categories/', 'تصنيفات السلع'),
    ('/expenses/', 'المصروفات التشغيلية'),
    ('/expenses/categories/', 'بنود وتصنيفات المصروفات'),
    ('/suppliers/', 'دليل الموردين'),
    ('/suppliers/orders/', 'أوامر الشراء والتوريد'),
    ('/suppliers/special-deals/', 'الصفقات الاستثنائية'),
    ('/suppliers/schedules/', 'مواعيد وجداول زيارات الموردين'),
    ('/intelligence/', 'مركز الذكاء الاصطناعي'),
    ('/intelligence/forecasts/', 'التنبؤ بالطلب'),
    ('/intelligence/smart-offers/', 'العروض والخصومات الذكية'),
    ('/intelligence/anomalies/', 'رصد الشذوذ والتنبيهات الرقابية'),
    ('/intelligence/calendar/', 'التقويم الذكي'),
    ('/audit/', 'سجل العمليات والتدقيق'),
    ('/backup/', 'النسخ الاحتياطي واستعادة البيانات'),
    ('/settings/', 'إعدادات المتجر'),
    ('/accounts/users/', 'إدارة المستخدمين والصلاحيات'),
]

for path, expected_text in pages:
    r = opener.open('http://127.0.0.1:8000' + path)
    content = r.read().decode('utf-8')
    assert expected_text in content, f'Expected keyword "{expected_text}" not found in {path}'
    print(f'✅ Page {path:<26} -> HTTP {r.status} OK (Keyword verified: {expected_text})')

print('\n🎉 ALL 27 KEY APPLICATION SCREENS VERIFIED SUCCESSFULLY!')
