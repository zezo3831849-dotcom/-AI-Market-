import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class Sale(models.Model):
    PAYMENT_CHOICES = [
        ('CASH', 'نقداً (Cash)'),
        ('CARD', 'بطاقة / فيزا (Card)'),
        ('WALLET', 'محفظة إلكترونية (Wallet)'),
        ('SPLIT', 'دفع مختلط (Split)'),
    ]

    STATUS_CHOICES = [
        ('COMPLETED', 'مكتملة وناجحة'),
        ('CANCELLED', 'ملغاة'),
        ('REFUNDED', 'مسترجعة كلياً'),
        ('PARTIAL_REFUND', 'مسترجعة جزئياً'),
    ]

    invoice_number = models.CharField(max_length=60, unique=True, verbose_name='رقم الفاتورة')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='sales', verbose_name='الكاشير')
    customer_name = models.CharField(max_length=150, default='عميل نقدي', verbose_name='اسم العميل')
    
    # Financials
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='إجمالي المنتجات قبل الخصم (ج.م)')
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='قيمة الخصم (ج.م)')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='صافي إيراد الفاتورة (ج.م)')
    
    # Critical accounting metrics from PDF
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='تكلفة البضاعة المباعة COGS (ج.م)')
    gross_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='مجمل ربح الفاتورة (ج.م)')
    
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='CASH', verbose_name='طريقة الدفع')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='COMPLETED', verbose_name='حالة العملية')
    
    # Offline sync resilience & Idempotency
    client_uuid = models.CharField(max_length=100, unique=True, default=uuid.uuid4, verbose_name='معرف العملية الفريد (UUID)')
    is_offline_sync = models.BooleanField(default=False, verbose_name='تم تسجيلها أثناء انقطاع الاتصال ومزامنتها')
    synced_at = models.DateTimeField(null=True, blank=True, verbose_name='وقت وصول المزامنة للخادم')
    
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='تاريخ ووقت البيع')

    class Meta:
        verbose_name = 'عملية بيع'
        verbose_name_plural = 'المبيعات'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.invoice_number} - {self.total_amount} ج.م ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    @property
    def gross_margin_percent(self):
        if self.total_amount > 0:
            return round((self.gross_profit / self.total_amount) * 100, 2)
        return 0.0


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items', verbose_name='الفاتورة')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT, related_name='sale_items', verbose_name='المنتج')
    batch = models.ForeignKey('inventory.ProductBatch', on_delete=models.SET_NULL, null=True, blank=True, related_name='sale_items', verbose_name='دفعة الشراء')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الكمية المباعة')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='سعر البيع الفعلي للوحدة (ج.م)')
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name='تكلفة الوحدة للشراء (ج.م)')
    total_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='إجمالي سعر البيع')
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='إجمالي تكلفة البضاعة')
    gross_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='مجمل ربح البند')

    class Meta:
        verbose_name = 'بند فاتورة بيع'
        verbose_name_plural = 'بنود فواتير البيع'

    def __str__(self):
        return f"{self.product.name} x {self.quantity} في {self.sale.invoice_number}"

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        self.total_cost = self.quantity * self.unit_cost
        self.gross_profit = self.total_price - self.total_cost
        super().save(*args, **kwargs)


class Return(models.Model):
    return_number = models.CharField(max_length=60, unique=True, verbose_name='رقم إذن المرتجع')
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name='returns', verbose_name='فاتورة البيع الأصلية')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='المستلم')
    total_refund_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='إجمالي المبلغ المسترد (ج.م)')
    reason = models.TextField(verbose_name='سبب الإرجاع')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='تاريخ ووقت المرتجع')

    class Meta:
        verbose_name = 'عملية مرتجع'
        verbose_name_plural = 'المرتجهات'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.return_number} - استرداد {self.total_refund_amount} ج.م"


class ReturnItem(models.Model):
    CONDITION_CHOICES = [
        ('SELLABLE', 'سليم وصالح للبيع (يعاد للمخزون)'),
        ('DAMAGED', 'تالف / معيب (لا يعاد للمخزون البيعي)'),
        ('EXPIRED', 'منتهي الصلاحية (هالك)'),
    ]

    return_record = models.ForeignKey(Return, on_delete=models.CASCADE, related_name='items', verbose_name='إذن المرتجع')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT, verbose_name='المنتج')
    batch = models.ForeignKey('inventory.ProductBatch', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='الدفعة الأصلية')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الكمية المرتجعة')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='سعر الوحدة المسترد')
    total_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='إجمالي المسترد للبند')
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='SELLABLE', verbose_name='حالة المنتج المرتجع')
    returned_to_stock = models.BooleanField(default=True, verbose_name='تم إعادته للمخزون الفعلي')

    class Meta:
        verbose_name = 'بند مرتجع'
        verbose_name_plural = 'بنود المرتجعات'

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)


class SyncOperation(models.Model):
    STATUS_CHOICES = [
        ('SUCCESS', 'تمت المزامنة بنجاح'),
        ('DUPLICATE', 'عملية مكررة تم تجاهلها'),
        ('CONFLICT', 'تعارض بيانات يحتاج مراجعة'),
        ('FAILED', 'فشل في المزامنة'),
    ]

    client_uuid = models.CharField(max_length=100, unique=True, verbose_name='معرف العملية للعميل')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='الكاشير')
    operation_type = models.CharField(max_length=50, default='OFFLINE_SALE', verbose_name='نوع العملية')
    payload = models.TextField(verbose_name='بيانات العملية (JSON)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUCCESS', verbose_name='حالة المزامنة')
    reconciliation_notes = models.TextField(blank=True, verbose_name='تقرير التسوية والمطابقة')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الوصول للخادم')

    class Meta:
        verbose_name = 'عملية مزامنة أوفلاين'
        verbose_name_plural = 'عمليات المزامنة'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.client_uuid} - {self.get_status_display()}"
