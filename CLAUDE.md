# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Full-stack financial and inventory management system for Mexican businesses (SAT compliance). Backend is Python/Flask; mobile client is Flutter/Dart. Core domain: CFDI electronic invoicing, multi-company accounting, inventory, and SAT (tax authority) integration.

## Commands

### Backend (Python/Flask)

```bash
# Activate virtual environment (Windows)
.venv\Scripts\activate

# Run development server
flask run

# Run tests
pytest
pytest tests/test_specific.py          # single test file
pytest -k "test_name"                  # single test by name
pytest --cov=. --cov-report=html       # with coverage

# Database migrations
flask db migrate -m "description"      # generate migration
flask db upgrade                       # apply migrations
flask db downgrade                     # revert last migration

# Production
gunicorn --bind 0.0.0.0:8000 wsgi:app
```

### Mobile (Flutter)

```bash
cd android-app/medica_app
flutter pub get
flutter run
flutter test
flutter build apk
```

## Architecture

### Backend Structure

- **`app.py`** — Flask application factory (`create_app()`)
- **`config.py`** — Config class; reads from `.env`
- **`extensions.py`** — Flask extensions initialized here (db, login_manager, mail, cache, etc.)
- **`models.py`** — All SQLAlchemy ORM models in one file
- **`forms.py`** — WTForms definitions
- **`routes/`** — Blueprint modules:
  - `api.py` — AJAX/JSON API (session auth, CSRF protected)
  - `mobile_api.py` — REST API for Flutter app (JWT Bearer tokens)
  - `companies.py`, `taxes.py`, and others — web UI routes
- **`services/`** — Business logic layer:
  - `sat_service.py` — CFDI operations, SAT downloads/verification
  - `cfdi_generator.py` — Invoice XML generation via `satcfdi` library
  - `facturacion_service.py` — Invoicing orchestration
  - `barcode_service.py` — External barcode lookup API
  - `qr_service.py` — QR code generation
  - `catalogs_service.py` — Product catalog management
- **`utils/timezone_helper.py`** — Mexico City timezone enforcement (use this for all datetime operations)
- **`migrations/versions/`** — Alembic migration scripts; always generate via `flask db migrate`
- **`scripts/`** — One-off maintenance scripts (see `scripts/README.md`)

### Authentication

Two parallel auth systems:
- **Web:** Flask-Login session cookies + CSRF (Flask-WTF)
- **Mobile:** JWT Bearer tokens (`PyJWT`), 72-hour expiration (configurable via `JWT_EXPIRATION_HOURS`)

### Key Domain Concepts

- **RFC** — Mexican business/personal tax ID (validated throughout)
- **CFDI** — Mexican electronic invoice format; generated via `satcfdi` library
- **Finkok** — PAC (third-party certifier) used to stamp/sign CFDIs; credentials encrypted with `FERNET_KEY`
- **SAT** — Mexican tax authority; the app downloads and verifies invoices from SAT APIs
- **Multi-company** — Users access multiple companies via `UserCompanyAccess` join table

### Database

- Default: SQLite at `instance/sat_app.db`
- Configurable via `DATABASE_URL` env var (PostgreSQL for production)
- All models in `models.py`; migrate with Flask-Migrate/Alembic

### Environment Variables

Critical vars (see `.env.example`):

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session signing |
| `FERNET_KEY` | Encrypts Finkok PAC credentials in DB |
| `JWT_SECRET_KEY` | Signs mobile JWT tokens |
| `DATABASE_URL` | SQLAlchemy DB URI |
| `TIMEZONE` | Should be `America/Mexico_City` |
| `FERNET_KEY` | Must be a valid Fernet key (use `cryptography.fernet.Fernet.generate_key()`) |

### Mobile App

Located at `android-app/medica_app/`. Connects to Flask backend via `/api/mobile/` endpoints. State management with `provider`. Uses `mobile_scanner` for barcode scanning and `audioplayers` for scan feedback.

### Deployment

- Production entry point: `wsgi.py` (PythonAnywhere-compatible)
- Logging: rotating file handlers configured in `logging_config.py`
- Caching: Flask-Caching applied to company stats endpoints
