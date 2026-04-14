"""Caching utility functions for UniOne API."""
from django.core.cache import cache
from functools import wraps


def cache_key(*parts):
    """Generate a cache key from parts."""
    return f"unione:{':'.join(str(p) for p in parts if p is not None)}"


def get_cached(key, default=None):
    """Get value from cache."""
    return cache.get(cache_key(key) if isinstance(key, str) else key, default)


def set_cached(key, value, timeout=None):
    """Set value in cache."""
    full_key = cache_key(key) if isinstance(key, str) else key
    cache.set(full_key, value, timeout)


def delete_cached(key):
    """Delete value from cache."""
    full_key = cache_key(key) if isinstance(key, str) else key
    cache.delete(full_key)


def cached(timeout=3600, key_prefix='api'):
    """Decorator to cache API view responses."""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(instance, request, *args, **kwargs):
            # Only cache GET requests
            if request.method != 'GET':
                return view_func(instance, request, *args, **kwargs)

            # Generate cache key
            key_parts = [key_prefix, request.path]
            if request.query_params:
                key_parts.append(str(sorted(request.query_params.items())))
            
            cache_key_full = cache_key(*key_parts)
            
            # Try to get cached response
            cached_response = cache.get(cache_key_full)
            if cached_response is not None:
                from rest_framework.response import Response
                response = Response(cached_response['data'], status=cached_response['status'])
                response['X-Cache'] = 'HIT'
                response['X-Cache-Key'] = cache_key_full
                return response

            # Call the view
            response = view_func(instance, request, *args, **kwargs)
            
            # Cache successful responses
            if hasattr(response, 'data') and response.status_code == 200:
                cache.set(cache_key_full, {
                    'data': response.data,
                    'status': response.status_code,
                }, timeout)
                response['X-Cache'] = 'MISS'
                response['X-Cache-Key'] = cache_key_full

            return response
        return _wrapped_view
    return decorator


def invalidate_pattern(pattern):
    """Invalidate all cache keys matching a pattern."""
    # Django's cache doesn't support pattern deletion directly
    # This requires Redis client access
    from django.core.cache import caches
    from django_redis import get_redis_connection
    
    try:
        redis_conn = get_redis_connection("default")
        pattern_key = f"unione:{pattern}*"
        keys = redis_conn.keys(pattern_key)
        if keys:
            redis_conn.delete(*keys)
            return len(keys)
    except Exception:
        pass
    return 0
