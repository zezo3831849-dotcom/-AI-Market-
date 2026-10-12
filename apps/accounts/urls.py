from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('users/', views.users_list_view, name='users_list'),
    path('users/add/', views.user_create_view, name='user_create'),
]
