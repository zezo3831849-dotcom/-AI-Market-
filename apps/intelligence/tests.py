from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.inventory.models import Product, Category, Warehouse, ProductBatch
from apps.expenses.models import OperatingExpense, ExpenseCategory
from apps.intelligence.models import AIRecommendation, Forecast
from apps.core.models import AuditLog
from apps.intelligence.chatbot_service import MarketAIChatbot

User = get_user_model()


class IntelligenceAndChatbotTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='Password123!',
            role='ADMIN',
            first_name='Admin',
            last_name='User'
        )
        self.client.force_login(self.admin_user)

        self.category = Category.objects.create(name='مواد غذائية')
        self.warehouse = Warehouse.objects.create(name='المستودع الرئيسي', code='MAIN')

        self.product = Product.objects.create(
            name='سكر الأسرة 1 كجم',
            code='PRD-SUGAR',
            barcode='6221234567890',
            category=self.category,
            sale_price=Decimal('30.00'),
            default_cost_price=Decimal('22.00'),
            min_stock_limit=10,
            unit='piece',
            is_active=True
        )

        self.batch = ProductBatch.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            batch_number='B-001',
            cost_price=Decimal('22.00'),
            initial_quantity=50,
            current_quantity=50
        )

    # 1. Intelligence Center Views Tests
    def test_intelligence_center_view(self):
        url = reverse('intelligence:center')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_forecasts_view(self):
        url = reverse('intelligence:forecasts_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_anomalies_view(self):
        url = reverse('intelligence:anomalies_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_smart_offers_view(self):
        url = reverse('intelligence:smart_offers')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    # 2. Chatbot Service Intent & Logic Tests
    def test_chatbot_greeting_on_empty(self):
        res = MarketAIChatbot.process_message("", user=self.admin_user)
        self.assertEqual(res.get("action"), "greeting")
        self.assertIn("مرحباً بك", res.get("reply"))
        self.assertTrue(len(res.get("suggestions", [])) > 0)

    def test_chatbot_query_today_sales(self):
        res = MarketAIChatbot.process_message("مبيعات اليوم", user=self.admin_user)
        self.assertEqual(res.get("action"), "stats")
        self.assertIn("مبيعات اليوم", res.get("reply"))

    def test_chatbot_query_financial_summary(self):
        res = MarketAIChatbot.process_message("تقرير الأرباح والسيولة", user=self.admin_user)
        self.assertEqual(res.get("action"), "stats")
        self.assertIn("مجمل الربح", res.get("reply"))

    def test_chatbot_create_product_intent(self):
        message = "أضف منتج جديد عصير جهينة مانجو بسعر 20 وتكلفة 14 وباركود 622111222333"
        res = MarketAIChatbot.process_message(message, user=self.admin_user)
        self.assertEqual(res.get("action"), "created")

        created = Product.objects.filter(barcode='622111222333').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.sale_price, Decimal('20.00'))

    def test_chatbot_create_expense_intent(self):
        message = "سجل مصروف كهرباء بقيمة 450"
        res = MarketAIChatbot.process_message(message, user=self.admin_user)
        self.assertEqual(res.get("action"), "created")

        exp = OperatingExpense.objects.filter(amount=Decimal('450.00')).first()
        self.assertIsNotNone(exp)

    def test_chatbot_update_challenges_auth(self):
        message = "عدل سعر بيع سكر الأسرة إلى 38"
        res = MarketAIChatbot.process_message(message, user=self.admin_user)
        self.assertTrue(res.get("auth_required"))
        self.assertEqual(res.get("action"), "auth_required")

        pending = res.get("pending_action")
        self.assertEqual(pending.get("new_value"), 38.0)

    def test_chatbot_execute_auth_success(self):
        pending_action = {
            "type": "update_product",
            "product_id": self.product.id,
            "field_name": "sale_price",
            "action_title": "سعر البيع",
            "old_value": 30.00,
            "new_value": 38.00
        }
        auth_data = {
            "username": "admin_test",
            "password": "Password123!"
        }
        res = MarketAIChatbot.process_message("", user=self.admin_user, auth_data=auth_data, pending_action=pending_action)
        self.assertEqual(res.get("action"), "success")

        self.product.refresh_from_db()
        self.assertEqual(self.product.sale_price, Decimal('38.00'))

    def test_chatbot_store_rag_search(self):
        from apps.intelligence.gemini_service import GeminiMarketAgent
        ctx = GeminiMarketAgent.search_store_database("سكر")
        self.assertIn("سكر الأسرة", ctx)
        self.assertIn("30.00", ctx)

    # 3. Chatbot Views Tests
    def test_chatbot_api_view_post(self):
        url = reverse('intelligence:chatbot_api')
        res = self.client.post(
            url,
            data='{"message": "مبيعات اليوم"}',
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("action"), "stats")

    def test_chatbot_page_view(self):
        url = reverse('intelligence:chatbot_page')
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "مساعد السوق الذكي الشامل")
