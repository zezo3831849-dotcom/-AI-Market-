from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('ADMIN', 'مدير عام / مالك'),
        ('MANAGER', 'مدير عمليات / فرع'),
        ('CASHIER', 'كاشير / مسؤول مبيعات'),
        ('INVENTORY', 'مسؤول مخزن وجرد'),
        ('ACCOUNTANT', 'محاسب مالي'),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='CASHIER',
        verbose_name='الدور الوظيفي'
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name='رقم الهاتف')
    notes = models.TextField(blank=True, verbose_name='ملاحظات')

    class Meta:
        verbose_name = 'مستخدم'
        verbose_name_plural = 'المستخدمون'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def is_admin_or_manager(self):
        return self.is_superuser or self.role in ['ADMIN', 'MANAGER']

    @property
    def can_manage_expenses(self):
        return self.is_superuser or self.role in ['ADMIN', 'MANAGER', 'ACCOUNTANT']

    @property
    def can_manage_inventory(self):
        return self.is_superuser or self.role in ['ADMIN', 'MANAGER', 'INVENTORY']

    @property
    def can_manage_pos(self):
        return True  # all active users can sell
