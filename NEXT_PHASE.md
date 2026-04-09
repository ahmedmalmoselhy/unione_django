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

## Remaining Work

### Environment and Deployment Validation

- Run migrations against PostgreSQL target (unione_db) and validate all command paths.
- Enable and verify scheduler service in target environment.
- Verify archive directory lifecycle and retention settings under real load.

### Test and Quality Hardening

- Add broader tests for admin organization CRUD and analytics filters.
- Add integration tests for import validation edge cases and malformed files.
- Add production smoke-test checklist for webhook scheduler + cleanup command.

## Priority

1. PostgreSQL migration and smoke validation.
2. Scheduler service rollout validation.
3. Test coverage expansion for admin and import/export edge cases.
