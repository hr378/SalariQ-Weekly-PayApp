from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update a default admin account for SalariQ."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")
        parser.add_argument("--email", default="admin@salariq.local")
        parser.add_argument("--password", default="SalariQ2026!")

    def handle(self, *args, **options):
        user_model = get_user_model()
        username = options["username"]
        email = options["email"]
        password = options["password"]

        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_staff": True,
                "is_superuser": True,
            },
        )

        changed = False
        if user.email != email:
            user.email = email
            changed = True
        if not user.is_staff:
            user.is_staff = True
            changed = True
        if not user.is_superuser:
            user.is_superuser = True
            changed = True

        user.set_password(password)
        changed = True

        if created or changed:
            user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created default admin user '{username}'"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated default admin user '{username}'"))
