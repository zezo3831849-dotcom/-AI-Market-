from decimal import Decimal
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from apps.sales.models import Sale, Return
from apps.expenses.models import OperatingExpense


def get_financial_summary(start_date=None, end_date=None):
    """
    Computes rigorous financial metrics according to the specification:
    1. Net Revenue = Completed Sales - Returns
    2. COGS = Cost of goods sold
    3. Gross Profit = Net Revenue - COGS
    4. Gross Margin % = (Gross Profit / Net Revenue) * 100
    5. Operating Expenses = Total recorded operating expenses
    6. Net Operating Profit = Gross Profit - Operating Expenses
    """
    sales_qs = Sale.objects.filter(status='COMPLETED')
    returns_qs = Return.objects.all()
    expenses_qs = OperatingExpense.objects.all()

    if start_date:
        sales_qs = sales_qs.filter(created_at__date__gte=start_date)
        returns_qs = returns_qs.filter(created_at__date__gte=start_date)
        expenses_qs = expenses_qs.filter(expense_date__gte=start_date)

    if end_date:
        sales_qs = sales_qs.filter(created_at__date__lte=end_date)
        returns_qs = returns_qs.filter(created_at__date__lte=end_date)
        expenses_qs = expenses_qs.filter(expense_date__lte=end_date)

    sales_agg = sales_qs.aggregate(
        total_rev=Sum('total_amount'),
        total_cogs=Sum('total_cost'),
        total_discount=Sum('discount_amount'),
        sales_count=Count('id')
    )

    returns_agg = returns_qs.aggregate(
        total_refund=Sum('total_refund_amount'),
        returns_count=Count('id')
    )

    expenses_agg = expenses_qs.aggregate(
        total_exp=Sum('amount'),
        total_paid_exp=Sum('paid_amount'),
        expenses_count=Count('id')
    )

    gross_sales_revenue = sales_agg['total_rev'] or Decimal('0.00')
    total_refunds = returns_agg['total_refund'] or Decimal('0.00')
    net_sales_revenue = max(gross_sales_revenue - total_refunds, Decimal('0.00'))

    cogs = sales_agg['total_cogs'] or Decimal('0.00')
    gross_profit = net_sales_revenue - cogs

    gross_margin_pct = Decimal('0.00')
    if net_sales_revenue > 0:
        gross_margin_pct = round((gross_profit / net_sales_revenue) * Decimal('100.0'), 2)

    operating_expenses = expenses_agg['total_exp'] or Decimal('0.00')
    paid_operating_expenses = expenses_agg['total_paid_exp'] or Decimal('0.00')
    pending_expenses = operating_expenses - paid_operating_expenses

    net_operating_profit = gross_profit - operating_expenses

    return {
        'gross_sales_revenue': gross_sales_revenue,
        'total_refunds': total_refunds,
        'net_sales_revenue': net_sales_revenue,
        'cogs': cogs,
        'gross_profit': gross_profit,
        'gross_margin_pct': gross_margin_pct,
        'operating_expenses': operating_expenses,
        'paid_operating_expenses': paid_operating_expenses,
        'pending_expenses': pending_expenses,
        'net_operating_profit': net_operating_profit,
        'sales_count': sales_agg['sales_count'] or 0,
        'returns_count': returns_agg['returns_count'] or 0,
        'expenses_count': expenses_agg['expenses_count'] or 0,
    }
