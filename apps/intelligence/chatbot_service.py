"""
MarketAIChatbot Service - Interactive AI Agent for Market Manager
Provides conversational intelligence, live database queries, direct record creation,
and authenticated updates with Human-in-the-Loop security and audit logging across all 19 features.
"""

import re
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Q, F
from django.contrib.auth import authenticate
from django.urls import reverse

from apps.inventory.models import Product, ProductBatch, Category, Warehouse, InventoryMovement
from apps.sales.models import Sale, SaleItem, Return
from apps.expenses.models import OperatingExpense, ExpenseCategory
from apps.suppliers.models import Supplier, PurchaseOrder, SupplierSchedule
from apps.intelligence.models import CalendarEvent, Forecast, AIRecommendation
from apps.core.models import SystemSettings, AuditLog
from .gemini_service import GeminiMarketAgent


class MarketAIChatbot:
    """
    Central orchestration service for the AI Market Assistant.
    """

    @classmethod
    def process_message(cls, message, user=None, auth_data=None, pending_action=None, history=None):
        message = (message or "").strip()

        # 1. If user submitted credentials to execute a pending authenticated action
        if pending_action and auth_data:
            return cls.execute_authenticated_action(pending_action, auth_data, user)

        if not message:
            return {
                "reply": "مرحباً بك! أنا مساعد السوق الذكي 🤖 مدعوم بـ Google Gemini Pro. كيف يمكنني خدمتك اليوم؟ يمكنك سؤالي عن السلع، مبيعات اليوم، الأرباح، النواقص، أو استشارتي في أي موضوع تجاري أو عام.",
                "action": "greeting",
                "suggestions": ["مبيعات اليوم 📈", "النواقص في المخزن ⚠️", "سعر السكر كام؟ 📦", "تقرير الأرباح 📊", "أضف منتج جديد ➕", "سجل مصروف 💸"]
            }

        # 2. Check for modification intents (strictly requires password confirmation)
        update_match = cls.detect_update_intent(message)
        if update_match:
            return cls.handle_update_intent(update_match, user, auth_data)

        # 3. Check for creation intents (add product, expense, supplier, event)
        create_match = cls.detect_create_intent(message)
        if create_match:
            return cls.handle_create_intent(create_match, user)

        # 4. Check for navigation intents
        nav_match = cls.detect_navigation_intent(message)
        if nav_match:
            return cls.handle_navigation_intent(nav_match)

        # 5. Check for direct query intents (instant DB response across all 19 core features)
        query_match = cls.detect_query_intent(message)
        if query_match:
            return cls.handle_query_intent(query_match, user=user)

        # 6. Conversational Gemini Pro AI Agent (Store Grounding RAG with learning & multi-turn memory)
        try:
            gemini_res = GeminiMarketAgent.generate_response(message, user=user, history=history)
            if gemini_res:
                return gemini_res
        except Exception:
            pass

        return cls.handle_general_assistance(message)

    # =========================================================================
    # INTENT DETECTION
    # =========================================================================

    @classmethod
    def detect_update_intent(cls, text):
        price_patterns = [
            r'(?:عدل|غير|حدث|بدل)\s+(?:سعر\s+بيع|سعر|سعرها|سعره)\s+(.+?)\s+(?:إلى|الى|=|لـ|ل)\s+([0-9]+(?:\.[0-9]+)?)',
            r'(?:عدل|غير|حدث|بدل)\s+(?:تكلفة|سعر\s+شراء|سعر\s+التكلفة)\s+(.+?)\s+(?:إلى|الى|=|لـ|ل)\s+([0-9]+(?:\.[0-9]+)?)',
            r'(?:عدل|غير|حدث)\s+(?:حد\s+المخزون|الحد\s+الأدنى|الحد\s+الادنى)\s+(?:لـ|ل)?(.+?)\s+(?:إلى|الى|=|لـ|ل)\s+([0-9]+(?:\.[0-9]+)?)',
        ]

        m = re.search(price_patterns[0], text, re.IGNORECASE)
        if m:
            return {"type": "update_sale_price", "target_name": m.group(1).strip(), "new_value": m.group(2).strip()}

        m = re.search(price_patterns[1], text, re.IGNORECASE)
        if m:
            return {"type": "update_cost_price", "target_name": m.group(1).strip(), "new_value": m.group(2).strip()}

        m = re.search(price_patterns[2], text, re.IGNORECASE)
        if m:
            return {"type": "update_min_stock", "target_name": m.group(1).strip(), "new_value": m.group(2).strip()}

        return None

    @classmethod
    def detect_create_intent(cls, text):
        if any(w in text for w in ["أضف منتج", "اضف منتج", "سجل منتج", "منتج جديد", "إضافة منتج", "اضافة منتج"]):
            return {"entity": "product", "text": text}
        # Only treat as expense creation if an amount is present
        if any(w in text for w in ["سجل مصروف", "أضف مصروف", "اضف مصروف", "تسجيل مصروف", "مصروف جديد", "دفع مصروف"]):
            if re.search(r'[0-9]+', text):
                return {"entity": "expense", "text": text}
            else:
                return None  # Let it fall through to expenses guide / query handler
        if any(w in text for w in ["أضف مورد", "اضف مورد", "مورد جديد", "تسجيل مورد"]):
            return {"entity": "supplier", "text": text}
        if any(w in text for w in ["أضف مناسبة", "اضف مناسبة", "أضف موسم", "اضف موسم", "مناسبة جديدة"]):
            return {"entity": "calendar_event", "text": text}
        return None

    @classmethod
    def detect_navigation_intent(cls, text):
        nav_map = {
            "pos": ["كاشير", "نقطة البيع", "بيع جديد", "شاشة البيع", "pos"],
            "inventory": ["دليل المنتجات", "المخزون", "السلع", "المخزن", "المستودع"],
            "financial": ["الأرباح", "التقارير المالية", "تقرير الأرباح", "صافي الربح", "السيولة"],
            "expenses": ["المصروفات", "الفواتير", "سجل المصروفات", "مصاريف"],
            "suppliers": ["الموردين", "الموردون", "الشركات"],
            "intelligence": ["مركز الذكاء", "التوصيات", "الذكاء الاصطناعي", "ai"],
            "calendar": ["التقويم", "المناسبات", "المواسم"],
            "backup": ["نسخ احتياطي", "النسخ الاحتياطي", "استعادة"],
        }
        for page_key, keywords in nav_map.items():
            if any(k in text for k in keywords):
                if any(v in text for v in ["عايز اروح", "وديني", "افتح", "اذهب الى", "صفحة", "شاشة", "انتقل"]):
                    return page_key
        return None

    @classmethod
    def detect_query_intent(cls, text):
        t = text.strip()
        if any(w in t for w in ["مبيعات اليوم", "مبيعات النهارده", "كم بعنا اليوم", "ايراد اليوم"]):
            return "today_sales"
        if any(w in t for w in ["نواقص", "النواقص", "منخفض المخزون", "قرب يخلص", "ناقص", "نفاد", "نواقص في المخزن"]):
            return "low_stock"
        if any(w in t for w in ["صلاحية", "منتهي الصلاحية", "قريب الانتهاء", "تاريخ الصلاحية", "الصلاحية", "متابعة الصلاحية"]):
            return "near_expiry"
        if any(w in t for w in ["تحليل الأرباح", "تقرير الأرباح", "صافي الربح", "مجمل الربح", "حساب الربح", "السيولة لهذا الشهر", "تقرير الأرباح والسيولة"]):
            return "financial_summary"
        if any(w in t for w in ["جدولة الموردين", "أوامر الشراء", "مواعيد زيارة الموردين", "جدول الموردين", "أمر شراء", "مواعيد زيارة"]):
            return "suppliers_scheduling"
        if any(w in t for w in ["العروض الذكية", "اقتراحات العروض", "الخصومات", "عروض وخصومات", "تخفيضات"]):
            return "smart_offers"
        if any(w in t for w in ["التنبؤ بالطلب", "توقعات الطلب", "المواسم", "مناسبات", "المناسبات", "الطلب والمواسم", "التنبؤ بالطلب والمواسم"]):
            return "demand_forecast_seasons"
        if any(w in t for w in ["فحص التناقضات", "الشذوذ", "التناقضات", "تجاوزات", "فروق الجرد", "فحص التناقضات والشذوذ"]):
            return "anomalies_audit"
        if any(w in t for w in ["تسجيل المصروفات", "مصاريف الشهر", "مصروفات الشهر", "فواتير الشهر", "المصروفات التشغيلية"]):
            return "month_expenses"
        if any(w in t for w in ["استشارة ذكاء الأعمال", "ازاي ازود ارباح", "ازاي اكسب", "نصيحة", "استشارة", "تطوير المتجر"]):
            return "business_consulting"
        return None

    # =========================================================================
    # INTENT HANDLERS
    # =========================================================================

    @classmethod
    def handle_update_intent(cls, match, user=None, auth_data=None):
        target_name = match.get("target_name")
        new_val_str = match.get("new_value")
        intent_type = match.get("type")

        clean_name = re.sub(r'^(سعر\s+بيع|سعر|تكلفة|حد\s+المخزون)\s+', '', target_name).strip()
        product = Product.objects.filter(is_active=True).filter(
            Q(name__icontains=clean_name) | Q(code__iexact=clean_name) | Q(barcode__iexact=clean_name)
        ).first()

        if not product:
            return {
                "reply": f"عذراً، لم أتمكن من العثور على منتج باسم أو كود '{clean_name}'. يرجى التأكد من اسم السلعة والمحاولة مرة أخرى.",
                "action": "error",
                "suggestions": ["عرض دليل المنتجات 📦", "النواقص في المخزن ⚠️"]
            }

        try:
            new_value = float(new_val_str)
        except ValueError:
            return {"reply": "يرجى تحديد قيمة رقمية صحيحة للتعديل.", "action": "error"}

        field_map = {
            "update_sale_price": ("sale_price", "سعر البيع", float(product.sale_price)),
            "update_cost_price": ("default_cost_price", "سعر التكلفة", float(product.default_cost_price)),
            "update_min_stock": ("min_stock_limit", "الحد الأدنى للمخزون", int(product.min_stock_limit)),
        }
        field_name, action_title, old_value = field_map[intent_type]

        pending_action = {
            "type": "update_product",
            "product_id": product.id,
            "product_name": product.name,
            "field_name": field_name,
            "action_title": action_title,
            "old_value": old_value,
            "new_value": new_value
        }

        return {
            "reply": (
                f"⚠️ **طلب تعديل بيانات حساسة:**\n\n"
                f"• السلعة: **{product.name}**\n"
                f"• التعديل المطلوب: **{action_title}**\n"
                f"• القيمة الحالية: `{old_value}` ← القيمة الجديدة: `{new_value}`\n\n"
                f"🔒 **تأكيد الأمان:** لحماية بيانات المتجر والمخزون، يرجى تأكيد كلمة المرور للمتابعة والتنفيذ في النظام."
            ),
            "action": "auth_required",
            "auth_required": True,
            "pending_action": pending_action
        }

    @classmethod
    def execute_authenticated_action(cls, pending_action, auth_data, request_user=None):
        username = auth_data.get("username", "").strip()
        password = auth_data.get("password", "")

        user = authenticate(username=username, password=password)
        if not user:
            return {
                "reply": "❌ **فشل التحقق من الهوية:** اسم المستخدم أو كلمة المرور غير صحيحة. تم إلغاء العملية لحماية النظام.",
                "action": "auth_failed"
            }

        if getattr(user, 'role', '') not in ['ADMIN', 'MANAGER'] and not user.is_superuser:
            return {
                "reply": "⛔ **تم رفض العملية:** حسابك لا يملك صلاحية المدير أو المسؤول (Manager/Admin) لتعديل الأسعار والمخزون.",
                "action": "permission_denied"
            }

        action_type = pending_action.get("type")
        if action_type == "update_product":
            product_id = pending_action.get("product_id")
            field_name = pending_action.get("field_name")
            new_value = pending_action.get("new_value")
            action_title = pending_action.get("action_title")
            old_value = pending_action.get("old_value")

            try:
                prod = Product.objects.get(id=product_id)
                setattr(prod, field_name, Decimal(str(new_value)) if field_name != 'min_stock_limit' else int(new_value))
                prod.save(update_fields=[field_name, 'updated_at'])

                AuditLog.objects.create(
                    user=user,
                    action='PRICE_CHANGE' if 'price' in field_name else 'INVENTORY_ADJUST',
                    target_model='Product',
                    target_id=str(prod.id),
                    description=f"تعديل {action_title} للمنتج '{prod.name}' بواسطة المساعد الذكي من {old_value} إلى {new_value}"
                )

                return {
                    "reply": (
                        f"✅ **تم التحقق بنجاح وتحديث البيانات في النظام:**\n\n"
                        f"• المنتج: **{prod.name}**\n"
                        f"• {action_title}: تم التعديل من `{old_value}` إلى **`{new_value}`** بنجاح.\n"
                        f"• تم توثيق العملية في سجل تدقيق النظام باسم: **{user.get_full_name() or user.username}**."
                    ),
                    "action": "success",
                    "card": {
                        "title": prod.name,
                        "description": f"سعر البيع: {prod.sale_price:,.2f} ج.م | الرصيد: {prod.total_stock}",
                        "url": reverse("inventory:product_edit", args=[prod.id]),
                        "button_text": "عرض / تعديل السلعة في المخزن 📦"
                    }
                }
            except Product.DoesNotExist:
                return {"reply": "عذراً، المنتج لم يعد موجوداً في قاعدة البيانات.", "action": "error"}

        return {"reply": "نوع الإجراء غير معروف.", "action": "error"}

    @classmethod
    def handle_create_intent(cls, match, user=None):
        entity = match.get("entity")
        text = match.get("text")

        if entity == "product":
            name_m = re.search(r'(?:أضف منتج|اضف منتج|سجل منتج|منتج جديد|إضافة منتج|اضافة منتج)\s*[:\-]?\s*(.+?)(?:،|,|\s+سعر|\s+تكلفة|\s+كود|\s+باركود|$)', text)
            prod_name = name_m.group(1).strip() if name_m else "منتج جديد"

            sell_m = re.search(r'(?:سعر\s+بيع|سعر|بيعه)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)', text)
            cost_m = re.search(r'(?:سعر\s+شراء|تكلفة|شراء)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)', text)
            qty_m = re.search(r'(?:كمية|رصيد|عدد)\s*[:=]?\s*([0-9]+)', text)
            barcode_m = re.search(r'(?:باركود)\s*[:=]?\s*([0-9a-zA-Z_\-]+)', text)

            sell_price = Decimal(sell_m.group(1)) if sell_m else Decimal('10.00')
            cost_price = Decimal(cost_m.group(1)) if cost_m else Decimal('8.00')
            init_qty = int(qty_m.group(1)) if qty_m else 10

            safe_sku = f"SKU-{timezone.now().strftime('%m%d%H%M%S')}"
            barcode = barcode_m.group(1).strip() if barcode_m else f"622{timezone.now().strftime('%y%m%d%H%M')}"

            cat = Category.objects.first()
            if not cat:
                cat = Category.objects.create(name="أغذية وبقالة")

            prod = Product.objects.create(
                name=prod_name,
                code=safe_sku,
                barcode=barcode,
                category=cat,
                sale_price=sell_price,
                default_cost_price=cost_price,
                min_stock_limit=5,
                is_active=True
            )

            wh = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()
            if not wh:
                wh = Warehouse.objects.create(name="المخزن الرئيسي", code="WH-MAIN", is_default=True)

            ProductBatch.objects.create(
                product=prod,
                warehouse=wh,
                batch_number=f"B-{timezone.now().strftime('%y%m%d')}",
                initial_quantity=Decimal(str(init_qty)),
                current_quantity=Decimal(str(init_qty)),
                cost_price=cost_price
            )

            AuditLog.objects.create(
                user=user,
                action='CREATE_PRODUCT',
                target_model='Product',
                target_id=str(prod.id),
                description=f"إضافة منتج جديد '{prod.name}' عبر المساعد الذكي بسعر بيع {prod.sale_price}"
            )

            return {
                "reply": f"🎉 **تمت إضافة المنتج الجديد بنجاح في قاعدة البيانات:**\n\n• الاسم: **{prod.name}**\n• سعر البيع: **{prod.sale_price:,.2f} ج.م**\n• سعر التكلفة: **{prod.default_cost_price:,.2f} ج.م**\n• الباركود: `{prod.barcode}`",
                "action": "created",
                "card": {
                    "title": prod.name,
                    "description": f"الكود: {prod.code} | الباركود: {prod.barcode}",
                    "url": reverse("inventory:product_edit", args=[prod.id]),
                    "button_text": "تعديل تفاصيل السلعة أو إضافة دفعات 📦"
                }
            }

        elif entity == "expense":
            amount_m = re.search(r'([0-9]+(?:\.[0-9]+)?)', text)
            amount = Decimal(amount_m.group(1)) if amount_m else Decimal('100.00')

            title_m = re.search(r'(?:مصروف|فاتورة)\s+(.+?)(?:\s+بقيمة|\s+بمبلغ|\s+[0-9]|$)', text)
            title = title_m.group(1).strip() if title_m else "مصروف تشغيلي"

            cat = ExpenseCategory.objects.first()
            if not cat:
                cat = ExpenseCategory.objects.create(name="مصروفات عامة")

            exp = OperatingExpense.objects.create(
                title=title,
                amount=amount,
                expense_date=timezone.localdate(),
                category=cat,
                payment_status='PAID',
                created_by=user
            )

            AuditLog.objects.create(
                user=user,
                action='CREATE_EXPENSE',
                target_model='OperatingExpense',
                target_id=str(exp.id),
                description=f"تسجيل مصروف '{exp.title}' بقيمة {exp.amount} بواسطة المساعد الذكي"
            )

            return {
                "reply": f"💸 **تم تسجيل المصروف التشغيلي بنجاح:**\n\n• البند: **{exp.title}**\n• المبلغ: **{exp.amount:,.2f} ج.م**\n• التاريخ: **{exp.expense_date}**\n• الحالة: مدفوع بالكامل ✅",
                "action": "created",
                "card": {
                    "title": f"مصروف: {exp.title}",
                    "description": f"المبلغ: {exp.amount:,.2f} ج.م - مدفوع",
                    "url": reverse("expenses:expenses_list"),
                    "button_text": "عرض سجل المصروفات التشغيلية 🧾"
                }
            }

        elif entity == "supplier":
            name_m = re.search(r'(?:مورد|شركة)\s+(.+?)(?:\s+هاتف|\s+تليفون|\s+[0-9]|$)', text)
            comp_name = name_m.group(1).strip() if name_m else "مورد جديد"

            phone_m = re.search(r'(?:هاتف|تليفون|موبايل)?\s*([0-9]{8,14})', text)
            phone = phone_m.group(1).strip() if phone_m else "01000000000"

            sup = Supplier.objects.create(
                company_name=comp_name,
                phone=phone,
                lead_time_days=2,
                is_active=True
            )

            AuditLog.objects.create(
                user=user,
                action='CREATE_SUPPLIER',
                target_model='Supplier',
                target_id=str(sup.id),
                description=f"تسجيل مورد جديد '{sup.company_name}' بواسطة المساعد الذكي"
            )

            return {
                "reply": f"🚚 **تم تسجيل المورد الجديد بنجاح:**\n\n• اسم الشركة: **{sup.company_name}**\n• الهاتف: `{sup.phone}`\n• مهلة التوريد: {sup.lead_time_days} أيام",
                "action": "created",
                "card": {
                    "title": sup.company_name,
                    "description": f"هاتف: {sup.phone}",
                    "url": reverse("suppliers:suppliers_list"),
                    "button_text": "عرض قائمة الموردين 🚚"
                }
            }

        return {"reply": "تم استلام الطلب ولكن البيانات غير مكتملة.", "action": "info"}

    @classmethod
    def handle_navigation_intent(cls, page_key):
        nav_routes = {
            "pos": (reverse("sales:pos"), "شاشة نقطة البيع (الكاشير)", "🛒"),
            "inventory": (reverse("inventory:products_list"), "دليل المنتجات والمخزون", "📦"),
            "financial": (reverse("core:financial_report"), "تقرير الأرباح والسيولة المالية", "📊"),
            "expenses": (reverse("expenses:expenses_list"), "سجل المصروفات التشغيلية", "🧾"),
            "suppliers": (reverse("suppliers:suppliers_list"), "دليل الموردين وأذونات الشراء", "🚚"),
            "intelligence": (reverse("intelligence:center"), "مركز الذكاء الاصطناعي والتوصيات", "🤖"),
            "calendar": (reverse("intelligence:calendar_events"), "التقويم الذكي والمواسم", "📅"),
            "backup": (reverse("core:settings"), "النسخ الاحتياطي وإعدادات النظام", "⚙️"),
        }
        url, title, icon = nav_routes.get(page_key, (reverse("core:dashboard"), "لوحة التحكم", "🏠"))
        return {
            "reply": f"تفضل! يمكنك التوجه إلى **{title}** مباشرة بالضغط على الزر أدناه:",
            "action": "navigation",
            "url": url,
            "buttons": [{"text": f"{icon} الانتقال إلى {title}", "url": url}]
        }

    # =========================================================================
    # CORE FEATURES DIRECT QUERY HANDLERS (Blazing fast & 100% reliable)
    # =========================================================================

    @classmethod
    def handle_query_intent(cls, query_type, user=None):
        today = timezone.localdate()

        if query_type == "today_sales":
            sales = Sale.objects.filter(created_at__date=today, status='COMPLETED')
            tot = sum((s.total_amount for s in sales), Decimal('0.00'))
            cogs = sum((s.total_cost for s in sales), Decimal('0.00'))
            gross = tot - cogs
            margin = (gross / tot * Decimal('100.0')) if tot > 0 else Decimal('0.0')

            return {
                "reply": (
                    f"📈 **مبيعات اليوم ({today}):**\n\n"
                    f"• إجمالي الإيرادات: **{tot:,.2f} ج.م**\n"
                    f"• تكلفة البضاعة المباعة (COGS): **{cogs:,.2f} ج.م**\n"
                    f"• مجمل الربح المحقق: **{gross:,.2f} ج.م** (هامش {margin:.1f}%)\n"
                    f"• عدد العمليات المكتملة: **{sales.count()} فاتورة**"
                ),
                "action": "stats",
                "buttons": [
                    {"text": "فتح الكاشير (POS) 🛒", "url": reverse("sales:pos")},
                    {"text": "تقرير الأرباح والسيولة 📊", "url": reverse("core:financial_report")}
                ]
            }

        elif query_type == "low_stock":
            active_prods = list(Product.objects.filter(is_active=True).prefetch_related('batches', 'category'))
            low_prods = [p for p in active_prods if p.is_low_stock][:10]

            if not low_prods:
                return {
                    "reply": "✅ **ممتاز!** جميع المنتجات في المتجر تتمتع بمستويات مخزون آمنة أعلى من الحد الأدنى لإعادة الطلب.",
                    "action": "low_stock",
                    "buttons": [
                        {"text": "دليل المنتجات والمخزون 📦", "url": reverse("inventory:products_list")},
                        {"text": "أوامر الشراء 🚚", "url": reverse("suppliers:orders_list")}
                    ]
                }

            items = [f"• **{p.name}** [كود: `{p.code}`]: المتبقي `{p.total_stock}` (الحد الأدنى: `{p.min_stock_limit}`)" for p in low_prods]
            return {
                "reply": f"⚠️ **تنبيه النواقص في المخزن ({len(low_prods)} سلع بحاجة لإعادة طلب):**\n\n" + "\n".join(items),
                "action": "low_stock",
                "buttons": [
                    {"text": "دليل المنتجات والمخزون 📦", "url": reverse("inventory:products_list")},
                    {"text": "إنشاء أمر شراء مع الموردين 🚚", "url": reverse("suppliers:orders_list")}
                ]
            }

        elif query_type == "near_expiry":
            batches = ProductBatch.objects.filter(
                current_quantity__gt=0,
                expiry_date__isnull=False,
                expiry_date__lte=today + timezone.timedelta(days=45)
            ).select_related('product', 'warehouse').order_by('expiry_date')[:8]

            if not batches:
                return {
                    "reply": "✅ **حالة الصلاحية ممتازة!** لا توجد دفعات قريبة من تاريخ انتهاء الصلاحية خلال الـ 45 يوماً القادمة.",
                    "action": "info",
                    "buttons": [{"text": "دليل المخزون 📦", "url": reverse("inventory:products_list")}]
                }

            items = [f"• **{b.product.name}** (تشغيلة `{b.batch_number}`): ينتهي في `{b.expiry_date}` (المتبقي: `{b.current_quantity}` في {b.warehouse.name})" for b in batches]
            return {
                "reply": "⏳ **تنبيه السلع والدفعات القريبة من انتهاء الصلاحية:**\n\n" + "\n".join(items),
                "action": "info",
                "buttons": [
                    {"text": "اقتراح عروض وخصومات ذكية لتصريفها 🏷️", "url": reverse("intelligence:smart_offers")},
                    {"text": "دليل المنتجات والمخزون 📦", "url": reverse("inventory:products_list")}
                ]
            }

        elif query_type == "financial_summary":
            start_m = today.replace(day=1)
            m_sales = Sale.objects.filter(created_at__date__gte=start_m, created_at__date__lte=today, status='COMPLETED')
            m_rev = sum((s.total_amount for s in m_sales), Decimal('0.00'))
            m_cogs = sum((s.total_cost for s in m_sales), Decimal('0.00'))
            m_gross = m_rev - m_cogs
            m_exp = sum((e.amount for e in OperatingExpense.objects.filter(expense_date__gte=start_m, expense_date__lte=today)), Decimal('0.00'))
            net_op = m_gross - m_exp
            margin = (m_gross / m_rev * Decimal('100.0')) if m_rev > 0 else Decimal('0.0')

            return {
                "reply": (
                    f"📊 **الملخص المالي والربحي لهذا الشهر ({start_m.strftime('%B %Y')}):**\n\n"
                    f"• **صافي إيرادات المبيعات**: **{m_rev:,.2f} ج.م**\n"
                    f"• **تكلفة البضاعة المباعة (COGS)**: **{m_cogs:,.2f} ج.م**\n"
                    f"• **مجمل الربح**: **{m_gross:,.2f} ج.م** (هامش مجمل ربح: `{margin:.1f}%`)\n"
                    f"• **المصروفات التشغيلية المسجلة**: **{m_exp:,.2f} ج.م**\n"
                    f"• 💰 **صافي الربح التشغيلي التقريبي**: **`{net_op:,.2f} ج.م`**\n\n"
                    f"*(ملاحظة: تم تطبيق الفصل المحاسبي التام بين تكلفة البضاعة والمصروفات التشغيلية دون تكرار الخصم وفق معايير النظام)*"
                ),
                "action": "stats",
                "buttons": [
                    {"text": "تقرير الأرباح والسيولة الكامل 📊", "url": reverse("core:financial_report")},
                    {"text": "سجل المصروفات التشغيلية 🧾", "url": reverse("expenses:expenses_list")}
                ]
            }

        elif query_type == "suppliers_scheduling":
            suppliers = Supplier.objects.filter(is_active=True).prefetch_related('schedules')[:6]
            recent_pos = PurchaseOrder.objects.select_related('supplier').order_by('-order_date')[:4]

            sup_lines = []
            for s in suppliers:
                schedules = list(s.schedules.all())
                days = ", ".join([sch.get_visit_day_display() for sch in schedules]) if schedules else "حسب الطلب"
                sup_lines.append(f"• **{s.company_name}** | هاتف: `{s.phone}` | موعد الزيارة: **{days}** | مهلة التوريد: {s.lead_time_days} أيام")

            po_lines = []
            for po in recent_pos:
                po_lines.append(f"• طلب #{po.po_number} من **{po.supplier.company_name}**: {po.total_amount:,.2f} ج.م (الحالة: **{po.get_status_display()}**)")

            reply_text = "🚚 **جدولة الموردين ومواعيد التوريد الذكية:**\n\n"
            reply_text += "**دليل الشركات ومواعيد المندوبين:**\n" + ("\n".join(sup_lines) if sup_lines else "لا يوجد موردين مسجلين حالياً.")
            if po_lines:
                reply_text += "\n\n**أحدث أوامر الشراء:**\n" + "\n".join(po_lines)

            return {
                "reply": reply_text,
                "action": "stats",
                "buttons": [
                    {"text": "أوامر الشراء الذكية 📋", "url": reverse("suppliers:orders_list")},
                    {"text": "دليل الموردين والشركات 🚚", "url": reverse("suppliers:suppliers_list")},
                    {"text": "مواعيد زيارات المندوبين 📅", "url": reverse("suppliers:schedules_list")}
                ]
            }

        elif query_type == "smart_offers":
            offers = AIRecommendation.objects.filter(recommendation_type='SMART_OFFER', status='PENDING')[:4]
            # Also find near-expiry products to recommend
            near_exp = ProductBatch.objects.filter(current_quantity__gt=0, expiry_date__isnull=False, expiry_date__lte=today + timezone.timedelta(days=35)).select_related('product')[:3]

            offer_lines = []
            for o in offers:
                offer_lines.append(f"• **{o.title}**: {o.rationale} (مستوى الثقة: {o.confidence_level}%)")

            if near_exp:
                for b in near_exp:
                    offer_lines.append(f"• **مقترح تصريف**: سلعة `{b.product.name}` (دفعة تنتهي {b.expiry_date}) - يفضل تقديم عرض تخفيض 10% أو باقة 2+1 لحماية رأس المال.")

            if not offer_lines:
                offer_lines.append("• لا توجد مقترحات عروض معلقة حالياً؛ مستويات البيع وحركة السلع مستقرة ومتوازنة.")

            return {
                "reply": (
                    "🏷️ **اقتراحات العروض الترويجية والخصومات الذكية:**\n\n" +
                    "\n".join(offer_lines) +
                    "\n\n*(تعتمد العروض على الحفاظ الصارم على حد أدنى لهامش الربح وعدم الإضرار بالربحية الصافية)*"
                ),
                "action": "stats",
                "buttons": [
                    {"text": "لوحة العروض والخصومات الذكية 🏷️", "url": reverse("intelligence:smart_offers")},
                    {"text": "مركز التوصيات والقرارات 🤖", "url": reverse("intelligence:center")}
                ]
            }

        elif query_type == "demand_forecast_seasons":
            events = CalendarEvent.objects.filter(end_date__gte=today).order_by('start_date')[:4]
            forecasts = Forecast.objects.select_related('product').order_by('-forecast_date')[:5]

            ev_lines = []
            for ev in events:
                ev_lines.append(f"• 🌙 **{ev.title}** ({ev.get_event_type_display()}): من `{ev.start_date}` إلى `{ev.end_date}` - {ev.description or 'زيادة متوقعة في الطلب'}")

            fc_lines = []
            for fc in forecasts:
                fc_lines.append(f"• **{fc.product.name}**: متوقع بيع `{fc.predicted_quantity}` قطعة خلال {fc.horizon_days} أيام (دقة التوقع: {fc.confidence_score}%)")

            reply_text = "🌙 **التنبؤ بالطلب والذكاء الموسمي والمناسبات:**\n\n"
            reply_text += "**المواسم والمناسبات القادمة:**\n" + ("\n".join(ev_lines) if ev_lines else "لا توجد مواسم مسجلة حالياً.")
            if fc_lines:
                reply_text += "\n\n**توقعات الطلب المستقبلي على السلع:**\n" + "\n".join(fc_lines)

            return {
                "reply": reply_text,
                "action": "stats",
                "buttons": [
                    {"text": "التنبؤ المستقبلي بالطلب 📈", "url": reverse("intelligence:forecasts_list")},
                    {"text": "التقويم والمواسم الذكية 📅", "url": reverse("intelligence:calendar_events")}
                ]
            }

        elif query_type == "anomalies_audit":
            anomalies = AIRecommendation.objects.filter(recommendation_type='ANOMALY', status='PENDING')[:4]
            recent_logs = AuditLog.objects.order_by('-created_at')[:4]

            anom_lines = []
            for an in anomalies:
                anom_lines.append(f"• ⚠️ **{an.title}**: {an.rationale}")

            log_lines = []
            for log in recent_logs:
                log_lines.append(f"• `{log.created_at.strftime('%H:%M')}` - {log.get_action_display()}: {log.description[:80]}")

            reply_text = "🛡️ **فحص التناقضات والشذوذ والرقابة التشغيلية:**\n\n"
            if anom_lines:
                reply_text += "**تنبيهات الشذوذ بانتظار المراجعة البشرية:**\n" + "\n".join(anom_lines) + "\n\n"
            else:
                reply_text += "✅ **لا توجد تناقضات حرجة مسجلة حالياً:** حركات البيع متطابقة مع المخزون ولا توجد فروق جرد غير مبررة.\n\n"

            if log_lines:
                reply_text += "**آخر عمليات سجل التدقيق (Audit Log):**\n" + "\n".join(log_lines)

            return {
                "reply": reply_text,
                "action": "stats",
                "buttons": [
                    {"text": "رصد الشذوذ والتجاوزات 🛡️", "url": reverse("intelligence:anomalies_list")},
                    {"text": "سجل تدقيق النظام 📋", "url": reverse("core:settings")}
                ]
            }

        elif query_type == "month_expenses":
            return cls.handle_expenses_overview()

        elif query_type == "business_consulting":
            return cls.handle_business_consulting()

        return {"reply": "تم استلام استفسارك وسأساعدك فيه فوراً.", "action": "info"}

    @classmethod
    def handle_expenses_overview(cls):
        today = timezone.localdate()
        start_m = today.replace(day=1)
        expenses = OperatingExpense.objects.filter(expense_date__gte=start_m, expense_date__lte=today)
        tot_exp = sum((e.amount for e in expenses), Decimal('0.00'))
        paid_exp = sum((e.amount for e in expenses.filter(payment_status='PAID')), Decimal('0.00'))
        pending_exp = tot_exp - paid_exp

        recent_exp = list(expenses.order_by('-expense_date')[:4])
        lines = [f"• **{e.title}**: `{e.amount:,.2f} ج.م` ({e.get_payment_status_display()})" for e in recent_exp]

        return {
            "reply": (
                f"🧾 **إدارة المصروفات التشغيلية ({start_m.strftime('%B %Y')}):**\n\n"
                f"• إجمالي المصروفات: **{tot_exp:,.2f} ج.م**\n"
                f"• المسدد فعلياً: **{paid_exp:,.2f} ج.م** | المستحق أو المعلق: **{pending_exp:,.2f} ج.م**\n\n"
                f"**أحدث الفواتير المسجلة:**\n" + ("\n".join(lines) if lines else "لا توجد فواتير مسجلة هذا الشهر.") + "\n\n"
                f"💡 **طريقة تسجيل مصروف عبر الشات مباشرة:**\n"
                f"اكتب لي: `سجل مصروف كهرباء بقيمة 350` أو `سجل مصروف إيجار بقيمة 4000` وسأقوم بإضافته فوراً وتحديث القوائم المالية."
            ),
            "action": "stats",
            "buttons": [
                {"text": "سجل المصروفات والفواتير 🧾", "url": reverse("expenses:expenses_list")},
                {"text": "تقرير الأرباح والسيولة 📊", "url": reverse("core:financial_report")}
            ]
        }

    @classmethod
    def handle_business_consulting(cls):
        return {
            "reply": (
                f"💡 **استراتيجية الذكاء التجاري لتعظيم أرباح السوبر ماركت والسوق:**\n\n"
                f"### 1. هندسة الأسعار وهوامش الربح (Price & Margin Engineering):\n"
                f"• **السلع سريعة الدوران (Traffic Drivers)**: السكر، الزيت، الأرز. حافظ على أسعار منافسة وهامش ربح (3% - 6%) لجذب العملاء اليوميين.\n"
                f"• **السلع عالية الهامش (Profit Generators)**: التوابل، المقرمشات، المنظفات، الأجبان الخاصة. ارفع هامش ربحها إلى (20% - 35%) لتعويض السلع الأساسية.\n\n"
                f"### 2. زيادة متوسط سلة المشتريات (Basket Size Growth):\n"
                f"• طبق أسلوب **الترويج المتقاطع (Cross-Merchandising)**: ضع الشاي مباشرة بجانب السكر، والمشروبات الباردة بجانب المقرمشات.\n"
                f"• ضع عند نقطة الكاشير (Impulse Buy Area) سلعاً سريعة مثل اللبان والشوكولاتة والبطاريات.\n\n"
                f"### 3. تقليل الهدر والتالف (Loss & Waste Prevention):\n"
                f"• راقب الدفعات القريبة من الصلاحية قبل 30 يوماً؛ تصريفها بخصم 10% أو كعرض مجمع أفضل محاسبياً بـ 100% من تلفها وتحمل 0 عائد.\n\n"
                f"### 4. التفاوض الذكي مع الموردين:\n"
                f"• استفد من قسم **الصفقات الاستثنائية** بالمشروع لشراء كميات بخصومات كاش من الشركات ذات مهلة توريد سريعة."
            ),
            "action": "gemini_response",
            "buttons": [
                {"text": "تقرير الأرباح والسيولة 📊", "url": reverse("core:financial_report")},
                {"text": "فتح الكاشير (POS) 🛒", "url": reverse("sales:pos")},
                {"text": "دليل النواقص والمخزون 📦", "url": reverse("inventory:products_list")}
            ]
        }

    @classmethod
    def handle_general_assistance(cls, message):
        return {
            "reply": (
                "أهلاً بك يا مدير! أنا **مساعد السوق الذكي الشامل (Market AI)**.\n\n"
                "أنا جاهز ومتحكم في جميع المميزات الـ 19 الأساسية للنظام. يمكنك الضغط على أي زر أدناه أو توجيه أي سؤال تجاري أو إداري:"
            ),
            "action": "general_help",
            "buttons": [
                {"text": "مبيعات اليوم 📈", "url": reverse("sales:pos")},
                {"text": "النواقص في المخزن ⚠️", "url": reverse("inventory:products_list")},
                {"text": "تقرير الأرباح 📊", "url": reverse("core:financial_report")},
                {"text": "جدولة الموردين 🚚", "url": reverse("suppliers:suppliers_list")}
            ],
            "suggestions": [
                "مبيعات اليوم",
                "النواقص في المخزن",
                "المنتجات القريبة من انتهاء الصلاحية",
                "تقرير الأرباح والسيولة لهذا الشهر",
                "أوامر الشراء ومواعيد زيارة الموردين",
                "اقتراحات العروض الذكية والخصومات",
                "توقعات الطلب المستقبلي والمواسم",
                "فحص التناقضات والشذوذ في المبيعات والمخزون",
                "تسجيل المصروفات"
            ]
        }
