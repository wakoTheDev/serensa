# Sensa - Value Based Shop Computation System

Sensa is a Django web application for value-based shop operations.
It supports role-based access for Admin and Vendor users, captures daily shop values (not product inventory), computes profit/loss, and generates ledger plus graphical reports.

## Core Features

- Single authentication flow for Admin and Vendor users.
- Automatic role-based redirect after login:
	- Admin -> Admin dashboard
	- Vendor -> Vendor dashboard
- Shop management:
	- Create, update, delete shops.
- Value-entry management per shop:
	- Opening stock
	- Stock added
	- Expenses
	- Debts (credit sales value)
	- Closing stock
	- Cash received
- Vendor permissions:
	- Can feed data only for assigned shop(s).
	- Can update records only for the same day.
	- Sees immediate latest record on vendor dashboard.
- Admin permissions:
	- Access all shops and reports.
	- Add users/vendors, assign vendors to one or multiple shops, remove (deactivate) vendors.
- Reports:
	- Daily, weekly, monthly filters.
	- Ledger table view.
	- Responsive chart view (Chart.js), mobile friendly.
	- Export to Excel and PDF.
- Jenga API integration point:
	- Fetch Equity account balance and save snapshots.
	- Includes mock fallback via env vars for local development.

## Profit/Loss Computation

Per entry:

- Stock available = opening stock + stock added
- Stock consumed = stock available - closing stock
- Total sales value = cash received + debts
- Profit/Loss = total sales value - stock consumed - expenses

## Tech Stack

- Django 5
- SQLite (default, local fallback)
- MongoDB Atlas (optional free tier)
- Chart.js (CDN)
- Vanilla CSS with responsive layout

## Setup

1. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

2. Apply migrations:

```bash
python manage.py migrate
```

### Use MongoDB Atlas Free Tier (Optional)

This project now supports MongoDB through environment variables.

1. Create a free MongoDB Atlas cluster:

- Sign in to Atlas and create an M0 free cluster.
- Create a database user (username/password).
- In Network Access, allow your IP (or use 0.0.0.0/0 during development only).
- Copy your connection string from Atlas.

2. Set database environment variables:

```bash
export DB_ENGINE=django_mongodb_backend
export MONGODB_NAME=serensa
export MONGODB_URI='mongodb+srv://<username>:<password>@<cluster-host>/?retryWrites=true&w=majority'
```

3. Install dependencies and migrate:

```bash
python -m pip install -r requirements.txt
python manage.py migrate
```

For a fresh production MongoDB database, this migration step is required before using `/setup-admin/`.
The app now uses a custom Django user model so auth and profile relations stay compatible with MongoDB `ObjectId` primary keys.

4. Create admin account and run:

```bash
python manage.py createsuperuser
python manage.py runserver
```

### Move Existing SQLite Data To MongoDB

If you already have data in SQLite and want to move it:

1. With SQLite active (DB_ENGINE not set), export data:

```bash
python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission --indent 2 > data.json
```

2. Switch to MongoDB env vars (as above), migrate schema, then import:

```bash
python manage.py migrate
python manage.py loaddata data.json
```

3. Verify by logging in and checking shops, users, and reports.

3. Create an admin/superuser:

```bash
python manage.py createsuperuser
```

4. Run server:

```bash
python manage.py runserver
```

5. Open browser at:

```text
http://127.0.0.1:8000/accounts/login/
```

## Jenga API Environment Variables

Configure these for live balance fetch:

- `JENGA_BALANCE_ENDPOINT`
- `JENGA_API_TOKEN` (optional if using static bearer token)
- `EQUITY_ACCOUNT_REF`

For OAuth token flow:

- `JENGA_AUTH_ENDPOINT`
- `JENGA_CLIENT_ID`
- `JENGA_CLIENT_SECRET`

Optional advanced settings:

- `JENGA_GRANT_TYPE` (default: `client_credentials`)
- `JENGA_SCOPE`
- `JENGA_API_KEY` (sent as `X-API-Key`)
- `JENGA_BALANCE_HTTP_METHOD` (`GET` or `POST`, default `POST`)
- `JENGA_BALANCE_FIELD_PATH` (dot-path to balance in JSON, default `balance`)
- `JENGA_PROVIDER_NAME` (default `Jenga`)

Optional for local mock mode:

- `JENGA_MOCK_BALANCE` (default: `0.00`)

If live endpoint/token are missing, the app uses mock response mode.

## Key Routes

- `/setup-admin/` first-time admin account setup (phone + numeric password)
- `/accounts/login/` login
- `/admin-dashboard/` admin home
- `/vendor-dashboard/` vendor home
- `/entries/new/` create/update daily value entry
- `/shops/` manage shops
- `/users/` manage users/vendors and assignments
- `/reports/` ledger + chart reports
- `/reports/export/excel/` export filtered report to Excel
- `/reports/export/pdf/` export filtered report to PDF

## Notes

- The project uses a custom Django auth user model with an attached `UserProfile` model for role and shop assignments.
- Vendor removal is implemented as deactivation (`is_active=False`) to preserve historical records.
- Admin authentication supports phone number login.
- Session timeout is configured to auto-logout admin/vendor users after 2 hours of inactivity.

## CI/CD To Vercel (Auto Deploy On Main)

This repository now includes GitHub Actions CI/CD for Vercel:

- Workflow file: `.github/workflows/vercel-deploy.yml`
- Trigger: push to `main` branch (and manual `workflow_dispatch`)
- Deployment target: Vercel Production
- The workflow now pulls Vercel production environment variables, runs `python manage.py migrate --noinput`, then deploys.

### Required GitHub Repository Secrets

Add these secrets in GitHub -> Settings -> Secrets and variables -> Actions:

- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

### Required Vercel Project Environment Variables

Set these in Vercel Project Settings -> Environment Variables:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=0`
- `DJANGO_ALLOWED_HOSTS=.vercel.app,<your-custom-domain>`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-app>.vercel.app,https://<your-custom-domain>`

If using MongoDB in production, also set:

- `DB_ENGINE=django_mongodb_backend`
- `MONGODB_NAME=serensa`
- `MONGODB_URI=<your-atlas-connection-string>`

Then run the migrations once against that same Atlas database before opening the live site:

```bash
export DB_ENGINE=django_mongodb_backend
export MONGODB_NAME=serensa
export MONGODB_URI='<your-atlas-connection-string>'
python manage.py migrate
```

If the database is still empty, no data migration is needed.

And any app-level variables you use (for example Jenga credentials).

### Vercel Runtime Files Added

- `vercel.json` for Python runtime routing
- `api/index.py` as WSGI serverless entrypoint
- `.vercelignore` to keep deployment package clean

After these secrets are configured, any commit pushed to `main` automatically runs migrations against the production database and then deploys to Vercel.