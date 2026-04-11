# UniOne Django - QWEN.md

## Project Overview

UniOne is a comprehensive academic management system implemented with Django 5 and Django REST Framework. It provides role-based APIs for managing university operations including student enrollment, grading, attendance, announcements, and administrative functions.

### Key Features

- **Multi-tier organization structure**: University -> Faculty -> Department
- **6 user roles**: admin, faculty_admin, department_admin, professor, student, employee
- **Role-based portals**: Student, Professor, and Admin portals with scoped access
- **Full academic lifecycle**: Enrollment, grades, transcripts, attendance, scheduling
- **Webhook system**: Event-driven integrations with delivery queue, retries, and archival
- **Audit trail**: Automatic model-level audit signals for critical entities
- **Import/Export**: Bulk data operations for users, courses, enrollments, and grades

### Current Status

- **Phase**: Phase 3 API Completion
- **Coverage**: 92% app-code coverage (tests/migrations excluded)
- **Database**: PostgreSQL (with SQLite fallback for testing)
- **API Endpoints**: 50+ endpoints implemented

---

## Directory Structure

```bash
unione_django/
├── config/                 # Django project settings, URLs, WSGI/ASGI
│   ├── settings.py         # Main settings (env-based config)
│   ├── urls.py             # Root URL configuration
│   ├── wsgi.py
│   └── asgi.py
├── accounts/               # Authentication, users, tokens, profiles
├── organization/           # University, faculty, department models & APIs
├── academics/              # Courses, sections, terms, grading models
├── enrollment/             # Enrollment, waitlist, student/professor APIs
│   ├── urls.py             # Student API routes
│   ├── professor_urls.py   # Professor API routes
│   ├── shared_urls.py      # Shared API routes
│   └── admin_urls.py       # Admin API routes
├── deployment/             # Systemd, supervisor, docker-compose for scheduler
├── .github/workflows/      # CI/CD pipeline (Django tests + coverage)
├── requirements.txt        # Runtime dependencies
├── requirements-dev.txt    # Development dependencies
├── manage.py               # Django management script
└── db.sqlite3              # Local SQLite database (dev/testing)
```

### App Responsibilities

| App | Purpose |
| ----- | --------- |
| `accounts` | User model, authentication, token management, password flows, profile management |
| `organization` | University, faculty, department models with scoped access control |
| `academics` | Course, section, academic term, grade, attendance session/record models |
| `enrollment` | Enrollment lifecycle, waitlist management, student/professor/admin/shared API views |

---

## Technology Stack

### Core

- **Django**: 5.0+
- **Django REST Framework**: Primary API framework
- **django-filter**: Query filtering
- **drf-spectacular**: OpenAPI schema generation
- **psycopg[binary]**: PostgreSQL adapter

### Development & Testing

- **pytest** + **pytest-django**: Testing framework
- **factory-boy**: Test fixture generation
- **coverage**: Code coverage reporting (threshold: 70%)
- **ruff**: Fast linter
- **black**: Code formatter

### Planned/Optional

- **Celery** + **Redis**: Background job processing (webhooks, scheduled tasks)

### Database

- **Primary**: PostgreSQL (unione_db)
- **Testing/Dev**: SQLite (db.sqlite3) via `DB_ENGINE=django.db.backends.sqlite3`

---

## Building and Running

### Prerequisites

- Python 3.11+
- PostgreSQL 12+ (optional, SQLite works for dev)

### Initial Setup

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements-dev.txt

# Configure environment
# Edit .env with your settings (DB credentials, webhook settings, etc.)

# Run migrations
python manage.py migrate

# Seed initial data (roles, baseline fixtures)
python manage.py seed_phase1
python manage.py seed_phase2_baseline

# Start development server
python manage.py runserver
```

Server will be available at: <http://127.0.0.1:8000>

- API root: <http://127.0.0.1:8000/api/>
- API docs (Swagger): <http://127.0.0.1:8000/api/docs/>
- OpenAPI schema: <http://127.0.0.1:8000/api/schema/>
- Django admin: <http://127.0.0.1:8000/admin/>
- Health check: <http://127.0.0.1:8000/health>

### Running Tests

```bash
# Run all tests
python manage.py test accounts organization enrollment academics -v 2

# Run with pytest
pytest

# Run with coverage
coverage run manage.py test accounts organization enrollment academics -v 2
coverage report --omit="*/migrations/*,*/tests*.py,manage.py" --fail-under=70
```

### Code Quality

```bash
# Lint with ruff
ruff check .

