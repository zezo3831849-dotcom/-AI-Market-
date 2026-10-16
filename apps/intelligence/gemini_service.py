"""
Market Manager AI - Comprehensive Gemini Pro Agent & Store-Grounding RAG Engine
Grounds Google Gemini Pro in real-time store database across all 19 Core Features:
Products, Batches, Sales, Profits, Inventory, Barcodes, Seasons, Offers, Returns,
Suppliers, Orders, Calendar, Deals, Expenses, Forecasts, Anomalies, Human-in-the-Loop,
Backup & Offline Continuity, and Audit Logs.
"""

import os
import re
import json
import urllib.request
import urllib.error
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, Q, Count, F
from django.urls import reverse

from apps.inventory.models import Product, ProductBatch, Category, Warehouse, InventoryMovement
from apps.sales.models import Sale, SaleItem, Return
from apps.expenses.models import OperatingExpense, ExpenseCategory
from apps.suppliers.models import Supplier, PurchaseOrder, SpecialDeal
from apps.intelligence.models import CalendarEvent, Forecast, AIRecommendation
from apps.core.models import SystemSettings, AuditLog


class GeminiMarketAgent:
    """
    Intelligent agent powered by Google Gemini Pro, fully grounded in the
    store's real-time database with comprehensive knowledge of all 19 system features.
    """

    @classmethod
    def get_api_key(cls):
        key = getattr(settings, 'GEMINI_API_KEY', '') or os.environ.get('GEMINI_API_KEY', '')
        if not key:
            env_file = os.path.join(settings.BASE_DIR, '.env')
            if os.path.exists(env_file):
                try:
                    with open(env_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('GEMINI_API_KEY='):
                                key = line.strip().split('=', 1)[1]
                                break
                except Exception:
                    pass
        return key

    @classmethod
    def get_models(cls):
        return getattr(settings, 'GEMINI_MODELS', [
            'gemini-flash-lite-latest',
            'gemini-3.1-flash-lite',
            'gemini-flash-latest',
        ])

    # =========================================================================
    # RAG: COMPREHENSIVE STORE DATABASE SEARCH & LIVE CONTEXT BUILDER
    # =========================================================================

    @classmethod
    def search_store_database(cls, user_message):
        """
        Extracts entities from the user's inquiry and constructs a rich,
        live factual snapshot covering all relevant features.
        """
        context_parts = []
        today = timezone.localdate()

        # 1. System Settings & Currency
        try:
            store_settings = SystemSettings.get_settings()
            store_name = store_settings.store_name if store_settings else "سوق المستقبل الذكي"
            currency = store_settings.currency if store_settings else "ج.م"
        except Exception:
            store_name = "سوق المستقبل الذكي"
            currency = "ج.م"

        context_parts.append(
            f"📌 [بيانات المتجر الأساسية]:\n"
            f"• اسم المتجر: {store_name}\n"
            f"• العملة المعتمدة: {currency}\n"
            f"• تاريخ اليوم: {today.strftime('%Y-%m-%d')}"
        )

        # 2. Executive Financial & Operational Indicators (Features 2, 3, 4, 13)
        try:
            total_prods = Product.objects.filter(is_active=True).count()
            low_stock_count = Product.objects.filter(is_active=True, total_stock__lte=F('min_stock_limit')).count()
            
            # Today's Sales
            today_sales = Sale.objects.filter(created_at__date=today, status='COMPLETED')
            today_rev = sum((s.final_amount for s in today_sales), Decimal('0.00'))
            today_sales_count = today_sales.count()

            # Month Financials
            start_of_month = today.replace(day=1)
            month_sales = Sale.objects.filter(created_at__date__gte=start_of_month, created_at__date__lte=today, status='COMPLETED')
            month_rev = sum((s.final_amount for s in month_sales), Decimal('0.00'))
            month_cogs = sum((s.total_cogs for s in month_sales), Decimal('0.00'))
            month_gross_profit = month_rev - month_cogs
            gross_margin_pct = (month_gross_profit / month_rev * Decimal('100.0')) if month_rev > 0 else Decimal('0.0')

            # Month Operating Expenses
            month_expenses = OperatingExpense.objects.filter(expense_date__gte=start_of_month, expense_date__lte=today)
            month_exp_tot = sum((e.amount for e in month_expenses), Decimal('0.00'))
            month_net_operating_profit = month_gross_profit - month_exp_tot

            # Batches near expiry (30 days)
            near_expiry_count = ProductBatch.objects.filter(
                current_quantity__gt=0,
                expiry_date__isnull=False,
                expiry_date__lte=today + timezone.timedelta(days=30)
            ).count()

            # AI Recommendations pending
            pending_recs = AIRecommendation.objects.filter(status='PENDING').count()

            context_parts.append(
                f"📊 [المؤشرات المالية والتشغيلية اللحظية]:\n"
                f"• إجمالي المنتجات النشطة: {total_prods} منتج\n"
                f"• منتجات منخفضة المخزون (نواقص): {low_stock_count} منتج\n"
                f"• مبيعات اليوم ({today}): {today_rev:,.2f} {currency} ({today_sales_count} فاتورة)\n"
                f"• إيرادات هذا الشهر: {month_rev:,.2f} {currency}\n"
                f"• تكلفة البضاعة المباعة (COGS) هذا الشهر: {month_cogs:,.2f} {currency}\n"
                f"• مجمل الربح هذا الشهر: {month_gross_profit:,.2f} {currency} (هامش مجمل الربح: {gross_margin_pct:.1f}%)\n"
                f"• إجمالي المصروفات التشغيلية هذا الشهر: {month_exp_tot:,.2f} {currency}\n"
                f"• صافي الربح التشغيلي التقريبي هذا الشهر: {month_net_operating_profit:,.2f} {currency}\n"
                f"• دفعات قريبة من انتهاء الصلاحية (خلال 30 يوم): {near_expiry_count} دفعة\n"
                f"• توصيات ذكاء اصطناعي بانتظار قرار المدير: {pending_recs} توصية"
            )
        except Exception:
            pass

        # 3. Targeted Product & Inventory Search (Features 1 & 4)
        clean_query = re.sub(r'[^\w\s]', ' ', user_message)
        stop_words = {'هل', 'في', 'من', 'على', 'عن', 'الى', 'إلى', 'كام', 'سعر', 'عندنا', 'عايز', 'بكام', 'موجود', 'ايه', 'معانا', 'محتاج', 'فين', 'رصيد', 'كمية', 'كل', 'لو', 'معايا'}
        keywords = [w.strip() for w in clean_query.split() if len(w.strip()) >= 2 and w.strip() not in stop_words]

        matched_products = []
        if keywords:
            q_filter = Q()
            for kw in keywords[:4]:
                q_filter |= Q(name__icontains=kw) | Q(brand__icontains=kw) | Q(code__icontains=kw) | Q(barcode__icontains=kw) | Q(category__name__icontains=kw)
            matched_products = list(Product.objects.filter(is_active=True).filter(q_filter).distinct()[:6])

        if matched_products:
            prod_lines = []
            for p in matched_products:
                batches = p.batches.filter(current_quantity__gt=0).order_by('expiry_date')
                batch_info = ", ".join([
                    f"دفعة {b.batch_number} (تكلفة {b.cost_price:,.2f} {currency}, رصيد {b.current_quantity}{p.get_unit_display()}" +
                    (f", تنتهي {b.expiry_date}" if b.expiry_date else "") + ")"
                    for b in batches[:3]
                ])
                profit_unit = p.sale_price - p.default_cost_price
                margin_pct = (profit_unit / p.sale_price * Decimal('100.0')) if p.sale_price > 0 else Decimal('0.0')

                prod_lines.append(
                    f"• {p.name} [{p.code} | باركود: {p.barcode or 'غير مسجل'}]:\n"
                    f"  - سعر البيع: {p.sale_price:,.2f} {currency} | سعر التكلفة: {p.default_cost_price:,.2f} {currency} | مجمل ربح القطعة: {profit_unit:,.2f} {currency} ({margin_pct:.1f}%)\n"
                    f"  - الرصيد الكلي: {p.total_stock} {p.get_unit_display()} | الحد الأدنى للمخزون: {p.min_stock_limit} | الحالة: {'⚠️ منخفض المخزون' if p.is_low_stock else '✅ متوفر'}\n"
                    f"  - الدفعات النشطة: {batch_info if batch_info else 'لا توجد دفعات بمخزون حالياً'}"
                )
            context_parts.append("📦 [بيانات السلع المطابقة لسؤال المستخدم]:\n" + "\n".join(prod_lines))

        # 4. Suppliers & Purchase Orders (Features 9 & 10)
        if any(w in user_message for w in ['مورد', 'موردين', 'شركة', 'مندوب', 'شراء', 'توريد', 'طلب شراء']):
            suppliers = Supplier.objects.filter(is_active=True)[:5]
            if suppliers:
                sup_lines = [
                    f"• {s.company_name} (مندوب: {s.rep_name or 'غير محدد'}, هاتف: {s.phone}, مهلة التوريد: {s.lead_time_days} أيام, حد أدنى للطلب: {s.min_order_amount:,.2f} {currency})"
                    for s in suppliers
                ]
                context_parts.append("🚚 [دليل الموردين النشطين]:\n" + "\n".join(sup_lines))

            recent_pos = PurchaseOrder.objects.order_by('-order_date')[:3]
            if recent_pos:
                po_lines = [
                    f"• إذن شراء #{po.po_number} من {po.supplier.company_name}: إجمالي {po.total_amount:,.2f} {currency} (الحالة: {po.get_status_display()})"
                    for po in recent_pos
                ]
                context_parts.append("📋 [آخر طلبات الشراء]:\n" + "\n".join(po_lines))

        # 5. Operating Expenses (Feature 13)
        if any(w in user_message for w in ['مصروف', 'مصاريف', 'فاتورة', 'كهرباء', 'مياه', 'غاز', 'إيجار', 'ايجار', 'صيانة', 'راتب', 'مرتبات']):
            recent_exp = OperatingExpense.objects.order_by('-expense_date')[:5]
            if recent_exp:
                exp_lines = [
                    f"• {e.title} [{e.category.name if e.category else 'عام'}]: {e.amount:,.2f} {currency} بتاريخ {e.expense_date} (الحالة: {e.get_payment_status_display()})"
                    for e in recent_exp
                ]
                context_parts.append("💸 [آخر المصروفات التشغيلية المسجلة]:\n" + "\n".join(exp_lines))

        # 6. Seasonal Calendar & Events (Features 6 & 11)
        if any(w in user_message for w in ['موسم', 'مناسبة', 'رمضان', 'عيد', 'مدارس', 'صيف', 'شتاء', 'حدث', 'تقويم']):
            upcoming_events = CalendarEvent.objects.filter(end_date__gte=today).order_by('start_date')[:4]
            if upcoming_events:
                ev_lines = [
                    f"• {ev.title} ({ev.get_event_type_display()}): من {ev.start_date} إلى {ev.end_date} - {ev.description or 'لا يوجد وصف'}"
                    for ev in upcoming_events
                ]
                context_parts.append("📅 [المناسبات والمواسم الحالية والقادمة]:\n" + "\n".join(ev_lines))

        # 7. AI Recommendations & Forecasts (Features 7, 14, 15, 16)
        if any(w in user_message for w in ['توقع', 'توقعات', 'توصية', 'توصيات', 'عرض', 'عروض', 'شذوذ', 'تناقض', 'ذكاء']):
            recs = AIRecommendation.objects.filter(status='PENDING').order_by('-confidence_score')[:4]
            if recs:
                rec_lines = [
                    f"• [{rec.get_recommendation_type_display()}] {rec.title}: {rec.rationale} (اليقين: {rec.confidence_score}%)"
                    for rec in recs
                ]
                context_parts.append("💡 [توصيات الذكاء الاصطناعي قيد المراجعة]:\n" + "\n".join(rec_lines))

        return "\n\n".join(context_parts)

    # =========================================================================
    # SYSTEM PROMPT: GROUNDED IN ALL 19 CORE SYSTEM FEATURES
    # =========================================================================

    @classmethod
    def get_system_prompt(cls, store_context, user=None):
        username = getattr(user, 'first_name', '') or getattr(user, 'username', 'المدير')
        role_name = getattr(user, 'get_role_display', lambda: 'المدير')() if user else 'المدير'

        return f"""أنت "المساعد الذكي لإدارة السوق" (Market AI Assistant)، المساعد الشامل والمدعوم بـ Google Gemini Pro.
أنت مخصص بالكامل وبشكل حصري لنظام إدارة هذا المتجر بكافة مميزاته الأساسية الـ 19.
المستخدم الحالي الذي يتحدث معك هو: {username} (دوره في النظام: {role_name}).

المرجع المعرفي والصلاحيات الخاصة بالنظام (المميزات الـ 19 الأساسية):
1. إدارة المنتجات (Product Management): تسجيل الاسم، الكود، الباركود، الفئة، العلامة التجارية، سعر الشراء، سعر البيع، الكمية، والحد الأدنى. التمييز الحازم بين بيانات السلعة الأساسية والدفعات.
2. إدارة المبيعات (Sales Management): تسجيل العمليات والكميات، وتحديث المخزون ترابطياً مع الحسابات، وتقارير الفترات والأكثر مبيعاً.
3. تحليل الأرباح (Profit & Financial Analysis):
   - صافي إيرادات المبيعات = المبيعات بعد الخصومات والمرتجعات.
   - تكلفة البضاعة المباعة (COGS) = تكلفة السلع المباعة فعلياً.
   - مجمل الربح = الإيرادات - تكلفة البضاعة المباعة.
   - هامش مجمل الربح = (مجمل الربح ÷ الإيرادات) × 100%.
   - صافي الربح التشغيلي = مجمل الربح - المصروفات التشغيلية ذات الصلة.
   - احرص على عدم خصم تكلفة البضاعة مرتين والتمييز بين مجمل وصافي الربح.
4. إدارة المخزون (Inventory Management): تتبع الأرصدة، تنبيهات انخفاض المخزون (النواقص)، متابعة تواريخ الصلاحية، ودفعات الشراء المستقلة.
5. متابعة نشاط الباركود (Barcode Monitoring): ربط المسح بالبيع واكتشاف الفروقات للمراجعة.
6. الذكاء الموسمي (Seasonal Intelligence): مواسم رمضان، الأعياد، المدارس، الصيف، وتقديم اقتراحات مبنية على الفترات المماثلة.
7. العروض الذكية (Smart Offers): اقتراح خصومات وتجميعات على السلع الراكدة أو القريبة من انتهاء الصلاحية مع مراعاة حد أدنى للربحية.
8. إدارة المرتجعات (Returns Management): توثيق سبب الإرجاع وفحص حالة السلعة (صالحة لإعادتها للمخزون أم تالفة).
9. إدارة الموردين (Supplier Management): بيانات الشركات والمندوبين ومهل التوريد والحد الأدنى للطلبات.
10. جدولة الموردين والطلبات الذكية (Smart Ordering): اقتراح إعادة الطلب بالكميات المناسبة دون تكديس.
11. التقويم الذكي وتحليل المناسبات (Smart Calendar): ربط المناسبات بتوقعات الطلب.
12. الصفقات الاستثنائية (Special Deals): دراسة العروض المؤقتة وربحيتها وتفادي التكرار.
13. إدارة المصروفات التشغيلية (Operating Expenses): تصنيف الفواتير (كهرباء، ماء، إيجار، مرتبات، صيانة) وسدادها الجزئي/الكلي وتأثيرها على صافي الربح.
14. التنبؤ بالطلب (AI Demand Forecasting): تقدير كميات البيع المستقبلية ونسب اليقين.
15. اكتشاف التناقضات (AI Anomaly Detection): إظهار الأخطاء أو التجاوزات للمراجعة البشرية دون إصدار أحكام تلقائية.
16. الذكاء الاصطناعي مع المراجعة البشرية (Human-in-the-Loop): القرارات الحساسة (أسعار، خصومات، طلبات شراء) تتطلب موافقة المدير.
17. النسخ الاحتياطي (Backup & Disaster Recovery): حماية البيانات وسياسات RPO و RTO.
18. استمرارية المبيعات والأوفلاين (Sales Continuity): حفظ المبيعات محلياً عند انقطاع الشبكة ثم مزامنتها بدون تكرار.
19. سجل العمليات والصلاحيات (Audit Logs & Permissions): تأمين التعديلات الحساسة وتوثيق من قام بالعملية وتاريخها.

قواعد التعامل وسلوك المساعد:
• استخدم دائماً الأرقام والبيانات الواقعية المرفقة في سياق المتجر أدناه عند الإجابة عن أي سلعة أو مؤشر مالي.
• إذا سأل المدير عن أي موضوع تجاري، مالي، إداري أو عام، أجب بذكاء واحترافية وبأسلوب منظم وودود مع أمثلة عملية تناسب السوبر ماركت والسوق.
• في حال طلب المستخدم تعديل سعر أو مخزون، وجهه بصيغة مباشرة مثل: "عدل سعر بيع سكر إلى 35" واشرح له أن النظام سيتطلب تأكيد كلمة المرور كإجراء أمني معتمد لحماية المتجر.
• نسق إجابتك باستخدام Markdown الأنيق (عناوين ###، نقاط •، خط عريض **، وإيموجي معبر).

{store_context}
"""

    # =========================================================================
    # MULTI-MODEL GEMINI CALLER WITH FALLBACK
    # =========================================================================

    @classmethod
    def call_gemini(cls, user_message, store_context, user=None):
        api_key = cls.get_api_key()
        if not api_key:
            return None, None

        system_instruction = cls.get_system_prompt(store_context, user)
        models = cls.get_models()

        full_prompt = (
            f"تعليمات وقواعد النظام والمتجر:\n{system_instruction}\n\n"
            f"سؤال أو طلب المستخدم:\n{user_message}"
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": full_prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.95,
                "maxOutputTokens": 1024
            }
        }
        data = json.dumps(payload).encode('utf-8')

        for model_name in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            try:
                with urllib.request.urlopen(req, timeout=9) as resp:
                    res_json = json.loads(resp.read().decode('utf-8'))
                    candidates = res_json.get('candidates', [])
                    if candidates and 'content' in candidates[0]:
                        parts = candidates[0]['content'].get('parts', [])
                        text_parts = [p.get('text', '') for p in parts if p.get('text')]
                        if text_parts:
                            return "\n".join(text_parts).strip(), model_name
            except Exception:
                continue

        return None, None

    # =========================================================================
    # MAIN AGENT INTERACTION PIPELINE
    # =========================================================================

    @classmethod
    def generate_response(cls, user_message, user=None):
        user_message = (user_message or "").strip()
        if not user_message:
            return {
                "reply": "مرحباً بك! أنا مساعد السوق الذكي 🤖 مدعوم بـ Google Gemini Pro. كيف يمكنني خدمتك اليوم؟ يمكنك سؤالي عن السلع، مبيعات اليوم، الأرباح، النواقص، أو استشارتي في أي موضوع يخص إدارة وتطوير المتجر.",
                "action": "greeting",
                "suggestions": ["مبيعات اليوم 📈", "النواقص في المخزن ⚠️", "سعر السكر كام؟ 📦", "تقرير الأرباح 📊", "نصيحة لزيادة المبيعات 💡"]
            }

        # 1. RAG search
        store_context = cls.search_store_database(user_message)

        # 2. Call Gemini Pro
        gemini_text, used_model = cls.call_gemini(user_message, store_context, user)

        if not gemini_text:
            return None

        # 3. Dynamic Action Buttons based on intent & topics mentioned
        buttons = []
        lower_msg = user_message.lower()

        if any(w in lower_msg for w in ['كاشير', 'بيع', 'pos', 'فاتورة']):
            buttons.append({"text": "فتح الكاشير (POS) 🛒", "url": reverse("sales:pos")})
        if any(w in lower_msg for w in ['منتج', 'مخزون', 'بضاعة', 'سلع', 'نواقص', 'رصيد', 'سكر', 'جبنة', 'زيت', 'أرز', 'صلاحية']):
            buttons.append({"text": "دليل المنتجات والمخزون 📦", "url": reverse("inventory:products_list")})
        if any(w in lower_msg for w in ['أرباح', 'ربح', 'سيولة', 'تقرير', 'مكسب', 'هامش', 'cogs']):
            buttons.append({"text": "تقرير الأرباح والسيولة 📊", "url": reverse("core:financial_report")})
        if any(w in lower_msg for w in ['مصروف', 'مصاريف', 'كهرباء', 'إيجار', 'مرتبات']):
            buttons.append({"text": "سجل المصروفات التشغيلية 🧾", "url": reverse("expenses:expenses_list")})
        if any(w in lower_msg for w in ['مورد', 'موردين', 'شراء', 'مندوب']):
            buttons.append({"text": "دليل الموردين 🚚", "url": reverse("suppliers:suppliers_list")})
        if any(w in lower_msg for w in ['ذكاء', 'توقع', 'توصيات', 'ai', 'تنبؤ']):
            buttons.append({"text": "مركز الذكاء الاصطناعي 🤖", "url": reverse("intelligence:center")})
        if any(w in lower_msg for w in ['تقويم', 'موسم', 'مناسبة', 'رمضان', 'أعياد']):
            buttons.append({"text": "التقويم الذكي والمناسبات 📅", "url": reverse("intelligence:calendar_events")})

        suggestions = ["مبيعات اليوم", "النواقص في المخزن", "تقرير الأرباح", "نصيحة تسويقية للمحل"]

        return {
            "reply": gemini_text,
            "action": "gemini_response",
            "model_used": used_model,
            "buttons": buttons,
            "suggestions": suggestions
        }
