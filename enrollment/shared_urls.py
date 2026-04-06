from django.urls import path

from .shared_views import (
	SharedAnnouncementsView,
	SharedAnnouncementReadView,
	SharedNotificationsView,
	SharedNotificationsReadAllView,
	SharedNotificationReadView,
	SharedNotificationDeleteView,
)

urlpatterns = [
	path('announcements', SharedAnnouncementsView.as_view(), name='shared-announcements'),
	path('announcements/<int:announcement_id>/read', SharedAnnouncementReadView.as_view(), name='shared-announcement-read'),
	path('notifications', SharedNotificationsView.as_view(), name='shared-notifications'),
	path('notifications/read-all', SharedNotificationsReadAllView.as_view(), name='shared-notifications-read-all'),
	path('notifications/<int:notification_id>/read', SharedNotificationReadView.as_view(), name='shared-notification-read'),
	path('notifications/<int:notification_id>', SharedNotificationDeleteView.as_view(), name='shared-notification-delete'),
]
