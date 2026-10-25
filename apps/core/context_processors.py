import time
from .models import SystemSettings
from apps.intelligence.models import AIRecommendation
from apps.inventory.models import ProductBatch
from django.utils import timezone
from datetime import timedelta

_CACHED_SETTINGS = None
_CACHED_SETTINGS_TIME = 0

def get_cached_settings():
    global _CACHED_SETTINGS, _CACHED_SETTINGS_TIME
    now = time.time()
    if _CACHED_SETTINGS is None or (now - _CACHED_SETTINGS_TIME) > 60:
        try:
            _CACHED_SETTINGS = SystemSettings.get_settings()
            _CACHED_SETTINGS_TIME = now
        except Exception:
            return None
    return _CACHED_SETTINGS


def global_settings(request):
    settings_obj = get_cached_settings()

    pending_recommendations_count = 0
    near_expiry_count = 0

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
        except Exception:
            pass

    return {
        'system_settings': settings_obj,
        'pending_ai_count': pending_recommendations_count,
        'near_expiry_count': near_expiry_count,
    }

