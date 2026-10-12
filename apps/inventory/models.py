from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class Category(models.Model):
    name = models.CharField(max_length=120, unique=True, verbose_name='اسم التصنيف')
    description = models.TextField(blank=True, verbose_name='الوصف')
    icon = models.CharField(max_length=50, default='bi-tag', verbose_name='الأيقونة')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')

    class Meta:
        verbose_name = 'تصنيف'
        verbose_name_plural = 'التصنيفات'
        ordering = ['name']

    def __str__(self):
        return self.name


class Warehouse(models.Model):
    name = models.CharField(max_length=120, verbose_name='اسم المخزن / الفرع')
    code = models.CharField(max_length=50, unique=True, verbose_name='كود المخزن')
    location = models.CharField(max_length=255, blank=True, verbose_name='الموقع')
    is_default = models.BooleanField(default=False, verbose_name='المخزن الرئيسي الافتراضي')

    class Meta:
        verbose_name = 'مخزن'
        verbose_name_plural = 'المخازن'

    def __str__(self):
        return f"{self.name} ({self.code})"

    def save(self, *args, **kwargs):
        if self.is_default:
            Warehouse.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class Product(models.Model):
    UNIT_CHOICES = [
        ('piece', 'قطعة (Piece)'),
        ('kg', 'كيلوجرام (Kg)'),
        ('gram', 'جرام (Gram)'),
        ('liter', 'لتر (Liter)'),
        ('box', 'كرتونة / علبة (Box)'),
        ('pack', 'باكتة / عبوة (Pack)'),
    ]

    name = models.CharField(max_length=200, verbose_name='اسم المنتج')
    code = models.CharField(max_length=60, unique=True, verbose_name='كود المنتج (SKU)')
    barcode = models.CharField(max_length=80, blank=True, null=True, unique=True, verbose_name='الباركود')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products', verbose_name='التصنيف')
    brand = models.CharField(max_length=100, blank=True, verbose_name='العلامة التجارية')
    supplier = models.ForeignKey('suppliers.Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='supplied_products', verbose_name='المورد المعتاد')
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='piece', verbose_name='الوحدة')
    size_or_weight = models.CharField(max_length=80, blank=True, verbose_name='الحجم أو الوزن')
    default_cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name='سعر الشراء الافتراضي (ج.م)')
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name='سعر البيع (ج.م)')
    min_stock_limit = models.DecimalField(max_digits=10, decimal_places=2, default=5.00, verbose_name='الحد الأدنى للمخزون (نقطة إعادة الطلب)')
    storage_location = models.CharField(max_length=100, blank=True, verbose_name='مكان التخزين (الرف / القسم)')
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    notes = models.TextField(blank=True, verbose_name='ملاحظات')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإضافة')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخر تحديث')

    class Meta:
        verbose_name = 'منتج'
        verbose_name_plural = 'المنتجات'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} [{self.code}]"

    @property
    def total_stock(self):
        result = self.batches.aggregate(models.Sum('current_quantity'))['current_quantity__sum']
        return result or 0

    @property
    def is_low_stock(self):
        return self.total_stock <= self.min_stock_limit

    @property
    def gross_margin_per_unit(self):
        return self.sale_price - self.default_cost_price

    @property
    def gross_margin_percentage(self):
        if self.sale_price > 0:
            return round(((self.sale_price - self.default_cost_price) / self.sale_price) * 100, 2)
        return 0


class ProductBatch(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='batches', verbose_name='المنتج')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='batches', verbose_name='المخزن')
    batch_number = models.CharField(max_length=80, verbose_name='رقم الدفعة / التشغيلة')
    initial_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الكمية الأصلية المستلمة')
    current_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الكمية المتبقية الحالية')
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='سعر الشراء الفعلي للدفعة (ج.م)')
    received_date = models.DateField(default=timezone.now, verbose_name='تاريخ الاستلام')
    expiry_date = models.DateField(null=True, blank=True, verbose_name='تاريخ انتهاء الصلاحية')
    supplier = models.ForeignKey('suppliers.Supplier', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='المورد')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='وقت التسجيل')

    class Meta:
        verbose_name = 'دفعة منتج'
        verbose_name_plural = 'دفعات المنتجات'
        ordering = ['expiry_date', 'received_date']

    def __str__(self):
        return f"{self.product.name} - دفعة {self.batch_number} (متبقي: {self.current_quantity})"

    @property
    def is_expired(self):
        if self.expiry_date:
            return self.expiry_date < timezone.now().date()
        return False

    @property
    def is_near_expiry(self):
        if self.expiry_date:
            today = timezone.now().date()
            return today <= self.expiry_date <= (today + timedelta(days=30))
        return False


