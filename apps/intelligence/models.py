from django.db import models
from django.conf import settings
from django.utils import timezone


class CalendarEvent(models.Model):
    EVENT_TYPES = [
        ('RELIGIOUS', 'مناسبة دينية (رمضان، الأعياد)'),
        ('SEASON', 'موسم مناخي / فصلي (صيف، شتاء)'),
        ('ACADEMIC', 'موسم دراسي (العودة للمدارس / الجامعات)'),
        ('COMMERCIAL', 'موسم تجاري (الجمعة البيضاء، عروض نهاية العام)'),
        ('LOCAL', 'مناسبة أو فعالية محلية'),
    ]

    title = models.CharField(max_length=150, verbose_name='اسم المناسبة / الموسم')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, default='LOCAL', verbose_name='نوع المناسبة')
    start_date = models.DateField(verbose_name='تاريخ البداية')
    end_date = models.DateField(verbose_name='تاريخ النهاية')
    description = models.TextField(blank=True, verbose_name='وصف المناسبة وتأثيرها المتوقع')
    target_categories = models.ManyToManyField('inventory.Category', blank=True, verbose_name='الفئات الأكثر تأثراً بالحدث')
    recurring_yearly = models.BooleanField(default=False, verbose_name='مناسبة سنوية متكررة')

    class Meta:
        verbose_name = 'مناسبة تقويمية'
        verbose_name_plural = 'التقويم الذكي والمناسبات'
        ordering = ['start_date']

    def __str__(self):
        return f"{self.title} ({self.start_date.strftime('%Y-%m-%d')} إلى {self.end_date.strftime('%Y-%m-%d')})"

    @property
    def is_current(self):
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date

    @property
    def is_upcoming(self):
        today = timezone.now().date()
        return self.start_date > today


class Forecast(models.Model):
    product = models.ForeignKey('inventory.Product', on_delete=models.CASCADE, related_name='forecasts', verbose_name='المنتج')
    forecast_date = models.DateField(default=timezone.now, verbose_name='تاريخ بدء التنبؤ')
    horizon_days = models.PositiveIntegerField(default=7, verbose_name='أفق التوقع (بالأيام)')
    predicted_quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الكمية المتوقع بيعها')
    lower_bound = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الحد الأدنى للتوقع')
    upper_bound = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='الحد الأقصى للتوقع')
    confidence_score = models.FloatField(default=85.0, verbose_name='نسبة اليقين والاعتمادية (%)')
    algorithm_used = models.CharField(max_length=100, default='Linear Regression + Trend & Seasonality', verbose_name='الخوارزمية المستخدمة')
    actual_quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='الكمية الفعلية المباعة (للتقييم اللاحق)')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'تنبؤ بالطلب'
        verbose_name_plural = 'تنبؤات الطلب'
        ordering = ['-created_at']

    def __str__(self):
        return f"توقع {self.product.name} ({self.predicted_quantity} قطعة خلال {self.horizon_days} أيام)"


class AIRecommendation(models.Model):
    TYPE_CHOICES = [
        ('RESTOCK', 'اقتراح إعادة طلب كميات (Restock Order)'),
        ('SMART_OFFER', 'اقتراح عرض ترويجي / خصم ذكي (Smart Promotion)'),
        ('ANOMALY', 'اكتشاف شذوذ / ارتفاع غير معتاد (Anomaly Alert)'),
        ('SEASONAL_PREP', 'تجهيز واستعداد موسمي (Seasonal Prep)'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'بانتظار مراجعة وقرار المدير'),
        ('APPROVED', 'مقبولة ومعتمدة'),
        ('REJECTED', 'مرفوضة من المدير'),
        ('MODIFIED', 'معدلة من المدير'),
    ]

    recommendation_type = models.CharField(max_length=30, choices=TYPE_CHOICES, verbose_name='نوع التوصية')
    product = models.ForeignKey('inventory.Product', on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_recommendations', verbose_name='المنتج المرتبط')
    title = models.CharField(max_length=200, verbose_name='عنوان التوصية')
    description = models.TextField(verbose_name='نص التوصية المفصل')
    suggested_action = models.TextField(verbose_name='الإجراء المقترح القابل للتنفيذ')
    rationale = models.TextField(verbose_name='السبب والبيانات الداعمة (Human-in-the-Loop Explainability)')
    data_evidence = models.TextField(blank=True, verbose_name='مؤشرات رقمية إضافية')
    confidence_level = models.FloatField(default=90.0, verbose_name='مستوى اليقين (%)')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name='حالة القرار')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='وقت إصدار التوصية')

    class Meta:
        verbose_name = 'توصية ذكاء اصطناعي'
        verbose_name_plural = 'توصيات الذكاء الاصطناعي'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_recommendation_type_display()}] {self.title} ({self.get_status_display()})"


class RecommendationDecision(models.Model):
    DECISION_CHOICES = [
        ('APPROVED', 'موافقة وتطبيق'),
        ('REJECTED', 'رفض التوصية'),
        ('MODIFIED', 'تعديل التوصية ثم التطبيق'),
    ]

    recommendation = models.OneToOneField(AIRecommendation, on_delete=models.CASCADE, related_name='decision', verbose_name='التوصية')
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='المدير متخذ القرار')
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, verbose_name='القرار')
    modification_notes = models.TextField(blank=True, verbose_name='تفاصيل التعديل أو سبب الرفض')
    outcome_metric = models.CharField(max_length=255, blank=True, verbose_name='متابعة الأثر المالي الفعلي لاحقاً')
    decided_at = models.DateTimeField(auto_now_add=True, verbose_name='وقت اتخاذ القرار')

    class Meta:
        verbose_name = 'قرار مراجعة التوصية'
        verbose_name_plural = 'سجل قرارات التوصيات'

    def __str__(self):
        return f"قرار {self.get_decision_display()} على {self.recommendation.title}"
