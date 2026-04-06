from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Announcement, GlobalAnnouncementRead, Notification
from enrollment.models import CourseEnrollment


def _user_role_slugs(user):
	if not user.is_authenticated:
		return set()
	return set(user.user_roles.values_list('role__slug', flat=True))


def _announcement_queryset_for_user(user):
	now = timezone.now()
	queryset = Announcement.objects.select_related('author').filter(
		deleted_at__isnull=True,
		published_at__lte=now,
	).filter(
		Q(expires_at__isnull=True) | Q(expires_at__gt=now)
	)

	faculty_id = None
	department_id = None
	section_ids = []

	if hasattr(user, 'student_profile'):
		student_profile = user.student_profile
		faculty_id = student_profile.faculty_id
		department_id = student_profile.department_id
		section_ids = list(
			CourseEnrollment.objects.filter(student=student_profile)
			.exclude(status=CourseEnrollment.EnrollmentStatus.DROPPED)
			.values_list('section_id', flat=True)
		)
	elif hasattr(user, 'professor_profile'):
		professor_profile = user.professor_profile
		department_id = professor_profile.department_id
		faculty_id = professor_profile.department.faculty_id if professor_profile.department_id else None

	visibility_filter = Q(visibility=Announcement.Visibility.UNIVERSITY)
	if faculty_id:
		visibility_filter |= Q(visibility=Announcement.Visibility.FACULTY, target_id=faculty_id)
	if department_id:
		visibility_filter |= Q(visibility=Announcement.Visibility.DEPARTMENT, target_id=department_id)
	if section_ids:
		visibility_filter |= Q(visibility=Announcement.Visibility.SECTION, target_id__in=section_ids)

	return queryset.filter(visibility_filter).order_by('-published_at', '-id')


class SharedAnnouncementsView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		queryset = _announcement_queryset_for_user(request.user)

		section_id = request.query_params.get('section_id')
		if section_id:
			queryset = queryset.filter(visibility=Announcement.Visibility.SECTION, target_id=section_id)

		per_page_param = request.query_params.get('per_page', 20)
		page_param = request.query_params.get('page', 1)
		try:
			per_page = max(1, min(int(per_page_param), 50))
		except (TypeError, ValueError):
			per_page = 20
		try:
			page = max(1, int(page_param))
		except (TypeError, ValueError):
			page = 1

		total = queryset.count()
		start = (page - 1) * per_page
		end = start + per_page
		paged_queryset = queryset[start:end]
		last_page = max(1, (total + per_page - 1) // per_page)

		announcement_ids = list(paged_queryset.values_list('id', flat=True))
		read_map = {
			read.announcement_id: read.read_at
			for read in GlobalAnnouncementRead.objects.filter(user=request.user, announcement_id__in=announcement_ids)
		}

		data = [
			{
				'id': announcement.id,
				'title': announcement.title,
				'body': announcement.body,
				'type': announcement.type,
				'visibility': announcement.visibility,
				'published_at': announcement.published_at,
				'expires_at': announcement.expires_at,
				'is_read': announcement.id in read_map,
				'read_at': read_map.get(announcement.id),
				'author': {
					'first_name': announcement.author.first_name,
					'last_name': announcement.author.last_name,
				}
				if announcement.author
				else None,
			}
			for announcement in paged_queryset
		]

		return Response(
			{
				'status': 'success',
				'data': data,
				'meta': {
					'current_page': page,
					'last_page': last_page,
					'per_page': per_page,
					'total': total,
				},
			}
		)


class SharedAnnouncementReadView(APIView):
	permission_classes = [IsAuthenticated]

	def post(self, request, announcement_id):
		announcement = Announcement.objects.filter(
			id=announcement_id,
			deleted_at__isnull=True,
			published_at__lte=timezone.now(),
		).first()
		if announcement is None:
			return Response(
				{'status': 'error', 'message': 'Announcement not found'},
				status=status.HTTP_404_NOT_FOUND,
			)

		read, _created = GlobalAnnouncementRead.objects.get_or_create(
			announcement=announcement,
			user=request.user,
		)
		return Response(
			{
				'status': 'success',
				'message': 'Announcement marked as read',
				'data': {'announcement_id': announcement.id, 'read_at': read.read_at},
			}
		)


class SharedNotificationsView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		queryset = Notification.objects.filter(recipient=request.user, deleted_at__isnull=True).order_by('-created_at', '-id')
		unread_raw = request.query_params.get('unread', request.query_params.get('unread_only', ''))
		if str(unread_raw).lower() in {'1', 'true', 'yes'}:
			queryset = queryset.filter(read_at__isnull=True)

		per_page_param = request.query_params.get('per_page', 20)
		page_param = request.query_params.get('page', 1)
		try:
			per_page = max(1, min(int(per_page_param), 50))
		except (TypeError, ValueError):
			per_page = 20
		try:
			page = max(1, int(page_param))
		except (TypeError, ValueError):
			page = 1

		total = queryset.count()
		start = (page - 1) * per_page
		end = start + per_page
		paged_queryset = queryset[start:end]
		last_page = max(1, (total + per_page - 1) // per_page)
		unread_count = Notification.objects.filter(
			recipient=request.user,
			deleted_at__isnull=True,
			read_at__isnull=True,
		).count()

		data = [
			{
				'id': notification.id,
				'title': notification.title,
				'body': notification.body,
				'notification_type': notification.notification_type,
				'payload': notification.payload,
				'read_at': notification.read_at,
				'created_at': notification.created_at,
			}
			for notification in paged_queryset
		]
		return Response(
			{
				'status': 'success',
				'data': data,
				'meta': {
					'current_page': page,
					'last_page': last_page,
					'per_page': per_page,
					'total': total,
					'unread_count': unread_count,
				},
			}
		)


class SharedNotificationsReadAllView(APIView):
	permission_classes = [IsAuthenticated]

	def post(self, request):
		now = timezone.now()
		updated = Notification.objects.filter(
			recipient=request.user,
			deleted_at__isnull=True,
			read_at__isnull=True,
		).update(read_at=now, updated_at=now)
		return Response(
			{
				'status': 'success',
				'message': 'Notifications marked as read',
				'data': {'updated_count': updated},
			}
		)


class SharedNotificationReadView(APIView):
	permission_classes = [IsAuthenticated]

	def post(self, request, notification_id):
		notification = Notification.objects.filter(
			id=notification_id,
			recipient=request.user,
			deleted_at__isnull=True,
		).first()
		if notification is None:
			return Response(
				{'status': 'error', 'message': 'Notification not found'},
				status=status.HTTP_404_NOT_FOUND,
			)

		if notification.read_at is None:
			notification.read_at = timezone.now()
			notification.save(update_fields=['read_at', 'updated_at'])

		return Response(
			{
				'status': 'success',
				'message': 'Notification marked as read',
				'data': {'notification_id': notification.id, 'read_at': notification.read_at},
			}
		)


class SharedNotificationDeleteView(APIView):
	permission_classes = [IsAuthenticated]

	def delete(self, request, notification_id):
		notification = Notification.objects.filter(
			id=notification_id,
			recipient=request.user,
			deleted_at__isnull=True,
		).first()
		if notification is None:
			return Response(
				{'status': 'error', 'message': 'Notification not found'},
				status=status.HTTP_404_NOT_FOUND,
			)

		now = timezone.now()
		notification.deleted_at = now
		notification.save(update_fields=['deleted_at', 'updated_at'])
		return Response({'status': 'success', 'message': 'Notification deleted successfully'})
