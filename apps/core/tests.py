from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User
from apps.inventory.models import Product, ProductBatch, Warehouse, InventoryMovement
from apps.sales.models import Sale, SaleItem, Return
from apps.sales.services import process_sale, process_return, sync_offline_sales
from apps.expenses.models import ExpenseCategory, OperatingExpense
from apps.core.financial_services import get_financial_summary
from apps.core.backup_service import perform_backup
from apps.intelligence.services import run_complete_ai_pipeline


class MarketManagerComprehensiveTests(TestCase):
    def setUp(self):
        # Create test users
        self.admin = User.objects.create_user(username='admin_test', password='password', role='ADMIN')
        self.cashier = User.objects.create_user(username='cashier_test', password='password', role='CASHIER')
        
        # Warehouse
        self.wh = Warehouse.objects.create(name='المخزن الرئيسي', code='WH-1', is_default=True)
        
        # Product & Batches with multiple costs (Feature 1 & 4)
        self.product = Product.objects.create(
            name='لبن جهينة 1 لتر',
            code='JUH-MILK',
            default_cost_price=Decimal('30.00'),
            sale_price=Decimal('40.00'),
            min_stock_limit=Decimal('5.00')
        )
        self.batch1 = ProductBatch.objects.create(
            product=self.product,
            warehouse=self.wh,
            batch_number='B-01',
            initial_quantity=Decimal('10.00'),
            current_quantity=Decimal('10.00'),
            cost_price=Decimal('28.00'), # older batch bought at 28
            received_date=timezone.now().date()
        )
        self.batch2 = ProductBatch.objects.create(
            product=self.product,
            warehouse=self.wh,
            batch_number='B-02',
            initial_quantity=Decimal('20.00'),
            current_quantity=Decimal('20.00'),
            cost_price=Decimal('32.00'), # newer batch bought at 32
            received_date=timezone.now().date()
        )

    def test_fifo_sale_and_profit_calculation(self):
        """Tests that sale deducts from oldest batch first and computes exact COGS & gross profit."""
        items_data = [{
            'product_id': self.product.id,
            'quantity': 15,  # 10 from batch1 (cost 28) + 5 from batch2 (cost 32)
            'unit_price': 40
        }]
        
        sale, created, msg = process_sale(
            cashier=self.cashier,
            items_data=items_data,
            discount_amount=Decimal('0.00')
        )
        
        self.assertTrue(created)
        self.assertEqual(sale.total_amount, Decimal('600.00')) # 15 * 40
        # Expected COGS: (10 * 28) + (5 * 32) = 280 + 160 = 440
        self.assertEqual(sale.total_cost, Decimal('440.00'))
        # Gross profit: 600 - 440 = 160
        self.assertEqual(sale.gross_profit, Decimal('160.00'))
        
        # Batch 1 should now be 0, Batch 2 should be 15
        self.batch1.refresh_from_db()
        self.batch2.refresh_from_db()
        self.assertEqual(self.batch1.current_quantity, Decimal('0.00'))
        self.assertEqual(self.batch2.current_quantity, Decimal('15.00'))

    def test_offline_sync_idempotency(self):
        """Tests that a re-sent offline sale UUID is not duplicated or stock re-deducted."""
        uuid_key = 'unique-offline-uuid-12345'
        items_data = [{'product_id': self.product.id, 'quantity': 2, 'unit_price': 40}]
        
        # First sync
        summary1 = sync_offline_sales(self.cashier, [{
            'client_uuid': uuid_key,
            'items': items_data
        }])
        self.assertEqual(summary1['success'], 1)
        self.assertEqual(summary1['duplicates'], 0)
        
        stock_after_first = self.product.total_stock
        
        # Second sync with same UUID
        summary2 = sync_offline_sales(self.cashier, [{
            'client_uuid': uuid_key,
            'items': items_data
        }])
        self.assertEqual(summary2['success'], 0)
        self.assertEqual(summary2['duplicates'], 1)
        
        # Stock should remain untouched
        self.assertEqual(self.product.total_stock, stock_after_first)

    def test_financial_statement_separation(self):
        """Tests that COGS and Operating Expenses are strictly separated and Net Operating Profit is exact."""
        # 1. Process sale
        process_sale(
            cashier=self.cashier,
            items_data=[{'product_id': self.product.id, 'quantity': 5, 'unit_price': 40}],
            discount_amount=Decimal('0.00')
        ) # Revenue: 200, COGS: 140 (5*28), Gross Profit: 60
        
        # 2. Add operating expense
        cat = ExpenseCategory.objects.create(name='كهرباء', code='EXP-ELEC')
        OperatingExpense.objects.create(
            title='فاتورة كهرباء',
            category=cat,
            amount=Decimal('25.00'),
            paid_amount=Decimal('25.00'),
            created_by=self.admin
        )
        
        # 3. Calculate financial summary
        finance = get_financial_summary()
        self.assertEqual(finance['net_sales_revenue'], Decimal('200.00'))
        self.assertEqual(finance['cogs'], Decimal('140.00'))
        self.assertEqual(finance['gross_profit'], Decimal('60.00'))
        self.assertEqual(finance['operating_expenses'], Decimal('25.00'))
        # Net operating profit: 60 - 25 = 35
        self.assertEqual(finance['net_operating_profit'], Decimal('35.00'))

    def test_backup_and_recovery_service(self):
        """Tests database snapshot backup generation."""
        success, log = perform_backup("اختبار النسخ الاحتياطي التلقائي")
        self.assertTrue(success)
        self.assertEqual(log.status, 'SUCCESS')
        self.assertGreater(log.file_size_kb, 0)
