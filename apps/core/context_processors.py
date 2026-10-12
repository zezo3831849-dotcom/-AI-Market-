from .models import SystemSettings
from apps.intelligence.models import AIRecommendation
from apps.inventory.models import Product, ProductBatch
from django.utils import timezone
from datetime import timedelta


def global_settings(request):
    try:
        settings_obj = SystemSettings.get_settings()
    except Exception:
        settings_obj = None

    pending_recommendations_count = 0
    near_expiry_count = 0
    low_stock_count = 0

    if request.user.is_authenticated:
        try:
            pending_recommendations_count = AIRecommendation.objects.filter(status='PENDING').count()
            today = timezone.now().date()
            thirty_days = today + timedelta(days=30)
            near_expiry_count = ProductBatch.objects.filter(
                expiry_date__isnull=False,
                expiry_date__gte=today,
                expiry_date__lte=thirty_days,
                current_quantity__gt=0
            ).count()
            # low stock count
            low_stock_count = Product.objects.filter(is_active=True).filter(
                batches__current_quantity__gt=0
            ).distinct().count()
        except Exception:
            pass

    return {
        'system_settings': settings_obj,
        'pending_ai_count': pending_recommendations_count,
        'near_expiry_count': near_expiry_count,
    }
