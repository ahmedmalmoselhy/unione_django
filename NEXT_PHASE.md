# Next Phase - Hardening and Production Validation

Last Updated: April 9, 2026
Phase: Phase 8 (Hardening)

## Summary

Phase 7 admin scope is now implemented in code, including organization CRUD, analytics endpoints, audit endpoints, import/export flows, webhook cleanup command, and scheduler deployment templates.

## Completed in This Milestone

- Admin user CRUD endpoints.
- Admin organization CRUD endpoints (faculties, departments, courses, sections, academic terms).
- Admin analytics endpoints (enrollment, grades, attendance, webhooks, students, professors).
- Admin audit log query/detail endpoints.
- Admin import/export endpoints:
  - POST /api/admin/import/users
  - POST /api/admin/import/courses
  - GET /api/admin/export/enrollments
  - GET /api/admin/export/grades
- Webhook cleanup command: cleanup_webhook_deliveries.
- Scheduler deployment templates:
  - deployment/run_webhook_scheduler.service
  - deployment/run_webhook_scheduler.supervisor.conf
  - deployment/docker-compose.scheduler.yml
- Automatic model-level audit trail via signals for key entities.
- Admin management/analytics/audit API tests added.
- GitHub Actions workflow updated to run Django system checks and app-level tests.
- Comprehensive enrollment tests added for services and key student/professor/admin branches.
- CI coverage fail-under threshold increased to 70.
- Comprehensive admin analytics/import-export/webhook validation tests added.
- Organization-admin comprehensive CRUD/filter/scope coverage added.
- App-code coverage baseline increased to 86% (tests/migrations omitted).
- Shared endpoints, admin views, audit log views, and webhook delivery engine now have comprehensive branch coverage.
- App-code coverage baseline increased further to 92% (tests/migrations omitted).

## Remaining Work

### Environment and Deployment Validation

- Run migrations against PostgreSQL target (unione_db) and validate all command paths.
- Enable and verify scheduler service in target environment.
- Verify archive directory lifecycle and retention settings under real load.

### Test and Quality Hardening

- Add integration tests for malformed CSV file uploads and large-file import behavior.
- Add production smoke-test checklist for webhook scheduler + cleanup command.
- Expand deep branch coverage in the largest remaining modules (`enrollment/views.py`, `enrollment/organization_admin_views.py`).

## Priority

1. PostgreSQL migration and smoke validation.
2. Scheduler service rollout validation.
3. Deep branch coverage expansion in enrollment/views and organization_admin_views.
