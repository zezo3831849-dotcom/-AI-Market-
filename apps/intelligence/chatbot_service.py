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
from apps.suppliers.models import Supplier, PurchaseOrder
from apps.intelligence.models import CalendarEvent, Forecast, AIRecommendation
from apps.core.models import SystemSettings, AuditLog
from .gemini_service import GeminiMarketAgent


class MarketAIChatbot:
    """
    Central orchestration service for the AI Market Assistant.
    """

    @classmethod
    def process_message(cls, message, user=None, auth_data=None, pending_action=None):
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

        # 5. Check for direct statistical queries
        query_match = cls.detect_query_intent(message)
        if query_match and query_match in ['today_sales', 'low_stock', 'near_expiry', 'month_expenses', 'financial_summary']:
            return cls.handle_query_intent(query_match)

        # 6. Conversational Gemini Pro AI Agent (Store Grounding RAG)
        try:
            gemini_res = GeminiMarketAgent.generate_response(message, user=user)
            if gemini_res:
                return gemini_res
        except Exception:
            pass

        # 7. Fallback to smart local assistant response
        if query_match:
            return cls.handle_query_intent(query_match)

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
        if any(w in text for w in ["سجل مصروف", "أضف مصروف", "اضف مصروف", "تسجيل مصروف", "مصروف جديد", "دفع مصروف"]):
            return {"entity": "expense", "text": text}
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
        if any(w in text for w in ["مبيعات اليوم", "مبيعات النهارده", "كم بعنا اليوم", "ايراد اليوم"]):
            return "today_sales"
        if any(w in text for w in ["نواقص", "النواقص", "منخفض المخزون", "قرب يخلص", "ناقص"]):
            return "low_stock"
        if any(w in text for w in ["صلاحية", "منتهي الصلاحية", "قريب الانتهاء", "تاريخ الصلاحية"]):
            return "near_expiry"
        if any(w in text for w in ["مصاريف الشهر", "مصروفات الشهر", "فواتير الشهر"]):
            return "month_expenses"
        if any(w in text for w in ["تقرير الأرباح", "صافي الربح", "مجمل الربح", "حساب الربح"]):
            return "financial_summary"
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

        return {"reply": "نوع العملية غير معتمد.", "action": "error"}

    @classmethod
    def handle_create_intent(cls, match, user=None):
        entity = match.get("entity")
        text = match.get("text", "")

        if entity == "product":
            name_m = re.search(r'(?:أضف|اضف|سجل|إضافة)\s+منتج(?:\s+جديد)?\s+(.+?)(?:\s+بسعر|\s+سعر|\s+تكلفة|\s+بـ|$)', text)
            prod_name = name_m.group(1).strip() if name_m else "منتج جديد"
            
            price_m = re.search(r'(?:سعر|بسعر)\s+([0-9]+(?:\.[0-9]+)?)', text)
            sale_price = Decimal(price_m.group(1)) if price_m else Decimal('10.00')

            cost_m = re.search(r'(?:تكلفة|بتكلفة)\s+([0-9]+(?:\.[0-9]+)?)', text)
            cost_price = Decimal(cost_m.group(1)) if cost_m else sale_price * Decimal('0.75')

            barcode_m = re.search(r'(?:باركود|كود)\s+([0-9a-zA-Z]+)', text)
            barcode = barcode_m.group(1).strip() if barcode_m else f"AUTO-{int(timezone.now().timestamp())}"

            cat = Category.objects.first()
            if not cat:
                cat = Category.objects.create(name="عام")

            prod = Product.objects.create(
                name=prod_name,
                code=f"PRD-{int(timezone.now().timestamp()) % 100000}",
                barcode=barcode,
                category=cat,
                sale_price=sale_price,
                default_cost_price=cost_price,
                min_stock_limit=5,
                unit='piece',
                is_active=True
            )

            AuditLog.objects.create(
                user=user,
                action='CREATE_PRODUCT',
                target_model='Product',
                target_id=str(prod.id),
                description=f"إنشاء منتج جديد '{prod.name}' بواسطة المساعد الذكي بسعر {prod.sale_price}"
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

    @classmethod
    def handle_query_intent(cls, query_type):
        today = timezone.localdate()

        if query_type == "today_sales":
            sales = Sale.objects.filter(created_at__date=today, status='COMPLETED')
            tot = sum((s.final_amount for s in sales), Decimal('0.00'))
            cogs = sum((s.total_cogs for s in sales), Decimal('0.00'))
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
            low_prods = Product.objects.filter(is_active=True, total_stock__lte=F('min_stock_limit'))[:8]
            if not low_prods:
                return {"reply": "✅ **ممتاز!** جميع المنتجات في المتجر تتمتع بمستويات مخزون آمنة أعلى من الحد الأدنى.", "action": "low_stock"}

            items = [f"• **{p.name}**: المتبقي `{p.total_stock}` (الحد الأدنى: `{p.min_stock_limit}`)" for p in low_prods]
            return {
                "reply": f"⚠️ **تنبيه النواقص في المخزن ({len(low_prods)} سلع بحاجة لإعادة طلب):**\n\n" + "\n".join(items),
                "action": "low_stock",
                "buttons": [
                    {"text": "دليل المنتجات والمخزون 📦", "url": reverse("inventory:products_list")},
                    {"text": "إنشاء طلب توريد مع الموردين 🚚", "url": reverse("suppliers:suppliers_list")}
                ]
            }

        elif query_type == "near_expiry":
            batches = ProductBatch.objects.filter(
                current_quantity__gt=0,
                expiry_date__isnull=False,
                expiry_date__lte=today + timezone.timedelta(days=45)
            ).order_by('expiry_date')[:6]

            if not batches:
                return {"reply": "✅ لا توجد دفعات قريبة من تاريخ انتهاء الصلاحية خلال الـ 45 يوماً القادمة.", "action": "info"}

            items = [f"• **{b.product.name}** (دفعة {b.batch_number}): ينتهي في `{b.expiry_date}` (المتبقي: `{b.current_quantity}`)" for b in batches]
            return {
                "reply": "⏳ **تنبيه السلع القريبة من انتهاء الصلاحية:**\n\n" + "\n".join(items),
                "action": "info",
                "buttons": [
                    {"text": "اقتراح عروض وخصومات ذكية لتصريفها 🏷️", "url": reverse("intelligence:smart_offers")}
                ]
            }

        elif query_type == "month_expenses":
            start_m = today.replace(day=1)
            expenses = OperatingExpense.objects.filter(expense_date__gte=start_m, expense_date__lte=today)
            tot_exp = sum((e.amount for e in expenses), Decimal('0.00'))
            paid_exp = sum((e.amount for e in expenses.filter(payment_status='PAID')), Decimal('0.00'))
            pending_exp = tot_exp - paid_exp

            return {
                "reply": (
                    f"🧾 **المصروفات التشغيلية لهذا الشهر:**\n\n"
                    f"• الإجمالي: **{tot_exp:,.2f} ج.م**\n"
                    f"• المسدد فعلياً: **{paid_exp:,.2f} ج.م**\n"
                    f"• المستحق أو المعلق: **{pending_exp:,.2f} ج.م**\n"
                    f"• عدد الفواتير المسجلة: **{expenses.count()} فاتورة**"
                ),
                "action": "stats",
                "buttons": [{"text": "عرض سجل المصروفات 🧾", "url": reverse("expenses:expenses_list")}]
            }

        elif query_type == "financial_summary":
            start_m = today.replace(day=1)
            m_sales = Sale.objects.filter(created_at__date__gte=start_m, created_at__date__lte=today, status='COMPLETED')
            m_rev = sum((s.final_amount for s in m_sales), Decimal('0.00'))
            m_cogs = sum((s.total_cogs for s in m_sales), Decimal('0.00'))
            m_gross = m_rev - m_cogs
            m_exp = sum((e.amount for e in OperatingExpense.objects.filter(expense_date__gte=start_m, expense_date__lte=today)), Decimal('0.00'))
            net_op = m_gross - m_exp
            margin = (m_gross / m_rev * Decimal('100.0')) if m_rev > 0 else Decimal('0.0')

            return {
                "reply": (
                    f"📊 **الملخص المالي والربحي لهذا الشهر:**\n\n"
                    f"• إيرادات المبيعات: **{m_rev:,.2f} ج.م**\n"
                    f"• تكلفة البضاعة المباعة (COGS): **{m_cogs:,.2f} ج.م**\n"
                    f"• مجمل الربح: **{m_gross:,.2f} ج.م** (هامش {margin:.1f}%)\n"
                    f"• المصروفات التشغيلية: **{m_exp:,.2f} ج.م**\n"
                    f"• **صافي الربح التشغيلي التقريبي**: **{net_op:,.2f} ج.م**"
                ),
                "action": "stats",
                "buttons": [{"text": "تقرير الأرباح والسيولة الكامل 📊", "url": reverse("core:financial_report")}]
            }

        return {"reply": "تم استلام استفسارك.", "action": "info"}

    @classmethod
    def handle_general_assistance(cls, message):
        return {
            "reply": "أهلاً بك! أنا مساعد السوق الذكي الشامل. يمكنك سؤالي عن أسعار السلع، مبيعات اليوم، النواقص، طلب إضافة منتج أو مصروف، أو الاستفسار عن الأرباح والموردين.",
            "action": "general_help",
            "suggestions": ["مبيعات اليوم", "النواقص في المخزن", "سعر السكر كام؟", "تقرير الأرباح"]
        }
