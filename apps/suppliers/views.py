from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone

from .models import Supplier, SupplierSchedule, SupplierProduct, PurchaseOrder, PurchaseOrderItem, SpecialDeal
from apps.inventory.models import Product, ProductBatch, Warehouse, InventoryMovement
from apps.core.models import AuditLog


@login_required
def suppliers_list_view(request):
    suppliers = Supplier.objects.prefetch_related('schedules').all()
    return render(request, 'suppliers/suppliers_list.html', {'suppliers': suppliers})


@login_required
def supplier_create_view(request):
    if not request.user.can_manage_inventory:
        messages.error(request, 'غير مصرح لك بإضافة موردين.')
        return redirect('suppliers:suppliers_list')

    if request.method == 'POST':
        company_name = request.POST.get('company_name')
        rep_name = request.POST.get('rep_name', '')
        phone = request.POST.get('phone')
        secondary_phone = request.POST.get('secondary_phone', '')
        email = request.POST.get('email', '')
        address = request.POST.get('address', '')
        lead_time_days = int(request.POST.get('lead_time_days', 2))
        min_order_value = Decimal(request.POST.get('min_order_value', '0.00'))
        payment_terms = request.POST.get('payment_terms', 'نقدي عند الاستلام')
        rating = Decimal(request.POST.get('rating', '5.00'))
        notes = request.POST.get('notes', '')

        supplier = Supplier.objects.create(
            company_name=company_name,
            rep_name=rep_name,
            phone=phone,
            secondary_phone=secondary_phone,
            email=email,
            address=address,
            lead_time_days=lead_time_days,
            min_order_value=min_order_value,
            payment_terms=payment_terms,
            rating=rating,
            notes=notes
        )

        AuditLog.objects.create(
            user=request.user,
            action='CREATE',
            target_model='Supplier',
            target_id=str(supplier.id),
            description=f"إضافة مورد جديد: {supplier.company_name} (المندوب: {supplier.rep_name})"
        )
        messages.success(request, f'تمت إضافة المورد {supplier.company_name} بنجاح.')
        return redirect('suppliers:suppliers_list')

    return render(request, 'suppliers/supplier_form.html', {'title': 'إضافة مورد جديد'})


@login_required
def supplier_edit_view(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if not request.user.can_manage_inventory:
        messages.error(request, 'غير مصرح لك بتعديل بيانات الموردين.')
        return redirect('suppliers:suppliers_list')

    if request.method == 'POST':
        supplier.company_name = request.POST.get('company_name')
        supplier.rep_name = request.POST.get('rep_name', '')
        supplier.phone = request.POST.get('phone')
        supplier.secondary_phone = request.POST.get('secondary_phone', '')
        supplier.email = request.POST.get('email', '')
        supplier.address = request.POST.get('address', '')
        supplier.lead_time_days = int(request.POST.get('lead_time_days', supplier.lead_time_days))
        supplier.min_order_value = Decimal(request.POST.get('min_order_value', str(supplier.min_order_value)))
        supplier.payment_terms = request.POST.get('payment_terms', supplier.payment_terms)
        supplier.rating = Decimal(request.POST.get('rating', str(supplier.rating)))
        supplier.notes = request.POST.get('notes', '')
        supplier.is_active = 'is_active' in request.POST
        supplier.save()

        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            target_model='Supplier',
            target_id=str(supplier.id),
            description=f"تحديث بيانات المورد {supplier.company_name}"
        )
        messages.success(request, 'تم تحديث بيانات المورد بنجاح.')
        return redirect('suppliers:suppliers_list')

    return render(request, 'suppliers/supplier_form.html', {
        'supplier': supplier,
        'title': f'تعديل المورد: {supplier.company_name}',
    })


@login_required
def purchase_orders_list_view(request):
    orders = PurchaseOrder.objects.select_related('supplier', 'created_by').all()
    return render(request, 'suppliers/orders_list.html', {'orders': orders})


