import csv
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum
from django.forms.models import model_to_dict
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from .forms import (
    ActivityForm,
    CommentForm,
    PayrollWeekForm,
    PayoutBatchForm,
    RateRuleForm,
    SiteForm,
    WorkRecordAssignmentFormSet,
    WorkRecordForm,
    WorkerForm,
)
from .models import (
    Activity,
    PayoutBatch,
    PayrollResult,
    PayrollWeek,
    RateRule,
    Site,
    ValidationIssue,
    WorkRecord,
    Worker,
)
from .services import prepare_payout_batch, recalculate_week, recalculate_work_record, record_audit, transition_week_status


def _serialise_instance_value(instance, field_name):
    field = instance._meta.get_field(field_name)
    if field.many_to_many:
        return ", ".join(str(item) for item in getattr(instance, field_name).all())
    value = getattr(instance, field_name)
    if hasattr(value, "all"):
        return ", ".join(str(item) for item in value.all())
    return value


class AuditFormMixin(LoginRequiredMixin):
    template_name = "payroll/form.html"
    page_title = ""
    submit_label = "Save"
    success_message = "Saved successfully."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.page_title
        context["submit_label"] = self.submit_label
        return context

    def form_valid(self, form):
        changes = {}
        if getattr(self, "object", None):
            for field_name in form.changed_data:
                changes[field_name] = (_serialise_instance_value(self.object, field_name), None)

        self.object = form.save()

        for field_name in list(changes.keys()):
            changes[field_name] = (changes[field_name][0], _serialise_instance_value(self.object, field_name))

        action = "created" if self.request.path.endswith("/new/") else "updated"
        record_audit(self.object, self.request.user, action, changes or None)
        messages.success(self.request, self.success_message)
        return redirect(self.get_success_url())


