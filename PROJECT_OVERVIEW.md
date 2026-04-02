# UniOne Django Project Overview

Last Updated: April 2, 2026
Status: Bootstrap Started

## Summary

This repository tracks a Django-first implementation of UniOne, mirroring core academic workflows from existing implementations:

- authentication and role-based access
- student enrollment lifecycle
- professor grading and attendance
- announcements and notifications
- admin operations and audits

## Target Architecture

```text
Django REST API <-> PostgreSQL
          |
   Web/Mobile Clients
```

## Planned App Layout

- apps.accounts
- apps.organization
- apps.academics
- apps.enrollment
- apps.attendance
- apps.communication
- apps.integrations
- apps.audit

## Delivery Phases

1. Foundation: settings, auth, base models, CI baseline
2. Student core: enrollments, grades read APIs
3. Professor core: grading and attendance write APIs
4. Academic features: transcript, schedule, history
5. Communication: announcements, notifications
6. Integrations: webhooks and retries
7. Admin management: CRUD and scoped access
8. Testing, optimization, deployment hardening

## Baseline Metrics (Target)

- 34+ tables
- 50+ endpoints
- 6 user roles
- full scope parity with UniOne domain
