from django.urls import path
from . import views

app_name = 'suppliers'

urlpatterns = [
    path('', views.suppliers_list_view, name='suppliers_list'),
    path('add/', views.supplier_create_view, name='supplier_create'),
    path('<int:pk>/edit/', views.supplier_edit_view, name='supplier_edit'),
    path('orders/', views.purchase_orders_list_view, name='orders_list'),
    path('orders/new/', views.purchase_order_create_view, name='order_create'),
    path('orders/<int:pk>/', views.purchase_order_detail_view, name='order_detail'),
    path('orders/<int:pk>/receive/', views.purchase_order_receive_view, name='order_receive'),
    path('special-deals/', views.special_deals_list_view, name='special_deals_list'),
    path('special-deals/new/', views.special_deal_create_view, name='special_deal_create'),
    path('special-deals/<int:pk>/decide/', views.special_deal_decision_view, name='special_deal_decision'),
    path('schedules/', views.schedules_view, name='schedules_list'),
]
