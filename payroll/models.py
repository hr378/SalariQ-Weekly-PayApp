from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Site(TimeStampedModel):
    class PayrollModel(models.TextChoices):
        SIMPLE = "simple", "Simple site payroll"
        INTEGRATED = "integrated", "Integrated production payroll"
        EXTRA = "extra", "Extra activities"

    class PaymentMethod(models.TextChoices):
        MPESA = "mpesa", "MPESA"
        BANK = "bank", "Bank"
        CASH = "cash", "Cash"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100, unique=True)
    department = models.CharField(max_length=100, blank=True)
    supervisor_name = models.CharField(max_length=120, blank=True)
    payroll_model = models.CharField(max_length=20, choices=PayrollModel.choices, default=PayrollModel.SIMPLE)
    default_payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.MPESA)
    approval_chain = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Worker(TimeStampedModel):
    class Gender(models.TextChoices):
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        BLACKLISTED = "blacklisted", "Blacklisted"

    worker_code = models.CharField(max_length=20, unique=True, blank=True)
    full_name = models.CharField(max_length=150)
    national_id = models.CharField(max_length=30, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    mpesa_phone = models.CharField(max_length=20, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    home_site = models.ForeignKey(Site, on_delete=models.SET_NULL, null=True, blank=True, related_name="workers")
    worker_category = models.CharField(max_length=100, blank=True)
    job_type = models.CharField(max_length=100, blank=True)
    nhif_number = models.CharField(max_length=30, blank=True)
    nssf_number = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    date_joined = models.DateField(default=timezone.localdate)
    supervisor_name = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["national_id"],
                condition=~models.Q(national_id=""),
                name="unique_non_blank_worker_national_id",
            )
        ]

    def clean(self):
        if self.phone_number and not self.phone_number.replace("+", "").isdigit():
            raise ValidationError({"phone_number": "Phone number should contain digits only."})
        if self.mpesa_phone and not self.mpesa_phone.replace("+", "").isdigit():
            raise ValidationError({"mpesa_phone": "MPESA phone should contain digits only."})

    def save(self, *args, **kwargs):
        if not self.worker_code:
            self.worker_code = f"WKR-{uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    @property
    def payout_phone(self) -> str:
        return self.mpesa_phone or self.phone_number

    @property
    def statutory_complete(self) -> bool:
        return all([self.national_id, self.payout_phone, self.nhif_number, self.nssf_number])

    def __str__(self) -> str:
        return f"{self.full_name} ({self.worker_code})"


class PayrollWeek(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        UNDER_REVIEW = "under_review", "Under Review"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        ARCHIVED = "archived", "Archived"

    reference = models.CharField(max_length=30, unique=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    active_sites = models.ManyToManyField(Site, blank=True, related_name="payroll_weeks")

    class Meta:
        ordering = ["-start_date"]

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"WK-{self.start_date:%Y%m%d}-{self.end_date:%Y%m%d}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.reference


class Activity(TimeStampedModel):
    class UnitOfMeasure(models.TextChoices):
        TONNAGE = "tonnage", "Tonnage"
        DAY = "day", "Day"
        SHIFT = "shift", "Shift"
        TRIP = "trip", "Trip"
        HEADCOUNT = "headcount", "Headcount"
        FIXED = "fixed", "Fixed amount"

    class RateModel(models.TextChoices):
        PIECE_RATE = "piece_rate", "Piece rate"
        FIXED = "fixed", "Fixed pay"
        SHARED_POOL = "shared_pool", "Shared pool"
        PARAMETER = "parameter", "Parameter driven"
        MANUAL = "manual", "Manual override"

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    unit_of_measure = models.CharField(max_length=20, choices=UnitOfMeasure.choices, default=UnitOfMeasure.TONNAGE)
    rate_model = models.CharField(max_length=20, choices=RateModel.choices, default=RateModel.PIECE_RATE)
    max_manpower = models.PositiveIntegerField(null=True, blank=True)
    default_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    sites = models.ManyToManyField(Site, blank=True, related_name="activities")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RateRule(TimeStampedModel):
    class WeightingMode(models.TextChoices):
        EQUAL = "equal", "Equal split"
        WEIGHTED = "weighted", "Weighted split"
        ROLE = "role", "Role-based split"
        MANUAL = "manual", "Manual allocation"

    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="rate_rules")
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="rate_rules")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    model = models.CharField(max_length=20, choices=Activity.RateModel.choices, blank=True)
    unit_rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    pooled_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    max_manpower = models.PositiveIntegerField(null=True, blank=True)
    weighting_mode = models.CharField(max_length=20, choices=WeightingMode.choices, default=WeightingMode.EQUAL)
    parameter_notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["site__name", "activity__name", "-effective_from"]
        constraints = [
            models.UniqueConstraint(fields=["site", "activity", "effective_from"], name="unique_rate_rule_by_effective_date")
        ]

    def applies_to(self, work_date):
        return self.effective_from <= work_date and (self.effective_to is None or self.effective_to >= work_date)

    def resolved_model(self) -> str:
        return self.model or self.activity.rate_model

    def __str__(self) -> str:
        return f"{self.site} - {self.activity} ({self.effective_from:%d %b %Y})"


