from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User
from apps.core.models import AuditLog


def login_view(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')

    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            AuditLog.objects.create(
                user=user,
                action='CREATE',
                target_model='UserSession',
                description=f"تسجيل دخول ناجح للمستخدم {user.username} بدور {user.get_role_display()}"
            )
            messages.success(request, f'مرحباً بك مجدداً، {user.get_full_name() or user.username}!')
            next_url = request.GET.get('next')
            return redirect(next_url if next_url else 'core:dashboard')
        else:
            messages.error(request, 'اسم المستخدم أو كلمة المرور غير صحيحة.')

    return render(request, 'accounts/login.html')


def logout_view(request):
    if request.user.is_authenticated:
        AuditLog.objects.create(
            user=request.user,
            action='DELETE',
            target_model='UserSession',
            description=f"تسجيل خروج للمستخدم {request.user.username}"
        )
    logout(request)
    messages.info(request, 'تم تسجيل الخروج بنجاح.')
    return redirect('accounts:login')


@login_required
def users_list_view(request):
    if not request.user.is_admin_or_manager:
        messages.error(request, 'غير مصرح لك باستعراض قائمة المستخدمين.')
        return redirect('core:dashboard')
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'accounts/users_list.html', {'users': users})


@login_required
def user_create_view(request):
    if not request.user.is_admin_or_manager:
        messages.error(request, 'إضافة المستخدمين متاحة للمدير فقط.')
        return redirect('core:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        phone = request.POST.get('phone', '')
        role = request.POST.get('role', 'CASHIER')
        password = request.POST.get('password')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'اسم المستخدم موجود مسبقاً.')
        else:
            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role=role
            )
            AuditLog.objects.create(
                user=request.user,
                action='CREATE',
                target_model='User',
                target_id=str(user.id),
                description=f"إنشاء حساب مستخدم جديد {user.username} بدور {user.get_role_display()}"
            )
            messages.success(request, f'تم إنشاء حساب المستخدم {username} بنجاح.')
            return redirect('accounts:users_list')

    return render(request, 'accounts/user_form.html')
