import uuid
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.inventory.models import Product, ProductBatch, InventoryMovement, Warehouse, BarcodeEvent
from apps.core.models import AuditLog
from .models import Sale, SaleItem, Return, ReturnItem, SyncOperation


class InsufficientStockError(Exception):
    pass


def process_sale(cashier, items_data, customer_name='عميل نقدي', discount_amount=Decimal('0.00'), payment_method='CASH', client_uuid=None, is_offline=False, notes=''):
    """
    Executes a retail sale atomically:
    1. Validates and deducts stock from batches (FIFO).
    2. Calculates actual unit selling prices and batch cost prices (COGS).
    3. Records InventoryMovement records.
    4. Creates Sale and SaleItem records.
    5. Prevents duplicate execution if client_uuid already exists.
    """
    if not client_uuid:
        client_uuid = str(uuid.uuid4())

    # Check idempotency
    existing = Sale.objects.filter(client_uuid=client_uuid).first()
    if existing:
        return existing, False, "عملية مكررة تم تسجيلها بالفعل"

    discount_amount = Decimal(str(discount_amount or 0))

    with transaction.atomic():
        # Generate Invoice Number
        date_str = timezone.now().strftime("%Y%m%d")
        last_today = Sale.objects.filter(invoice_number__startswith=f"INV-{date_str}").count()
        invoice_number = f"INV-{date_str}-{(last_today + 1):04d}"

        sale = Sale.objects.create(
            invoice_number=invoice_number,
            cashier=cashier,
            customer_name=customer_name or 'عميل نقدي',
            discount_amount=discount_amount,
            payment_method=payment_method,
            status='COMPLETED',
            client_uuid=client_uuid,
            is_offline_sync=is_offline,
            synced_at=timezone.now() if is_offline else None,
            notes=notes
        )

        subtotal = Decimal('0.00')
        total_cogs = Decimal('0.00')

        default_warehouse = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()

        for item in items_data:
            product_id = item['product_id']
            qty = Decimal(str(item['quantity']))
            custom_price = item.get('unit_price')

            product = Product.objects.select_for_update().get(id=product_id)
            unit_price = Decimal(str(custom_price)) if custom_price is not None else product.sale_price

            # Allocate from available batches (FIFO)
            batches = product.batches.filter(current_quantity__gt=0).order_by('received_date', 'id')
            remaining_to_deduct = qty

            allocated_batches = []
            for b in batches:
                if remaining_to_deduct <= 0:
                    break
                deduct_qty = min(b.current_quantity, remaining_to_deduct)
                allocated_batches.append((b, deduct_qty, b.cost_price))
                remaining_to_deduct -= deduct_qty

            # If not enough batch stock, use default product cost for remainder
            if remaining_to_deduct > 0:
                allocated_batches.append((None, remaining_to_deduct, product.default_cost_price))

            for batch, batch_qty, unit_cost in allocated_batches:
                if batch:
                    batch.current_quantity -= batch_qty
                    batch.save(update_fields=['current_quantity'])
                    wh = batch.warehouse
                else:
                    wh = default_warehouse

                # Create SaleItem
                item_total_price = batch_qty * unit_price
                item_total_cost = batch_qty * unit_cost
                subtotal += item_total_price
                total_cogs += item_total_cost

                SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    batch=batch,
                    quantity=batch_qty,
                    unit_price=unit_price,
                    unit_cost=unit_cost,
                    total_price=item_total_price,
                    total_cost=item_total_cost,
                    gross_profit=item_total_price - item_total_cost
                )

                # Record InventoryMovement
                balance_after = product.total_stock
                InventoryMovement.objects.create(
                    product=product,
                    batch=batch,
                    warehouse=wh,
                    movement_type='SALE',
                    quantity=batch_qty,
                    balance_after=balance_after,
                    reference_id=sale.invoice_number,
                    reason=f"مبيعات فاتورة {sale.invoice_number}",
                    user=cashier
                )

                # Log barcode activity match
                if product.barcode:
                    BarcodeEvent.objects.create(
                        barcode=product.barcode,
                        product=product,
                        cashier=cashier,
                        sale_ref=sale.invoice_number,
                        status='MATCHED',
                        notes=f"بيع ناجح - فاتورة {sale.invoice_number}"
                    )

        total_amount = max(subtotal - discount_amount, Decimal('0.00'))
        gross_profit = total_amount - total_cogs

        sale.subtotal = subtotal
        sale.total_amount = total_amount
        sale.total_cost = total_cogs
        sale.gross_profit = gross_profit
        sale.save()

        # Audit Log
        AuditLog.objects.create(
            user=cashier,
            action='CREATE',
            target_model='Sale',
            target_id=sale.invoice_number,
            description=f"تسجيل عملية بيع فاتورة {sale.invoice_number} بإجمالي {sale.total_amount} ج.م ومجمل ربح {sale.gross_profit} ج.م"
        )

        return sale, True, "تم تسجيل العملية بنجاح"


