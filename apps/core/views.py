import os
import json
from decimal import Decimal
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse, FileResponse
from django.utils import timezone
from django.db.models import Sum, Count

from .models import SystemSettings, AuditLog, BackupLog
from .backup_service import perform_backup
from .financial_services import get_financial_summary
from apps.inventory.models import Product, ProductBatch
from apps.sales.models import Sale, SaleItem, Return
from apps.expenses.models import OperatingExpense, ExpenseCategory
from apps.intelligence.models import AIRecommendation


@login_required
def dashboard_view(request):
    settings_obj = SystemSettings.get_settings()
    today = timezone.now().date()
    start_of_month = today.replace(day=1)

    # 1. Financial summary for current month
    finance = get_financial_summary(start_date=start_of_month, end_date=today)

    # 2. Daily sales & profit trend for the last 10 days
    last_10_days = [today - timedelta(days=i) for i in range(9, -1, -1)]
    chart_dates = []
    chart_sales = []
    chart_cogs = []
    chart_profit = []
    chart_expenses = []

    for d in last_10_days:
        chart_dates.append(d.strftime("%m/%d"))
        
        # Sales on this day
        day_sales = Sale.objects.filter(created_at__date=d, status='COMPLETED').aggregate(
            rev=Sum('total_amount'),
            cost=Sum('total_cost')
        )
        s_rev = float(day_sales['rev'] or 0)
        s_cost = float(day_sales['cost'] or 0)
        
        # Expenses on this day
        day_exp = OperatingExpense.objects.filter(expense_date=d).aggregate(
            tot=Sum('amount')
        )['tot'] or 0

        chart_sales.append(s_rev)
        chart_cogs.append(s_cost)
        chart_profit.append(round(s_rev - s_cost, 2))
        chart_expenses.append(float(day_exp))

    # 3. Expense breakdown by category for Doughnut Chart
    exp_cats = ExpenseCategory.objects.annotate(
        total_amount=Sum('expenses__amount')
    ).filter(total_amount__gt=0).order_by('-total_amount')

    donut_labels = [c.name for c in exp_cats]
    donut_values = [float(c.total_amount or 0) for c in exp_cats]

    # 4. Top selling products
    top_products = SaleItem.objects.filter(
        sale__status='COMPLETED'
    ).values('product__name', 'product__code').annotate(
        total_sold=Sum('quantity'),
        total_rev=Sum('total_price'),
        total_profit=Sum('gross_profit')
    ).order_by('-total_sold')[:5]

    # 5. Low stock alerts
    low_stock_products = [p for p in Product.objects.filter(is_active=True) if p.is_low_stock][:6]

    # 6. Near-expiry batches
    thirty_days = today + timedelta(days=30)
    near_expiry_batches = ProductBatch.objects.filter(
        expiry_date__isnull=False,
        expiry_date__gte=today,
        expiry_date__lte=thirty_days,
        current_quantity__gt=0
    ).select_related('product')[:6]

    # 7. AI Recommendations pending
    ai_recs = AIRecommendation.objects.filter(status='PENDING').order_by('-created_at')[:4]

    context = {
        'settings': settings_obj,
        'finance': finance,
        'chart_dates_json': json.dumps(chart_dates),
        'chart_sales_json': json.dumps(chart_sales),
        'chart_profit_json': json.dumps(chart_profit),
        'chart_expenses_json': json.dumps(chart_expenses),
        'donut_labels_json': json.dumps(donut_labels),
        'donut_values_json': json.dumps(donut_values),
        'top_products': top_products,
        'low_stock_products': low_stock_products,
        'near_expiry_batches': near_expiry_batches,
        'ai_recs': ai_recs,
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def audit_log_view(request):
    logs = AuditLog.objects.select_related('user').all()[:100]
    return render(request, 'core/audit_log.html', {'logs': logs})


@login_required
def backup_management_view(request):
    logs = BackupLog.objects.all()[:30]
    return render(request, 'core/backup_management.html', {'logs': logs})


@login_required
def create_backup_view(request):
    if not request.user.is_admin_or_manager:
        messages.error(request, 'غير مصرح لك بإنشاء نسخ احتياطية.')
        return redirect('core:backup_management')

    success, log = perform_backup(notes=f"تم إنشاؤها بواسطة {request.user.username}")
    if success:
        AuditLog.objects.create(
            user=request.user,
            action='BACKUP',
            target_model='BackupLog',
            target_id=str(log.id),
            description=f"إنشاء نسخة احتياطية ناجحة {log.file_name} بحجم {log.file_size_kb} KB"
        )
        messages.success(request, f'تم إنشاء النسخة الاحتياطية بنجاح: {log.file_name} ({log.file_size_kb} كيلوبايت)')
    else:
        messages.error(request, f'فشل إنشاء النسخة الاحتياطية: {log.notes}')

    return redirect('core:backup_management')


@login_required
def download_backup_view(request, backup_id):
    if not request.user.is_admin_or_manager:
        messages.error(request, 'غير مصرح لك بتحميل النسخ الاحتياطية.')
        return redirect('core:backup_management')

    log = get_object_or_404(BackupLog, id=backup_id)
    if os.path.exists(log.file_path):
        return FileResponse(open(log.file_path, 'rb'), as_attachment=True, filename=log.file_name)
    messages.error(request, 'ملف النسخة غير موجود على الخادم.')
    return redirect('core:backup_management')


@login_required
def system_settings_view(request):
    if not request.user.is_admin_or_manager:
        messages.error(request, 'تعديل الإعدادات متاح للمدير فقط.')
        return redirect('core:dashboard')

    settings_obj = SystemSettings.get_settings()
    if request.method == 'POST':
        settings_obj.store_name = request.POST.get('store_name', settings_obj.store_name)
        settings_obj.phone = request.POST.get('phone', settings_obj.phone)
        settings_obj.address = request.POST.get('address', settings_obj.address)
        settings_obj.currency = request.POST.get('currency', settings_obj.currency)
        settings_obj.min_profit_margin_percent = Decimal(request.POST.get('min_profit_margin_percent', '15.0'))
        settings_obj.default_low_stock_limit = int(request.POST.get('default_low_stock_limit', 10))
        settings_obj.near_expiry_days = int(request.POST.get('near_expiry_days', 30))
        settings_obj.offline_sync_enabled = 'offline_sync_enabled' in request.POST
        settings_obj.save()

        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            target_model='SystemSettings',
            description='تحديث إعدادات المتجر العامة والحدود الرقابية'
        )
        messages.success(request, 'تم حفظ الإعدادات بنجاح.')
        return redirect('core:settings')

    return render(request, 'core/settings.html', {'settings': settings_obj})


