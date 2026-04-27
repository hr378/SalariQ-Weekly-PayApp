from django.db import OperationalError, ProgrammingError

from payroll.models import PayrollWeek, ValidationIssue


def navigation_context(request):
    try:
        active_week = PayrollWeek.objects.filter(
            status__in=[PayrollWeek.Status.OPEN, PayrollWeek.Status.UNDER_REVIEW]
        ).order_by("-start_date").first()
        open_issues = ValidationIssue.objects.filter(is_resolved=False).count()
    except (OperationalError, ProgrammingError):
        active_week = None
        open_issues = 0
    return {
        "nav_active_week": active_week,
        "nav_open_issues": open_issues,
    }
