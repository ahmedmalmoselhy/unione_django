"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def api_root(_request):
    return JsonResponse(
        {
            "message": "Welcome to UniOne Django API",
            "version": "0.1.0",
            "health": "/health",
            "docs": "/api/docs/",
            "note": "API versioning is now available at /api/v1/",
        }
    )


def health(_request):
    return JsonResponse({"status": "ok", "service": "unione_django"})

# V1 API URLs (versioned)
v1_urlpatterns = [
    path('admin/', include('enrollment.admin_urls')),
    path('auth/', include('accounts.urls')),
    path('organization/', include('organization.urls')),
    path('student/', include('enrollment.urls')),
    path('professor/', include('enrollment.professor_urls')),
    path('announcements/', include('enrollment.shared_urls')),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api_root),
    path('api/v1/', include((v1_urlpatterns, 'v1'))),
    # Legacy URLs (backward compatibility - will be deprecated)
    path('api/', include('enrollment.shared_urls')),
    path('api/admin/', include('enrollment.admin_urls')),
    path('api/auth/', include('accounts.urls')),
    path('api/organization/', include('organization.urls')),
    path('api/student/', include('enrollment.urls')),
    path('api/professor/', include('enrollment.professor_urls')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('health', health),
]
