"""Middleware to add rate limit headers to responses."""
import time


class RateLimitHeadersMiddleware:
    """
    Add standard rate limit headers to all responses.
    Headers: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Add standard rate limit headers if not already set by DRF throttling
        if 'X-RateLimit-Limit' not in response:
            # Default values (can be overridden per-view)
            response['X-RateLimit-Limit'] = '60'
            response['X-RateLimit-Remaining'] = '59'
            response['X-RateLimit-Reset'] = str(int(time.time()) + 60)

        # Add custom headers for API governance
        if hasattr(request, 'user') and request.user.is_authenticated:
            roles = list(request.user.user_roles.values_list('role__slug', flat=True))
            response['X-User-Roles'] = ','.join(roles) if roles else 'none'

        # Add API version header
        response['X-API-Version'] = 'v1'

        return response