@login_required
def purchase_order_create_view(request):
    if not request.user.can_manage_inventory:
        messages.error(request, 'غير مصرح لك بإنشاء أوامر شراء.')
        return redirect('suppliers:orders_list')

    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        supplier = get_object_or_404(Supplier, id=supplier_id)
        expected_date = request.POST.get('expected_delivery_date') or None
        notes = request.POST.get('notes', '')

        date_str = timezone.now().strftime("%Y%m%d")
        last_po = PurchaseOrder.objects.filter(po_number__startswith=f"PO-{date_str}").count()
        po_number = f"PO-{date_str}-{(last_po + 1):03d}"

        with transaction.atomic():
            order = PurchaseOrder.objects.create(
                po_number=po_number,
                supplier=supplier,
                expected_delivery_date=expected_date,
                created_by=request.user,
                notes=notes,
                status='APPROVED'
            )

            # Process items
            total_amount = Decimal('0.00')
            products = Product.objects.filter(is_active=True)
            for p in products:
                qty_val = request.POST.get(f'qty_{p.id}')
                cost_val = request.POST.get(f'cost_{p.id}')
                if qty_val and Decimal(str(qty_val)) > 0:
                    qty = Decimal(str(qty_val))
                    cost = Decimal(str(cost_val)) if cost_val else p.default_cost_price
                    item_total = qty * cost
                    total_amount += item_total

                    PurchaseOrderItem.objects.create(
                        order=order,
                        product=p,
                        ordered_quantity=qty,
                        unit_cost=cost,
                        total_cost=item_total
                    )

            order.total_amount = total_amount
            order.save()

            AuditLog.objects.create(
                user=request.user,
                action='ORDER_APPROVE',
                target_model='PurchaseOrder',
                target_id=order.po_number,
                description=f"إنشاء أمر شراء {order.po_number} للمورد {supplier.company_name} بإجمالي {total_amount} ج.م"
            )
            messages.success(request, f'تم إنشاء أمر الشراء {order.po_number} بنجاح.')
            return redirect('suppliers:order_detail', pk=order.pk)

    suppliers = Supplier.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True)
    return render(request, 'suppliers/order_form.html', {
        'suppliers': suppliers,
        'products': products,
    })


@login_required
def purchase_order_detail_view(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk)
    return render(request, 'suppliers/order_detail.html', {'order': order})


@login_required
def purchase_order_receive_view(request, pk):
    order = get_object_or_404(PurchaseOrder, pk=pk)
    if order.status == 'RECEIVED':
        messages.info(request, 'تم استلام هذا الطلب وإيداعه بالمخزن مسبقاً.')
        return redirect('suppliers:order_detail', pk=order.pk)

    default_wh = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()

    with transaction.atomic():
        for item in order.items.all():
            qty = item.ordered_quantity
            item.received_quantity = qty
            item.save(update_fields=['received_quantity'])

            # Create batch
            batch_num = f"PO-{order.po_number[-4:]}-{item.product.code}"
            batch = ProductBatch.objects.create(
                product=item.product,
                warehouse=default_wh,
                batch_number=batch_num,
                initial_quantity=qty,
                current_quantity=qty,
                cost_price=item.unit_cost,
                received_date=timezone.now().date(),
                supplier=order.supplier,
            )

            # Record inventory movement
            InventoryMovement.objects.create(
                product=item.product,
                batch=batch,
                warehouse=default_wh,
                movement_type='PURCHASE',
                quantity=qty,
                balance_after=item.product.total_stock,
                reference_id=order.po_number,
                reason=f"استلام واردات أمر الشراء {order.po_number}",
                user=request.user
            )

        order.status = 'RECEIVED'
        order.actual_delivery_date = timezone.now().date()
        order.save()

        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            target_model='PurchaseOrder',
            target_id=order.po_number,
            description=f"استلام بضائع أمر الشراء {order.po_number} وإيداعها بالمخزن"
        )
        messages.success(request, f'تم استلام بضاعة أمر الشراء {order.po_number} وإيداعها في المخزن بنجاح!')

    return redirect('suppliers:order_detail', pk=order.pk)


@login_required
def special_deals_list_view(request):
    deals = SpecialDeal.objects.select_related('supplier', 'linked_product').all()
    return render(request, 'suppliers/special_deals_list.html', {'deals': deals})


