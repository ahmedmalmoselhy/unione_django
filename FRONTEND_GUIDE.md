# UniOne Frontend Integration Guide (for Django API)

This guide remaps frontend integration assumptions to a Django REST backend.

## API Contract

- Base URL: <http://127.0.0.1:8000/api>
- Auth strategy: token/JWT based (finalized in auth module)
- Error format: consistent status/message/errors envelope

## Frontend Expectations

- Preserve role-based portals: student, professor, admin
- Use API service layer with interceptors for auth headers
- Implement refresh/re-login strategy for 401 responses
- Keep pagination/filter conventions stable across modules

## Recommended Client Stack

- React + TypeScript
- TanStack Query
- Axios
- React Router

## Integration Checklist

1. configure API base URL by environment
2. wire login flow against /api/auth/login
3. fetch current user from /api/auth/me
4. gate routes by role claims
5. implement student and professor module calls
6. implement notification polling/realtime strategy
