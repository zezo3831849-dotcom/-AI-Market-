from django.db import models
from django.conf import settings
from django.utils import timezone


class Supplier(models.Model):
    company_name = models.CharField(max_length=150, verbose_name='اسم الشركة / المورد')
    rep_name = models.CharField(max_length=100, blank=True, verbose_name='اسم المندوب')
    phone = models.CharField(max_length=50, verbose_name='رقم الهاتف')
    secondary_phone = models.CharField(max_length=50, blank=True, verbose_name='هاتف إضافي')
    email = models.EmailField(blank=True, verbose_name='البريد الإلكتروني')
    address = models.CharField(max_length=255, blank=True, verbose_name='العنوان')
    
    lead_time_days = models.PositiveIntegerField(default=2, verbose_name='مهلة تجهيز وتسليم الطلب (بالأيام)')
    min_order_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='الحد الأدنى لقيمة الطلب (ج.م)')
    min_order_qty = models.PositiveIntegerField(default=1, verbose_name='الحد الأدنى لكمية الطلب')
    payment_terms = models.CharField(max_length=100, blank=True, default='نقدي عند الاستلام', verbose_name='شروط الدفع والتوريد')
    
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.00, verbose_name='تقييم الالتزام (من 5)')
    notes = models.TextField(blank=True, verbose_name='ملاحظات عامة')
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'مورد'
        verbose_name_plural = 'الموردون'
        ordering = ['company_name']

    def __str__(self):
        return f"{self.company_name} ({self.rep_name or self.phone})"


class SupplierSchedule(models.Model):
    DAY_CHOICES = [
        ('SAT', 'السبت'),
        ('SUN', 'الأحد'),
        ('MON', 'الاثنين'),
        ('TUE', 'الثلاثاء'),
        ('WED', 'الأربعاء'),
        ('THU', 'الخميس'),
        ('FRI', 'الجمعة'),
    ]

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='schedules', verbose_name='المورد')
    visit_day = models.CharField(max_length=10, choices=DAY_CHOICES, verbose_name='يوم زيارة المندوب المعتاد')
    order_deadline_time = models.TimeField(null=True, blank=True, verbose_name='الموعد النهائي لإرسال الطلب')
    expected_delivery_delay_days = models.PositiveIntegerField(default=1, verbose_name='أيام التسليم المتوقعة بعد الطلب')
    notes = models.CharField(max_length=255, blank=True, verbose_name='ملاحظات الموعد')

    class Meta:
        verbose_name = 'جدول مواعيد المورد'
        verbose_name_plural = 'جداول مواعيد الموردين'

    def __str__(self):
        return f"زيارة {self.supplier.company_name} يوم {self.get_visit_day_display()}"


class SupplierProduct(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='products_offered', verbose_name='المورد')
    product = models.ForeignKey('inventory.Product', on_delete=models.CASCADE, related_name='supplier_prices', verbose_name='المنتج')
    supply_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='سعر الشراء المسجل (ج.م)')
    is_primary = models.BooleanField(default=True, verbose_name='المورد الرئيسي لهذا المنتج')
    notes = models.CharField(max_length=255, blank=True, verbose_name='شروط خاصة بالمنتج')

    class Meta:
        verbose_name = 'سعر توريد منتج'
        verbose_name_plural = 'أسعار توريد المنتجات'
        unique_together = ('supplier', 'product')

    def __str__(self):
        return f"{self.supplier.company_name} - {self.product.name} ({self.supply_price} ج.م)"


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'مسودة طلب'),
        ('APPROVED', 'معتمد من المدير'),
        ('SENT', 'تم الإرسال للمورد'),
        ('PARTIAL', 'مستلم جزئياً'),
        ('RECEIVED', 'مستلم بالكامل وجاري إيداعه بالمخزن'),
        ('CANCELLED', 'ملغي'),
    ]

    po_number = models.CharField(max_length=60, unique=True, verbose_name='رقم أمر الشراء')
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name='purchase_orders', verbose_name='المورد')
    order_date = models.DateField(default=timezone.now, verbose_name='تاريخ أمر الشراء')
    expected_delivery_date = models.DateField(null=True, blank=True, verbose_name='تاريخ التسليم المتوقع')
    actual_delivery_date = models.DateField(null=True, blank=True, verbose_name='تاريخ الاستلام الفعلي')
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='إجمالي الطلب (ج.م)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name='حالة الطلب')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='أنشئ بواسطة')
    notes = models.TextField(blank=True, verbose_name='ملاحظات التوريد')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'أمر شراء'
        verbose_name_plural = 'أوامر الشراء'
        ordering = ['-order_date', '-created_at']

    def __str__(self):
        return f"{self.po_number} - {self.supplier.company_name} ({self.get_status_display()})"


class PurchaseOrderItem(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items', verbose_name='أمر الشراء')
    product = models.ForeignKey('inventory.Product', on_delete=models.PROTECT, verbose_name='المنتج')
    ordered_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الكمية المطلوبة')
    received_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name='الكمية المستلمة فعلياً')
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='سعر الوحدة المتفق عليه (ج.م)')
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='إجمالي التكلفة')

    class Meta:
        verbose_name = 'بند أمر شراء'
        verbose_name_plural = 'بنود أوامر الشراء'

    def save(self, *args, **kwargs):
        self.total_cost = self.ordered_quantity * self.unit_cost
        super().save(*args, **kwargs)


class SpecialDeal(models.Model):
    STATUS_CHOICES = [
        ('PROPOSED', 'فرصة مطروحة للدراسة'),
        ('APPROVED', 'معتمدة للشراء'),
        ('REJECTED', 'مرفوضة من الإدارة'),
        ('EXECUTED', 'تم الشراء وإيداع المخزون'),
    ]

    title = models.CharField(max_length=200, verbose_name='عنوان الصفقة / العرض الخاص')
    supplier = models.ForeignKey(Supplier, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='المورد أو الشركة العارضة')
    product_name = models.CharField(max_length=200, verbose_name='اسم المنتج / البضاعة')
    linked_product = models.ForeignKey('inventory.Product', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='المنتج المقابل في المخزن')
    
    quantity_offered = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الكمية المعروضة')
    deal_unit_cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='سعر الشراء الاستثنائي للوحدة (ج.م)')
    expected_selling_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='سعر البيع المتوقع للوحدة (ج.م)')
    extra_expenses = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name='مصروفات نقل أو تجهيز إضافية (ج.م)')
    
    expiry_date = models.DateField(null=True, blank=True, verbose_name='تاريخ صلاحية المنتج (إن وجد)')
    offer_deadline = models.DateField(null=True, blank=True, verbose_name='الموعد النهائي لقبول العرض')
    
    potential_gross_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='مجمل الربح التقديري (ج.م)')
    roi_percent = models.DecimalField(max_digits=6, decimal_places=2, default=0.00, verbose_name='العائد على الاستثمار المتوقع (%)')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PROPOSED', verbose_name='حالة الصفقة')
    manager_decision_notes = models.TextField(blank=True, verbose_name='ملاحظات وقرار المدير')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'صفقة استثنائية'
        verbose_name_plural = 'الصفقات الاستثنائية'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - ربح تقديري {self.potential_gross_profit} ج.م ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        total_cost = (self.quantity_offered * self.deal_unit_cost) + self.extra_expenses
        total_revenue = self.quantity_offered * self.expected_selling_price
        self.potential_gross_profit = total_revenue - total_cost
        if total_cost > 0:
            self.roi_percent = round((self.potential_gross_profit / total_cost) * 100, 2)
        super().save(*args, **kwargs)