class WorkRecord(TimeStampedModel):
    class Shift(models.TextChoices):
        A = "A", "Shift A"
        B = "B", "Shift B"
        C = "C", "Shift C"
        DAY = "DAY", "Day"
        NIGHT = "NIGHT", "Night"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        RETURNED = "returned", "Returned for correction"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        ARCHIVED = "archived", "Archived"

    class PaymentCategory(models.TextChoices):
        GENERAL = "general", "General payroll"
        EXTRA = "extra", "Extra payroll"
        PRODUCTION = "production", "Production payroll"
        ADJUSTMENT = "adjustment", "Adjustment"

    week = models.ForeignKey(PayrollWeek, on_delete=models.CASCADE, related_name="work_records")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="work_records")
    work_date = models.DateField()
    shift = models.CharField(max_length=10, choices=Shift.choices, default=Shift.DAY)
    truck_number = models.CharField(max_length=50, blank=True)
    client_details = models.CharField(max_length=255, blank=True)
    activity = models.ForeignKey(Activity, on_delete=models.PROTECT, related_name="work_records")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    manual_total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    rate_rule = models.ForeignKey(RateRule, on_delete=models.SET_NULL, null=True, blank=True, related_name="work_records")
    rate_value_snapshot = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_category = models.CharField(max_length=20, choices=PaymentCategory.choices, default=PaymentCategory.GENERAL)
    remarks = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entered_work_records",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_work_records",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-work_date", "site__name", "activity__name"]

    def __str__(self) -> str:
        return f"{self.site} {self.work_date:%d %b %Y} {self.activity}"


class WorkRecordAssignment(TimeStampedModel):
    work_record = models.ForeignKey(WorkRecord, on_delete=models.CASCADE, related_name="assignments")
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="work_assignments")
    role_label = models.CharField(max_length=100, blank=True)
    weight = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1.00"))
    manual_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["worker__full_name"]
        constraints = [
            models.UniqueConstraint(fields=["work_record", "worker"], name="unique_worker_assignment_per_record")
        ]

    def __str__(self) -> str:
        return f"{self.worker} -> {self.work_record}"


class PayrollResult(TimeStampedModel):
    class Source(models.TextChoices):
        WORK_RECORD = "work_record", "Work record"
        ADJUSTMENT = "adjustment", "Adjustment"

    week = models.ForeignKey(PayrollWeek, on_delete=models.CASCADE, related_name="payroll_results")
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="payroll_results")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="payroll_results")
    activity = models.ForeignKey(Activity, on_delete=models.SET_NULL, null=True, blank=True, related_name="payroll_results")
    work_record = models.ForeignKey(WorkRecord, on_delete=models.CASCADE, null=True, blank=True, related_name="payroll_results")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.WORK_RECORD)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    payment_category = models.CharField(max_length=20, choices=WorkRecord.PaymentCategory.choices, default=WorkRecord.PaymentCategory.GENERAL)
    is_paid = models.BooleanField(default=False)

    class Meta:
        ordering = ["worker__full_name"]

    def __str__(self) -> str:
        return f"{self.worker} - {self.amount}"


