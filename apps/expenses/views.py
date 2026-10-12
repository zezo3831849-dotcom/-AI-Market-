from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.utils import timezone

from .models import OperatingExpense, ExpenseCategory, ExpensePayment
from apps.core.models import AuditLog


@login_required
def expenses_list_view(request):
    category_id = request.GET.get('category')
    status = request.GET.get('status')

    expenses = OperatingExpense.objects.select_related('category', 'created_by').all()

    if category_id:
        expenses = expenses.filter(category_id=category_id)
    if status:
        expenses = expenses.filter(payment_status=status)

    categories = ExpenseCategory.objects.all()
    totals = expenses.aggregate(
        total_amount=Sum('amount'),
        total_paid=Sum('paid_amount')
    )

    total_amount = totals['total_amount'] or Decimal('0.00')
    total_paid = totals['total_paid'] or Decimal('0.00')
    total_remaining = total_amount - total_paid

    return render(request, 'expenses/expenses_list.html', {
        'expenses': expenses,
        'categories': categories,
        'selected_category': category_id,
        'selected_status': status,
        'total_amount': total_amount,
        'total_paid': total_paid,
        'total_remaining': total_remaining,
    })


@login_required
def expense_create_view(request):
    if not request.user.can_manage_expenses:
        messages.error(request, 'غير مصرح لك بتسجيل مصروفات.')
        return redirect('expenses:expenses_list')

    if request.method == 'POST':
        title = request.POST.get('title')
        category_id = request.POST.get('category')
        amount = Decimal(request.POST.get('amount', '0.00'))
        is_paid_now = 'is_paid_now' in request.POST
        paid_amount = amount if is_paid_now else Decimal(request.POST.get('paid_amount', '0.00'))
        expense_date = request.POST.get('expense_date') or timezone.now().date()
        due_date = request.POST.get('due_date') or None
        period_covered = request.POST.get('period_covered', '')
        payee = request.POST.get('payee', '')
        payment_method = request.POST.get('payment_method', 'CASH')
        invoice_number = request.POST.get('invoice_number', '')
        receipt_image = request.FILES.get('receipt_image')
        notes = request.POST.get('notes', '')

        category = get_object_or_404(ExpenseCategory, id=category_id)

        expense = OperatingExpense.objects.create(
            title=title,
            category=category,
            amount=amount,
            paid_amount=paid_amount,
            expense_date=expense_date,
            due_date=due_date,
            period_covered=period_covered,
            payee=payee,
            payment_method=payment_method,
            invoice_number=invoice_number,
            receipt_image=receipt_image,
            notes=notes,
            created_by=request.user
        )

        if paid_amount > 0:
            ExpensePayment.objects.create(
                expense=expense,
                amount=paid_amount,
                payment_date=expense_date,
                payment_method=payment_method,
                recorded_by=request.user,
                notes='دفعة سداد أولية عند إنشاء المصروف'
            )

        AuditLog.objects.create(
            user=request.user,
            action='EXPENSE_ADD',
            target_model='OperatingExpense',
            target_id=str(expense.id),
            description=f"تسجيل مصروف تشغيلي: {expense.title} بقيمة {expense.amount} ج.م في تصنيف {category.name}"
        )

        messages.success(request, f'تم تسجيل المصروف {expense.title} بنجاح.')
        return redirect('expenses:expenses_list')

    categories = ExpenseCategory.objects.all()
    return render(request, 'expenses/expense_form.html', {
        'categories': categories,
        'title': 'تسجيل مصروف تشغيلي جديد',
    })


@login_required
def expense_edit_view(request, pk):
    expense = get_object_or_404(OperatingExpense, pk=pk)
    if not request.user.can_manage_expenses:
        messages.error(request, 'غير مصرح لك بتعديل المصروفات.')
        return redirect('expenses:expenses_list')

    if request.method == 'POST':
        expense.title = request.POST.get('title')
        expense.category_id = request.POST.get('category')
        expense.amount = Decimal(request.POST.get('amount', str(expense.amount)))
        expense.expense_date = request.POST.get('expense_date') or expense.expense_date
        expense.due_date = request.POST.get('due_date') or None
        expense.period_covered = request.POST.get('period_covered', '')
        expense.payee = request.POST.get('payee', '')
        expense.payment_method = request.POST.get('payment_method', expense.payment_method)
        expense.invoice_number = request.POST.get('invoice_number', '')
        if 'receipt_image' in request.FILES:
            expense.receipt_image = request.FILES['receipt_image']
        expense.notes = request.POST.get('notes', '')
        expense.save()

        AuditLog.objects.create(
            user=request.user,
            action='UPDATE',
            target_model='OperatingExpense',
            target_id=str(expense.id),
            description=f"تعديل بيانات المصروف {expense.title}"
        )
        messages.success(request, 'تم تعديل بيانات المصروف بنجاح.')
        return redirect('expenses:expenses_list')

    categories = ExpenseCategory.objects.all()
    return render(request, 'expenses/expense_form.html', {
        'expense': expense,
        'categories': categories,
        'title': f'تعديل مصروف: {expense.title}',
    })


@login_required
def expense_add_payment_view(request, pk):
    expense = get_object_or_404(OperatingExpense, pk=pk)
    if not request.user.can_manage_expenses:
        messages.error(request, 'غير مصرح لك بتسجيل دفعات المصروفات.')
        return redirect('expenses:expenses_list')

    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', '0.00'))
        payment_method = request.POST.get('payment_method', 'CASH')
        notes = request.POST.get('notes', '')

        if amount > 0:
            ExpensePayment.objects.create(
                expense=expense,
                amount=amount,
                payment_method=payment_method,
                recorded_by=request.user,
                notes=notes
            )
            expense.paid_amount += amount
            expense.save()

            AuditLog.objects.create(
                user=request.user,
                action='UPDATE',
                target_model='OperatingExpense',
                target_id=str(expense.id),
                description=f"سداد دفعة {amount} ج.م لمصروف {expense.title}"
            )
            messages.success(request, f'تم تسجيل سداد بمبلغ {amount} ج.م بنجاح.')
    return redirect('expenses:expenses_list')


@login_required
def expense_categories_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        code = request.POST.get('code')
        description = request.POST.get('description', '')
        icon = request.POST.get('icon', 'bi-receipt')
        is_recurring = 'is_recurring' in request.POST
        if name and code:
            ExpenseCategory.objects.create(
                name=name, code=code, description=description, icon=icon, is_recurring=is_recurring
            )
            messages.success(request, f'تمت إضافة تصنيف المصروفات {name}.')
        return redirect('expenses:categories_list')

    categories = ExpenseCategory.objects.annotate(expenses_count=Sum('expenses__amount')).all()
    return render(request, 'expenses/categories_list.html', {'categories': categories})
