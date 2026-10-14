from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.inventory.models import Product, Category, Warehouse, ProductBatch
from apps.expenses.models import OperatingExpense, ExpenseCategory
from apps.core.models import AuditLog, SystemSettings
from apps.intelligence.chatbot_service import MarketAIChatbot

User = get_user_model()


class MarketAIChatbotTests(TestCase):
    def setUp(self):
        # Create test users
        self.admin_user = User.objects.create_user(
            username='admin_test',
            password='Password123!',
            role='ADMIN',
            first_name='Admin',
            last_name='User'
        )
        self.cashier_user = User.objects.create_user(
            username='cashier_test',
            password='Password123!',
            role='CASHIER',
            first_name='Cashier',
            last_name='User'
        )

        # Create basic test data
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

        # Batch
        self.batch = ProductBatch.objects.create(
            product=self.product,
            warehouse=self.warehouse,
            batch_number='B-001',
            cost_price=Decimal('22.00'),
            initial_quantity=50,
            current_quantity=50
        )

    def test_greeting_on_empty_message(self):
        res = MarketAIChatbot.process_message("", user=self.admin_user)
        self.assertEqual(res.get("action"), "greeting")
        self.assertIn("مرحباً بك", res.get("reply"))
        self.assertTrue(len(res.get("suggestions", [])) > 0)

    def test_navigation_intent_pos(self):
        res = MarketAIChatbot.process_message("عايز اروح لنقطة البيع الكاشير", user=self.admin_user)
        self.assertEqual(res.get("action"), "navigation")
        self.assertIn("/sales/pos/", res.get("url"))

    def test_navigation_intent_products(self):
        res = MarketAIChatbot.process_message("افتح دليل المنتجات والمخزون", user=self.admin_user)
        self.assertEqual(res.get("action"), "navigation")
        self.assertIn("/inventory/products/", res.get("url"))

    def test_query_today_sales(self):
        res = MarketAIChatbot.process_message("مبيعات اليوم", user=self.admin_user)
        self.assertEqual(res.get("action"), "stats")
        self.assertIn("مبيعات اليوم", res.get("reply"))

    def test_query_low_stock(self):
        # Create a product with min_stock_limit 10 and 0 stock to trigger low_stock
        Product.objects.create(
            name='زيت عافية 1 لتر',
            code='PRD-OIL-LOW',
            sale_price=Decimal('70.00'),
            default_cost_price=Decimal('55.00'),
            min_stock_limit=10,
            unit='piece',
            is_active=True
        )
        res = MarketAIChatbot.process_message("النواقص في المخزن", user=self.admin_user)
        self.assertEqual(res.get("action"), "low_stock")
        self.assertIn("النواقص", res.get("reply"))

    def test_create_product_intent(self):
        message = "أضف منتج جديد عصير تفاح جهينة بسعر 25 وتكلفة 18 وباركود 622999888777"
        res = MarketAIChatbot.process_message(message, user=self.admin_user)
        self.assertEqual(res.get("action"), "created")

        # Verify product created in DB
        created = Product.objects.filter(barcode='622999888777').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.sale_price, Decimal('25.00'))
        self.assertEqual(created.default_cost_price, Decimal('18.00'))

    def test_create_expense_intent(self):
        message = "سجل مصروف صيانة مكيفات بقيمة 350"
        res = MarketAIChatbot.process_message(message, user=self.admin_user)
        self.assertEqual(res.get("action"), "created")

        # Verify expense created in DB
        expense = OperatingExpense.objects.filter(amount=Decimal('350.00')).first()
        self.assertIsNotNone(expense)

    def test_update_intent_challenges_auth(self):
        message = "عدل سعر بيع سكر الأسرة إلى 40"
        res = MarketAIChatbot.process_message(message, user=self.admin_user)
        self.assertTrue(res.get("auth_required"))
        self.assertEqual(res.get("action"), "auth_required")
        self.assertIsNotNone(res.get("pending_action"))

        pending = res["pending_action"]
        self.assertEqual(pending.get("type"), "update_product")
        self.assertEqual(pending.get("new_value"), 40.0)
        self.assertEqual(pending.get("product_id"), self.product.id)

    def test_execute_authenticated_action_success(self):
        pending_action = {
            "type": "update_product",
            "product_id": self.product.id,
            "field_name": "sale_price",
            "action_title": "سعر البيع",
            "old_value": 30.00,
            "new_value": 45.00
        }
        auth_data = {
            "username": "admin_test",
            "password": "Password123!"
        }

        res = MarketAIChatbot.process_message("", user=self.admin_user, auth_data=auth_data, pending_action=pending_action)
        self.assertEqual(res.get("action"), "success")
        self.assertIn("تم التحقق بنجاح وتحديث البيانات", res.get("reply"))

        # Check DB update
        self.product.refresh_from_db()
        self.assertEqual(self.product.sale_price, Decimal('45.00'))

        # Check AuditLog
        log = AuditLog.objects.filter(target_model='Product', target_id=str(self.product.id), action='PRICE_CHANGE').first()
        self.assertIsNotNone(log)
        self.assertIn("المساعد الذكي", log.description)

    def test_execute_authenticated_action_invalid_password(self):
        pending_action = {
            "type": "update_product",
            "product_id": self.product.id,
            "field_name": "sale_price",
            "action_title": "سعر البيع",
            "old_value": 30.00,
            "new_value": 50.00
        }
        auth_data = {
            "username": "admin_test",
            "password": "WrongPassword!"
        }

        res = MarketAIChatbot.process_message("", user=self.admin_user, auth_data=auth_data, pending_action=pending_action)
        self.assertEqual(res.get("action"), "auth_failed")
        self.assertIn("فشل التحقق من الهوية", res.get("reply"))

        # Check DB was NOT modified
        self.product.refresh_from_db()
        self.assertEqual(self.product.sale_price, Decimal('30.00'))

    def test_execute_authenticated_action_unauthorized_role(self):
        # Cashier role should be denied even with correct credentials
        pending_action = {
            "type": "update_product",
            "product_id": self.product.id,
            "field_name": "sale_price",
            "action_title": "سعر البيع",
            "old_value": 30.00,
            "new_value": 50.00
        }
        auth_data = {
            "username": "cashier_test",
            "password": "Password123!"
        }

        res = MarketAIChatbot.process_message("", user=self.cashier_user, auth_data=auth_data, pending_action=pending_action)
        self.assertEqual(res.get("action"), "permission_denied")
        self.assertIn("صلاحية", res.get("reply"))

        # Verify no DB change
        self.product.refresh_from_db()
        self.assertEqual(self.product.sale_price, Decimal('30.00'))


class ChatbotViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='view_admin',
            password='Password123!',
            role='ADMIN'
        )
        self.client.force_login(self.user)

    def test_chatbot_api_view_post_json(self):
        url = reverse('intelligence:chatbot_api')
        response = self.client.post(
            url,
            data='{"message": "مبيعات اليوم"}',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("action"), "stats")

    def test_chatbot_page_view(self):
        url = reverse('intelligence:chatbot_page')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "المساعد الذكي لإدارة السوق")
