"""
Google Gemini AI Engine for Market Manager
Provides conversational intelligence, website RAG search, and business advisory
customized exclusively for this market management system.
"""

import os
import json
import re
import urllib.request
import urllib.error
from decimal import Decimal
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.db.models import Q, Sum
from django.urls import reverse

from apps.core.models import SystemSettings
from apps.inventory.models import Product, ProductBatch, Category, Warehouse
from apps.sales.models import Sale, SaleItem
from apps.expenses.models import OperatingExpense, ExpenseCategory
from apps.suppliers.models import Supplier
from apps.intelligence.models import CalendarEvent, Forecast, AIRecommendation


class GeminiMarketAgent:
    """
    Intelligent agent powered by Google Gemini, grounded in live store data.
    """

    @classmethod
    def get_api_key(cls):
        return getattr(settings, 'GEMINI_API_KEY', '') or os.environ.get('GEMINI_API_KEY', '')

    @classmethod
    def get_models(cls):
        return getattr(settings, 'GEMINI_MODELS', [
            'gemini-flash-lite-latest',
            'gemini-3.1-flash-lite',
            'gemini-flash-latest',
        ])

    # =========================================================================
    # RAG: SEARCH STORE DATABASE & BUILD LIVE CONTEXT
    # =========================================================================

    @classmethod
    def search_store_database(cls, user_message):
        """
        Extracts entities from the user's question, searches products, batches,
        sales, expenses, and suppliers, and returns rich textual context.
        """
        context_parts = []
        today = timezone.localdate()

        # 1. Basic Store Settings & Overview
        try:
            store_settings = SystemSettings.get_settings()
            store_name = store_settings.store_name if store_settings else "سوق المستقبل الذكي"
            currency = store_settings.currency if store_settings else "ج.م"
        except Exception:
            store_name = "سوق المستقبل الذكي"
            currency = "ج.م"

        context_parts.append(f"📌 [بيانات المتجر]: الاسم: {store_name} | العملة المعتمدة: {currency} | التاريخ الحالي: {today.strftime('%Y-%m-%d')}")

        # 2. Live Store Health & Performance
        try:
            today_sales = Sale.objects.filter(created_at__date=today, status='COMPLETED')
            today_rev = sum((s.final_amount for s in today_sales), Decimal('0.00'))
            today_count = today_sales.count()

            # Month financial preview
            start_of_month = today.replace(day=1)
            month_expenses = OperatingExpense.objects.filter(expense_date__gte=start_of_month, expense_date__lte=today)
            month_exp_tot = sum((e.amount for e in month_expenses), Decimal('0.00'))

            # Inventory counts
            total_prods = Product.objects.filter(is_active=True).count()
            low_stock_prods = [p for p in Product.objects.filter(is_active=True) if p.is_low_stock]
            
            near_expiry_count = ProductBatch.objects.filter(
                current_quantity__gt=0,
                expiry_date__isnull=False,
                expiry_date__lte=today + timedelta(days=30),
                expiry_date__gte=today
            ).count()

            pending_recs = AIRecommendation.objects.filter(status='PENDING').count()

            context_parts.append(
                f"📊 [مؤشرات المتجر اللحظية]:\n"
                f"- إجمالي السلع المسجلة: {total_prods} منتج\n"
                f"- مبيعات اليوم: {today_rev:,.2f} {currency} ({today_count} فاتورة مكتملة)\n"
                f"- إجمالي مصروفات هذا الشهر: {month_exp_tot:,.2f} {currency}\n"
                f"- عدد السلع التي بحاجة لإعادة طلب (نواقص): {len(low_stock_prods)} سلع\n"
                f"- دفعات قريبة من تاريخ الانتهاء (خلال شهر): {near_expiry_count} دفعة\n"
                f"- توصيات الذكاء الاصطناعي المعلقة بانتظار قرار المدير: {pending_recs} توصية"
            )
        except Exception:
            pass

        # 3. Targeted Product & Inventory Search based on User Query
        clean_query = re.sub(r'[^\w\s]', ' ', user_message)
        stop_words = {'هل', 'في', 'من', 'على', 'عن', 'الى', 'إلى', 'كام', 'سعر', 'عندنا', 'عايز', 'بكام', 'موجود', 'ايه', 'معانا', 'محتاج', 'فين', 'رصيد', 'كمية'}
        keywords = [w.strip() for w in clean_query.split() if len(w.strip()) >= 2 and w.strip() not in stop_words]

        matched_products = []
        if keywords:
            q_filter = Q()
            for kw in keywords[:4]:
                q_filter |= Q(name__icontains=kw) | Q(brand__icontains=kw) | Q(code__icontains=kw) | Q(barcode__icontains=kw)
            matched_products = list(Product.objects.filter(is_active=True).filter(q_filter).distinct()[:6])

        if matched_products:
            prod_lines = []
            for p in matched_products:
                batches = p.batches.filter(current_quantity__gt=0).order_by('expiry_date')
                batch_info = ", ".join([f"دفعة {b.batch_number} (متبقي {b.current_quantity}{p.get_unit_display()}" + (f", تنتهي {b.expiry_date}" if b.expiry_date else "") + ")" for b in batches[:2]])
                
                prod_lines.append(
                    f"• {p.name} [{p.code}]: سعر البيع: {p.sale_price:,.2f} {currency} | سعر التكلفة: {p.default_cost_price:,.2f} {currency} | "
                    f"الرصيد الكلي: {p.total_stock} {p.get_unit_display()} | الحد الأدنى: {p.min_stock_limit} | "
                    f"الباركود: {p.barcode or 'غير مسجل'} | الحالة: {'⚠️ منخفض المخزون' if p.is_low_stock else '✅ متوفر'} "
                    + (f"| الدفعات: {batch_info}" if batch_info else "| لا توجد دفعات حالياً")
                )
            context_parts.append("📦 [نتائج البحث عن السلع المذكورة في المتجر]:\n" + "\n".join(prod_lines))

        # 4. Search for Suppliers if mentioned
        if any(w in user_message for w in ['مورد', 'موردين', 'شركة', 'مندوب', 'شراء']):
            suppliers = Supplier.objects.filter(is_active=True)[:5]
            if suppliers:
                sup_lines = [f"• {s.company_name} (هاتف: {s.phone}, مندوب: {s.rep_name or 'غير محدد'}, مهلة التوريد: {s.lead_time_days} أيام)" for s in suppliers]
                context_parts.append("🚚 [دليل الموردين النشطين بالمتجر]:\n" + "\n".join(sup_lines))

        # 5. Search for Operating Expenses if mentioned
        if any(w in user_message for w in ['مصروف', 'مصاريف', 'فاتورة', 'كهرباء', 'إيجار', 'ايجار', 'صيانة', 'راتب']):
            recent_exp = OperatingExpense.objects.order_by('-expense_date')[:4]
            if recent_exp:
                exp_lines = [f"• {e.title}: {e.amount:,.2f} {currency} بتاريخ {e.expense_date} (الحالة: {e.get_payment_status_display()})" for e in recent_exp]
                context_parts.append("💸 [آخر المصروفات المسجلة]:\n" + "\n".join(exp_lines))

        return "\n\n".join(context_parts)

    # =========================================================================
    # SYSTEM PROMPT GENERATOR
    # =========================================================================

    @classmethod
    def get_system_prompt(cls, store_context, user=None):
        username = getattr(user, 'first_name', '') or getattr(user, 'username', 'المدير')
        role_name = getattr(user, 'get_role_display', lambda: 'المدير')() if user else 'المدير'

        return f"""أنت "المساعد الذكي لإدارة السوق" (Market AI Assistant)، مدعوم بنموذج Google Gemini Pro الفائق.
أنت مخصص حصرياً لهذا المتجر ونظام إدارته الإلكتروني المتكامل.
المستخدم الحالي الذي يتحدث معك هو: {username} ({role_name}).

القدرات والصلاحيات المتاحة لك:
1. أنت متصل مباشرة بقاعدة بيانات المتجر عبر السياق الحي المرفق أدناه، لذا استند دائماً إلى الأرقام والأسعار والكميات الحقيقية للمتجر في إجاباتك.
2. إذا سأل المستخدم عن صنف أو سعر أو كمية في المخزن، ابحث في السياق وأجب بدقة: (سعر البيع، سعر التكلفة، هامش الربح، الرصيد المتاح، وتاريخ الانتهاء إن وجد).
3. إذا سأل عن سلعة غير موجودة في المتجر، وضح بلباقة أنها غير مسجلة حالياً واقترح عليه إضافتها بنص واضح مثل: "أضف منتج جديد [اسم المنتج] بسعر ... وتكلفة ...".
4. يمكنك تقديم تحليلات تجارية، واستشارات تسعيرية، ونصائح لزيادة الأرباح وتصريف السلع الراكدة، واقتراح حملات وعروض ترويجية.
5. يمكنك الإجابة عن أي أسئلة عامة (تجارية، محاسبية، تسويقية، أو عامة في أي مجال) بأسلوب ودود وذكي واحترافي، مع ربط الإجابة بالمتجر كلما كان ذلك ملائماً.
6. إذا طلب المستخدم تعديل سعر أو حد مخزون، وجهه لكتابة الأمر مثل: "عدل سعر بيع سكر إلى 35" واشرح له أن النظام سيتطلب تأكيد كلمة المرور كإجراء أمني معتمد.
7. استخدم دائماً تنسيق Markdown الجميل (عناوين، نقاط، خط عريض **، وإيموجي ذكي) لتكون الإجابة سهلة القراءة وممتعة.

{store_context}
"""

    # =========================================================================
    # MULTI-MODEL GEMINI CALLER WITH FALLBACK
    # =========================================================================

    @classmethod
    def call_gemini(cls, user_message, store_context, user=None):
        """
        Sends query to Google Gemini API with fallback over available models.
        """
        api_key = cls.get_api_key()
        if not api_key:
            return None

        system_instruction = cls.get_system_prompt(store_context, user)
        models = cls.get_models()

        full_prompt = (
            f"تعليمات النظام وقواعد المتجر:\n{system_instruction}\n\n"
            f"سؤال أو رسالة المستخدم:\n{user_message}"
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
            except Exception as e:
                # Silently try next candidate model upon rate limit (429), high demand (503), or timeout
                continue

        return None, None

    # =========================================================================
    # MAIN AGENT INTERACTION METHOD
    # =========================================================================

    @classmethod
    def generate_response(cls, user_message, user=None):
        """
        Processes any user message, searches the store, calls Gemini Pro,
        and generates rich action buttons and navigation shortcuts.
        """
        user_message = (user_message or "").strip()
        if not user_message:
            return {
                "reply": "مرحباً بك! أنا مساعد السوق الذكي 🤖 مدعوم بـ Google Gemini Pro. كيف أستطيع خدمتك اليوم؟",
                "action": "greeting",
                "suggestions": ["مبيعات اليوم 📈", "النواقص في المخزن ⚠️", "سعر السكر كام؟ 📦", "نصيحة لزيادة الأرباح 💡"]
            }

        # 1. Gather live store context (RAG)
        store_context = cls.search_store_database(user_message)

        # 2. Call Gemini Pro
        gemini_text, used_model = cls.call_gemini(user_message, store_context, user)

        # 3. Fallback to smart local answering if Gemini API is unreachable (e.g. offline)
        if not gemini_text:
            return None

        # 4. Generate contextual Action Buttons based on topics mentioned
        buttons = []
        lower_msg = user_message.lower()

        if any(w in lower_msg for w in ['كاشير', 'بيع', 'pos', 'فاتورة']):
            buttons.append({"text": "فتح الكاشير (POS) 🛒", "url": reverse("sales:pos")})
        if any(w in lower_msg for w in ['منتج', 'مخزون', 'بضاعة', 'سلع', 'نواقص', 'رصيد', 'سكر', 'جبنة', 'زيت', 'أرز']):
            buttons.append({"text": "دليل المنتجات والمخزون 📦", "url": reverse("inventory:products_list")})
        if any(w in lower_msg for w in ['أرباح', 'ربح', 'سيولة', 'تقرير', 'مكسب']):
            buttons.append({"text": "تقرير الأرباح والسيولة 📊", "url": reverse("core:financial_report")})
        if any(w in lower_msg for w in ['مصروف', 'مصاريف', 'كهرباء', 'إيجار']):
            buttons.append({"text": "سجل المصروفات 🧾", "url": reverse("expenses:expenses_list")})
        if any(w in lower_msg for w in ['مورد', 'موردين', 'شراء']):
            buttons.append({"text": "دليل الموردين 🚚", "url": reverse("suppliers:suppliers_list")})
        if any(w in lower_msg for w in ['ذكاء', 'توقع', 'توصيات', 'ai']):
            buttons.append({"text": "مركز الذكاء الاصطناعي 🤖", "url": reverse("intelligence:center")})

        # Suggestions
        suggestions = ["مبيعات اليوم", "النواقص في المخزن", "تقرير الأرباح", "نصيحة تسويقية للمحل"]

        return {
            "reply": gemini_text,
            "action": "gemini_response",
            "model_used": used_model,
            "buttons": buttons,
            "suggestions": suggestions
        }
