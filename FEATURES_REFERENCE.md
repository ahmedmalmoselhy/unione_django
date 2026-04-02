# UniOne Django Features Reference

## Core Scope

- Organizational hierarchy: university -> faculty -> department
- Role-based access with scoped permissions
- Student, professor, and admin portals
- Communication modules (announcements, notifications)
- Integrations (webhooks), audit logging, exports

## Role Matrix

- admin: system-wide
- faculty_admin: faculty scope
- department_admin: department scope
- professor: section teaching scope
- student: personal academic scope
- employee: operational support scope

## Key Modules

1. Authentication and profile
2. Student enrollment and grades
3. Professor grading and attendance
4. Academic terms, courses, sections
5. Announcements and notifications
6. Admin analytics and management
7. Webhooks and delivery tracking
8. Audit logs

## Data/Output Features

- Transcript JSON and PDF
- Schedule JSON and iCalendar export
- Rate-limited auth flows
- Soft delete strategy where required
