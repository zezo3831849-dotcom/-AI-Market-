from django.urls import path
from . import views

app_name = 'intelligence'

urlpatterns = [
    path('', views.intelligence_center_view, name='center'),
    path('run-scan/', views.run_ai_pipeline_view, name='run_pipeline'),
    path('recommendations/<int:pk>/decision/', views.ai_recommendation_decision_view, name='recommendation_decision'),
    path('forecasts/', views.forecasts_view, name='forecasts_list'),
    path('forecasts/run/', views.run_forecast_view, name='run_forecast'),
    path('calendar/', views.calendar_events_view, name='calendar_events'),
    path('calendar/add/', views.calendar_event_create_view, name='calendar_event_create'),
    path('anomalies/', views.anomalies_view, name='anomalies_list'),
    path('smart-offers/', views.smart_offers_view, name='smart_offers'),
]
