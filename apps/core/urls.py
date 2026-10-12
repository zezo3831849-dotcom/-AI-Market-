from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('audit/', views.audit_log_view, name='audit_log'),
    path('backup/', views.backup_management_view, name='backup_management'),
    path('backup/create/', views.create_backup_view, name='create_backup'),
    path('backup/download/<int:backup_id>/', views.download_backup_view, name='download_backup'),
    path('settings/', views.system_settings_view, name='settings'),
    path('financial-report/', views.financial_report_view, name='financial_report'),
    path('quick-search/', views.quick_search_api, name='quick_search'),
]
