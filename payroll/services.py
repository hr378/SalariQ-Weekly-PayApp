from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import (
    Activity,
    ApprovalAction,
    AuditLog,
    PayoutBatch,
    PayoutBatchItem,
    PayrollAdjustment,
    PayrollResult,
    PayrollWeek,
    RateRule,
    ValidationIssue,
    WorkRecord,
    WorkRecordAssignment,
    Worker,
)


TWO_DP = Decimal("0.01")


def quantize_amount(value: Decimal) -> Decimal:
    return Decimal(value).quantize(TWO_DP, rounding=ROUND_HALF_UP)


def phone_is_valid(phone_number: str) -> bool:
    if not phone_number:
        return False
    digits = phone_number.replace("+", "")
    return digits.isdigit() and 10 <= len(digits) <= 15


def resolve_rate_rule(site, activity, work_date):
    return (
        RateRule.objects.filter(
            site=site,
            activity=activity,
            is_active=True,
            effective_from__lte=work_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=work_date))
        .order_by("-effective_from")
        .first()
    )


def record_audit(instance, user, action, changes=None, reason=""):
    object_id = str(getattr(instance, "pk", "")) or ""
    if not changes:
        AuditLog.objects.create(
            model_name=instance.__class__.__name__,
            object_id=object_id,
            action=action,
            reason=reason,
            user=user,
        )
        return

    for field_name, values in changes.items():
        old_value, new_value = values
        AuditLog.objects.create(
            model_name=instance.__class__.__name__,
            object_id=object_id,
            action=action,
            field_name=field_name,
            old_value="" if old_value is None else str(old_value),
            new_value="" if new_value is None else str(new_value),
            reason=reason,
            user=user,
        )


def _resolved_total_amount(record: WorkRecord, rule: RateRule | None):
    if rule:
        model = rule.resolved_model()
        unit_rate = rule.unit_rate
        fixed_amount = rule.fixed_amount
        pooled_amount = rule.pooled_amount
    else:
        model = record.activity.rate_model
        unit_rate = record.activity.default_rate
        fixed_amount = record.activity.fixed_amount
        pooled_amount = Decimal("0.00")

    quantity = record.quantity or Decimal("0.00")

    if model in [Activity.RateModel.PIECE_RATE, Activity.RateModel.PARAMETER]:
        total_amount = quantity * unit_rate
        rate_snapshot = unit_rate
    elif model == Activity.RateModel.FIXED:
        total_amount = fixed_amount or unit_rate or record.manual_total_amount
        rate_snapshot = total_amount
    elif model == Activity.RateModel.SHARED_POOL:
        total_amount = pooled_amount or (quantity * unit_rate) or record.manual_total_amount
        rate_snapshot = pooled_amount or unit_rate
    else:
        total_amount = record.manual_total_amount
        rate_snapshot = record.manual_total_amount

    return model, quantize_amount(total_amount), quantize_amount(rate_snapshot)


@transaction.atomic
def recalculate_work_record(record: WorkRecord, actor=None):
    rule = record.rate_rule or resolve_rate_rule(record.site, record.activity, record.work_date)
    model, total_amount, rate_snapshot = _resolved_total_amount(record, rule)

    record.rate_rule = rule
    record.rate_value_snapshot = rate_snapshot
    record.total_amount = total_amount
    record.save(update_fields=["rate_rule", "rate_value_snapshot", "total_amount", "updated_at"])

    assignments = list(record.assignments.select_related("worker"))
    if not assignments:
        record.payroll_results.all().delete()
        return record

    manual_assignments = [assignment for assignment in assignments if assignment.manual_amount is not None]
    auto_assignments = [assignment for assignment in assignments if assignment.manual_amount is None]
    total_manual = sum((assignment.manual_amount or Decimal("0.00")) for assignment in manual_assignments)
    remaining = total_amount - total_manual
    if remaining < 0:
        remaining = Decimal("0.00")

    total_weight = sum((assignment.weight or Decimal("0.00")) for assignment in auto_assignments) or Decimal("0.00")

    allocations = []
    running_total = Decimal("0.00")
    for index, assignment in enumerate(assignments):
        if assignment.manual_amount is not None:
            amount = quantize_amount(assignment.manual_amount)
        elif total_weight > 0:
            amount = quantize_amount(remaining * (assignment.weight / total_weight))
        else:
            amount = quantize_amount(remaining / Decimal(len(auto_assignments) or 1))

        if index == len(assignments) - 1:
            amount = quantize_amount(total_amount - running_total)

        assignment.allocated_amount = amount
        assignment.save(update_fields=["allocated_amount", "updated_at"])
        running_total += amount
        allocations.append((assignment.worker, amount))

    record.payroll_results.all().delete()
    PayrollResult.objects.bulk_create(
        [
            PayrollResult(
                week=record.week,
                worker=worker,
                site=record.site,
                activity=record.activity,
                work_record=record,
                quantity=record.quantity,
                rate=rate_snapshot,
                amount=amount,
                payment_category=record.payment_category,
            )
            for worker, amount in allocations
        ]
    )

    record_audit(record, actor, "recalculated", {"total_amount": ("", total_amount), "rate_value_snapshot": ("", rate_snapshot)}, "")
    return record


