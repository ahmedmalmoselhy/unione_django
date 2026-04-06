# UniOne Django API Endpoints (Planned)

Base path: /api

## Authentication

- POST /api/auth/login
- POST /api/auth/logout
- GET /api/auth/me
- POST /api/auth/forgot-password
- POST /api/auth/reset-password
- POST /api/auth/change-password
- PATCH /api/auth/profile
- GET /api/auth/tokens
- DELETE /api/auth/tokens
- DELETE /api/auth/tokens/{token_id}

## Student

- GET /api/student/profile
- GET /api/student/enrollments
- POST /api/student/enrollments
- DELETE /api/student/enrollments/{id}
- GET /api/student/grades
- GET /api/student/academic-terms
- GET /api/student/sections
- GET /api/student/transcript
- GET /api/student/transcript/pdf
- GET /api/student/academic-history
- GET /api/student/schedule
- GET /api/student/schedule/ics
- GET /api/student/attendance
- GET /api/student/waitlist
- DELETE /api/student/waitlist/{section_id}
- GET /api/student/ratings
- POST /api/student/ratings
- GET /api/student/sections/{section_id}/announcements

## Professor

- GET /api/professor/profile
- GET /api/professor/sections
- GET /api/professor/schedule
- GET /api/professor/sections/{section_id}/students
- GET /api/professor/sections/{section_id}/grades
- POST /api/professor/sections/{section_id}/grades
- GET /api/professor/sections/{section_id}/attendance
- POST /api/professor/sections/{section_id}/attendance
- GET /api/professor/sections/{section_id}/attendance/{session_id}
- PUT /api/professor/sections/{section_id}/attendance/{session_id}
- GET /api/professor/sections/{section_id}/announcements
- POST /api/professor/sections/{section_id}/announcements
- DELETE /api/professor/sections/{section_id}/announcements/{id}

## Shared

- GET /api/announcements
- POST /api/announcements/{id}/read
- GET /api/notifications
- POST /api/notifications/read-all
- POST /api/notifications/{id}/read
- DELETE /api/notifications/{id}

## Admin

- GET /api/admin/webhooks
- POST /api/admin/webhooks
- PATCH /api/admin/webhooks/{id}
- DELETE /api/admin/webhooks/{id}
- GET /api/admin/webhooks/{id}/deliveries

## Response Convention

```json
{
  "status": "success",
  "message": "Operation completed",
  "data": {}
}
```
