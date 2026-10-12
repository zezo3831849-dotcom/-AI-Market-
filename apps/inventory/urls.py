from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    path('products/', views.products_list_view, name='products_list'),
    path('products/add/', views.product_create_view, name='product_create'),
    path('products/<int:pk>/edit/', views.product_edit_view, name='product_edit'),
    path('batches/', views.batches_list_view, name='batches_list'),
    path('batches/add/', views.batch_create_view, name='batch_create'),
    path('movements/', views.movements_list_view, name='movements_list'),
    path('counts/', views.inventory_counts_view, name='counts_list'),
    path('counts/new/', views.inventory_count_create_view, name='count_create'),
    path('counts/<int:pk>/', views.inventory_count_detail_view, name='count_detail'),
    path('barcodes/', views.barcode_events_view, name='barcode_events'),
    path('categories/', views.categories_view, name='categories_list'),
]