class InventoryMovement(models.Model):
    MOVEMENT_TYPES = [
        ('PURCHASE', 'وارد مشتريات'),
        ('SALE', 'منصرف مبيعات'),
        ('RETURN_IN', 'وارد مرتجع صالح'),
        ('ADJUST_ADD', 'تسوية جردية بالزيادة'),
        ('ADJUST_SUB', 'تسوية جردية بالنقص'),
        ('TRANSFER_IN', 'تحويل مخزني وارد'),
        ('TRANSFER_OUT', 'تحويل مخزني منصرف'),
        ('WASTE', 'هالك / تالف / منتهي الصلاحية'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='movements', verbose_name='المنتج')
    batch = models.ForeignKey(ProductBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements', verbose_name='الدفعة')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='movements', verbose_name='المخزن')
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES, verbose_name='نوع الحركة')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الكمية')
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الرصيد بعد الحركة')
    reference_id = models.CharField(max_length=100, blank=True, verbose_name='رقم المرجع (فاتورة / إذن)')
    reason = models.CharField(max_length=255, blank=True, verbose_name='السبب / البيان')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='المستخدم المنفذ')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ ووقت الحركة')

    class Meta:
        verbose_name = 'حركة مخزون'
        verbose_name_plural = 'سجل حركات المخزون'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.product.name} - {self.get_movement_type_display()} ({self.quantity}) في {self.created_at.strftime('%Y-%m-%d %H:%M')}"


class InventoryCount(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'مسودة جرد'),
        ('COMPLETED', 'تم الحصر والاعتماد'),
        ('ADJUSTED', 'تم تطبيق التسويات آلياً'),
    ]

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, verbose_name='المخزن المستهدف')
    count_date = models.DateField(default=timezone.now, verbose_name='تاريخ الجرد')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', verbose_name='حالة الجرد')
    conducted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='المسؤول عن الجرد')
    notes = models.TextField(blank=True, verbose_name='ملاحظات الجرد')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'جلسة جرد مخزني'
        verbose_name_plural = 'جلسات الجرد'
        ordering = ['-count_date']

    def __str__(self):
        return f"جرد {self.warehouse.name} بتاريخ {self.count_date}"


class InventoryCountItem(models.Model):
    count_session = models.ForeignKey(InventoryCount, on_delete=models.CASCADE, related_name='items', verbose_name='جلسة الجرد')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='المنتج')
    system_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الرصيد الدفتري المسجل')
    physical_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الرصيد الفعلي المعدود')
    difference = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, verbose_name='الفرق (الفعلي - الدفتري)')
    notes = models.CharField(max_length=255, blank=True, verbose_name='سبب الفرق إن وجد')

    class Meta:
        verbose_name = 'بند جرد'
        verbose_name_plural = 'بنود الجرد'

    def save(self, *args, **kwargs):
        self.difference = self.physical_quantity - self.system_quantity
        super().save(*args, **kwargs)


class BarcodeEvent(models.Model):
    STATUS_CHOICES = [
        ('MATCHED', 'متطابقة مع عملية بيع ناجحة'),
        ('UNMATCHED', 'ممسوحة دون إتمام بيع (اشتباه)'),
        ('LOOKUP', 'استعلام عن سعر ومخزون'),
        ('CANCELLED', 'ملغاة أثناء البيع'),
    ]

    barcode = models.CharField(max_length=100, verbose_name='الباركود الممسوح')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='المنتج المرتبط')
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='الكاشير')
    sale_ref = models.CharField(max_length=100, blank=True, verbose_name='رقم الفاتورة إن وجدت')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='MATCHED', verbose_name='حالة المسح')
    device_id = models.CharField(max_length=80, blank=True, default='POS-01', verbose_name='معرف جهاز الكاشير')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='وقت المسح')
    notes = models.CharField(max_length=255, blank=True, verbose_name='ملاحظات وتفاصيل')

    class Meta:
        verbose_name = 'سجل نشاط الباركود'
        verbose_name_plural = 'سجلات نشاط الباركود'
        ordering = ['-created_at']

    def __str__(self):
        return f"مسح: {self.barcode} - {self.get_status_display()} ({self.created_at.strftime('%H:%M:%S')})"
