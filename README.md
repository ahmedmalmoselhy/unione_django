# UniOne Platform - Django Implementation

A complete academic management system implemented with a Django backend and a separate frontend client, reusing the same PostgreSQL domain model as the existing UniOne platforms.

## Project Overview

UniOne supports:

- Student portal: enrollment, grades, transcripts, attendance
- Professor portal: grading, attendance sessions, section announcements
- Admin portal: organization management, analytics, webhooks, audit logs
- Multi-tier organization: university -> faculty -> department
- 6 roles: admin, faculty_admin, department_admin, professor, student, employee

## Technology Stack

- Backend: Django 5 + Django REST Framework
- Database: PostgreSQL (unione_db)
- Auth: DRF token auth with custom multi-token session support
- Background jobs: webhook scheduler commands implemented; Celery/Redis optional extension
- Testing: pytest + pytest-django

## Documentation

Start here:

1. QUICK_REFERENCE.md
2. DOCUMENTATION_INDEX.md

Detailed references:

- PROJECT_OVERVIEW.md
- IMPLEMENTATION_PLAN.md
- API_ENDPOINTS.md
- DATABASE_SCHEMA.md
- FEATURES_REFERENCE.md
- DEPENDENCIES_SETUP.md
- CURRENT_STATUS.md

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 12+

### Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Server: <http://127.0.0.1:8000>

## Delivery Snapshot

- Core backend modules are implemented (accounts, organization, academics, enrollment)
- API scope is at backend parity for the UniOne domain baseline
- Remaining effort focuses on operational hardening, extended test depth, and optional integrations

## Status

See CURRENT_STATUS.md for live implementation progress.