@login_required
def financial_report_view(request):
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    today = timezone.now().date()
    start_date = timezone.datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else today.replace(day=1)
    end_date = timezone.datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else today

    finance = get_financial_summary(start_date=start_date, end_date=end_date)
    
    # Category expense details
    cat_expenses = ExpenseCategory.objects.annotate(
        period_total=Sum('expenses__amount')
    ).filter(expenses__expense_date__gte=start_date, expenses__expense_date__lte=end_date)

    context = {
        'start_date': start_date.strftime("%Y-%m-%d"),
        'end_date': end_date.strftime("%Y-%m-%d"),
        'finance': finance,
        'cat_expenses': cat_expenses,
    }
    return render(request, 'core/financial_report.html', context)


@login_required
def quick_search_api(request):
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'results': []})

    products = Product.objects.filter(name__icontains=query)[:5]
    sales = Sale.objects.filter(invoice_number__icontains=query)[:5]

    results = []
    for p in products:
        results.append({
            'type': 'منتج',
            'title': p.name,
            'subtitle': f"كود: {p.code} | السعر: {p.sale_price} ج.م | المخزون: {p.total_stock}",
            'url': f"/inventory/products/?q={p.code}"
        })
    for s in sales:
        results.append({
            'type': 'فاتورة',
            'title': s.invoice_number,
            'subtitle': f"الإجمالي: {s.total_amount} ج.م | العميل: {s.customer_name}",
            'url': f"/sales/invoices/{s.id}/"
        })

    return JsonResponse({'results': results})