@login_required
def special_deal_create_view(request):
    if not request.user.is_admin_or_manager:
        messages.error(request, 'تسجيل الصفقات الاستثنائية متاح للمدير فقط.')
        return redirect('suppliers:special_deals_list')

    if request.method == 'POST':
        title = request.POST.get('title')
        supplier_id = request.POST.get('supplier') or None
        product_name = request.POST.get('product_name')
        linked_product_id = request.POST.get('linked_product') or None
        quantity_offered = Decimal(request.POST.get('quantity_offered', '0'))
        deal_unit_cost = Decimal(request.POST.get('deal_unit_cost', '0.00'))
        expected_selling_price = Decimal(request.POST.get('expected_selling_price', '0.00'))
        extra_expenses = Decimal(request.POST.get('extra_expenses', '0.00'))
        expiry_date = request.POST.get('expiry_date') or None
        offer_deadline = request.POST.get('offer_deadline') or None
        notes = request.POST.get('notes', '')

        deal = SpecialDeal.objects.create(
            title=title,
            supplier_id=supplier_id,
            product_name=product_name,
            linked_product_id=linked_product_id,
            quantity_offered=quantity_offered,
            deal_unit_cost=deal_unit_cost,
            expected_selling_price=expected_selling_price,
            extra_expenses=extra_expenses,
            expiry_date=expiry_date,
            offer_deadline=offer_deadline,
            manager_decision_notes=notes,
        )

        AuditLog.objects.create(
            user=request.user,
            action='CREATE',
            target_model='SpecialDeal',
            target_id=str(deal.id),
            description=f"تسجيل دراسة صفقة استثنائية: {deal.title} بربح تقديري {deal.potential_gross_profit} ج.م"
        )
        messages.success(request, f'تم تسجيل الصفقة {deal.title} بحسابات ربح تقديرية {deal.potential_gross_profit} ج.م وعائد {deal.roi_percent}%.')
        return redirect('suppliers:special_deals_list')

    suppliers = Supplier.objects.filter(is_active=True)
    products = Product.objects.filter(is_active=True)
    return render(request, 'suppliers/special_deal_form.html', {
        'suppliers': suppliers,
        'products': products,
    })


@login_required
def special_deal_decision_view(request, pk):
    deal = get_object_or_404(SpecialDeal, pk=pk)
    if not request.user.is_admin_or_manager:
        messages.error(request, 'غير مصرح لك باتخاذ قرار بالصفقات.')
        return redirect('suppliers:special_deals_list')

    decision = request.POST.get('decision')
    notes = request.POST.get('decision_notes', '')

    if decision == 'APPROVE':
        deal.status = 'APPROVED'
        deal.manager_decision_notes = notes
        deal.save()
        messages.success(request, f'تمت الموافقة على اعتماد الصفقة {deal.title}.')
    elif decision == 'EXECUTE':
        with transaction.atomic():
            default_wh = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()
            prod = deal.linked_product
            if not prod:
                # Create a product if none linked
                code = f"DEAL-{deal.id:04d}"
                prod = Product.objects.create(
                    name=deal.product_name,
                    code=code,
                    sale_price=deal.expected_selling_price,
                    default_cost_price=deal.deal_unit_cost,
                    supplier=deal.supplier
                )
                deal.linked_product = prod

            batch = ProductBatch.objects.create(
                product=prod,
                warehouse=default_wh,
                batch_number=f"DEAL-BATCH-{deal.id}",
                initial_quantity=deal.quantity_offered,
                current_quantity=deal.quantity_offered,
                cost_price=deal.deal_unit_cost,
                received_date=timezone.now().date(),
                expiry_date=deal.expiry_date,
                supplier=deal.supplier
            )

            InventoryMovement.objects.create(
                product=prod,
                batch=batch,
                warehouse=default_wh,
                movement_type='PURCHASE',
                quantity=deal.quantity_offered,
                balance_after=prod.total_stock,
                reference_id=f"DEAL-{deal.id}",
                reason=f"شراء وتنفيذ صفقة استثنائية: {deal.title}",
                user=request.user
            )

            deal.status = 'EXECUTED'
            deal.save()
            messages.success(request, f'تم تنفيذ الصفقة {deal.title} وإيداع {deal.quantity_offered} وحدة في المخزن بنجاح!')
    elif decision == 'REJECT':
        deal.status = 'REJECTED'
        deal.manager_decision_notes = notes
        deal.save()
        messages.info(request, f'تم رفض الصفقة {deal.title}.')

    return redirect('suppliers:special_deals_list')


@login_required
def schedules_view(request):
    schedules = SupplierSchedule.objects.select_related('supplier').all()
    suppliers = Supplier.objects.filter(is_active=True)

    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        visit_day = request.POST.get('visit_day')
        deadline = request.POST.get('order_deadline_time') or None
        delay = int(request.POST.get('expected_delivery_delay_days', 1))
        notes = request.POST.get('notes', '')

        SupplierSchedule.objects.create(
            supplier_id=supplier_id,
            visit_day=visit_day,
            order_deadline_time=deadline,
            expected_delivery_delay_days=delay,
            notes=notes
        )
        messages.success(request, 'تمت إضافة موعد الزيارة بنجاح.')
        return redirect('suppliers:schedules_list')

    return render(request, 'suppliers/schedules.html', {
        'schedules': schedules,
        'suppliers': suppliers,
    })
