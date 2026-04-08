# Next Phase - Admin CRUD, Analytics, and Audit

Last Updated: April 6, 2026
Phase: Phase 7 (Admin Management)

## Summary

Core endpoints per API_ENDPOINTS.md are complete. This phase covers remaining admin functionality from Phase 7 of IMPLEMENTATION_PLAN.md: full CRUD operations for organization entities, analytics endpoints, audit log endpoints, and import/export flows.

## Missing from Phase 7

### Admin Organization Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/admin/users | GET | List users with role filters |
| /api/admin/users | POST | Create user with roles |
| /api/admin/users/{id} | GET | Get user details |
| /api/admin/users/{id} | PATCH | Update user roles/info |
| /api/admin/users/{id} | DELETE | Soft delete user |
| /api/admin/faculties | POST | Create faculty |
| /api/admin/faculties/{id} | PATCH | Update faculty |
| /api/admin/faculties/{id} | DELETE | Delete faculty |
| /api/admin/departments | POST | Create department |
| /api/admin/departments/{id} | PATCH | Update department |
| /api/admin/departments/{id} | DELETE | Delete department |
| /api/admin/courses | GET | List all courses |
| /api/admin/courses | POST | Create course |
| /api/admin/courses/{id} | PATCH | Update course |
| /api/admin/courses/{id} | DELETE | Delete course |
| /api/admin/sections | GET | List all sections |
| /api/admin/sections | POST | Create section |
| /api/admin/sections/{id} | PATCH | Update section |
| /api/admin/sections/{id} | DELETE | Delete section |
| /api/admin/academic-terms | GET | List terms |
| /api/admin/academic-terms | POST | Create term |
| /api/admin/academic-terms/{id} | PATCH | Update term |
| /api/admin/academic-terms/{id} | DELETE | Delete term |

### Analytics Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/admin/analytics/enrollment | GET | Enrollment statistics by faculty/department/term |
| /api/admin/analytics/grades | GET | Grade distribution reports |
| /api/admin/analytics/attendance | GET | Attendance summary reports |
| /api/admin/analytics/webhooks | GET | Webhook delivery metrics and recent failures |

### Audit Log Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/admin/audit-logs | GET | Query audit logs with filters |
| /api/admin/audit-logs/{id} | GET | Get specific audit entry |

### Import/Export

| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/admin/import/users | POST | Bulk import users from CSV/Excel |
| /api/admin/import/courses | POST | Bulk import courses |
| /api/admin/export/enrollments | GET | Export enrollment data |
| /api/admin/export/grades | GET | Export grade reports |

## Webhook Infrastructure Improvements

### Background Scheduler Deployment

The `run_webhook_scheduler` command exists but needs deployment configuration:
- systemd service file
- Supervisor config
- Docker container entrypoint for scheduler workers

### Delivery Cleanup Command

Create management command to archive/clean old webhook deliveries:
- Archive deliveries older than X days
- Purge archived records after Y days
- Configurable via settings

## Model Audit Trail

Add audit logging to models:
- Enrollment changes (status, drops)
- Grade updates
- Attendance modifications
- Organization structure changes
- User role assignments

## Implementation Priority

1. **High**: User CRUD endpoints (blocking for admin portal)
2. **High**: Organization CRUD (faculties, departments, courses, sections, terms)
3. **Medium**: Analytics endpoints (enrollment, grades)
4. **Medium**: Webhook metrics endpoint
5. **Low**: Import/Export flows
6. **Low**: Full audit log system

## Technical Notes

### Scoped Admin Access

Current admin endpoints use `HasAnyRole` with `['admin', 'faculty_admin', 'department_admin']`. For organization CRUD:
- `admin`: Full access to all entities
- `faculty_admin`: Access limited to their faculty and child departments
- `department_admin`: Access limited to their department only

Add helper to filter queryset by admin scope:
```python
def scope_queryset_for_admin(queryset, user, scope_model):
    if user.is_superuser or user.user_roles.filter(role__slug='admin').exists():
        return queryset
    # Apply faculty/department filters based on user's scoped roles
```

### Analytics Aggregation

Use Django ORM aggregation for stats:
- `Count`, `Avg`, `Sum` for enrollment/grade metrics
- Consider materialized views for heavy reports
- Add caching layer (Redis) for frequently accessed analytics
