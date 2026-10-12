from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.db.models import Q, Count

from .models import Product, ProductBatch, Category, Warehouse, InventoryMovement, InventoryCount, InventoryCountItem, BarcodeEvent
from apps.core.models import AuditLog
from apps.suppliers.models import Supplier


@login_required
def products_list_view(request):
    q = request.GET.get('q', '').strip()
    category_id = request.GET.get('category')
    stock_status = request.GET.get('stock')

    products = Product.objects.select_related('category', 'supplier').all()

    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(code__icontains=q) | Q(barcode__icontains=q)
        )
    if category_id:
        products = products.filter(category_id=category_id)

    # Filter by stock status if requested
    filtered_list = []
    for p in products:
        st = p.total_stock
        if stock_status == 'low' and not p.is_low_stock:
            continue
        if stock_status == 'out' and st > 0:
            continue
        if stock_status == 'in' and st <= 0:
            continue
        filtered_list.append(p)

    categories = Category.objects.all()
    return render(request, 'inventory/products_list.html', {
        'products': filtered_list,
        'categories': categories,
        'q': q,
        'selected_category': category_id,
        'stock_status': stock_status,
    })


@login_required
def product_create_view(request):
    if not request.user.can_manage_inventory:
        messages.error(request, 'غير مصرح لك بإضافة منتجات.')
        return redirect('inventory:products_list')

    if request.method == 'POST':
        name = request.POST.get('name')
        code = request.POST.get('code')
        barcode = request.POST.get('barcode') or None
        category_id = request.POST.get('category')
        brand = request.POST.get('brand', '')
        supplier_id = request.POST.get('supplier')
        unit = request.POST.get('unit', 'piece')
        size_or_weight = request.POST.get('size_or_weight', '')
        default_cost_price = Decimal(request.POST.get('default_cost_price', '0.00'))
        sale_price = Decimal(request.POST.get('sale_price', '0.00'))
        min_stock_limit = Decimal(request.POST.get('min_stock_limit', '5.00'))
        storage_location = request.POST.get('storage_location', '')
        initial_qty = Decimal(request.POST.get('initial_qty', '0.00'))
        batch_number = request.POST.get('batch_number', 'BATCH-INIT')
        expiry_date = request.POST.get('expiry_date') or None

        if Product.objects.filter(code=code).exists():
            messages.error(request, 'كود المنتج مسجل مسبقاً.')
        elif barcode and Product.objects.filter(barcode=barcode).exists():
            messages.error(request, 'الباركود مسجل لمنتج آخر.')
        else:
            with transaction.atomic():
                product = Product.objects.create(
                    name=name,
                    code=code,
                    barcode=barcode,
                    category_id=category_id if category_id else None,
                    brand=brand,
                    supplier_id=supplier_id if supplier_id else None,
                    unit=unit,
                    size_or_weight=size_or_weight,
                    default_cost_price=default_cost_price,
                    sale_price=sale_price,
                    min_stock_limit=min_stock_limit,
                    storage_location=storage_location,
                )

                default_wh = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()
                if not default_wh:
                    default_wh = Warehouse.objects.create(name='المخزن الرئيسي', code='WH-MAIN', is_default=True)

                if initial_qty > 0:
                    batch = ProductBatch.objects.create(
                        product=product,
                        warehouse=default_wh,
                        batch_number=batch_number,
                        initial_quantity=initial_qty,
                        current_quantity=initial_qty,
                        cost_price=default_cost_price,
                        received_date=timezone.now().date(),
                        expiry_date=expiry_date,
                        supplier_id=supplier_id if supplier_id else None,
                    )

                    InventoryMovement.objects.create(
                        product=product,
                        batch=batch,
                        warehouse=default_wh,
                        movement_type='PURCHASE',
                        quantity=initial_qty,
                        balance_after=initial_qty,
                        reference_id=f"INIT-{product.code}",
                        reason="رصيد أولي عند إضافة المنتج",
                        user=request.user
                    )

                AuditLog.objects.create(
                    user=request.user,
                    action='CREATE',
                    target_model='Product',
                    target_id=product.code,
                    description=f"إضافة منتج جديد: {product.name} (كود: {product.code}) برصيد أولي {initial_qty}"
                )

                messages.success(request, f'تمت إضافة المنتج {product.name} بنجاح.')
                return redirect('inventory:products_list')

    categories = Category.objects.all()
    suppliers = Supplier.objects.filter(is_active=True)
    return render(request, 'inventory/product_form.html', {
        'categories': categories,
        'suppliers': suppliers,
        'title': 'إضافة منتج جديد',
    })


