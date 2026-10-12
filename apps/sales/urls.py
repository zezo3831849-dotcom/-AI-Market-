from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    path('pos/', views.pos_view, name='pos'),
    path('api/process-sale/', views.api_process_sale, name='api_process_sale'),
    path('api/sync-offline/', views.api_sync_offline_sales, name='api_sync_offline'),
    path('api/products-catalog/', views.api_products_catalog, name='api_products_catalog'),
    path('invoices/', views.invoices_list_view, name='invoices_list'),
    path('invoices/<int:pk>/', views.invoice_detail_view, name='invoice_detail'),
    path('returns/', views.returns_list_view, name='returns_list'),
    path('returns/new/', views.return_create_view, name='return_create'),
    path('sync-history/', views.sync_history_view, name='sync_history'),
]
