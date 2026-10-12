from django.db import models
from django.conf import settings
from django.utils import timezone


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=120, unique=True, verbose_name='اسم التصنيف')
    code = models.CharField(max_length=50, unique=True, verbose_name='كود التصنيف')
    description = models.TextField(blank=True, verbose_name='الوصف')
    icon = models.CharField(max_length=50, default='bi-receipt', verbose_name='الأيقونة')
    is_recurring = models.BooleanField(default=False, verbose_name='مصروف دوري متكرر (شهري/سنوي)')

    class Meta:
        verbose_name = 'تصنيف مصروفات'
        verbose_name_plural = 'تصنيفات المصروفات'
        ordering = ['name']

    def __str__(self):
        return self.name


class OperatingExpense(models.Model):
    PAYMENT_STATUS = [
        ('PAID', 'مسدد بالكامل'),
        ('PARTIAL', 'مسدد جزئياً'),
        ('PENDING', 'مستحق الدفع (غير مسدد)'),
        ('OVERDUE', 'متأخر عن موعد الاستحقاق'),
    ]

    PAYMENT_METHODS = [
        ('CASH', 'نقداً (خزينة المحل)'),
        ('BANK', 'تحويل بنكي'),
        ('CARD', 'بطاقة ائتمان / مدفوعات إلكترونية'),
        ('OTHER', 'أخرى'),
    ]

    title = models.CharField(max_length=200, verbose_name='بيان / اسم المصروف')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expenses', verbose_name='التصنيف')
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='المبلغ الإجمالي (ج.م)')
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name='المبلغ المدفوع حتى الآن (ج.م)')
    
    expense_date = models.DateField(default=timezone.now, verbose_name='تاريخ المصروف')
    period_covered = models.CharField(max_length=100, blank=True, verbose_name='الفترة التي يغطيها (مثل: شهر أكتوبر 2026)')
    due_date = models.DateField(null=True, blank=True, verbose_name='تاريخ الاستحقاق')
    payee = models.CharField(max_length=150, blank=True, verbose_name='الجهة أو الشخص المستفيد')
    
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='CASH', verbose_name='طريقة الدفع')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='PAID', verbose_name='حالة السداد')
    invoice_number = models.CharField(max_length=100, blank=True, verbose_name='رقم الفاتورة أو الإيصال')
    receipt_image = models.ImageField(upload_to='expenses/receipts/', null=True, blank=True, verbose_name='صورة الإيصال / الفاتورة')
    
    notes = models.TextField(blank=True, verbose_name='ملاحظات إضافية')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='المسؤول المسجل')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ التسجيل')

    class Meta:
        verbose_name = 'مصروف تشغيلي'
        verbose_name_plural = 'المصروفات التشغيلية'
        ordering = ['-expense_date', '-created_at']

    def __str__(self):
        return f"{self.title} - {self.amount} ج.م ({self.get_payment_status_display()})"

    @property
    def remaining_amount(self):
        return max(self.amount - self.paid_amount, 0)

    @property
    def is_overdue(self):
        if self.due_date and self.payment_status in ['PENDING', 'PARTIAL']:
            return self.due_date < timezone.now().date()
        return False

    def save(self, *args, **kwargs):
        if self.paid_amount >= self.amount:
            self.payment_status = 'PAID'
        elif self.paid_amount > 0:
            self.payment_status = 'PARTIAL'
        elif self.due_date and self.due_date < timezone.now().date():
            self.payment_status = 'OVERDUE'
        else:
            self.payment_status = 'PENDING'
        super().save(*args, **kwargs)


class ExpensePayment(models.Model):
    expense = models.ForeignKey(OperatingExpense, on_delete=models.CASCADE, related_name='payments', verbose_name='المصروف')
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='مبلغ الدفعة المسدد (ج.م)')
    payment_date = models.DateField(default=timezone.now, verbose_name='تاريخ الدفع')
    payment_method = models.CharField(max_length=20, choices=OperatingExpense.PAYMENT_METHODS, default='CASH', verbose_name='طريقة الدفع')
    transaction_ref = models.CharField(max_length=100, blank=True, verbose_name='رقم الحوالة / الإيصال')
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='المسؤول')
    notes = models.TextField(blank=True, verbose_name='ملاحظات الدفعة')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'دفعة سداد مصروف'
        verbose_name_plural = 'دفعات سداد المصروفات'
        ordering = ['-payment_date']

    def __str__(self):
        return f"دفعة {self.amount} ج.م لمصروف {self.expense.title}"