def process_return(cashier, original_sale_id, items_to_return, reason=''):
    """
    Handles customer returns accurately:
    1. Re-stocks only if item condition is SELLABLE.
    2. Calculates refund and updates financials.
    3. Keeps audit log trail.
    """
    with transaction.atomic():
        sale = Sale.objects.filter(id=original_sale_id).first() if original_sale_id else None
        date_str = timezone.now().strftime("%Y%m%d")
        last_ret = Return.objects.filter(return_number__startswith=f"RET-{date_str}").count()
        return_number = f"RET-{date_str}-{(last_ret + 1):04d}"

        return_obj = Return.objects.create(
            return_number=return_number,
            sale=sale,
            cashier=cashier,
            total_refund_amount=Decimal('0.00'),
            reason=reason or 'مرتجع بضاعة من عميل'
        )

        total_refund = Decimal('0.00')
        default_wh = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()

        for itm in items_to_return:
            product = Product.objects.get(id=itm['product_id'])
            qty = Decimal(str(itm['quantity']))
            unit_price = Decimal(str(itm['unit_price']))
            condition = itm.get('condition', 'SELLABLE')
            batch_id = itm.get('batch_id')
            batch = ProductBatch.objects.filter(id=batch_id).first() if batch_id else None

            item_refund = qty * unit_price
            total_refund += item_refund
            restocked = (condition == 'SELLABLE')

            ReturnItem.objects.create(
                return_record=return_obj,
                product=product,
                batch=batch,
                quantity=qty,
                unit_price=unit_price,
                condition=condition,
                returned_to_stock=restocked
            )

            if restocked:
                if batch:
                    batch.current_quantity += qty
                    batch.save(update_fields=['current_quantity'])
                    wh = batch.warehouse
                else:
                    wh = default_wh

                InventoryMovement.objects.create(
                    product=product,
                    batch=batch,
                    warehouse=wh,
                    movement_type='RETURN_IN',
                    quantity=qty,
                    balance_after=product.total_stock,
                    reference_id=return_number,
                    reason=f"مرتجع صالح من فاتورة {sale.invoice_number if sale else 'غير محددة'}",
                    user=cashier
                )

        return_obj.total_refund_amount = total_refund
        return_obj.save()

        if sale:
            sale.status = 'PARTIAL_REFUND'
            sale.save(update_fields=['status'])

        AuditLog.objects.create(
            user=cashier,
            action='CREATE',
            target_model='Return',
            target_id=return_number,
            description=f"تسجيل مرتجع {return_number} بمبلغ {total_refund} ج.م"
        )

        return return_obj


def sync_offline_sales(cashier, offline_sales_data):
    """
    Syncs offline queued transactions safely and idempotently.
    Returns: {
        'total': count,
        'success': count,
        'duplicates': count,
        'errors': list of errors
    }
    """
    summary = {'total': len(offline_sales_data), 'success': 0, 'duplicates': 0, 'errors': []}

    for item in offline_sales_data:
        client_uuid = item.get('client_uuid')
        if not client_uuid:
            summary['errors'].append("معرف عملية مفقود")
            continue

        existing = Sale.objects.filter(client_uuid=client_uuid).first()
        if existing:
            summary['duplicates'] += 1
            SyncOperation.objects.get_or_create(
                client_uuid=client_uuid,
                defaults={
                    'cashier': cashier,
                    'operation_type': 'OFFLINE_SALE',
                    'payload': str(item),
                    'status': 'DUPLICATE',
                    'reconciliation_notes': f"تم التجاهل لمنع التكرار - الفاتورة مسجلة برقم {existing.invoice_number}"
                }
            )
            continue

        try:
            sale, created, msg = process_sale(
                cashier=cashier,
                items_data=item['items'],
                customer_name=item.get('customer_name', 'عميل نقدي (أوفلاين)'),
                discount_amount=Decimal(str(item.get('discount_amount', 0))),
                payment_method=item.get('payment_method', 'CASH'),
                client_uuid=client_uuid,
                is_offline=True,
                notes=item.get('notes', 'مسجلة دون اتصال بالإنترنت')
            )
            if created:
                summary['success'] += 1
                SyncOperation.objects.create(
                    client_uuid=client_uuid,
                    cashier=cashier,
                    operation_type='OFFLINE_SALE',
                    payload=str(item),
                    status='SUCCESS',
                    reconciliation_notes=f"تم التزامن بنجاح وأنشئت الفاتورة {sale.invoice_number}"
                )
            else:
                summary['duplicates'] += 1
        except Exception as e:
            summary['errors'].append(f"خطأ في العملية {client_uuid}: {str(e)}")
            SyncOperation.objects.create(
                client_uuid=client_uuid,
                cashier=cashier,
                operation_type='OFFLINE_SALE',
                payload=str(item),
                status='FAILED',
                reconciliation_notes=f"خطأ أثناء المزامنة: {str(e)}"
            )

    return summary
