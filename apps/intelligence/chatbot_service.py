"""
AI Market Assistant (Chatbot Service)
Natural language processing, navigation guide, data creation, and authenticated data modification.
"""

import re
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import authenticate
from django.urls import reverse

from apps.core.models import AuditLog, SystemSettings
from apps.inventory.models import Product, Category, Warehouse, ProductBatch, InventoryMovement
from apps.sales.models import Sale, SaleItem
from apps.expenses.models import OperatingExpense, ExpenseCategory
from apps.suppliers.models import Supplier
from apps.intelligence.models import CalendarEvent, Forecast, AIRecommendation
from .gemini_service import GeminiMarketAgent


class MarketAIChatbot:
    """
    Intelligent chatbot engine that guides users, answers queries, adds data,
    and updates existing system records with strict credential verification.
    Powered by Google Gemini Pro with store-grounded RAG.
    """

    @classmethod
    def process_message(cls, message, user=None, auth_data=None, pending_action=None):
        """
        Main entry point for processing incoming chat messages.
        """
        message = (message or "").strip()
        
        # 1. If user is submitting credentials to execute a pending authenticated action
        if pending_action and auth_data:
            return cls.execute_authenticated_action(pending_action, auth_data, user)

        if not message:
            return {
                "reply": "مرحباً بك! أنا مساعد السوق الذكي 🤖 مدعوم بـ Google Gemini Pro. كيف يمكنني مساعدتك اليوم؟ يمكنك سؤالي عن أي صنف في المحل، مبيعات اليوم، النواقص، طلب إضافة منتج أو مصروف، أو استشارتي في أي موضوع تجاري أو عام.",
                "action": "greeting",
                "suggestions": ["مبيعات اليوم 📈", "النواقص في المخزن ⚠️", "سعر السكر كام؟ 📦", "أضف منتج جديد ➕", "سجل مصروف 💸", "استشارة لزيادة الأرباح 💡"]
            }

        # 2. Check for modification intents (strictly requires authentication)
        update_match = cls.detect_update_intent(message)
        if update_match:
            return cls.handle_update_intent(update_match, user, auth_data)

        # 3. Check for creation intents (add product, expense, supplier, event)
        create_match = cls.detect_create_intent(message)
        if create_match:
            return cls.handle_create_intent(create_match, user)

        # 4. Check for navigation requests (e.g. 'وديني للكاشير')
        nav_match = cls.detect_navigation_intent(message)
        if nav_match:
            return cls.handle_navigation_intent(nav_match)

        # 5. Check for exact direct system statistics queries
        query_match = cls.detect_query_intent(message)
        if query_match and query_match in ['today_sales', 'low_stock', 'near_expiry', 'month_expenses']:
            return cls.handle_query_intent(query_match)

        # 6. Conversational Gemini Pro AI Agent (Searches store database + answers any general or business question)
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
        """
        Detects if user wants to update an existing record.
        e.g., 'عدل سعر بيع سكر الأسرة إلى 35' or 'حدث تكلفة جبنة دومتي الى 25'
        """
        # Price change pattern: (عدل|غير|حدث) (سعر|سعر بيع|سعر شراء|تكلفة) [product] (إلى|الى|=) [number]
        price_patterns = [
            r'(?:عدل|غير|حدث|بدل)\s+(?:سعر\s+بيع|سعر|سعرها|سعره)\s+(.+?)\s+(?:إلى|الى|=|لـ|ل)\s+([0-9]+(?:\.[0-9]+)?)',
            r'(?:عدل|غير|حدث|بدل)\s+(?:تكلفة|سعر\s+شراء|سعر\s+التكلفة)\s+(.+?)\s+(?:إلى|الى|=|لـ|ل)\s+([0-9]+(?:\.[0-9]+)?)',
            r'(?:عدل|غير|حدث)\s+(?:حد\s+المخزون|الحد\s+الأدنى|الحد\s+الادنى)\s+(?:لـ|ل)?(.+?)\s+(?:إلى|الى|=|لـ|ل)\s+([0-9]+(?:\.[0-9]+)?)',
        ]
        
        # Check selling price
        m = re.search(price_patterns[0], text, re.IGNORECASE)
        if m:
            return {"type": "update_sale_price", "target_name": m.group(1).strip(), "new_value": m.group(2).strip()}

        # Check cost price
        m = re.search(price_patterns[1], text, re.IGNORECASE)
        if m:
            return {"type": "update_cost_price", "target_name": m.group(1).strip(), "new_value": m.group(2).strip()}

        # Check min stock
        m = re.search(price_patterns[2], text, re.IGNORECASE)
        if m:
            return {"type": "update_min_stock", "target_name": m.group(1).strip(), "new_value": m.group(2).strip()}

        # Generic update keyword match
        if any(w in text for w in ["عدل سعر", "غير سعر", "حدث سعر", "تعديل سعر", "تحديث سعر"]):
            return {"type": "prompt_update_price", "raw": text}

        return None

    @classmethod
    def detect_create_intent(cls, text):
        """
        Detects requests to add new products, expenses, suppliers, or events.
        """
        # Add Product:
        # e.g., 'أضف منتج عصير برتقال بسعر 15 وتكلفة 10 وباركود 12345'
        if any(w in text for w in ["أضف منتج", "اضف منتج", "سجل منتج", "منتج جديد", "إضافة منتج", "اضافة منتج"]):
            return {"entity": "product", "text": text}

        # Add Expense:
        # e.g., 'سجل مصروف كهرباء بقيمة 350' or 'أضف مصروف صيانة بمبلغ 500'
        if any(w in text for w in ["سجل مصروف", "أضف مصروف", "اضف مصروف", "تسجيل مصروف", "مصروف جديد", "دفع مصروف"]):
            return {"entity": "expense", "text": text}

        # Add Supplier:
        # e.g., 'أضف مورد شركة الأهرام هاتف 01012345678'
        if any(w in text for w in ["أضف مورد", "اضف مورد", "مورد جديد", "تسجيل مورد"]):
            return {"entity": "supplier", "text": text}

        # Add Calendar Event:
        if any(w in text for w in ["أضف مناسبة", "اضف مناسبة", "أضف موسم", "حدث جديد", "مناسبة جديدة"]):
            return {"entity": "calendar_event", "text": text}

        return None

    @classmethod
    def detect_query_intent(cls, text):
        """
        Detects analytical and statistical queries.
        """
        if any(w in text for w in ["مبيعات اليوم", "مبيعات النهارده", "كم بعنا اليوم", "اجمالي المبيعات", "ارباح اليوم", "أرباح اليوم"]):
            return "today_sales"

        if any(w in text for w in ["نواقص", "ناقص", "منخفض", "المخزون المنخفض", "أوشك على النفاد", "خلصان"]):
            return "low_stock"

        if any(w in text for w in ["صلاحية", "منتهي", "قرب ينتهي", "قريب الانتهاء", "اكسباير"]):
            return "near_expiry"

        if any(w in text for w in ["مصروفات", "مصاريف الشهر", "كم صرفنا", "اجمالي المصروفات"]):
            return "month_expenses"

        if any(w in text for w in ["توقعات", "الذكاء الاصطناعي", "توقع المبيعات", "تنبؤ"]):
            return "ai_forecasts"

        if any(w in text for w in ["عروض ذكية", "اقتراح عروض", "عروض ترويجية"]):
            return "smart_offers"

        # Check for stock query of a specific product: 'كم رصيد سكر الأسرة' or 'مخزون جبنة'
        m = re.search(r'(?:كم\s+رصيد|رصيد|مخزون|كمية|باقي\s+من|سعر)\s+(.+)', text)
        if m and not any(k in text for k in ["عدل", "غير", "أضف", "اضف", "سجل"]):
            return {"type": "product_lookup", "query": m.group(1).strip()}

        return None

    @classmethod
    def detect_navigation_intent(cls, text):
        """
        Detects navigation and feature location queries.
        """
        nav_map = {
            "pos": ["كاشير", "نقطة بيع", "pos", "فاتورة بيع", "بيع جديد", "شاشة البيع", "اعمل فاتورة"],
            "invoices": ["فواتير", "سجل الفواتير", "فواتير البيع", "الفواتير السابقة"],
            "products": ["دليل المنتجات", "قائمة المنتجات", "صفحة المنتجات", "السلع", "الأصناف"],
            "add_product": ["صفحة اضافة منتج", "نموذج المنتج", "فورم المنتج"],
            "batches": ["دفعات", "دفعات الشراء", "تاريخ الصلاحية", "الباتشات"],
            "inventory_counts": ["جرد", "الجرد الفعلي", "تسوية جردية"],
            "barcode_events": ["باركود", "مراقبة الباركود", "مسح الباركود", "سكانر"],
            "expenses": ["المصروفات", "صفحة المصروفات", "فواتير الكهرباء", "المصاريف التشغيلية"],
            "suppliers": ["الموردين", "قائمة الموردين", "شركات التوريد", "مورد جديد"],
            "orders": ["أوامر الشراء", "طلبات الشراء", "طلبيات الموردين"],
            "financial": ["الأرباح", "التقرير المالي", "السيولة", "صافي الربح", "قائمة الدخل", "حسابات المحل"],
            "intelligence": ["مركز الذكاء", "مركز التحليلات", "لوحة الذكاء الاصطناعي", "توصيات ai"],
            "calendar": ["التقويم", "المواسم", "تقويم المناسبات"],
            "settings": ["إعدادات", "ضبط النظام", "اسم المحل", "تغيير الاعدادات"],
            "backup": ["نسخ احتياطي", "باك اب", "استعادة البيانات", "backup"],
            "audit": ["سجل العمليات", "الرقابة", "audit", "مين عمل ايه"],
        }

        for dest, keywords in nav_map.items():
            if any(k in text.lower() for k in keywords):
                return dest
        return None

    # =========================================================================
    # INTENT HANDLERS
    # =========================================================================

    @classmethod
    def handle_navigation_intent(cls, dest):
        """
        Generates direct navigation links and guidance.
        """
        destinations = {
            "pos": {
                "title": "نقطة البيع السريع (POS)",
                "url": reverse("sales:pos"),
                "icon": "bi-upc-scan",
                "desc": "واجهة الكاشير المباشرة لإنشاء فواتير البيع، مسح الباركود، وحساب الخصومات فورياً."
            },
            "invoices": {
                "title": "سجل فواتير المبيعات",
                "url": reverse("sales:invoices_list"),
                "icon": "bi-receipt",
                "desc": "استعراض جميع فواتير البيع المكتملة والمرتجعة وتفاصيل كل فاتورة."
            },
            "products": {
                "title": "دليل المنتجات والمخزون",
                "url": reverse("inventory:products_list"),
                "icon": "bi-box-seam",
                "desc": "إدارة المنتجات، مراجعة الأرصدة، وأسعار الشراء والبيع والباركود."
            },
            "add_product": {
                "title": "إضافة منتج جديد",
                "url": reverse("inventory:product_create"),
                "icon": "bi-plus-circle",
                "desc": "صفحة تسجيل صنف جديد في النظام مع الباركود وتكلفة الشراء."
            },
            "batches": {
                "title": "دفعات الشراء وتواريخ الصلاحية",
                "url": reverse("inventory:batches_list"),
                "icon": "bi-calendar-check",
                "desc": "متابعة دفعات التوريد، تواريخ الصلاحية القريبة، وتكلفة كل دفعة (FIFO)."
            },
            "inventory_counts": {
                "title": "الجرد الفعلي والتسويات",
                "url": reverse("inventory:counts_list"),
                "icon": "bi-clipboard2-check",
                "desc": "مطابقة الرصيد الدفتري بالرصيد الواقعي في المخازن واكتشاف الفروقات."
            },
            "barcode_events": {
                "title": "مراقبة نشاط قارئ الباركود",
                "url": reverse("inventory:barcode_events"),
                "icon": "bi-barcode",
                "desc": "كشف مسحات الباركود غير المكتملة ومنع الفقد والسرقات."
            },
            "expenses": {
                "title": "المصروفات التشغيلية",
                "url": reverse("expenses:expenses_list"),
                "icon": "bi-wallet2",
                "desc": "تسجيل فواتير الكهرباء، الإيجار، المرتبات، ومتابعة السداد."
            },
            "suppliers": {
                "title": "سجل الموردين",
                "url": reverse("suppliers:suppliers_list"),
                "icon": "bi-truck",
                "desc": "بيانات الموردين، مهل التوريد، والحدود الدنيا للطلبات."
            },
            "orders": {
                "title": "أوامر الشراء والتوريد",
                "url": reverse("suppliers:orders_list"),
                "icon": "bi-cart-check",
                "desc": "إنشاء أوامر شراء ذكية واستلام البضائع مباشرة في المخازن."
            },
            "financial": {
                "title": "تقرير الأرباح والسيولة المالية",
                "url": reverse("core:financial_report"),
                "icon": "bi-graph-up-arrow",
                "desc": "حساب محاسبي دقيق لمجمل الربح وصافي الربح التشغيلي وتكلفة البضاعة المباعة (COGS)."
            },
            "intelligence": {
                "title": "مركز الذكاء الاصطناعي (AI Center)",
                "url": reverse("intelligence:center"),
                "icon": "bi-robot",
                "desc": "توصيات ذكية، تنبؤات الطلب، رصد الشذوذ في المصروفات، والعروض الترويجية."
            },
            "calendar": {
                "title": "التقويم الذكي والمواسم",
                "url": reverse("intelligence:calendar_events"),
                "icon": "bi-calendar3",
                "desc": "تتبع المناسبات الموسمية (رمضان، الأعياد، المدارس) وتأثيرها على حركة السلع."
            },
            "settings": {
                "title": "إعدادات النظام",
                "url": reverse("core:settings"),
                "icon": "bi-gear",
                "desc": "تخصيص اسم المحل، العملة، نسب الأرباح، وحدود تنبيهات النواقص."
            },
            "backup": {
                "title": "النسخ الاحتياطي واستعادة البيانات",
                "url": reverse("core:backup_management"),
                "icon": "bi-database-check",
                "desc": "إنشاء لقطة فورية لقاعدة البيانات وتحميلها واستعادتها بأمان."
            },
            "audit": {
                "title": "سجل العمليات والرقابة (Audit Log)",
                "url": reverse("core:audit_log"),
                "icon": "bi-shield-check",
                "desc": "سجل تفصيلي يوثق كل عملية إضافة أو تعديل أو تغيير أسعار والمستخدم المسؤول."
            },
        }

        info = destinations.get(dest)
        if not info:
            return cls.handle_general_assistance("")

        return {
            "reply": f"تفضل، يمكنك الانتقال مباشرة إلى **{info['title']}**:",
            "action": "navigation",
            "url": info["url"],
            "card": {
                "title": info["title"],
                "description": info["desc"],
                "url": info["url"],
                "button_text": f"الذهاب إلى {info['title']} 🚀",
                "icon": info["icon"]
            },
            "suggestions": ["مبيعات اليوم", "النواقص في المخزن", "تقرير الأرباح", "الرئيسية"]
        }

    @classmethod
    def handle_query_intent(cls, intent):
        """
        Handles real-time system statistics and inventory queries.
        """
        today = timezone.localdate()

        if intent == "today_sales":
            today_sales = Sale.objects.filter(created_at__date=today, status='COMPLETED')
            count = today_sales.count()
            total_amount = sum((s.final_amount for s in today_sales), Decimal('0.00'))
            total_items = SaleItem.objects.filter(sale__in=today_sales).count()

            return {
                "reply": f"📊 **ملخص مبيعات اليوم ({today.strftime('%d/%m/%Y')}):**\n"
                         f"- إجمالي الإيرادات: **{total_amount:,.2f} ج.م**\n"
                         f"- عدد فواتير البيع: **{count} فاتورة**\n"
                         f"- عدد السلع المباعة: **{total_items} سلعة**\n\n"
                         f"المتجر يعمل بحالة ممتازة! هل تود استعراض تفاصيل الفواتير أو تقرير الأرباح؟",
                "action": "stats",
                "buttons": [
                    {"text": "سجل الفواتير 🧾", "url": reverse("sales:invoices_list")},
                    {"text": "تقرير الأرباح والسيولة 📈", "url": reverse("core:financial_report")},
                    {"text": "فتح الكاشير (POS) 🛒", "url": reverse("sales:pos")}
                ]
            }

        elif intent == "low_stock":
            products = Product.objects.filter(is_active=True)
            low_stock_items = [p for p in products if p.is_low_stock][:8]

            if not low_stock_items:
                return {
                    "reply": "✅ **أخبار رائعة!** لا توجد أي منتجات منخفضة المخزون حالياً، جميع الأصناف تتجاوز الحد الأدنى للأمان.",
                    "action": "info",
                    "suggestions": ["مبيعات اليوم", "دليل المنتجات", "أوامر الشراء"]
                }

            items_list = "\n".join([f"• **{p.name}**: المتبقي **{p.total_stock} {p.get_unit_display()}** (الحد الأدنى: {p.min_stock_limit})" for p in low_stock_items])
            return {
                "reply": f"⚠️ **تنبيه النواقص في المخزن ({len(low_stock_items)} أصناف بحاجة للطلب):**\n\n{items_list}\n\nيمكنك إنشاء أمر شراء بضغطة زر لتعويض هذه الأصناف فوراً:",
                "action": "low_stock",
                "buttons": [
                    {"text": "إنشاء أمر شراء للموردين 📦", "url": reverse("suppliers:order_create")},
                    {"text": "دليل المنتجات والمخزون 📋", "url": reverse("inventory:products_list")}
                ]
            }

        elif intent == "near_expiry":
            today = timezone.localdate()
            threshold = today + timedelta(days=30)
            batches = ProductBatch.objects.filter(
                current_quantity__gt=0,
                expiry_date__isnull=False,
                expiry_date__lte=threshold
            ).select_related('product', 'warehouse').order_expiry()[:8]

            if not batches:
                return {
                    "reply": "✅ **ممتاز!** لا توجد دفعات مخزون قريبة من الانتهاء خلال الـ 30 يوماً القادمة.",
                    "action": "info"
                }

            items_list = "\n".join([f"• **{b.product.name}** (دفعة {b.batch_number}): تنتهي في **{b.expiry_date}** (المتبقي: {b.current_quantity})" for b in batches])
            return {
                "reply": f"⏳ **دفعات قريبة من تاريخ الانتهاء (خلال شهر):**\n\n{items_list}\n\nيُنصح بعمل عروض ترويجية لتصريف هذه السلع بسرعة.",
                "action": "near_expiry",
                "buttons": [
                    {"text": "العروض الذكية المقترحة 🏷️", "url": reverse("intelligence:smart_offers")},
                    {"text": "سجل الدفعات والصلاحية 📅", "url": reverse("inventory:batches_list")}
                ]
            }

        elif intent == "month_expenses":
            first_day = today.replace(day=1)
            expenses = OperatingExpense.objects.filter(expense_date__gte=first_day, expense_date__lte=today)
            total = sum((e.amount for e in expenses), Decimal('0.00'))
            paid = sum((e.paid_amount for e in expenses), Decimal('0.00'))
            unpaid = total - paid

            return {
                "reply": f"💸 **المصروفات التشغيلية لشهر {today.strftime('%B %Y')}:**\n"
                         f"- الإجمالي المطلوب: **{total:,.2f} ج.م**\n"
                         f"- المسدد بالفعل: **{paid:,.2f} ج.م**\n"
                         f"- المتبقي للسداد: **{unpaid:,.2f} ج.م**\n"
                         f"- عدد الفواتير والمصروفات: **{expenses.count()} مصروف**",
                "action": "expenses",
                "buttons": [
                    {"text": "سجل المصروفات 🧾", "url": reverse("expenses:expenses_list")},
                    {"text": "تسجيل مصروف جديد ➕", "url": reverse("expenses:expense_create")}
                ]
            }

        elif intent == "ai_forecasts":
            forecasts = Forecast.objects.select_related('product').order_by('-generated_at')[:5]
            if not forecasts:
                return {
                    "reply": "🤖 لم يتم توليد توقعات جديدة بعد. يمكنك تشغيل خوارزميات التعلم الآلي للتنبؤ بمبيعات الأيام القادمة.",
                    "buttons": [{"text": "تشغيل التنبؤ بالطلب الآن 🚀", "url": reverse("intelligence:run_forecast")}]
                }

            fc_text = "\n".join([f"• **{f.product.name}**: متوقع مبيعات **{f.predicted_sales_next_7_days:.0f} وحدة** في 7 أيام القادمة (ثقة: {f.model_accuracy_r2*100:.0f}%)" for f in forecasts])
            return {
                "reply": f"🧠 **أحدث توقعات الذكاء الاصطناعي لحركة السلع:**\n\n{fc_text}",
                "buttons": [{"text": "استعراض مركز الذكاء الاصطناعي 🤖", "url": reverse("intelligence:center")}]
            }

        elif isinstance(intent, dict) and intent.get("type") == "product_lookup":
            q = intent.get("query", "").strip()
            # Search product
            prods = Product.objects.filter(name__icontains=q)[:3]
            if not prods:
                prods = Product.objects.filter(code__icontains=q)[:3]

            if not prods:
                return {
                    "reply": f"🔍 لم أتمكن من العثور على صنف باسم أو كود '{q}'. هل تود إضافته كمنتج جديد؟",
                    "action": "not_found",
                    "suggestions": [f"أضف منتج جديد {q}", "دليل المنتجات", "الرئيسية"]
                }

            p = prods[0]
            return {
                "reply": f"📦 **بيانات الصنف: {p.name}**\n"
                         f"- الكود: **{p.code}** | الباركود: **{p.barcode or 'غير مسجل'}**\n"
                         f"- سعر البيع: **{p.sale_price:,.2f} ج.م**\n"
                         f"- سعر الشراء (التكلفة): **{p.default_cost_price:,.2f} ج.م**\n"
                         f"- إجمالي الرصيد بالمخزن: **{p.total_stock} {p.get_unit_display()}**\n"
                         f"- الحد الأدنى للأمان: **{p.min_stock_limit}**\n"
                         f"- الحالة: **{'✅ متوفر' if not p.is_low_stock else '⚠️ منخفض المخزون'}**",
                "action": "product_info",
                "buttons": [
                    {"text": f"تعديل سعر {p.name} ✏️", "click_prompt": f"عدل سعر {p.name} إلى "},
                    {"text": "عرض في دليل المنتجات 🔍", "url": reverse("inventory:product_update", args=[p.id])}
                ]
            }

        return cls.handle_general_assistance("")

    # =========================================================================
    # DATA MODIFICATION (WITH CREDENTIAL VERIFICATION)
    # =========================================================================

    @classmethod
    def handle_update_intent(cls, match, user, auth_data):
        """
        Initiates an update request. If credentials are not provided or verified,
        it prompts the user for verification.
        """
        target_name = match.get("target_name", "").strip()
        new_val_str = match.get("new_value", "").strip()

        # Try to find the matching product
        products = Product.objects.filter(name__icontains=target_name)
        if not products.exists():
            # Try splitting
            words = target_name.split()
            if words:
                products = Product.objects.filter(name__icontains=words[0])

        if not products.exists():
            return {
                "reply": f"❌ لم أجد منتجاً بهذا الاسم: '{target_name}'. يرجى التأكد من اسم الصنف كما هو مسجل في النظام.",
                "action": "error",
                "suggestions": ["دليل المنتجات", "مبيعات اليوم"]
            }

        product = products.first()
        try:
            new_value = Decimal(new_val_str)
        except Exception:
            return {
                "reply": f"❌ القيمة المدخلة '{new_val_str}' غير صحيحة، يرجى إدخال رقم صحيح.",
                "action": "error"
            }

        update_type = match.get("type")
        action_title = ""
        field_name = ""
        old_val = Decimal("0.00")

        if update_type == "update_sale_price":
            action_title = "تعديل سعر البيع"
            field_name = "sale_price"
            old_val = product.sale_price
        elif update_type == "update_cost_price":
            action_title = "تعديل سعر التكلفة"
            field_name = "default_cost_price"
            old_val = product.default_cost_price
        elif update_type == "update_min_stock":
            action_title = "تعديل الحد الأدنى للمخزون"
            field_name = "min_stock_limit"
            old_val = product.min_stock_limit

        pending_action = {
            "type": "update_product",
            "product_id": product.id,
            "product_name": product.name,
            "field_name": field_name,
            "action_title": action_title,
            "old_value": float(old_val),
            "new_value": float(new_value)
        }

        # Check if auth_data was supplied in this turn
        if auth_data and auth_data.get("password"):
            return cls.execute_authenticated_action(pending_action, auth_data, user)

        # Trigger Authentication Challenge
        current_username = getattr(user, 'username', 'admin') if (user and user.is_authenticated) else 'admin'

        return {
            "reply": f"🔒 **إجراء أمني مطلوب للتحقق من الهوية:**\n\n"
                     f"أنت على وشك **{action_title}** للمنتج:\n"
                     f"📦 **{product.name}**\n"
                     f"- القيمة الحالية: **{old_val:,.2f}**\n"
                     f"- القيمة الجديدة المقترحة: **{new_value:,.2f}**\n\n"
                     f"لحماية بيانات وأسعار المتجر، يرجى تأكيد كلمة المرور الخاصة بحسابك للمتابعة:",
            "action": "auth_required",
            "auth_required": True,
            "pending_action": pending_action,
            "auth_form": {
                "username": current_username,
                "label": f"تأكيد كلمة المرور لحساب ({current_username}):",
                "button_text": "تأكيد وتنفيذ التعديل الآن 🔒"
            }
        }

    @classmethod
    def execute_authenticated_action(cls, pending_action, auth_data, user=None):
        """
        Verifies credentials and executes the authorized modification.
        """
        username = auth_data.get("username", "").strip()
        password = auth_data.get("password", "").strip()

        if not username and user and user.is_authenticated:
            username = user.username

        if not username or not password:
            return {
                "reply": "❌ يرجى إدخال اسم المستخدم وكلمة المرور لتأكيد الهوية.",
                "action": "auth_failed",
                "auth_required": True,
                "pending_action": pending_action
            }

        # Authenticate user
        auth_user = authenticate(username=username, password=password)
        if not auth_user:
            return {
                "reply": f"❌ **فشل التحقق من الهوية!**\nكلمة المرور غير صحيحة للمستخدم ({username}). لم يتم إجراء أي تعديل على بيانات النظام حفاظاً على الأمان.",
                "action": "auth_failed",
                "auth_required": True,
                "pending_action": pending_action
            }

        # Check role permission (Admin or Manager)
        user_role = getattr(auth_user, 'role', 'ADMIN')
        if user_role not in ['ADMIN', 'MANAGER'] and not auth_user.is_superuser:
            return {
                "reply": f"⛔ **تم رفض العملية:** الحساب ({auth_user.get_full_name() or auth_user.username}) لا يملك صلاحية تعديل أسعار أو بيانات الأصناف. الصلاحية مقتصرة على الإدارة.",
                "action": "permission_denied"
            }

        # Execute modification
        action_type = pending_action.get("type")
        if action_type == "update_product":
            product_id = pending_action.get("product_id")
            field_name = pending_action.get("field_name")
            new_val = Decimal(str(pending_action.get("new_value")))
            old_val = Decimal(str(pending_action.get("old_value")))

            try:
                with transaction.atomic():
                    product = Product.objects.select_for_update().get(id=product_id)
                    setattr(product, field_name, new_val)
                    product.save(update_fields=[field_name, 'updated_at'])

                    # Audit Log
                    audit_action = 'PRICE_CHANGE' if 'price' in field_name else 'UPDATE'
                    AuditLog.objects.create(
                        user=auth_user,
                        action=audit_action,
                        target_model="Product",
                        target_id=str(product.id),
                        description=f"تم تعديل {field_name} للمنتج '{product.name}' من {old_val} إلى {new_val} عبر المساعد الذكي بعد التحقق من الهوية."
                    )

                return {
                    "reply": f"✅ **تم التحقق بنجاح وتحديث البيانات!** 🎉\n\n"
                             f"📦 الصنف: **{product.name}**\n"
                             f"✏️ الحقل المعدل: **{pending_action.get('action_title')}**\n"
                             f"📉 القيمة السابقة: ~~{old_val:,.2f}~~\n"
                             f"📈 القيمة الجديدة: **{new_val:,.2f} ج.م**\n"
                             f"👤 المسؤول المعتمد: **{auth_user.get_full_name() or auth_user.username}** ({auth_user.get_role_display()})\n"
                             f"🛡️ تم توثيق العملية في سجل العمليات والرقابة (Audit Log).",
                    "action": "success",
                    "card": {
                        "title": product.name,
                        "description": f"السعر المعتمد الجديد: {new_val:,.2f} ج.م",
                        "url": reverse("inventory:product_edit", args=[product.id]),
                        "button_text": "عرض المنتج في الدليل 🔍",
                        "icon": "bi-check-circle-fill"
                    },
                    "suggestions": ["دليل المنتجات", "مبيعات اليوم", "تقرير الأرباح"]
                }
            except Exception as e:
                return {
                    "reply": f"❌ حدث خطأ أثناء تطبيق التعديل: {str(e)}",
                    "action": "error"
                }

        return {
            "reply": "⚠️ العملية المحددة غير مدعومة.",
            "action": "error"
        }

    # =========================================================================
    # DATA CREATION (ADD NEW RECORDS)
    # =========================================================================

    @classmethod
    def handle_create_intent(cls, match, user):
        """
        Parses parameters and creates new database records.
        """
        entity = match.get("entity")
        raw_text = match.get("text", "")

        if entity == "product":
            return cls.create_product_from_text(raw_text, user)
        elif entity == "expense":
            return cls.create_expense_from_text(raw_text, user)
        elif entity == "supplier":
            return cls.create_supplier_from_text(raw_text, user)
        elif entity == "calendar_event":
            return cls.create_calendar_event_from_text(raw_text, user)

        return cls.handle_general_assistance(raw_text)

    @classmethod
    def create_product_from_text(cls, text, user):
        """
        Extracts product details from Arabic prompt.
        e.g., 'أضف منتج عصير برتقال جهينة بسعر 20 وتكلفة 15 وباركود 6221234567890'
        """
        # Extract numbers for prices
        sale_price = None
        cost_price = None
        barcode = None

        m_sale = re.search(r'(?:بسعر|سعر\s+بيع|سعر)\s+([0-9]+(?:\.[0-9]+)?)', text)
        if m_sale:
            sale_price = Decimal(m_sale.group(1))

        m_cost = re.search(r'(?:بتكلفة|تكلفة|شراء|بسعر\s+شراء)\s+([0-9]+(?:\.[0-9]+)?)', text)
        if m_cost:
            cost_price = Decimal(m_cost.group(1))

        m_barcode = re.search(r'(?:باركود|كود|barcode)\s+([0-9A-Za-z_-]+)', text)
        if m_barcode:
            barcode = m_barcode.group(1)

        # Extract product name
        cleaned = re.sub(r'^(?:أضف\s+منتج\s+جديد|اضف\s+منتج\s+جديد|أضف\s+منتج|اضف\s+منتج|منتج\s+جديد)\s*', '', text).strip()
        cleaned = re.sub(r'(?:بسعر|سعر|بتكلفة|تكلفة|باركود).*$', '', cleaned).strip()

        prod_name = cleaned if len(cleaned) >= 2 else "صنف جديد"

        if not sale_price:
            sale_price = Decimal("10.00")
        if not cost_price:
            cost_price = Decimal(str(sale_price * Decimal("0.75"))).quantize(Decimal("0.01"))

        # Generate unique code/SKU
        base_code = f"PRD-{timezone.now().strftime('%y%m%d%H%M%S')}"
        if not barcode:
            barcode = f"622{timezone.now().strftime('%m%d%H%M%S')}"

        default_cat = Category.objects.first()
        if not default_cat:
            default_cat = Category.objects.create(name="أغذية ومشروبات عامة")

        try:
            with transaction.atomic():
                product = Product.objects.create(
                    name=prod_name,
                    code=base_code,
                    barcode=barcode,
                    category=default_cat,
                    default_cost_price=cost_price,
                    sale_price=sale_price,
                    min_stock_limit=5
                )

                # Add initial batch in default warehouse with stock = 10
                warehouse = Warehouse.objects.filter(is_default=True).first() or Warehouse.objects.first()
                if not warehouse:
                    warehouse = Warehouse.objects.create(name="المخزن الرئيسي", code="WH-MAIN", is_default=True)

                batch = ProductBatch.objects.create(
                    product=product,
                    warehouse=warehouse,
                    batch_number=f"BATCH-{timezone.now().strftime('%m%d%H%M')}",
                    initial_quantity=10,
                    current_quantity=10,
                    cost_price=cost_price,
                    expiry_date=timezone.localdate() + timedelta(days=180)
                )

                # Log
                AuditLog.objects.create(
                    user=user if (user and user.is_authenticated) else None,
                    action='CREATE',
                    target_model="Product",
                    target_id=str(product.id),
                    description=f"تمت إضافة المنتج '{product.name}' وتوليد رصيد افتراضي 10 وحدات عبر المساعد الذكي."
                )

            return {
                "reply": f"✨ **تمت إضافة المنتج الجديد بنجاح إلى قاعدة البيانات!** 📦\n\n"
                         f"- الاسم: **{product.name}**\n"
                         f"- الكود (SKU): **{product.code}**\n"
                         f"- الباركود: **`{product.barcode}`**\n"
                         f"- سعر البيع: **{product.sale_price:,.2f} ج.م**\n"
                         f"- سعر التكلفة: **{product.default_cost_price:,.2f} ج.م**\n"
                         f"- الرصيد المبدئي المضاف: **10 {product.get_unit_display()}** في {warehouse.name}\n\n"
                         f"المنتج أصبح متاحاً الآن فوراً في شاشة الكاشير والمخازن!",
                "action": "created",
                "card": {
                    "title": product.name,
                    "description": f"سعر البيع: {product.sale_price} ج.م | الباركود: {product.barcode}",
                    "url": reverse("inventory:product_edit", args=[product.id]),
                    "button_text": "عرض وتعديل تفاصيل المنتج 📋",
                    "icon": "bi-box-seam"
                },
                "buttons": [
                    {"text": "فتح الكاشير للبيع 🛒", "url": reverse("sales:pos")},
                    {"text": "دليل المنتجات 📦", "url": reverse("inventory:products_list")}
                ]
            }
        except Exception as e:
            return {
                "reply": f"❌ حدث خطأ أثناء إضافة المنتج: {str(e)}",
                "action": "error"
            }

    @classmethod
    def create_expense_from_text(cls, text, user):
        """
        Extracts expense details: e.g. 'سجل مصروف فاتورة كهرباء 450 جنيه'
        """
        amount = None
        m_amt = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*(?:جنيه|ج\.م|ج|EGP)?', text)
        if m_amt:
            amount = Decimal(m_amt.group(1))
        else:
            amount = Decimal("100.00")

        # Title
        title = re.sub(r'^(?:سجل\s+مصروف|أضف\s+مصروف|اضف\s+مصروف|تسجيل\s+مصروف)\s*', '', text).strip()
        title = re.sub(r'[0-9]+(?:\.[0-9]+)?.*$', '', title).strip()
        if not title:
            title = "مصروف تشغيلي عام"

        cat = ExpenseCategory.objects.first()
        if not cat:
            cat = ExpenseCategory.objects.create(name="مصروفات عامة وطارئة", code="EXP-GEN")

        try:
            expense = OperatingExpense.objects.create(
                title=title,
                category=cat,
                amount=amount,
                paid_amount=amount,
                payment_status='PAID',
                expense_date=timezone.localdate(),
                created_by=user if (user and user.is_authenticated) else None
            )

            AuditLog.objects.create(
                user=user if (user and user.is_authenticated) else None,
                action='EXPENSE_ADD',
                target_model="OperatingExpense",
                target_id=str(expense.id),
                description=f"تم تسجيل مصروف '{expense.title}' بقيمة {amount} ج.م عبر المساعد الذكي."
            )

            return {
                "reply": f"💸 **تم تسجيل المصروف بنجاح!**\n\n"
                         f"- البيان: **{expense.title}**\n"
                         f"- المبلغ: **{expense.amount:,.2f} ج.م**\n"
                         f"- التصنيف: **{cat.name}**\n"
                         f"- تاريخ الصرف: **{expense.expense_date}**\n"
                         f"- حالة السداد: **مسدد بالكامل نقداً**\n\n"
                         f"تم ترحيل المصروف فورياً لحسابات الأرباح والسيولة.",
                "action": "created",
                "buttons": [
                    {"text": "سجل المصروفات 🧾", "url": reverse("expenses:expenses_list")},
                    {"text": "تقرير الأرباح والسيولة 📊", "url": reverse("core:financial_report")}
                ]
            }
        except Exception as e:
            return {"reply": f"❌ تعذر تسجيل المصروف: {str(e)}", "action": "error"}

    @classmethod
    def create_supplier_from_text(cls, text, user):
        """
        Extracts supplier details: e.g. 'أضف مورد شركة النيل هاتف 01012345678'
        """
        phone = ""
        m_phone = re.search(r'([0-9]{10,12})', text)
        if m_phone:
            phone = m_phone.group(1)
        else:
            phone = "01000000000"

        company = re.sub(r'^(?:أضف\s+مورد|اضف\s+مورد|مورد\s+جديد)\s*', '', text).strip()
        company = re.sub(r'(?:هاتف|تليفون|رقم|phone|[0-9]).*$', '', company).strip()
        if not company:
            company = "شركة توريد جديدة"

        try:
            supplier = Supplier.objects.create(
                company_name=company,
                phone=phone,
                lead_time_days=2,
                min_order_value=500
            )

            AuditLog.objects.create(
                user=user if (user and user.is_authenticated) else None,
                action='CREATE',
                target_model="Supplier",
                target_id=str(supplier.id),
                description=f"تمت إضافة مورد جديد '{supplier.company_name}' عبر المساعد الذكي."
            )

            return {
                "reply": f"🚚 **تم تسجيل المورد الجديد بنجاح!**\n\n"
                         f"- اسم الشركة: **{supplier.company_name}**\n"
                         f"- رقم الهاتف: **{supplier.phone}**\n"
                         f"- مهلة التوريد الافتراضية: **{supplier.lead_time_days} أيام**",
                "action": "created",
                "buttons": [
                    {"text": "قائمة الموردين 📋", "url": reverse("suppliers:suppliers_list")},
                    {"text": "إنشاء أمر شراء 📦", "url": reverse("suppliers:order_create")}
                ]
            }
        except Exception as e:
            return {"reply": f"❌ تعذر إضافة المورد: {str(e)}", "action": "error"}

    @classmethod
    def create_calendar_event_from_text(cls, text, user):
        """
        Extracts calendar season/event details.
        """
        title = re.sub(r'^(?:أضف\s+مناسبة|اضف\s+مناسبة|أضف\s+موسم|حدث\s+جديد)\s*', '', text).strip()
        if not title:
            title = "موسم تجاري جديد"

        start = timezone.localdate()
        end = start + timedelta(days=14)

        try:
            event = CalendarEvent.objects.create(
                title=title,
                event_type="SEASON",
                start_date=start,
                end_date=end,
                description=f"تم إنشاء المناسبة عبر المساعد الذكي بتاريخ {start}."
            )

            return {
                "reply": f"🎉 **تم تسجيل الحدث في التقويم الذكي!**\n\n"
                         f"- المناسبة: **{event.title}**\n"
                         f"- تاريخ البدء: **{event.start_date}** | الانتهاء: **{event.end_date}**\n"
                         f"- مضاعف الإقبال المتوقع: **+{int((event.expected_demand_multiplier - 1) * 100)}%**\n"
                         f"ستقوم خوارزميات التنبؤ برفع تقديرات الطلب تلقائياً خلال هذه الفترة.",
                "action": "created",
                "buttons": [{"text": "تقويم المناسبات 📅", "url": reverse("intelligence:calendar_events")}]
            }
        except Exception as e:
            return {"reply": f"❌ تعذر إضافة المناسبة: {str(e)}", "action": "error"}

    # =========================================================================
    # GENERAL ASSISTANCE
    # =========================================================================

    @classmethod
    def handle_general_assistance(cls, text):
        """
        Fallback response explaining everything the chatbot can do.
        """
        return {
            "reply": "🤖 **مرحباً بك! أنا مساعد السوق الذكي (Market AI).**\n\n"
                     "أستطيع مساعدتك في الوصول لكل أركان النظام وإدارته بسهولة تامة:\n\n"
                     "🔹 **الاستعلام والإحصائيات:**\n"
                     "• اكتب *'مبيعات اليوم'* أو *'النواقص في المخزن'* أو *'تقرير الأرباح'*.\n"
                     "• اكتب *'سعر سكر الأسرة'* لمعرفة رصيد وسعر أي منتج.\n\n"
                     "🔹 **إضافة بيانات جديدة فوراً:**\n"
                     "• *'أضف منتج عصير راني بسعر 18 وتكلفة 13 وباركود 622998877'*.\n"
                     "• *'سجل مصروف فاتورة مياه 200 جنيه'*.\n"
                     "• *'أضف مورد شركة الدلتا هاتف 01234567890'*.\n\n"
                     "🔹 **تعديل البيانات الموجودة (بحماية كلمة المرور):**\n"
                     "• *'عدل سعر بيع جبنة دومتي إلى 32'*.\n"
                     "• *'عدل الحد الأدنى لمخزون زيت عافية إلى 15'*.\n"
                     "*(سيطلب منك النظام تأكيد كلمة مرور حسابك قبل تطبيق أي تعديل لضمان الأمان الكامل)*.",
            "action": "help",
            "suggestions": [
                "مبيعات اليوم 📈",
                "النواقص في المخزن ⚠️",
                "سجل فواتير البيع 🧾",
                "تقرير الأرباح والسيولة 📊",
                "نقطة البيع (POS) 🛒"
            ]
        }
