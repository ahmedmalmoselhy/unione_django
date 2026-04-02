# UniOne Django Database Schema Reference

This project targets the same domain schema used across UniOne implementations.

## Core Notes

- Database: PostgreSQL (unione_db)
- ORM: Django ORM
- Migrations: Django migration framework

## Primary Domain Tables (summary)

- users, roles, role_user
- universities, faculties, departments
- professors, employees, students
- courses, department_course, course_prerequisites
- academic_terms, sections
- enrollments, enrollment_waitlists
- grades, student_term_gpas, student_department_histories
- announcements, section_announcements, announcement_reads
- attendance_sessions, attendance_records
- course_ratings
- audit_logs
- webhooks, webhook_deliveries
- notifications

## Django Mapping Guidelines

- Use ForeignKey with explicit related_name values
- Use constraints for unique pairs (UniqueConstraint)
- Use TextChoices for status/enum fields
- Use JSONField for schedule/events/payload data
- Use soft-delete strategy only where needed (custom manager)

## Indexing Guidelines

- Unique: email, national_id, student_number, staff_number, course code
- Composite: (student_id, status), (section_id, student_id)
- Add partial indexes for active records when needed

## Migration Strategy

1. organization/auth models
2. academic catalog and term models
3. enrollment and grading models
4. communication and notifications
5. integrations and audit
