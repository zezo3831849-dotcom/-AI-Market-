from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction

from .models import AIRecommendation, RecommendationDecision, Forecast, CalendarEvent
from .services import run_complete_ai_pipeline, run_ai_demand_forecasting
from apps.inventory.models import Product, Category, ProductBatch
from apps.core.models import AuditLog


@login_required
def intelligence_center_view(request):
    recs = AIRecommendation.objects.select_related('product').all()
    filter_type = request.GET.get('type')
    filter_status = request.GET.get('status', 'PENDING')

    if filter_type:
        recs = recs.filter(recommendation_type=filter_type)
    if filter_status and filter_status != 'ALL':
        recs = recs.filter(status=filter_status)

    counts = {
        'pending': AIRecommendation.objects.filter(status='PENDING').count(),
        'restock': AIRecommendation.objects.filter(recommendation_type='RESTOCK', status='PENDING').count(),
        'offers': AIRecommendation.objects.filter(recommendation_type='SMART_OFFER', status='PENDING').count(),
        'anomalies': AIRecommendation.objects.filter(recommendation_type='ANOMALY', status='PENDING').count(),
        'seasonal': AIRecommendation.objects.filter(recommendation_type='SEASONAL_PREP', status='PENDING').count(),
    }

    return render(request, 'intelligence/center.html', {
        'recommendations': recs,
        'counts': counts,
        'selected_type': filter_type,
        'selected_status': filter_status,
    })


@login_required
def run_ai_pipeline_view(request):
    """Executes the full AI Intelligence scanning engine."""
    results = run_complete_ai_pipeline()
    messages.success(
        request,
        f"اكتمل الفحص الذكي بنجاح: {results['forecasts']} تنبؤات، {results['restock_recs']} مقترحات توريد، "
        f"{results['smart_offers']} عروض ذكية، {results['anomalies']} تنبيهات شذوذ، {results['seasonal_preps']} استعدادات موسمية."
    )
    return redirect('intelligence:center')


@login_required
def ai_recommendation_decision_view(request, pk):
    """Human-in-the-Loop decision point."""
    rec = get_object_or_404(AIRecommendation, pk=pk)
    if not request.user.is_admin_or_manager:
        messages.error(request, 'اتخاذ القرارات بشأن التوصيات متاح للإدارة فقط.')
        return redirect('intelligence:center')

    decision = request.POST.get('decision')  # APPROVED, REJECTED, MODIFIED
    notes = request.POST.get('notes', '')

    with transaction.atomic():
        rec.status = decision
        rec.save(update_fields=['status'])

        RecommendationDecision.objects.update_or_create(
            recommendation=rec,
            defaults={
                'manager': request.user,
                'decision': decision,
                'modification_notes': notes,
            }
        )

        AuditLog.objects.create(
            user=request.user,
            action='AI_DECISION',
            target_model='AIRecommendation',
            target_id=str(rec.id),
            description=f"قرار المدير ({rec.get_status_display()}) بخصوص توصية: {rec.title}"
        )

        if decision == 'APPROVED':
            # Execute automated application if appropriate
            if rec.recommendation_type == 'SMART_OFFER' and rec.product:
                # E.g., apply discount to product sale_price if mentioned
                pass
            messages.success(request, f'تمت الموافقة على توصية: "{rec.title}" واعتمادها.')
        elif decision == 'REJECTED':
            messages.info(request, f'تم رفض التوصية: "{rec.title}".')
        elif decision == 'MODIFIED':
            messages.success(request, f'تم تعديل التوصية: "{rec.title}" وحفظ الملاحظات.')

    return redirect('intelligence:center')


@login_required
def forecasts_view(request):
    forecasts = Forecast.objects.select_related('product').all()
    products = Product.objects.filter(is_active=True)
    return render(request, 'intelligence/forecasts_list.html', {
        'forecasts': forecasts,
        'products': products,
    })


@login_required
def run_forecast_view(request):
    product_id = request.POST.get('product_id') or None
    horizon = int(request.POST.get('horizon_days', 7))
    run_ai_demand_forecasting(product_id=product_id, horizon_days=horizon)
    messages.success(request, f'تم تحديث نموذج التنبؤ بالطلب بنجاح لأفق {horizon} أيام.')
    return redirect('intelligence:forecasts_list')


@login_required
def calendar_events_view(request):
    events = CalendarEvent.objects.prefetch_related('target_categories').all()
    categories = Category.objects.all()
    return render(request, 'intelligence/calendar_events.html', {
        'events': events,
        'categories': categories,
    })


@login_required
def calendar_event_create_view(request):
    if not request.user.is_admin_or_manager:
        messages.error(request, 'غير مصرح لك بإضافة مناسبات تقويمية.')
        return redirect('intelligence:calendar_events')

    if request.method == 'POST':
        title = request.POST.get('title')
        event_type = request.POST.get('event_type', 'LOCAL')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        description = request.POST.get('description', '')
        recurring = 'recurring_yearly' in request.POST
        selected_categories = request.POST.getlist('target_categories')

        event = CalendarEvent.objects.create(
            title=title,
            event_type=event_type,
            start_date=start_date,
            end_date=end_date,
            description=description,
            recurring_yearly=recurring
        )
        if selected_categories:
            event.target_categories.set(selected_categories)

        AuditLog.objects.create(
            user=request.user,
            action='CREATE',
            target_model='CalendarEvent',
            target_id=str(event.id),
            description=f"إضافة مناسبة تقويمية: {event.title}"
        )
        messages.success(request, f'تمت إضافة المناسبة {event.title} بنجاح.')
        return redirect('intelligence:calendar_events')

    categories = Category.objects.all()
    return render(request, 'intelligence/calendar_form.html', {'categories': categories})


@login_required
def anomalies_view(request):
    anomalies = AIRecommendation.objects.filter(recommendation_type='ANOMALY')
    return render(request, 'intelligence/anomalies.html', {'anomalies': anomalies})


@login_required
def smart_offers_view(request):
    offers = AIRecommendation.objects.filter(recommendation_type='SMART_OFFER')
    return render(request, 'intelligence/smart_offers.html', {'offers': offers})
