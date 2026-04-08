from django.urls import path

from .admin_views import (
    AdminUserDetailView,
    AdminUsersView,
    AdminWebhookDeliveriesView,
    AdminWebhookDetailView,
    AdminWebhooksView,
)

urlpatterns = [
    path('users', AdminUsersView.as_view(), name='admin-users'),
    path('users/<int:user_id>', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('webhooks', AdminWebhooksView.as_view(), name='admin-webhooks'),
    path('webhooks/<int:webhook_id>', AdminWebhookDetailView.as_view(), name='admin-webhook-detail'),
    path('webhooks/<int:webhook_id>/deliveries', AdminWebhookDeliveriesView.as_view(), name='admin-webhook-deliveries'),
]
