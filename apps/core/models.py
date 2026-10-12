from django.db import models
from django.conf import settings


class SystemSettings(models.Model):
    store_name = models.CharField(max_length=150, default='سوق المستقبل الذكي', verbose_name='اسم المحل / المتجر')
    phone = models.CharField(max_length=50, blank=True, default='01000000000', verbose_name='رقم الهاتف')
    address = models.CharField(max_length=255, blank=True, default='القاهرة، مصر', verbose_name='العنوان')
    currency = models.CharField(max_length=10, default='ج.م', verbose_name='العملة')
    min_profit_margin_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=15.00,
        verbose_name='الحد الأدنى لهامش الربح المقبول (%) للعروض'
    )
    default_low_stock_limit = models.PositiveIntegerField(
        default=10, verbose_name='الحد الافتراضي للتنبيه بانخفاض المخزون'
    )
    near_expiry_days = models.PositiveIntegerField(
        default=30, verbose_name='عدد الأيام للتحذير من قرب انتهاء الصلاحية'
    )
    offline_sync_enabled = models.BooleanField(
        default=True, verbose_name='تفعيل مزامنة المبيعات دون اتصال'
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='آخر تحديث')

    class Meta:
        verbose_name = 'إعدادات النظام'
        verbose_name_plural = 'إعدادات النظام'

    def __str__(self):
        return self.store_name

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('CREATE', 'إنشاء سجل جديد'),
        ('UPDATE', 'تعديل بيانات'),
        ('DELETE', 'حذف سجل'),
        ('PRICE_CHANGE', 'تعديل سعر البيع'),
        ('STOCK_ADJUST', 'تسوية جردية / تعديل مخزون'),
        ('EXPENSE_ADD', 'تسجيل مصروف'),
        ('EXPENSE_APPROVE', 'اعتماد مصروف'),
        ('ORDER_APPROVE', 'اعتماد طلب شراء'),
        ('AI_DECISION', 'قرار توصية ذكاء اصطناعي'),
        ('BACKUP', 'نسخ احتياطي'),
        ('RESTORE', 'استعادة قاعدة البيانات'),
        ('OFFLINE_SYNC', 'مزامنة مبيعات أوفلاين'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='المستخدم المسؤول'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES, verbose_name='نوع العملية')
    target_model = models.CharField(max_length=100, verbose_name='الجدول / الكيان')
    target_id = models.CharField(max_length=100, blank=True, verbose_name='معرف السجل')
    description = models.TextField(verbose_name='تفاصيل العملية')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='عنوان IP')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='وقت العملية')

    class Meta:
        verbose_name = 'سجل العمليات والتدقيق'
        verbose_name_plural = 'سجلات التدقيق'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_action_display()} - {self.target_model} بواسطة {self.user or 'النظام'}"


class BackupLog(models.Model):
    STATUS_CHOICES = [
        ('SUCCESS', 'نجاح'),
        ('FAILED', 'فشل'),
    ]

    file_name = models.CharField(max_length=255, verbose_name='اسم ملف النسخة')
    file_path = models.CharField(max_length=500, verbose_name='المسار')
    file_size_kb = models.FloatField(default=0.0, verbose_name='الحجم بالكيلوبايت')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='SUCCESS', verbose_name='الحالة')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ ووقت النسخ')
    notes = models.TextField(blank=True, verbose_name='ملاحظات / أخطاء إن وجدت')

    class Meta:
        verbose_name = 'سجل النسخ الاحتياطي'
        verbose_name_plural = 'سجلات النسخ الاحتياطي'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.file_name} ({self.get_status_display()}) - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
