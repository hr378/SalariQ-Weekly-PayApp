from django.contrib import admin

from .models import (
    Activity,
    ApprovalAction,
    AuditLog,
    PayrollAdjustment,
    PayrollResult,
    PayrollWeek,
    PayoutBatch,
    PayoutBatchItem,
    RateRule,
    Site,
    ValidationIssue,
    WorkRecord,
    WorkRecordAssignment,
    Worker,
)


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "payroll_model", "default_payment_method", "is_active"]
    search_fields = ["code", "name"]


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ["worker_code", "full_name", "national_id", "payout_phone", "home_site", "status"]
    search_fields = ["worker_code", "full_name", "national_id", "phone_number", "mpesa_phone"]
    list_filter = ["status", "home_site"]


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "unit_of_measure", "rate_model", "max_manpower", "is_active"]
    search_fields = ["code", "name"]
    list_filter = ["rate_model", "unit_of_measure", "is_active"]


@admin.register(RateRule)
class RateRuleAdmin(admin.ModelAdmin):
    list_display = ["site", "activity", "effective_from", "effective_to", "model", "unit_rate", "is_active"]
    list_filter = ["site", "activity", "model", "is_active"]


class WorkRecordAssignmentInline(admin.TabularInline):
    model = WorkRecordAssignment
    extra = 0


@admin.register(WorkRecord)
class WorkRecordAdmin(admin.ModelAdmin):
    list_display = ["week", "site", "work_date", "shift", "activity", "quantity", "total_amount", "status"]
    list_filter = ["week", "site", "status", "shift", "activity"]
    search_fields = ["truck_number", "client_details"]
    inlines = [WorkRecordAssignmentInline]


@admin.register(PayrollWeek)
class PayrollWeekAdmin(admin.ModelAdmin):
    list_display = ["reference", "start_date", "end_date", "status"]
    list_filter = ["status"]


admin.site.register(PayrollResult)
admin.site.register(PayrollAdjustment)
admin.site.register(ValidationIssue)
admin.site.register(PayoutBatch)
admin.site.register(PayoutBatchItem)
admin.site.register(ApprovalAction)
admin.site.register(AuditLog)