class PayrollAdjustment(TimeStampedModel):
    week = models.ForeignKey(PayrollWeek, on_delete=models.CASCADE, related_name="adjustments")
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="adjustments")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="adjustments")
    activity = models.ForeignKey(Activity, on_delete=models.SET_NULL, null=True, blank=True, related_name="adjustments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    is_recovery = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def signed_amount(self):
        return self.amount * Decimal("-1") if self.is_recovery else self.amount


class ValidationIssue(TimeStampedModel):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        BLOCKING = "blocking", "Blocking"

    week = models.ForeignKey(PayrollWeek, on_delete=models.CASCADE, related_name="validation_issues")
    site = models.ForeignKey(Site, on_delete=models.SET_NULL, null=True, blank=True, related_name="validation_issues")
    work_record = models.ForeignKey(WorkRecord, on_delete=models.CASCADE, null=True, blank=True, related_name="validation_issues")
    worker = models.ForeignKey(Worker, on_delete=models.SET_NULL, null=True, blank=True, related_name="validation_issues")
    code = models.CharField(max_length=60)
    message = models.CharField(max_length=255)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.WARNING)
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_validation_issues",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.message


class PayoutBatch(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        APPROVED = "approved", "Approved"
        EXPORTED = "exported", "Exported"
        PAID = "paid", "Paid"

    week = models.ForeignKey(PayrollWeek, on_delete=models.CASCADE, related_name="payout_batches")
    site = models.ForeignKey(Site, on_delete=models.SET_NULL, null=True, blank=True, related_name="payout_batches")
    batch_number = models.CharField(max_length=40, unique=True, blank=True)
    payment_method = models.CharField(max_length=20, choices=Site.PaymentMethod.choices, default=Site.PaymentMethod.MPESA)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_payout_batches")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_payout_batches")
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="paid_payout_batches")
    exported_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.batch_number:
            self.batch_number = f"MP-{timezone.now():%Y%m%d%H%M%S}"
        super().save(*args, **kwargs)

    @property
    def total_amount(self):
        return self.items.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

    def __str__(self) -> str:
        return self.batch_number


class PayoutBatchItem(TimeStampedModel):
    batch = models.ForeignKey(PayoutBatch, on_delete=models.CASCADE, related_name="items")
    worker = models.ForeignKey(Worker, on_delete=models.CASCADE, related_name="payout_items")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    phone_number = models.CharField(max_length=20)
    id_number = models.CharField(max_length=30, blank=True)
    nssf_number = models.CharField(max_length=30, blank=True)
    nhif_number = models.CharField(max_length=30, blank=True)
    payment_category = models.CharField(max_length=20, choices=WorkRecord.PaymentCategory.choices, default=WorkRecord.PaymentCategory.GENERAL)
    reference = models.CharField(max_length=80, blank=True)
    is_paid = models.BooleanField(default=False)

    class Meta:
        ordering = ["worker__full_name"]
        constraints = [models.UniqueConstraint(fields=["batch", "worker"], name="unique_worker_per_batch")]

    def __str__(self) -> str:
        return f"{self.worker} - {self.amount}"


class ApprovalAction(TimeStampedModel):
    week = models.ForeignKey(PayrollWeek, on_delete=models.CASCADE, null=True, blank=True, related_name="approval_actions")
    work_record = models.ForeignKey(WorkRecord, on_delete=models.CASCADE, null=True, blank=True, related_name="approval_actions")
    payout_batch = models.ForeignKey(PayoutBatch, on_delete=models.CASCADE, null=True, blank=True, related_name="approval_actions")
    action = models.CharField(max_length=60)
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30, blank=True)
    comments = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approval_actions")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.action


class AuditLog(TimeStampedModel):
    model_name = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    action = models.CharField(max_length=60)
    field_name = models.CharField(max_length=80, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    reason = models.CharField(max_length=255, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.model_name} {self.action}"