class SearchableListView(LoginRequiredMixin, ListView):
    search_fields = []

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        if query:
            filters = None
            for field_name in self.search_fields:
                clause = {f"{field_name}__icontains": query}
                if filters is None:
                    filters = clause
            if filters is not None:
                combined = queryset.none()
                for field_name in self.search_fields:
                    combined = combined | queryset.filter(**{f"{field_name}__icontains": query})
                queryset = combined.distinct()
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["q"] = self.request.GET.get("q", "").strip()
        return context


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "payroll/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_week = PayrollWeek.objects.order_by("-start_date").first()
        pending_records = WorkRecord.objects.filter(status__in=[WorkRecord.Status.SUBMITTED, WorkRecord.Status.UNDER_REVIEW]).count()
        open_issues = ValidationIssue.objects.filter(is_resolved=False).count()
        approved_total = (
            PayrollResult.objects.filter(work_record__status=WorkRecord.Status.APPROVED).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        unpaid_total = (
            PayrollResult.objects.filter(is_paid=False, work_record__status=WorkRecord.Status.APPROVED).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        site_totals = []
        recent_results = PayrollResult.objects.all()
        if current_week:
            recent_results = recent_results.filter(week=current_week)
            site_totals = list(
                recent_results.values("site__name")
                .annotate(total_amount=Sum("amount"), worker_count=Count("worker", distinct=True))
                .order_by("-total_amount")
            )

        context.update(
            {
                "current_week": current_week,
                "open_weeks": PayrollWeek.objects.filter(status=PayrollWeek.Status.OPEN).count(),
                "pending_records": pending_records,
                "open_issues": open_issues,
                "approved_total": approved_total,
                "unpaid_total": unpaid_total,
                "site_totals": site_totals,
                "pending_batches": PayoutBatch.objects.filter(status__in=[PayoutBatch.Status.DRAFT, PayoutBatch.Status.APPROVED]).count(),
                "recent_weeks": PayrollWeek.objects.all()[:5],
            }
        )
        return context


class WorkerListView(SearchableListView):
    template_name = "payroll/worker_list.html"
    model = Worker
    context_object_name = "workers"
    search_fields = ["worker_code", "full_name", "national_id", "phone_number", "mpesa_phone", "home_site__name"]


class WorkerCreateView(AuditFormMixin, CreateView):
    model = Worker
    form_class = WorkerForm
    page_title = "New Worker"
    submit_label = "Create worker"
    success_message = "Worker saved."
    success_url = reverse_lazy("worker-list")


class WorkerUpdateView(AuditFormMixin, UpdateView):
    model = Worker
    form_class = WorkerForm
    page_title = "Edit Worker"
    submit_label = "Update worker"
    success_message = "Worker updated."
    success_url = reverse_lazy("worker-list")


class WorkerDetailView(LoginRequiredMixin, DetailView):
    model = Worker
    template_name = "payroll/worker_detail.html"
    context_object_name = "worker"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        worker = self.object
        context["earnings_history"] = worker.payroll_results.select_related("week", "site", "activity").order_by("-week__start_date")[:25]
        context["validation_issues"] = worker.validation_issues.filter(is_resolved=False)[:10]
        return context


class SiteListView(SearchableListView):
    template_name = "payroll/site_list.html"
    model = Site
    context_object_name = "sites"
    search_fields = ["code", "name", "department", "supervisor_name"]


class SiteCreateView(AuditFormMixin, CreateView):
    model = Site
    form_class = SiteForm
    page_title = "New Site"
    submit_label = "Create site"
    success_message = "Site saved."
    success_url = reverse_lazy("site-list")


class SiteUpdateView(AuditFormMixin, UpdateView):
    model = Site
    form_class = SiteForm
    page_title = "Edit Site"
    submit_label = "Update site"
    success_message = "Site updated."
    success_url = reverse_lazy("site-list")


class ActivityListView(SearchableListView):
    template_name = "payroll/activity_list.html"
    model = Activity
    context_object_name = "activities"
    search_fields = ["code", "name", "description"]


class ActivityCreateView(AuditFormMixin, CreateView):
    model = Activity
    form_class = ActivityForm
    page_title = "New Activity"
    submit_label = "Create activity"
    success_message = "Activity saved."
    success_url = reverse_lazy("activity-list")


class ActivityUpdateView(AuditFormMixin, UpdateView):
    model = Activity
    form_class = ActivityForm
    page_title = "Edit Activity"
    submit_label = "Update activity"
    success_message = "Activity updated."
    success_url = reverse_lazy("activity-list")


class RateRuleListView(SearchableListView):
    template_name = "payroll/rate_rule_list.html"
    model = RateRule
    context_object_name = "rate_rules"
    search_fields = ["site__name", "activity__name", "parameter_notes"]


class RateRuleCreateView(AuditFormMixin, CreateView):
    model = RateRule
    form_class = RateRuleForm
    page_title = "New Rate Rule"
    submit_label = "Create rule"
    success_message = "Rate rule saved."
    success_url = reverse_lazy("rate-rule-list")


class RateRuleUpdateView(AuditFormMixin, UpdateView):
    model = RateRule
    form_class = RateRuleForm
    page_title = "Edit Rate Rule"
    submit_label = "Update rule"
    success_message = "Rate rule updated."
    success_url = reverse_lazy("rate-rule-list")


class PayrollWeekListView(ListView):
    template_name = "payroll/week_list.html"
    model = PayrollWeek
    context_object_name = "weeks"


class PayrollWeekCreateView(AuditFormMixin, CreateView):
    model = PayrollWeek
    form_class = PayrollWeekForm
    page_title = "New Payroll Week"
    submit_label = "Create week"
    success_message = "Payroll week saved."
    success_url = reverse_lazy("week-list")


class PayrollWeekUpdateView(AuditFormMixin, UpdateView):
    model = PayrollWeek
    form_class = PayrollWeekForm
    page_title = "Edit Payroll Week"
    submit_label = "Update week"
    success_message = "Payroll week updated."
    success_url = reverse_lazy("week-list")


class PayrollWeekDetailView(LoginRequiredMixin, DetailView):
    model = PayrollWeek
    template_name = "payroll/week_detail.html"
    context_object_name = "week"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        week = self.object
        context["work_records"] = week.work_records.select_related("site", "activity").prefetch_related("assignments__worker")
        context["issues"] = week.validation_issues.select_related("site", "worker", "work_record")
        context["site_summary"] = (
            week.payroll_results.values("site__name")
            .annotate(total_amount=Sum("amount"), workers=Count("worker", distinct=True))
            .order_by("-total_amount")
        )
        context["activity_summary"] = (
            week.payroll_results.values("activity__name")
            .annotate(total_amount=Sum("amount"), workers=Count("worker", distinct=True))
            .order_by("-total_amount")
        )
        context["blocking_issue_count"] = week.validation_issues.filter(severity=ValidationIssue.Severity.BLOCKING).count()
        context["comment_form"] = CommentForm()
        return context


@login_required
def recalculate_week_view(request, pk):
    week = get_object_or_404(PayrollWeek, pk=pk)
    recalculate_week(week, actor=request.user)
    messages.success(request, "Payroll week recalculated and validated.")
    return redirect("week-detail", pk=week.pk)


@login_required
def submit_week_view(request, pk):
    week = get_object_or_404(PayrollWeek, pk=pk)
    comments = request.POST.get("comments", "")
    transition_week_status(week, PayrollWeek.Status.UNDER_REVIEW, actor=request.user, comments=comments)
    week.work_records.filter(status=WorkRecord.Status.DRAFT).update(status=WorkRecord.Status.SUBMITTED, submitted_at=timezone.now())
    messages.success(request, "Payroll week submitted for review.")
    return redirect("week-detail", pk=week.pk)


@login_required
def approve_week_view(request, pk):
    week = get_object_or_404(PayrollWeek, pk=pk)
    blocking_issues = week.validation_issues.filter(severity=ValidationIssue.Severity.BLOCKING, is_resolved=False).count()
    if blocking_issues:
        messages.error(request, "Resolve all blocking issues before approval.")
        return redirect("week-detail", pk=week.pk)

    comments = request.POST.get("comments", "")
    transition_week_status(week, PayrollWeek.Status.APPROVED, actor=request.user, comments=comments)
    week.work_records.exclude(status=WorkRecord.Status.PAID).update(
        status=WorkRecord.Status.APPROVED,
        reviewed_by=request.user,
        approved_at=timezone.now(),
    )
    messages.success(request, "Payroll week approved.")
    return redirect("week-detail", pk=week.pk)


@login_required
def return_week_view(request, pk):
    week = get_object_or_404(PayrollWeek, pk=pk)
    comments = request.POST.get("comments", "")
    transition_week_status(week, PayrollWeek.Status.OPEN, actor=request.user, comments=comments)
    week.work_records.exclude(status=WorkRecord.Status.PAID).update(status=WorkRecord.Status.RETURNED)
    messages.warning(request, "Payroll week returned for correction.")
    return redirect("week-detail", pk=week.pk)


class WorkRecordListView(LoginRequiredMixin, ListView):
    template_name = "payroll/work_record_list.html"
    model = WorkRecord
    context_object_name = "records"

    def get_queryset(self):
        queryset = WorkRecord.objects.select_related("week", "site", "activity")
        week_id = self.request.GET.get("week")
        site_id = self.request.GET.get("site")
        status = self.request.GET.get("status")
        if week_id:
            queryset = queryset.filter(week_id=week_id)
        if site_id:
            queryset = queryset.filter(site_id=site_id)
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["weeks"] = PayrollWeek.objects.all()
        context["sites"] = Site.objects.filter(is_active=True)
        context["statuses"] = WorkRecord.Status.choices
        context["selected_week"] = self.request.GET.get("week", "")
        context["selected_site"] = self.request.GET.get("site", "")
        context["selected_status"] = self.request.GET.get("status", "")
        return context


@login_required
def work_record_form_view(request, pk=None):
    instance = get_object_or_404(WorkRecord, pk=pk) if pk else None
    page_title = "Edit Work Record" if instance else "New Work Record"
    submit_label = "Update record" if instance else "Create record"

    before_values = {}
    if instance:
        before_values = model_to_dict(instance, fields=WorkRecordForm.Meta.fields)

    form = WorkRecordForm(request.POST or None, instance=instance)
    formset = WorkRecordAssignmentFormSet(request.POST or None, instance=instance)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        record = form.save(commit=False)
        if not record.entered_by:
            record.entered_by = request.user
        record.save()
        form.save_m2m()
        formset.instance = record
        formset.save()
        recalculate_work_record(record, actor=request.user)
        recalculate_week(record.week, actor=request.user)

        changes = None
        if before_values:
            changes = {}
            for field_name, old_value in before_values.items():
                new_value = getattr(record, field_name)
                if old_value != new_value:
                    changes[field_name] = (old_value, new_value)
        record_audit(record, request.user, "updated" if instance else "created", changes)
        messages.success(request, "Work record saved and payroll refreshed.")
        return redirect("week-detail", pk=record.week_id)

    return render(
        request,
        "payroll/work_record_form.html",
        {
            "form": form,
            "formset": formset,
            "page_title": page_title,
            "submit_label": submit_label,
        },
    )


@login_required
def submit_record_view(request, pk):
    record = get_object_or_404(WorkRecord, pk=pk)
    record.status = WorkRecord.Status.SUBMITTED
    record.submitted_at = timezone.now()
    record.save(update_fields=["status", "submitted_at", "updated_at"])
    record_audit(record, request.user, "submitted", {"status": (WorkRecord.Status.DRAFT, WorkRecord.Status.SUBMITTED)})
    messages.success(request, "Work record submitted for review.")
    return redirect("week-detail", pk=record.week_id)


class PayoutBatchListView(LoginRequiredMixin, ListView):
    template_name = "payroll/payout_batch_list.html"
    model = PayoutBatch
    context_object_name = "batches"


@login_required
def payout_batch_create_view(request):
    form = PayoutBatchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        batch = form.save(commit=False)
        batch.created_by = request.user
        batch.save()
        prepare_payout_batch(batch, actor=request.user)
        messages.success(request, "Payout batch prepared.")
        return redirect("payout-batch-detail", pk=batch.pk)

    return render(
        request,
        "payroll/payout_batch_form.html",
        {
            "form": form,
            "page_title": "Create Payout Batch",
            "submit_label": "Prepare batch",
        },
    )


class PayoutBatchDetailView(LoginRequiredMixin, DetailView):
    model = PayoutBatch
    template_name = "payroll/payout_batch_detail.html"
    context_object_name = "batch"


@login_required
def export_payout_batch_csv(request, pk):
    batch = get_object_or_404(PayoutBatch, pk=pk)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{batch.batch_number}.csv"'

    writer = csv.writer(response)
    writer.writerow(["Name", "Phone", "ID", "NSSF", "NHIF", "Amount", "Type", "Site", "Week", "Reference"])
    for item in batch.items.select_related("worker"):
        writer.writerow(
            [
                item.worker.full_name,
                item.phone_number,
                item.id_number,
                item.nssf_number,
                item.nhif_number,
                item.amount,
                item.payment_category,
                batch.site.name if batch.site else "ALL",
                batch.week.reference,
                item.reference,
            ]
        )

    batch.status = PayoutBatch.Status.EXPORTED
    batch.exported_at = timezone.now()
    batch.save(update_fields=["status", "exported_at", "updated_at"])
    messages.success(request, "MPESA-ready CSV exported.")
    return response


@login_required
def mark_payout_batch_paid(request, pk):
    batch = get_object_or_404(PayoutBatch, pk=pk)
    batch.status = PayoutBatch.Status.PAID
    batch.paid_by = request.user
    batch.paid_at = timezone.now()
    batch.save(update_fields=["status", "paid_by", "paid_at", "updated_at"])

    batch.items.update(is_paid=True)
    paid_result_ids = batch.items.values_list("worker_id", flat=True)
    result_queryset = PayrollResult.objects.filter(week=batch.week, worker_id__in=paid_result_ids)
    record_queryset = batch.week.work_records.exclude(status=WorkRecord.Status.ARCHIVED)
    if batch.site_id:
        result_queryset = result_queryset.filter(site=batch.site)
        record_queryset = record_queryset.filter(site=batch.site)
    result_queryset.update(is_paid=True)
    record_queryset.update(status=WorkRecord.Status.PAID)

    remaining_unpaid = PayrollResult.objects.filter(week=batch.week, is_paid=False).exists()
    if not remaining_unpaid:
        batch.week.status = PayrollWeek.Status.PAID
        batch.week.save(update_fields=["status", "updated_at"])

    record_audit(batch, request.user, "paid", {"status": (PayoutBatch.Status.EXPORTED, PayoutBatch.Status.PAID)})
    messages.success(request, "Batch marked as paid.")
    return redirect("payout-batch-detail", pk=batch.pk)


@login_required
def reports_view(request):
    latest_week = PayrollWeek.objects.order_by("-start_date").first()
    site_totals = []
    activity_totals = []
    top_workers = []
    if latest_week:
        site_totals = (
            latest_week.payroll_results.values("site__name")
            .annotate(total_amount=Sum("amount"), headcount=Count("worker", distinct=True))
            .order_by("-total_amount")
        )
        activity_totals = (
            latest_week.payroll_results.values("activity__name")
            .annotate(total_amount=Sum("amount"))
            .order_by("-total_amount")
        )
        top_workers = (
            latest_week.payroll_results.values("worker__full_name", "site__name")
            .annotate(total_amount=Sum("amount"))
            .order_by("-total_amount")[:15]
        )

    return render(
        request,
        "payroll/reports.html",
        {
            "latest_week": latest_week,
            "site_totals": site_totals,
            "activity_totals": activity_totals,
            "top_workers": top_workers,
        },
    )
