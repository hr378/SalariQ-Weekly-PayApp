from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from payroll.models import Activity, PayrollWeek


class Command(BaseCommand):
    help = "Seed generic starter data for a standalone SalariQ deployment."

    def handle(self, *args, **options):
        activities = [
            ("LOAD", "Loading", Activity.UnitOfMeasure.TONNAGE, Activity.RateModel.PIECE_RATE, Decimal("500.00")),
            ("OFFLOAD", "Offloading", Activity.UnitOfMeasure.TONNAGE, Activity.RateModel.PIECE_RATE, Decimal("500.00")),
            ("SHIFT", "Shift Work", Activity.UnitOfMeasure.DAY, Activity.RateModel.FIXED, Decimal("400.00")),
            ("WATCH", "Watchman", Activity.UnitOfMeasure.DAY, Activity.RateModel.FIXED, Decimal("500.00")),
            ("DRYING", "Field Drying", Activity.UnitOfMeasure.TONNAGE, Activity.RateModel.PARAMETER, Decimal("600.00")),
            ("EXTRA", "Other Activities", Activity.UnitOfMeasure.FIXED, Activity.RateModel.MANUAL, Decimal("0.00")),
        ]
        for code, name, unit, model, rate in activities:
            Activity.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "unit_of_measure": unit,
                    "rate_model": model,
                    "default_rate": rate,
                    "fixed_amount": rate if model == Activity.RateModel.FIXED else Decimal("0.00"),
                },
            )

        today = timezone.localdate()
        start_date = today - timedelta(days=today.weekday())
        PayrollWeek.objects.get_or_create(
            start_date=start_date,
            end_date=start_date + timedelta(days=6),
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Generic starter data created successfully. No sites were seeded; add them from the Sites screen."
            )
        )