@login_required
def product_edit_view(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not request.user.can_manage_inventory:
        messages.error(request, 'غير مصرح لك بتعديل بيانات المنتجات.')
        return redirect('inventory:products_list')

    if request.method == 'POST':
        old_price = product.sale_price
        product.name = request.POST.get('name')
        new_barcode = request.POST.get('barcode') or None
        if new_barcode and Product.objects.filter(barcode=new_barcode).exclude(pk=product.pk).exists():
            messages.error(request, 'الباركود مسجل لمنتج آخر.')
            return redirect('inventory:product_edit', pk=product.pk)

        product.barcode = new_barcode
        product.category_id = request.POST.get('category') or None
        product.brand = request.POST.get('brand', '')
        product.supplier_id = request.POST.get('supplier') or None
        product.unit = request.POST.get('unit', product.unit)
        product.size_or_weight = request.POST.get('size_or_weight', '')
        product.default_cost_price = Decimal(request.POST.get('default_cost_price', '0.00'))
        new_sale_price = Decimal(request.POST.get('sale_price', '0.00'))
        product.min_stock_limit = Decimal(request.POST.get('min_stock_limit', '5.00'))
        product.storage_location = request.POST.get('storage_location', '')
        product.is_active = 'is_active' in request.POST

        price_changed = (old_price != new_sale_price)
        product.sale_price = new_sale_price
        product.save()

        if price_changed:
            AuditLog.objects.create(
                user=request.user,
                action='PRICE_CHANGE',
                target_model='Product',
                target_id=product.code,
                description=f"تعديل سعر بيع {product.name} من {old_price} ج.م إلى {new_sale_price} ج.م"
            )
        else:
            AuditLog.objects.create(
                user=request.user,
                action='UPDATE',
                target_model='Product',
                target_id=product.code,
                description=f"تحديث بيانات المنتج {product.name}"
            )

        messages.success(request, f'تم تحديث بيانات المنتج {product.name} بنجاح.')
        return redirect('inventory:products_list')

    categories = Category.objects.all()
    suppliers = Supplier.objects.filter(is_active=True)
    return render(request, 'inventory/product_form.html', {
        'product': product,
        'categories': categories,
        'suppliers': suppliers,
        'title': f'تعديل منتج: {product.name}',
    })


@login_required
def batches_list_view(request):
    batches = ProductBatch.objects.select_related('product', 'warehouse', 'supplier').all()
    filter_type = request.GET.get('filter')
    today = timezone.now().date()

    if filter_type == 'near_expiry':
        batches = [b for b in batches if b.is_near_expiry and b.current_quantity > 0]
    elif filter_type == 'expired':
        batches = [b for b in batches if b.is_expired and b.current_quantity > 0]
    elif filter_type == 'active':
        batches = [b for b in batches if b.current_quantity > 0]

    return render(request, 'inventory/batches_list.html', {
        'batches': batches,
        'filter_type': filter_type,
    })


@login_required
def batch_create_view(request):
    if not request.user.can_manage_inventory:
        messages.error(request, 'غير مصرح لك بإضافة دفعات مخزون.')
        return redirect('inventory:batches_list')

    if request.method == 'POST':
        product_id = request.POST.get('product')
        warehouse_id = request.POST.get('warehouse')
        batch_number = request.POST.get('batch_number')
        quantity = Decimal(request.POST.get('quantity', '1'))
        cost_price = Decimal(request.POST.get('cost_price', '0.00'))
        expiry_date = request.POST.get('expiry_date') or None
        received_date = request.POST.get('received_date') or timezone.now().date()
        supplier_id = request.POST.get('supplier') or None

        product = get_object_or_404(Product, pk=product_id)
        warehouse = get_object_or_404(Warehouse, pk=warehouse_id)

        with transaction.atomic():
            batch = ProductBatch.objects.create(
                product=product,
                warehouse=warehouse,
                batch_number=batch_number,
                initial_quantity=quantity,
                current_quantity=quantity,
                cost_price=cost_price,
                expiry_date=expiry_date,
                received_date=received_date,
                supplier_id=supplier_id
            )

            balance_after = product.total_stock
            InventoryMovement.objects.create(
                product=product,
                batch=batch,
                warehouse=warehouse,
                movement_type='PURCHASE',
                quantity=quantity,
                balance_after=balance_after,
                reference_id=f"BATCH-{batch.batch_number}",
                reason=f"إيداع دفعة شراء جديدة {batch_number}",
                user=request.user
            )

            AuditLog.objects.create(
                user=request.user,
                action='CREATE',
                target_model='ProductBatch',
                target_id=batch.batch_number,
                description=f"تسجيل دفعة شراء جديدة {batch.batch_number} للمنتج {product.name} بكمية {quantity}"
            )

            messages.success(request, f'تم إيداع الدفعة {batch_number} للمنتج {product.name} بنجاح.')
            return redirect('inventory:batches_list')

    products = Product.objects.filter(is_active=True)
    warehouses = Warehouse.objects.all()
    suppliers = Supplier.objects.filter(is_active=True)
    return render(request, 'inventory/batch_form.html', {
        'products': products,
        'warehouses': warehouses,
        'suppliers': suppliers,
    })


@login_required
def movements_list_view(request):
    movements = InventoryMovement.objects.select_related('product', 'batch', 'warehouse', 'user').all()[:150]
    return render(request, 'inventory/movements_list.html', {'movements': movements})


@login_required
def inventory_counts_view(request):
    counts = InventoryCount.objects.select_related('warehouse', 'conducted_by').all()
    return render(request, 'inventory/counts_list.html', {'counts': counts})


@login_required
def inventory_count_create_view(request):
    if not request.user.can_manage_inventory:
        messages.error(request, 'غير مصرح لك ببدء جلسات جرد.')
        return redirect('inventory:counts_list')

    default_wh = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()
    if request.method == 'POST':
        wh_id = request.POST.get('warehouse')
        warehouse = get_object_or_404(Warehouse, id=wh_id)
        count_session = InventoryCount.objects.create(
            warehouse=warehouse,
            conducted_by=request.user,
            notes=request.POST.get('notes', '')
        )
        # Snapshot current stock
        products = Product.objects.filter(is_active=True)
        for p in products:
            InventoryCountItem.objects.create(
                count_session=count_session,
                product=p,
                system_quantity=p.total_stock,
                physical_quantity=p.total_stock
            )
        messages.success(request, f'تم بدء جلسة الجرد للمخزن {warehouse.name}.')
        return redirect('inventory:count_detail', pk=count_session.id)

    warehouses = Warehouse.objects.all()
    return render(request, 'inventory/count_create.html', {'warehouses': warehouses})


@login_required
def inventory_count_detail_view(request, pk):
    count_session = get_object_or_404(InventoryCount, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_counts':
            for item in count_session.items.all():
                phys_val = request.POST.get(f'qty_{item.id}')
                item_note = request.POST.get(f'note_{item.id}', '')
                if phys_val is not None:
                    item.physical_quantity = Decimal(str(phys_val))
                    item.notes = item_note
                    item.save()
            messages.success(request, 'تم حفظ الأرقام الفعلية للجرد.')
        elif action == 'apply_adjustments' and count_session.status != 'ADJUSTED':
            with transaction.atomic():
                for item in count_session.items.all():
                    diff = item.difference
                    if diff != 0:
                        mov_type = 'ADJUST_ADD' if diff > 0 else 'ADJUST_SUB'
                        abs_diff = abs(diff)
                        
                        # Adjust on product batch or movement
                        first_batch = item.product.batches.first()
                        if first_batch:
                            first_batch.current_quantity = max(first_batch.current_quantity + diff, Decimal('0.00'))
                            first_batch.save(update_fields=['current_quantity'])

                        InventoryMovement.objects.create(
                            product=item.product,
                            warehouse=count_session.warehouse,
                            movement_type=mov_type,
                            quantity=abs_diff,
                            balance_after=item.product.total_stock,
                            reference_id=f"AUDIT-{count_session.id}",
                            reason=f"تسوية جردية آلية - جلسة جرد #{count_session.id} ({item.notes or 'تعديل الفروق'})",
                            user=request.user
                        )
                count_session.status = 'ADJUSTED'
                count_session.save(update_fields=['status'])
                AuditLog.objects.create(
                    user=request.user,
                    action='STOCK_ADJUST',
                    target_model='InventoryCount',
                    target_id=str(count_session.id),
                    description=f"تطبيق التسويات الجردية لجلسة الجرد رقم {count_session.id}"
                )
                messages.success(request, 'تم تطبيق التسويات الجردية وتحديث أرصدة المخزون بنجاح!')
        return redirect('inventory:count_detail', pk=count_session.pk)

    return render(request, 'inventory/count_detail.html', {'count_session': count_session})


@login_required
def barcode_events_view(request):
    events = BarcodeEvent.objects.select_related('product', 'cashier').all()[:150]
    return render(request, 'inventory/barcode_events.html', {'events': events})


@login_required
def categories_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        icon = request.POST.get('icon', 'bi-tag')
        if name and not Category.objects.filter(name=name).exists():
            Category.objects.create(name=name, description=description, icon=icon)
            messages.success(request, f'تمت إضافة التصنيف {name}.')
        return redirect('inventory:categories_list')

    categories = Category.objects.annotate(products_count=Count('products')).all()
    return render(request, 'inventory/categories_list.html', {'categories': categories})
