import os
from decimal import Decimal
from datetime import timedelta, date
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.accounts.models import User
from apps.core.models import SystemSettings, AuditLog
from apps.inventory.models import Category, Warehouse, Product, ProductBatch, InventoryMovement, BarcodeEvent
from apps.suppliers.models import Supplier, SupplierSchedule, PurchaseOrder, PurchaseOrderItem, SpecialDeal
from apps.expenses.models import ExpenseCategory, OperatingExpense, ExpensePayment
from apps.sales.models import Sale, SaleItem
from apps.intelligence.models import CalendarEvent
from apps.intelligence.services import run_complete_ai_pipeline


class Command(BaseCommand):
    help = "Seeds comprehensive realistic test data for AI-Powered Market Manager"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("بدء إنشاء بيانات السوق الذكي..."))

        # 1. System Settings
        settings_obj = SystemSettings.get_settings()
        settings_obj.store_name = "سوق المستقبل الذكي (AI Market)"
        settings_obj.phone = "01099887766"
        settings_obj.address = "مدينة نصر، القاهرة"
        settings_obj.currency = "ج.م"
        settings_obj.min_profit_margin_percent = Decimal('15.00')
        settings_obj.default_low_stock_limit = 10
        settings_obj.near_expiry_days = 30
        settings_obj.save()

        # 2. Users
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'first_name': 'زياد',
                'last_name': 'المدير',
                'email': 'admin@market.com',
                'role': 'ADMIN',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('admin1234')
            admin_user.save()

        cashier_user, _ = User.objects.get_or_create(
            username='cashier1',
            defaults={
                'first_name': 'أحمد',
                'last_name': 'الكاشير',
                'role': 'CASHIER',
            }
        )
        cashier_user.set_password('cashier123')
        cashier_user.save()

        accountant_user, _ = User.objects.get_or_create(
            username='accountant',
            defaults={
                'first_name': 'سارة',
                'last_name': 'المحاسبة',
                'role': 'ACCOUNTANT',
            }
        )
        accountant_user.set_password('acc1234')
        accountant_user.save()

        # 3. Warehouses
        main_wh, _ = Warehouse.objects.get_or_create(
            code='WH-MAIN',
            defaults={'name': 'المخزن الرئيسي الداخلي', 'location': 'البدروم والمخزن الخلفي', 'is_default': True}
        )
        pos_wh, _ = Warehouse.objects.get_or_create(
            code='WH-POS',
            defaults={'name': 'صالة العرض ونقطة البيع', 'location': 'الطابق الأرضي - صالة المحل', 'is_default': False}
        )

        # 4. Categories
        cat_dairy, _ = Category.objects.get_or_create(name='منتجات الألبان والأجبان', defaults={'icon': 'bi-cup-straw', 'description': 'حليب، جبن، زبادي'})
        cat_beverage, _ = Category.objects.get_or_create(name='المشروبات والعصائر', defaults={'icon': 'bi-droplet', 'description': 'مياه غازية، عصائر، شاي وقهوة'})
        cat_grocery, _ = Category.objects.get_or_create(name='البقوليات والسلع الأساسية', defaults={'icon': 'bi-basket', 'description': 'أرز، سكر، دقيق، مكرونة'})
        cat_oils, _ = Category.objects.get_or_create(name='الزيوت والسمن', defaults={'icon': 'bi-funnel', 'description': 'زيت ذرة، زيت عباد، سمن بلدي'})
        cat_cleaning, _ = Category.objects.get_or_create(name='المنظفات والعناية المنزلية', defaults={'icon': 'bi-stars', 'description': 'مساحيق غسيل، صابون، معقمات'})
        cat_snacks, _ = Category.objects.get_or_create(name='الحلويات والمقرمشات', defaults={'icon': 'bi-box2-heart', 'description': 'بسكويت، شوكولاتة، شيبسي'})

        # 5. Suppliers
        sup_juhayna, _ = Supplier.objects.get_or_create(
            company_name='شركة جهينة للصناعات الغذائية',
            defaults={
                'rep_name': 'م. تامر ممدوح',
                'phone': '01122334455',
                'lead_time_days': 2,
                'min_order_value': Decimal('1500.00'),
                'rating': Decimal('4.80')
            }
        )
        SupplierSchedule.objects.get_or_create(
            supplier=sup_juhayna, visit_day='SUN',
            defaults={'notes': 'زيارة أسبوعية كل أحد لتوريد الألبان والعصائر'}
        )

        sup_domty, _ = Supplier.objects.get_or_create(
            company_name='شركة دومتي للصناعات الغذائية',
            defaults={
                'rep_name': 'أ. كريم إبراهيم',
                'phone': '01233445566',
                'lead_time_days': 3,
                'min_order_value': Decimal('1200.00'),
                'rating': Decimal('4.70')
            }
        )
        SupplierSchedule.objects.get_or_create(
            supplier=sup_domty, visit_day='TUE',
            defaults={'notes': 'زيارة كل ثلاثاء لتوريد منتجات الجبن والزبادي'}
        )

        sup_savola, _ = Supplier.objects.get_or_create(
            company_name='شركة صافولا مصر (عافية وحلوة)',
            defaults={
                'rep_name': 'أ. مدحت فاروق',
                'phone': '01055667788',
                'lead_time_days': 4,
                'min_order_value': Decimal('3000.00'),
                'rating': Decimal('4.90')
            }
        )

        sup_nestle, _ = Supplier.objects.get_or_create(
            company_name='شركة نستله مصر',
            defaults={
                'rep_name': 'أ. وائل عصام',
                'phone': '01299887711',
                'lead_time_days': 3,
                'min_order_value': Decimal('2000.00'),
                'rating': Decimal('4.60')
            }
        )

        # 6. Products Catalog & Batches
        today = timezone.now().date()
        products_def = [
            {
                'name': 'حليب جهينة كامل الدسم 1 لتر',
                'code': 'JUH-MILK-1L',
                'barcode': '6223000100012',
                'category': cat_dairy,
                'brand': 'جهينة',
                'supplier': sup_juhayna,
                'cost': Decimal('34.00'),
                'price': Decimal('42.00'),
                'min_stock': Decimal('15.00'),
                'unit': 'piece',
                'batches': [
                    {'batch': 'JUH-B101', 'qty': Decimal('12.00'), 'expiry': today + timedelta(days=22), 'cost': Decimal('34.00')}, # near expiry for smart offer test!
                    {'batch': 'JUH-B102', 'qty': Decimal('45.00'), 'expiry': today + timedelta(days=90), 'cost': Decimal('34.00')},
                ]
            },
            {
                'name': 'جبنة دومتي بلس فيتا 500 جم',
                'code': 'DOM-FETA-500',
                'barcode': '6223000100029',
                'category': cat_dairy,
                'brand': 'دومتي',
                'supplier': sup_domty,
                'cost': Decimal('28.50'),
                'price': Decimal('36.00'),
                'min_stock': Decimal('12.00'),
                'unit': 'piece',
                'batches': [
                    {'batch': 'DOM-B201', 'qty': Decimal('35.00'), 'expiry': today + timedelta(days=120), 'cost': Decimal('28.50')},
                ]
            },
            {
                'name': 'زيت عافية ذرة نقي 800 مل',
                'code': 'AFIA-CORN-800',
                'barcode': '6223000100036',
                'category': cat_oils,
                'brand': 'عافية',
                'supplier': sup_savola,
                'cost': Decimal('68.00'),
                'price': Decimal('84.00'),
                'min_stock': Decimal('8.00'),
                'unit': 'piece',
                'batches': [
                    {'batch': 'AFIA-B301', 'qty': Decimal('24.00'), 'expiry': today + timedelta(days=300), 'cost': Decimal('68.00')},
                ]
            },
            {
                'name': 'أرز المطبخ مصري فاخر 1 كجم',
                'code': 'MTBK-RICE-1KG',
                'barcode': '6223000100043',
                'category': cat_grocery,
                'brand': 'المطبخ',
                'supplier': sup_savola,
                'cost': Decimal('31.00'),
                'price': Decimal('38.50'),
                'min_stock': Decimal('20.00'),
                'unit': 'piece',
                'batches': [
                    {'batch': 'RICE-B401', 'qty': Decimal('6.00'), 'expiry': today + timedelta(days=360), 'cost': Decimal('31.00')}, # low stock for restock test!
                ]
            },
            {
                'name': 'سكر الأسرة ناعم 1 كجم',
                'code': 'ESR-SUGAR-1KG',
                'barcode': '6223000100050',
                'category': cat_grocery,
                'brand': 'الأسرة',
                'supplier': sup_savola,
                'cost': Decimal('29.00'),
                'price': Decimal('35.00'),
                'min_stock': Decimal('15.00'),
                'unit': 'piece',
                'batches': [
                    {'batch': 'SUG-B501', 'qty': Decimal('50.00'), 'expiry': today + timedelta(days=365), 'cost': Decimal('29.00')},
                ]
            },
            {
                'name': 'شاي العروسة أسود فاخر 250 جم',
                'code': 'AROSA-TEA-250',
                'barcode': '6223000100067',
                'category': cat_beverage,
                'brand': 'العروسة',
                'supplier': sup_savola,
                'cost': Decimal('50.00'),
                'price': Decimal('60.00'),
                'min_stock': Decimal('10.00'),
                'unit': 'piece',
                'batches': [
                    {'batch': 'TEA-B601', 'qty': Decimal('30.00'), 'expiry': today + timedelta(days=400), 'cost': Decimal('50.00')},
                ]
            },
            {
                'name': 'نسكافيه كلاسيك سريع التحضير 200 جم',
                'code': 'NES-CLASSIC-200',
                'barcode': '6223000100074',
                'category': cat_beverage,
                'brand': 'نسكافيه',
                'supplier': sup_nestle,
                'cost': Decimal('165.00'),
                'price': Decimal('198.00'),
                'min_stock': Decimal('5.00'),
                'unit': 'piece',
                'batches': [
                    {'batch': 'NES-B701', 'qty': Decimal('15.00'), 'expiry': today + timedelta(days=500), 'cost': Decimal('165.00')},
                ]
            },
            {
                'name': 'مسحوق غسيل إريال أوتوماتيك 2.5 كجم',
                'code': 'ARIEL-AUTO-25',
                'barcode': '6223000100081',
                'category': cat_cleaning,
                'brand': 'إريال',
                'supplier': sup_savola,
                'cost': Decimal('175.00'),
                'price': Decimal('215.00'),
                'min_stock': Decimal('6.00'),
                'unit': 'piece',
                'batches': [
                    {'batch': 'AR-B801', 'qty': Decimal('18.00'), 'expiry': today + timedelta(days=700), 'cost': Decimal('175.00')},
                ]
            },
            {
                'name': 'بيبسي كولا كانز 330 مل',
                'code': 'PEP-CAN-330',
                'barcode': '6223000100098',
                'category': cat_beverage,
                'brand': 'بيبسي',
                'supplier': sup_juhayna,
                'cost': Decimal('11.50'),
                'price': Decimal('15.00'),
                'min_stock': Decimal('24.00'),
                'unit': 'piece',
                'batches': [
                    {'batch': 'PEP-B901', 'qty': Decimal('48.00'), 'expiry': today + timedelta(days=180), 'cost': Decimal('11.50')},
                ]
            },
            {
                'name': 'بسكويت أوريو شوكولاتة أصلي',
                'code': 'OREO-ORIG-40',
                'barcode': '6223000100104',
                'category': cat_snacks,
                'brand': 'أوريو',
                'supplier': sup_nestle,
                'cost': Decimal('7.00'),
                'price': Decimal('10.00'),
                'min_stock': Decimal('30.00'),
                'unit': 'piece',
                'batches': [
                    {'batch': 'OREO-B101', 'qty': Decimal('72.00'), 'expiry': today + timedelta(days=240), 'cost': Decimal('7.00')},
                ]
            },
        ]

        created_products = []
        for pdata in products_def:
            p, _ = Product.objects.get_or_create(
                code=pdata['code'],
                defaults={
                    'name': pdata['name'],
                    'barcode': pdata['barcode'],
                    'category': pdata['category'],
                    'brand': pdata['brand'],
                    'supplier': pdata['supplier'],
                    'default_cost_price': pdata['cost'],
                    'sale_price': pdata['price'],
                    'min_stock_limit': pdata['min_stock'],
                    'unit': pdata['unit'],
                }
            )
            created_products.append(p)

            for bdata in pdata['batches']:
                b, b_created = ProductBatch.objects.get_or_create(
                    product=p,
                    batch_number=bdata['batch'],
                    defaults={
                        'warehouse': main_wh,
                        'initial_quantity': bdata['qty'],
                        'current_quantity': bdata['qty'],
                        'cost_price': bdata['cost'],
                        'expiry_date': bdata['expiry'],
                        'received_date': today - timedelta(days=10),
                        'supplier': pdata['supplier']
                    }
                )
                if b_created:
                    InventoryMovement.objects.create(
                        product=p,
                        batch=b,
                        warehouse=main_wh,
                        movement_type='PURCHASE',
                        quantity=bdata['qty'],
                        balance_after=p.total_stock,
                        reference_id=f"INIT-{b.batch_number}",
                        reason="إيداع رصيد أولي للدفعات",
                        user=admin_user
                    )

        # 7. Operating Expenses Categories & Expenses
        cat_bills, _ = ExpenseCategory.objects.get_or_create(name='فواتير الكهرباء والمياه والغاز', defaults={'code': 'EXP-BILLS', 'icon': 'bi-lightning-charge', 'is_recurring': True})
        cat_rent, _ = ExpenseCategory.objects.get_or_create(name='إيجار المحل والمخزن', defaults={'code': 'EXP-RENT', 'icon': 'bi-building', 'is_recurring': True})
        cat_salaries, _ = ExpenseCategory.objects.get_or_create(name='مرتبات وأجور العاملين', defaults={'code': 'EXP-SALARIES', 'icon': 'bi-people', 'is_recurring': True})
        cat_maintenance, _ = ExpenseCategory.objects.get_or_create(name='صيانة وإصلاحات وثلاجات', defaults={'code': 'EXP-MAINT', 'icon': 'bi-wrench', 'is_recurring': False})
        cat_internet, _ = ExpenseCategory.objects.get_or_create(name='اتصالات وإنترنت وسيستم', defaults={'code': 'EXP-COMM', 'icon': 'bi-wifi', 'is_recurring': True})
        cat_supplies, _ = ExpenseCategory.objects.get_or_create(name='مستلزمات تشغيل وأكياس وبكر كاشير', defaults={'code': 'EXP-SUPP', 'icon': 'bi-bag', 'is_recurring': False})

        # Add historical expenses
        expenses_data = [
            {'title': 'فاتورة كهرباء شهر سبتمبر 2026', 'cat': cat_bills, 'amt': Decimal('3200.00'), 'date': today - timedelta(days=25), 'paid': True},
            {'title': 'فاتورة مياه شهر سبتمبر 2026', 'cat': cat_bills, 'amt': Decimal('450.00'), 'date': today - timedelta(days=25), 'paid': True},
            {'title': 'إيجار المحل لشهر أكتوبر 2026', 'cat': cat_rent, 'amt': Decimal('12000.00'), 'date': today - timedelta(days=10), 'paid': True},
            {'title': 'مرتبات العاملين والكاشير (نصف شهري)', 'cat': cat_salaries, 'amt': Decimal('9500.00'), 'date': today - timedelta(days=11), 'paid': True},
            {'title': 'صيانة دورية لثلاجات العرض والتبريد', 'cat': cat_maintenance, 'amt': Decimal('1250.00'), 'date': today - timedelta(days=8), 'paid': True},
            {'title': 'فاتورة خط الإنترنت والفايبر (شهر أكتوبر)', 'cat': cat_internet, 'amt': Decimal('650.00'), 'date': today - timedelta(days=5), 'paid': True},
            {'title': 'شراء بكر ورق فواتير كاشير وأكياس طباعة', 'cat': cat_supplies, 'amt': Decimal('1100.00'), 'date': today - timedelta(days=3), 'paid': True},
            # Anomalous expense to test AI Anomaly Detection!
            {'title': 'فاتورة استهلاك كهرباء غير معتادة لشهر أكتوبر', 'cat': cat_bills, 'amt': Decimal('8900.00'), 'date': today - timedelta(days=2), 'paid': False, 'due': today + timedelta(days=5)},
        ]

        for ed in expenses_data:
            exp, exp_created = OperatingExpense.objects.get_or_create(
                title=ed['title'],
                defaults={
                    'category': ed['cat'],
                    'amount': ed['amt'],
                    'paid_amount': ed['amt'] if ed['paid'] else Decimal('0.00'),
                    'expense_date': ed['date'],
                    'due_date': ed.get('due'),
                    'payee': 'الجهة المعنية',
                    'payment_status': 'PAID' if ed['paid'] else 'PENDING',
                    'created_by': accountant_user,
                    'notes': 'مصروف تشغيلي مسجل'
                }
            )
            if exp_created and ed['paid']:
                ExpensePayment.objects.create(
                    expense=exp,
                    amount=ed['amt'],
                    payment_date=ed['date'],
                    payment_method='CASH',
                    recorded_by=accountant_user
                )

        # 8. Historical Sales Simulation (over the last 12 days)
        if Sale.objects.count() < 10:
            for day_offset in range(12, -1, -1):
                sale_date = today - timedelta(days=day_offset)
                date_str = sale_date.strftime("%Y%m%d")
                
                # 2-3 sales per day
                for sale_idx in range(1, 3):
                    inv_num = f"INV-{date_str}-{sale_idx:04d}"
                    sale = Sale.objects.create(
                        invoice_number=inv_num,
                        cashier=cashier_user,
                        customer_name=f"عميل نقدي {sale_idx}",
                        payment_method='CASH' if sale_idx == 1 else 'CARD',
                        status='COMPLETED',
                        created_at=timezone.make_aware(timezone.datetime.combine(sale_date, timezone.datetime.min.time()) + timedelta(hours=10 + sale_idx*3))
                    )

                    # Add 2 items
                    sub = Decimal('0.00')
                    cost = Decimal('0.00')

                    p1 = created_products[(day_offset + sale_idx) % len(created_products)]
                    q1 = Decimal(str(2 + (day_offset % 3)))
                    t1_price = q1 * p1.sale_price
                    t1_cost = q1 * p1.default_cost_price
                    sub += t1_price
                    cost += t1_cost

                    SaleItem.objects.create(
                        sale=sale,
                        product=p1,
                        quantity=q1,
                        unit_price=p1.sale_price,
                        unit_cost=p1.default_cost_price,
                        total_price=t1_price,
                        total_cost=t1_cost,
                        gross_profit=t1_price - t1_cost
                    )

                    p2 = created_products[(day_offset + sale_idx + 3) % len(created_products)]
                    q2 = Decimal('1.00')
                    t2_price = q2 * p2.sale_price
                    t2_cost = q2 * p2.default_cost_price
                    sub += t2_price
                    cost += t2_cost

                    SaleItem.objects.create(
                        sale=sale,
                        product=p2,
                        quantity=q2,
                        unit_price=p2.sale_price,
                        unit_cost=p2.default_cost_price,
                        total_price=t2_price,
                        total_cost=t2_cost,
                        gross_profit=t2_price - t2_cost
                    )

                    sale.subtotal = sub
                    sale.total_amount = sub
                    sale.total_cost = cost
                    sale.gross_profit = sub - cost
                    sale.save()

        # 9. Smart Calendar Events
        ev1, _ = CalendarEvent.objects.get_or_create(
            title='شهر رمضان المبارك 1448 هـ',
            defaults={
                'event_type': 'RELIGIOUS',
                'start_date': today + timedelta(days=18),
                'end_date': today + timedelta(days=48),
                'description': 'موسم الصيام وزيادة الإقبال الكثيف على منتجات الألبان والأرز والسكر والزيوت والمشروبات الرمضانية.',
                'recurring_yearly': True
            }
        )
        ev1.target_categories.set([cat_dairy, cat_grocery, cat_oils, cat_beverage])

        ev2, _ = CalendarEvent.objects.get_or_create(
            title='موسم العودة للمدارس والجامعات',
            defaults={
                'event_type': 'ACADEMIC',
                'start_date': today + timedelta(days=4),
                'end_date': today + timedelta(days=25),
                'description': 'ارتفاع الطلب على ساندوتشات المدارس (الأجبان، العصائر، البسكويت، المقرمشات).',
                'recurring_yearly': True
            }
        )
        ev2.target_categories.set([cat_dairy, cat_snacks, cat_beverage])

        # 10. Special Deals (Feature 12)
        SpecialDeal.objects.get_or_create(
            title='عرض خاص: دفعة حليب جهينة مخفضة من المصنع مباشرة',
            defaults={
                'supplier': sup_juhayna,
                'product_name': 'حليب جهينة كامل الدسم 1 لتر',
                'linked_product': created_products[0],
                'quantity_offered': Decimal('200.00'),
                'deal_unit_cost': Decimal('29.00'),  # normal cost is 34.00
                'expected_selling_price': Decimal('42.00'),
                'extra_expenses': Decimal('200.00'),
                'expiry_date': today + timedelta(days=120),
                'offer_deadline': today + timedelta(days=5),
                'status': 'PROPOSED',
                'manager_decision_notes': 'فرصة شراء بسعر خصم 15% عن المعتاد، تحقق هامش ربح استثنائي يتجاوز 30%.'
            }
        )

        # 11. Run AI Pipeline
        self.stdout.write("تشغيل محرك الذكاء الاصطناعي لتوليد التنبؤات والتوصيات...")
        run_complete_ai_pipeline()

        self.stdout.write(self.style.SUCCESS("تم تجهيز وبناء بيانات السوق الذكي بالكامل بنجاح!"))