# Format with black
black .
```

### Management Commands

```bash
# Database
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations
python manage.py dbshell

# Seed data
python manage.py seed_phase1          # Roles and admin bootstrap
python manage.py seed_phase2_baseline # Courses, sections, terms, enrollments

# Webhook scheduler (requires Celery/Redis or standalone)
python manage.py dispatch_webhook_event   # Manual event dispatch
python manage.py process_webhook_deliveries  # Process pending deliveries
python manage.py run_webhook_scheduler       # Continuous scheduler loop
python manage.py cleanup_webhook_deliveries  # Archive old deliveries

# Shell
python manage.py shell
```

---

## API Architecture

### URL Routing Structure

The API uses a modular URL routing strategy with separate URL configs per role:

```bash
config/urls.py (root)
├── /api/                         -> Root welcome + health
├── /api/auth/                    -> accounts.urls (login, logout, profile, tokens, password)
├── /api/organization/            -> organization.urls (universities, faculties, departments)
├── /api/student/                 -> enrollment.urls (student profile, enrollments, grades, schedule)
├── /api/professor/               -> enrollment.professor_urls (professor profile, sections, grading)
├── /api/admin/                   -> enrollment.admin_urls (webhooks, CRUD, analytics, audit)
├── /api/                         -> enrollment.shared_urls (announcements, notifications)
├── /api/schema/                  -> OpenAPI schema
└── /api/docs/                    -> Swagger UI
```

### Response Format Convention

All API responses follow this JSON structure:

```json
{
  "status": "success",
  "message": "Operation completed",
  "data": { ... }
}
```

### Authentication

- Custom `AccessTokenAuthentication` backend (multi-token session parity)
- DRF `TokenAuthentication` as fallback
- `SessionAuthentication` for admin/browsable API
- Scoped throttling for login (60/min), password (60/min), enrollment (20/min), grade (30/min)

### Email Side Effects

Certain API actions trigger outbound emails:

- `POST /api/professor/sections/{section_id}/announcements` → Announcement emails to enrolled students
- `POST /api/admin/sections/{section_id}/exam-schedule/publish` → Exam schedule emails
- `POST /api/professor/sections/{section_id}/grades` (status=complete) → Final grade publication emails

---

## Database & Models

### Core Domain Models

**accounts**: Custom user model, roles, role assignments, access tokens

**organization**: University, Faculty, Department (with hierarchical relationships)

**academics**:

- Course, DepartmentCourse, CoursePrerequisites
- AcademicTerm, Section
- Grade, StudentTermGPA
- AttendanceSession, AttendanceRecord
- CourseRating

**enrollment**:

- Enrollment, EnrollmentWaitlist
- Student, Professor, Employee profiles
- Announcement, SectionAnnouncement, AnnouncementRead
- Notification

**integrations**: Webhook, WebhookDelivery

**audit**: AuditLog (automatic signals on enrollment/grade/attendance/org/role changes)

### Database Configuration

Environment-driven via `.env`:

```bash
DB_ENGINE=django.db.backends.postgresql  # or django.db.backends.sqlite3
DB_NAME=unione_db
DB_USER=unione
DB_PASSWORD=<password>
DB_HOST=127.0.0.1
DB_PORT=5432
```

---

## Webhook System

The webhook system provides event-driven integration capabilities:

### Components

- **Webhook model**: Subscription configuration (URL, events, filters)
- **WebhookDelivery model**: Delivery tracking with attempts, status, response data
- **Queue**: Deliveries queued on domain events (enrollment, attendance, announcements)
- **Scheduler**: `run_webhook_scheduler` command processes pending deliveries in batches
- **Retry logic**: Exponential backoff with configurable max attempts (default: 5)
- **Archival**: Old deliveries archived after configurable retention period (default: 30 days)

### Deployment Options

- systemd service: `deployment/run_webhook_scheduler.service`
- supervisor config: `deployment/run_webhook_scheduler.supervisor.conf`
- Docker Compose: `deployment/docker-compose.scheduler.yml`

---

## Testing Conventions

- Tests co-located within each app (`tests.py`, `test_*.py`)
- SQLite used in CI for speed (no PostgreSQL dependency)
- Coverage threshold enforced at 70% (current: 92%)
- Factory-boy for test data generation
- Comprehensive coverage of:
  - Auth flows (login, password, profile, tokens)
  - Organization scoped access control
  - Enrollment lifecycle and waitlist promotion
  - Professor grading and attendance
  - Admin webhook delivery behavior
  - Analytics and audit log endpoints
  - Import/export functionality

### CI Pipeline (GitHub Actions)

- Triggers: push/PR to `master`, manual dispatch
- Python 3.12 on Ubuntu
- Steps: checkout → install deps → system check → tests → coverage report → upload artifacts
- Coverage artifacts: `coverage.xml`, `.coverage`

---

## Development Conventions

### Code Style

- **Formatting**: Black (enforce consistent formatting)
- **Linting**: Ruff (fast Python linter)
- **Model fields**: Explicit `related_name` on ForeignKey
- **Enums**: TextChoices for status/enum fields
- **Constraints**: UniqueConstraint for unique pairs
- **JSON data**: JSONField for schedule/events/payload fields

### Indexing

- Unique indexes on: email, national_id, student_number, staff_number, course code
- Composite indexes on: (student_id, status), (section_id, student_id)
- Partial indexes for active records where applicable

### Migrations

- Django migration framework
- SQLite override for local dev/testing
- Migration order: org/auth → academics → enrollment → communication → integrations

### Soft Deletes

- Custom manager pattern where needed
- Not applied universally - only where business logic requires it

---

## Environment Variables

All configured in `.env` (see `.env.example` for template):

| Variable | Description | Default |
| ---------- | ------------- | --------- |
| `DEBUG` | Django debug mode | `True` |
| `SECRET_KEY` | Django secret key | (generate unique) |
| `ALLOWED_HOSTS` | Comma-separated hosts | `127.0.0.1,localhost` |
| `DB_ENGINE` | Database backend | `django.db.backends.postgresql` |
| `DB_NAME` | Database name | `unione_db` |
| `DB_USER` | Database user | `unione` |
| `DB_PASSWORD` | Database password | (set in .env) |
| `DB_HOST` | Database host | `127.0.0.1` |
| `DB_PORT` | Database port | `5432` |
| `WEBHOOK_WORKER_INTERVAL_SECONDS` | Scheduler loop interval | `60` |
| `WEBHOOK_DELIVERY_BATCH_LIMIT` | Deliveries per batch | `100` |
| `WEBHOOK_DELIVERY_TIMEOUT_SECONDS` | HTTP request timeout | `10` |
| `WEBHOOK_DELIVERY_MAX_ATTEMPTS` | Max retry attempts | `5` |
| `WEBHOOK_DELIVERY_RETRY_BASE_SECONDS` | Retry backoff base | `60` |
| `WEBHOOK_DELIVERY_ARCHIVE_AFTER_DAYS` | Archive threshold age | `30` |
| `WEBHOOK_DELIVERY_ARCHIVE_RETENTION_DAYS` | Archive retention period | `90` |
| `WEBHOOK_ARCHIVE_DIR` | Archive storage path | `var/webhook_archives` |

---

## Key Reference Documents

| Document | Purpose |
| ---------- | --------- |
| `README.md` | Entry point and setup guide |
| `QUICK_REFERENCE.md` | Commands, troubleshooting |
| `CURRENT_STATUS.md` | Live implementation progress |
| `API_ENDPOINTS.md` | Full REST API contract |
| `DATABASE_SCHEMA.md` | Schema reference and mapping notes |
| `IMPLEMENTATION_PLAN.md` | Technical roadmap |
| `PROJECT_OVERVIEW.md` | High-level architecture |
| `FEATURES_REFERENCE.md` | Feature matrix and capabilities |
| `DEPENDENCIES_SETUP.md` | Dependencies and setup guide |
| `DOCUMENTATION_INDEX.md` | Documentation navigation |

---

## Agent Guidelines

When working on this codebase:

1. **Always run tests** after making changes: `python manage.py test accounts organization enrollment academics -v 2`
2. **Check coverage** if modifying tested modules: `coverage run manage.py test ... && coverage report`
3. **Run linters** before committing: `ruff check . && black .`
4. **Use SQLite** for local dev unless PostgreSQL-specific features are needed
5. **Follow response format**: All API views return `{"status": "...", "message": "...", "data": {...}}`
6. **Respect role scoping**: Organization access is hierarchical (admin > faculty_admin > department_admin)
7. **Webhook events**: Enqueue webhook deliveries on enrollment, attendance, and announcement events
8. **Audit signals**: Model save/delete operations trigger automatic audit log entries
