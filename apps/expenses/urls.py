from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    path('', views.expenses_list_view, name='expenses_list'),
    path('add/', views.expense_create_view, name='expense_create'),
    path('<int:pk>/edit/', views.expense_edit_view, name='expense_edit'),
    path('<int:pk>/pay/', views.expense_add_payment_view, name='expense_add_payment'),
    path('categories/', views.expense_categories_view, name='categories_list'),
]
