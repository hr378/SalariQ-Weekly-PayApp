# SalariQ

Smart payroll. Happy people.

SalariQ is a Django payroll system for casual and weekly workers. It helps admins manage sites, workers, activities, weekly work records, payroll calculations, approvals, and payout batches from one place.

## What it does

- Add and manage your own site names
- Register workers and payment details
- Create activities and rate rules per site
- Capture weekly work records and worker allocations
- Calculate payroll totals and adjustments
- Review validation issues before approval
- Prepare MPESA-ready payout batches

## Tech stack

- Backend: Python + Django
- Database: PostgreSQL or SQLite for local setup
- Frontend: Django templates, HTML, CSS, JavaScript

## Quick start

1. Create a Python 3.12+ environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Copy the sample environment file:

```powershell
Copy-Item .env.example .env
```

4. Run migrations:

```powershell
python manage.py migrate
```

5. Seed starter data:

```powershell
python manage.py seed_salariq_starter
```

6. Create the default admin:

```powershell
python manage.py ensure_default_admin --username admin --email admin@salariq.local --password SalariQ2026!
```

7. Start the app:

```powershell
python manage.py runserver
```

Then open `http://127.0.0.1:8000/`.

## Environment

`SalariQ` uses PostgreSQL when `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` are set. Otherwise it falls back to SQLite for local use.

## Branding

- Product name: `SalariQ`
- Motto: `SMART PAYROLL. HAPPY PEOPLE.`

The color palette is documented in [SALARIQ-BRAND-KIT.md](C:\Users\admin\Documents\Codex\2026-04-21-files-mentioned-by-the-user-salariq\SALARIQ-BRAND-KIT.md).
