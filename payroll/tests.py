from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from payroll.models import Activity, PayoutBatch, PayrollWeek, RateRule, Site, WorkRecord, WorkRecordAssignment, Worker
from payroll.services import prepare_payout_batch, recalculate_week, recalculate_work_record


class PayrollServiceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tester", password="secret123")
        self.site = Site.objects.create(code="SITEA", name="Site A")
        self.other_site = Site.objects.create(code="SITEB", name="Site B")
        self.activity = Activity.objects.create(
            code="PLY",
            name="Ply Loading",
            unit_of_measure=Activity.UnitOfMeasure.TONNAGE,
            rate_model=Activity.RateModel.PIECE_RATE,
            default_rate=Decimal("500.00"),
            max_manpower=4,
        )
        self.week = PayrollWeek.objects.create(start_date=date(2026, 4, 8), end_date=date(2026, 4, 14))
        self.rule = RateRule.objects.create(
            site=self.site,
            activity=self.activity,
            effective_from=date(2026, 4, 8),
            model=Activity.RateModel.PIECE_RATE,
            unit_rate=Decimal("500.00"),
            max_manpower=4,
        )
        self.worker_1 = Worker.objects.create(
            full_name="Alice Worker",
            national_id="12345678",
            phone_number="254700000001",
            mpesa_phone="254700000001",
            nhif_number="NHIF1",
            nssf_number="NSSF1",
            home_site=self.site,
        )
        self.worker_2 = Worker.objects.create(
            full_name="Bob Worker",
            national_id="22345678",
            phone_number="254700000002",
            mpesa_phone="254700000002",
            nhif_number="NHIF2",
            nssf_number="NSSF2",
            home_site=self.site,
        )

    def test_piece_rate_work_record_allocates_amount_evenly(self):
        record = WorkRecord.objects.create(
            week=self.week,
            site=self.site,
            work_date=date(2026, 4, 8),
            shift=WorkRecord.Shift.DAY,
            activity=self.activity,
            quantity=Decimal("10.00"),
            rate_rule=self.rule,
            entered_by=self.user,
        )
        WorkRecordAssignment.objects.create(work_record=record, worker=self.worker_1, weight=Decimal("1.00"))
        WorkRecordAssignment.objects.create(work_record=record, worker=self.worker_2, weight=Decimal("1.00"))

        recalculate_work_record(record, actor=self.user)

        record.refresh_from_db()
        self.assertEqual(record.total_amount, Decimal("5000.00"))
        allocations = list(record.assignments.order_by("worker__full_name").values_list("allocated_amount", flat=True))
        self.assertEqual(allocations, [Decimal("2500.00"), Decimal("2500.00")])
        self.assertEqual(record.payroll_results.count(), 2)

    def test_validation_flags_same_worker_in_two_sites_same_shift(self):
        first_record = WorkRecord.objects.create(
            week=self.week,
            site=self.site,
            work_date=date(2026, 4, 9),
            shift=WorkRecord.Shift.DAY,
            activity=self.activity,
            quantity=Decimal("5.00"),
            rate_rule=self.rule,
        )
        second_record = WorkRecord.objects.create(
            week=self.week,
            site=self.other_site,
            work_date=date(2026, 4, 9),
            shift=WorkRecord.Shift.DAY,
            activity=self.activity,
            quantity=Decimal("4.00"),
        )
        RateRule.objects.create(
            site=self.other_site,
            activity=self.activity,
            effective_from=date(2026, 4, 8),
            model=Activity.RateModel.PIECE_RATE,
            unit_rate=Decimal("500.00"),
        )
        WorkRecordAssignment.objects.create(work_record=first_record, worker=self.worker_1)
        WorkRecordAssignment.objects.create(work_record=second_record, worker=self.worker_1)

        recalculate_week(self.week, actor=self.user)

        codes = set(self.week.validation_issues.values_list("code", flat=True))
        self.assertIn("conflicting_sites", codes)

    def test_prepare_payout_batch_collects_only_approved_results(self):
        record = WorkRecord.objects.create(
            week=self.week,
            site=self.site,
            work_date=date(2026, 4, 10),
            shift=WorkRecord.Shift.DAY,
            activity=self.activity,
            quantity=Decimal("8.00"),
            rate_rule=self.rule,
            status=WorkRecord.Status.APPROVED,
        )
        WorkRecordAssignment.objects.create(work_record=record, worker=self.worker_1, weight=Decimal("1.00"))
        recalculate_work_record(record, actor=self.user)

        batch = PayoutBatch.objects.create(week=self.week, site=self.site, created_by=self.user)
        prepare_payout_batch(batch, actor=self.user)

        self.assertEqual(batch.items.count(), 1)
        item = batch.items.first()
        self.assertEqual(item.worker, self.worker_1)
        self.assertEqual(item.amount, Decimal("4000.00"))