@transaction.atomic
def run_week_validations(week: PayrollWeek):
    week.validation_issues.all().delete()

    work_records = list(
        week.work_records.select_related("site", "activity", "rate_rule").prefetch_related("assignments__worker")
    )

    issues = []

    duplicate_trucks = (
        week.work_records.exclude(truck_number="")
        .values("site_id", "work_date", "shift", "truck_number")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    duplicate_truck_keys = {
        (row["site_id"], row["work_date"], row["shift"], row["truck_number"])
        for row in duplicate_trucks
    }

    worker_site_shift_map = defaultdict(set)
    worker_record_map = defaultdict(list)

    for record in work_records:
        assignments = list(record.assignments.all())
        if not assignments:
            issues.append(
                ValidationIssue(
                    week=week,
                    site=record.site,
                    work_record=record,
                    code="missing_workers",
                    message="This work record has no assigned workers.",
                    severity=ValidationIssue.Severity.BLOCKING,
                )
            )

        rule = record.rate_rule or resolve_rate_rule(record.site, record.activity, record.work_date)
        if not rule and record.activity.rate_model != Activity.RateModel.MANUAL:
            issues.append(
                ValidationIssue(
                    week=week,
                    site=record.site,
                    work_record=record,
                    code="missing_rate",
                    message="No active rate rule was found for this site and activity.",
                    severity=ValidationIssue.Severity.BLOCKING,
                )
            )

        if record.activity.rate_model in [Activity.RateModel.PIECE_RATE, Activity.RateModel.PARAMETER] and record.quantity <= 0:
            issues.append(
                ValidationIssue(
                    week=week,
                    site=record.site,
                    work_record=record,
                    code="missing_quantity",
                    message="Piece-rate and parameter-driven entries need a quantity greater than zero.",
                    severity=ValidationIssue.Severity.BLOCKING,
                )
            )

        allowed_people = (rule.max_manpower if rule and rule.max_manpower else record.activity.max_manpower) or 0
        if allowed_people and len(assignments) > allowed_people:
            issues.append(
                ValidationIssue(
                    week=week,
                    site=record.site,
                    work_record=record,
                    code="overstaffed",
                    message=f"Assigned workers ({len(assignments)}) exceed the configured manpower limit ({allowed_people}).",
                    severity=ValidationIssue.Severity.BLOCKING,
                )
            )

        if (record.site_id, record.work_date, record.shift, record.truck_number) in duplicate_truck_keys:
            issues.append(
                ValidationIssue(
                    week=week,
                    site=record.site,
                    work_record=record,
                    code="duplicate_truck",
                    message="The same truck number appears more than once for the same site, date, and shift.",
                    severity=ValidationIssue.Severity.BLOCKING,
                )
            )

        for assignment in assignments:
            worker = assignment.worker
            worker_record_map[(worker.id, record.work_date, record.shift, record.activity_id, record.site_id)].append(record.id)
            worker_site_shift_map[(worker.id, record.work_date, record.shift)].add(record.site_id)

            if not phone_is_valid(worker.payout_phone):
                issues.append(
                    ValidationIssue(
                        week=week,
                        site=record.site,
                        work_record=record,
                        worker=worker,
                        code="invalid_phone",
                        message=f"{worker.full_name} is missing a valid payout phone number.",
                        severity=ValidationIssue.Severity.BLOCKING,
                    )
                )

            if not worker.national_id:
                issues.append(
                    ValidationIssue(
                        week=week,
                        site=record.site,
                        work_record=record,
                        worker=worker,
                        code="missing_id",
                        message=f"{worker.full_name} is missing a national ID.",
                        severity=ValidationIssue.Severity.WARNING,
                    )
                )

            if not worker.nhif_number or not worker.nssf_number:
                issues.append(
                    ValidationIssue(
                        week=week,
                        site=record.site,
                        work_record=record,
                        worker=worker,
                        code="missing_statutory",
                        message=f"{worker.full_name} is missing NHIF and/or NSSF details.",
                        severity=ValidationIssue.Severity.WARNING,
                    )
                )

    for (worker_id, work_date, shift), site_ids in worker_site_shift_map.items():
        if len(site_ids) > 1:
            worker = Worker.objects.get(pk=worker_id)
            issues.append(
                ValidationIssue(
                    week=week,
                    worker=worker,
                    code="conflicting_sites",
                    message=f"{worker.full_name} is assigned in multiple sites on {work_date} shift {shift}.",
                    severity=ValidationIssue.Severity.BLOCKING,
                )
            )

    for (worker_id, work_date, shift, activity_id, site_id), record_ids in worker_record_map.items():
        if len(record_ids) > 1:
            worker = Worker.objects.get(pk=worker_id)
            site = None
            if site_id:
                site = Worker.objects.filter(pk=worker_id).first().home_site
            issues.append(
                ValidationIssue(
                    week=week,
                    worker=worker,
                    site=site,
                    code="duplicate_worker_assignment",
                    message=f"{worker.full_name} appears multiple times for the same date, shift, site, and activity.",
                    severity=ValidationIssue.Severity.BLOCKING,
                )
            )

    ValidationIssue.objects.bulk_create(issues)
    return issues


@transaction.atomic
def recalculate_week(week: PayrollWeek, actor=None):
    for record in week.work_records.all():
        recalculate_work_record(record, actor=actor)

    PayrollResult.objects.filter(week=week, source=PayrollResult.Source.ADJUSTMENT).delete()
    PayrollResult.objects.bulk_create(
        [
            PayrollResult(
                week=adjustment.week,
                worker=adjustment.worker,
                site=adjustment.site,
                activity=adjustment.activity,
                source=PayrollResult.Source.ADJUSTMENT,
                amount=adjustment.signed_amount(),
                payment_category=WorkRecord.PaymentCategory.ADJUSTMENT,
            )
            for adjustment in PayrollAdjustment.objects.filter(week=week)
        ]
    )

    run_week_validations(week)
    return week


@transaction.atomic
def prepare_payout_batch(batch: PayoutBatch, actor=None):
    site_filter = Q(site=batch.site) if batch.site_id else Q()
    grouped_results = (
        PayrollResult.objects.filter(
            week=batch.week,
            is_paid=False,
        )
        .filter(Q(work_record__status=WorkRecord.Status.APPROVED) | Q(source=PayrollResult.Source.ADJUSTMENT))
        .filter(site_filter)
        .values("worker_id", "payment_category")
        .annotate(total=Sum("amount"))
        .order_by("worker_id")
    )

    batch.items.all().delete()
    items = []
    for row in grouped_results:
        worker = Worker.objects.get(pk=row["worker_id"])
        items.append(
            PayoutBatchItem(
                batch=batch,
                worker=worker,
                amount=quantize_amount(row["total"]),
                phone_number=worker.payout_phone,
                id_number=worker.national_id,
                nssf_number=worker.nssf_number,
                nhif_number=worker.nhif_number,
                payment_category=row["payment_category"],
                reference=f"{batch.week.reference}-{worker.worker_code}",
            )
        )

    PayoutBatchItem.objects.bulk_create(items)
    record_audit(batch, actor, "prepared", {"items": ("", len(items))}, "Batch items generated")
    return batch


@transaction.atomic
def transition_week_status(week: PayrollWeek, to_status: str, actor=None, comments=""):
    from_status = week.status
    week.status = to_status
    week.save(update_fields=["status", "updated_at"])
    ApprovalAction.objects.create(
        week=week,
        action=f"week_{to_status}",
        from_status=from_status,
        to_status=to_status,
        comments=comments,
        actor=actor,
    )
    record_audit(week, actor, "status_changed", {"status": (from_status, to_status)}, comments)
    return week
