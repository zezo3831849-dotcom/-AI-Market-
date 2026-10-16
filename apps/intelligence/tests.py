from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.inventory.models import Product, Category
from apps.intelligence.models import AIRecommendation, Forecast

User = get_user_model()


class IntelligenceCenterTests(TestCase):
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
        self.product = Product.objects.create(
            name='سكر الأسرة 1 كجم',
            code='PRD-SUGAR',
            category=self.category,
            sale_price=Decimal('30.00'),
            default_cost_price=Decimal('22.00'),
            min_stock_limit=10,
            unit='piece',
            is_active=True
        )

    def test_intelligence_center_view(self):
        url = reverse('intelligence:center')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'مركز الذكاء الاصطناعي')

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
