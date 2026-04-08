# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

UniOne is an academic management system built with Django REST Framework. It supports student enrollment, professor grading/attendance, and admin operations across a multi-tier organization structure (university -> faculty -> department).

## Architecture

### App Structure

- **accounts**: User roles, permissions, custom AccessToken model for multi-token sessions, AccountProfile
- **organization**: University, Faculty, Department models
- **academics**: AcademicTerm, Course, Section, Grade, Attendance, Announcements, Notifications, Webhooks
- **enrollment**: ProfessorProfile, StudentProfile, CourseEnrollment, waitlist, ratings

### Authentication

Custom `AccessTokenAuthentication` backend (`accounts/authentication.py`) implements multi-token sessions. Tokens are stored in `AccessToken` model with `token_key`, `revoked_at`, and `last_used_at` fields. DRF's default `TokenAuthentication` is kept as fallback.

### API Organization

URL structure in `config/urls.py`:
- `/api/auth/*` → accounts.urls
- `/api/student/*` → enrollment.urls
- `/api/professor/*` → enrollment.professor_urls
- `/api/admin/*` → enrollment.admin_urls
- `/api/*` → enrollment.shared_urls (announcements, notifications)
- `/api/organization/*` → organization.urls
- `/api/schema/` and `/api/docs/` → drf-spectacular OpenAPI docs

### Response Convention

All API responses follow this envelope format:
```json
{
  "status": "success",
  "message": "Operation completed",
  "data": {}
}
```

## Common Commands

### Development Server

```bash
# Windows
.venv\Scripts\activate
python manage.py runserver

# Or set environment for SQLite override
$env:DB_ENGINE="django.db.backends.sqlite3"
$env:DB_NAME="db.sqlite3"
python manage.py runserver
```

### Database

```bash
python manage.py migrate
python manage.py makemigrations
python manage.py showmigrations
```

Environment-based DB selection: Set `DB_ENGINE` to `django.db.backends.sqlite3` for local testing, or use PostgreSQL defaults (reads from `.env` file).

### Seeding Data

```bash
# Phase 1: Create roles and optional admin user
python manage.py seed_phase1 --create-admin --admin-username admin --admin-password Admin1234!@#

# Phase 2: Create demo users, faculties, departments, courses, sections, enrollments
python manage.py seed_phase2_baseline --password Pass1234!@#
```

Demo credentials after seed_phase2_baseline:
- professor1 / Pass1234!@#
- professor2 / Pass1234!@#
- student1 / Pass1234!@#
- student2 / Pass1234!@#

### Testing

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test accounts
python manage.py test enrollment

# Run with pytest
pytest

# Run single test class
python manage.py test accounts.tests.AuthEndpointsTests
```

### Webhook Processing

```bash
# Dispatch a webhook event manually
python manage.py dispatch_webhook_event enrollment.created --payload '{"enrollment_id": 1}'

# Process pending webhook deliveries (one-time)
python manage.py process_webhook_deliveries --limit 100

# Run webhook scheduler loop (runs continuously)
python manage.py run_webhook_scheduler --interval-seconds 60 --limit 100
python manage.py run_webhook_scheduler --run-once  # single cycle
```

Webhook settings (configurable via env or settings.py):
- `WEBHOOK_WORKER_INTERVAL_SECONDS` (default: 60)
- `WEBHOOK_DELIVERY_BATCH_LIMIT` (default: 100)
- `WEBHOOK_DELIVERY_TIMEOUT_SECONDS` (default: 10)
- `WEBHOOK_DELIVERY_MAX_ATTEMPTS` (default: 5)
- `WEBHOOK_DELIVERY_RETRY_BASE_SECONDS` (default: 60)

### Code Quality

```bash
# Formatting
black .

# Linting
ruff check .
```

## Key Implementation Patterns

### RBAC and Scoped Access

Roles are checked via `Role` and `UserRole` models. Scoped access uses `scope` (university/faculty/department) and `scope_id` fields. See `accounts/models.py` for the `UserRole.Scope` choices.

### Throttling

Scoped throttling is configured in `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`:
- `api_login`: 60/min
- `api_password`: 60/min
- `api_enroll`: 20/min
- `api_grade`: 30/min

### Webhook Delivery Flow

1. Domain events call `enqueue_webhook_deliveries(event_name, payload)` from `academics/webhook_delivery.py`
2. Deliveries are created with `PENDING` status
3. `process_pending_deliveries()` polls for pending/retry deliveries and executes HTTP requests
4. Failed deliveries use exponential backoff for retries
5. Signature headers computed with HMAC-SHA256 when webhook has a secret

### Testing Patterns

Tests use Django's `APITestCase` with `rest_framework.test.APITestCase`. Authentication in tests:
```python
self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
```

### Enrollment and Waitlist Logic

The `enrollment/services.py` module contains business logic for:
- Enrolling with capacity checks
- Automatic waitlist placement when section is full
- Waitlist promotion when enrolled students drop
- Position management for waitlist entries

## Configuration

Environment variables (see `.env.example`):
- `DB_ENGINE`: Database backend (defaults to PostgreSQL)
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`

Switch to SQLite for local development:
```bash
$env:DB_ENGINE="django.db.backends.sqlite3"
$env:DB_NAME="db.sqlite3"
```
