import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import Sale, SaleItem, Return, ReturnItem, SyncOperation
from .services import process_sale, process_return, sync_offline_sales
from apps.inventory.models import Product, Category, BarcodeEvent
from apps.core.models import SystemSettings


@login_required
def pos_view(request):
    categories = Category.objects.all()
    products = Product.objects.filter(is_active=True).select_related('category')
    settings_obj = SystemSettings.get_settings()
    return render(request, 'sales/pos.html', {
        'categories': categories,
        'products': products,
        'settings': settings_obj,
    })


@login_required
def api_products_catalog(request):
    """Returns products for POS and browser offline caching."""
    products = Product.objects.filter(is_active=True)
    catalog = []
    for p in products:
        catalog.append({
            'id': p.id,
            'name': p.name,
            'code': p.code,
            'barcode': p.barcode or '',
            'sale_price': float(p.sale_price),
            'cost_price': float(p.default_cost_price),
            'stock': float(p.total_stock),
            'unit': p.get_unit_display(),
            'category_id': p.category_id,
            'category_name': p.category.name if p.category else 'عام',
        })
    return JsonResponse({'products': catalog})


@login_required
def api_process_sale(request):
    """Processes POS checkout via POST JSON."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'طريقة الطلب غير مقبولة'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
        items = data.get('items', [])
        if not items:
            return JsonResponse({'success': False, 'message': 'سلة المشتريات فارغة'}, status=400)

        customer_name = data.get('customer_name', 'عميل نقدي')
        discount_amount = Decimal(str(data.get('discount_amount', 0)))
        payment_method = data.get('payment_method', 'CASH')
        client_uuid = data.get('client_uuid')
        notes = data.get('notes', '')

        sale, created, msg = process_sale(
            cashier=request.user,
            items_data=items,
            customer_name=customer_name,
            discount_amount=discount_amount,
            payment_method=payment_method,
            client_uuid=client_uuid,
            notes=notes
        )

        return JsonResponse({
            'success': True,
            'invoice_number': sale.invoice_number,
            'total_amount': float(sale.total_amount),
            'gross_profit': float(sale.gross_profit),
            'gross_margin_pct': float(sale.gross_margin_percent),
            'created_at': sale.created_at.strftime("%Y-%m-%d %H:%M"),
            'message': msg
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f"خطأ أثناء حفظ الفاتورة: {str(e)}"}, status=500)


@login_required
def api_sync_offline_sales(request):
    """Endpoint for synchronizing offline sales queued in browser."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body.decode('utf-8'))
        offline_sales = data.get('sales', [])
        summary = sync_offline_sales(request.user, offline_sales)
        return JsonResponse({
            'success': True,
            'summary': summary,
            'message': f"تمت المزامنة: {summary['success']} ناجحة، {summary['duplicates']} مكررة تم تجاهلها، {len(summary['errors'])} أخطاء."
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


@login_required
def invoices_list_view(request):
    invoices = Sale.objects.select_related('cashier').all().order_by('-created_at')[:100]
    return render(request, 'sales/invoices_list.html', {'invoices': invoices})


@login_required
def invoice_detail_view(request, pk):
    invoice = get_object_or_404(Sale, pk=pk)
    items = invoice.items.select_related('product', 'batch').all()
    settings_obj = SystemSettings.get_settings()
    return render(request, 'sales/invoice_detail.html', {
        'invoice': invoice,
        'items': items,
        'settings': settings_obj,
    })


@login_required
def returns_list_view(request):
    returns = Return.objects.select_related('cashier', 'sale').all().order_by('-created_at')[:100]
    return render(request, 'sales/returns_list.html', {'returns': returns})


@login_required
def return_create_view(request):
    if request.method == 'POST':
        sale_id = request.POST.get('sale_id') or None
        product_id = request.POST.get('product_id')
        quantity = Decimal(request.POST.get('quantity', '1'))
        unit_price = Decimal(request.POST.get('unit_price', '0.00'))
        condition = request.POST.get('condition', 'SELLABLE')
        reason = request.POST.get('reason', '')

        items_to_return = [{
            'product_id': product_id,
            'quantity': quantity,
            'unit_price': unit_price,
            'condition': condition,
        }]

        return_obj = process_return(
            cashier=request.user,
            original_sale_id=sale_id,
            items_to_return=items_to_return,
            reason=reason
        )
        messages.success(request, f'تم تسجيل إذن المرتجع {return_obj.return_number} بمبلغ {return_obj.total_refund_amount} ج.م')
        return redirect('sales:returns_list')

    products = Product.objects.filter(is_active=True)
    recent_sales = Sale.objects.filter(status='COMPLETED').order_by('-created_at')[:30]
    return render(request, 'sales/return_form.html', {
        'products': products,
        'recent_sales': recent_sales,
    })


@login_required
def sync_history_view(request):
    sync_logs = SyncOperation.objects.select_related('cashier').all()[:100]
    return render(request, 'sales/sync_history.html', {'sync_logs': sync_logs})
