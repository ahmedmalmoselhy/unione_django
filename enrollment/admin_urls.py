from django.urls import path

from .admin_views import AdminWebhooksView, AdminWebhookDetailView, AdminWebhookDeliveriesView

urlpatterns = [
	path('webhooks', AdminWebhooksView.as_view(), name='admin-webhooks'),
	path('webhooks/<int:webhook_id>', AdminWebhookDetailView.as_view(), name='admin-webhook-detail'),
	path('webhooks/<int:webhook_id>/deliveries', AdminWebhookDeliveriesView.as_view(), name='admin-webhook-deliveries'),
]
