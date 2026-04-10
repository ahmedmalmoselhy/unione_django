# UniOne Django - Current Status

Last Updated: April 6, 2026
Project Phase: Phase 3 API Completion
Overall Status: ACTIVE DEVELOPMENT

## Status Maintenance Rule

- Update this file after each completed milestone.
- Keep checklist values factual and code-backed.
- Always update: Project Phase, Overall Status, Completed Work, Next Immediate Steps.

## Completion Summary

### Documentation

- Completed: Django-remapped documentation set created in this repository.
- Source baseline: unione_node top-level documentation set.

### Backend Setup

- Completed: Django project initialized (config project + manage.py).
- Completed: Environment-based settings prepared (.env, .env.example, PostgreSQL config).
- Completed: API bootstrap routes added (/api, /health).
- Completed: modular apps created (accounts, organization, academics, enrollment).
- Completed: base auth endpoints scaffolded (/api/auth/login, /api/auth/logout, /api/auth/me).
- Completed: auth password flows implemented (/api/auth/forgot-password, /api/auth/reset-password, /api/auth/change-password).
- Completed: OpenAPI schema and docs routes wired (/api/schema, /api/docs).
- Completed: initial model migrations generated.
- Completed: local migration validation via SQLite override.
- Completed: role seeding/admin bootstrap command implemented and validated (seed_phase1).
- Completed: organization read endpoints implemented with scoped access filtering (/api/organization/university, /api/organization/faculties, /api/organization/departments).
- Completed: Phase 1 API tests expanded (accounts + organization) and passing.
- Completed: Phase 2 student read endpoints implemented (/api/student/profile, /api/student/enrollments, /api/student/grades).
- Completed: Phase 2 section and term read endpoints implemented (/api/student/sections, /api/student/academic-terms).
- Completed: Grade model added for academic results storage.
- Completed: Phase 2 student API tests added and passing.
- Completed: student transcript and academic history endpoints implemented (/api/student/transcript, /api/student/academic-history).
- Completed: student schedule endpoints implemented (/api/student/schedule, /api/student/schedule/ics).
- Completed: student transcript PDF export endpoint implemented (/api/student/transcript/pdf).
- Completed: professor profile and sections read endpoints implemented (/api/professor/profile, /api/professor/sections).
- Completed: professor schedule and section students read endpoints implemented (/api/professor/schedule, /api/professor/sections/{section_id}/students).
- Completed: professor grading and attendance section endpoints implemented (/api/professor/sections/{section_id}/grades, /api/professor/sections/{section_id}/attendance).
- Completed: attendance session detail/update endpoints and section announcements endpoints implemented (/api/professor/sections/{section_id}/attendance/{session_id}, /api/professor/sections/{section_id}/announcements).
- Completed: shared announcements and notifications endpoints implemented (/api/announcements, /api/notifications).
- Completed: admin webhook CRUD and delivery listing endpoints implemented (/api/admin/webhooks, /api/admin/webhooks/{id}/deliveries).
- Completed: remaining student attendance/waitlist/ratings endpoints implemented (/api/student/attendance, /api/student/waitlist, /api/student/ratings).
- Completed: auth profile update endpoint implemented (/api/auth/profile PATCH).
- Completed: student enrollment write endpoints implemented (/api/student/enrollments POST, /api/student/enrollments/{id} DELETE).
- Completed: waitlist-aware enrollment flow implemented (auto-waitlist on full sections + promotion on drop).
- Completed: phase 2 baseline fixtures seed command implemented (seed_phase2_baseline).
- Completed: targeted API tests for auth profile update and enrollment write/waitlist promotion flows added and passing (SQLite).
- Completed: seed fixtures extended for additional faculties/departments/courses and multi-term enrollment scenarios.
- Completed: webhook delivery execution pipeline implemented with queue + processing management commands (dispatch_webhook_event, process_webhook_deliveries).
- Completed: automated webhook tests added for queue filtering and success/retry/failure delivery behavior.
- Completed: enrollment, attendance, and section announcement domain events now enqueue webhook deliveries.
- Completed: periodic webhook scheduler command implemented (run_webhook_scheduler) with settings-based runtime controls.
- Completed: auth token management endpoints implemented (/api/auth/tokens GET/DELETE, /api/auth/tokens/{id} DELETE).
- Completed: multi-token session parity implemented with custom access-token model and authentication backend.
- Completed: student section announcements endpoint parity implemented (/api/student/sections/{section_id}/announcements).
- Completed: admin webhook access parity improved (faculty_admin/department_admin roles + owner-scoped access).
- Completed: scoped API throttling parity implemented for login/password/enrollment/grade write flows.
- Completed: shared announcements/notifications response behavior aligned with paginated meta payloads and unread alias support.
- Completed: global announcements visibility/read parity implemented (university/faculty/department/section targeting with publish/expiry filtering).
- Completed: admin import/export endpoints implemented (/api/admin/import/users, /api/admin/import/courses, /api/admin/export/enrollments, /api/admin/export/grades).
- Completed: periodic cleanup command for old webhook deliveries implemented (cleanup_webhook_deliveries).
- Completed: deployment process templates added for webhook scheduler (systemd + supervisor + docker-compose scheduler service).
- Completed: automatic model-level audit trail signals added for enrollment/grade/attendance/organization/role assignment entities.
- Completed: admin management/analytics/audit API test coverage added and passing.
- Completed: GitHub Actions Django workflow updated to run system checks and full app test suite.
- Completed: GitHub Actions coverage artifacts and fail-under gate enabled (coverage.xml + threshold).
- Pending: migration execution against PostgreSQL target (unione_db) when connectivity is available.

### Frontend Planning

- Completed: integration assumptions documented for Django API.
- Pending: client scaffold and role-based UI implementation.

## Phase 1 Checklist

- [x] Django-mapped documentation created
- [x] Django project initialized
- [x] requirements files finalized
- [x] PostgreSQL settings configured
- [x] health endpoint available
- [x] auth base endpoints scaffolded
- [x] organization read endpoints scaffolded with scope-aware filtering
- [x] role seeding command available
- [x] auth password flows implemented
- [x] student read endpoints implemented
- [x] section and term read endpoints implemented

## Additional Completed in Phase 1

- [x] Core domain models scaffolded for organization, academics, enrollment, and RBAC foundations
- [x] API schema/docs endpoints configured
- [x] Initial auth and organization endpoint tests added and passing (SQLite)
- [x] Student read API tests added and passing (SQLite)
- [x] Student section/term API tests added and passing (SQLite)

## Next Immediate Steps

1. Run migrations against PostgreSQL target once local DB connectivity is confirmed.
2. Add deployment/runbook notes for enabling scheduler service in staging/production.
3. Validate archival retention behavior in production-like workload.
4. Validate PostgreSQL-specific CI path when DB service is introduced.
