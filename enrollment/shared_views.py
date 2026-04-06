from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import AnnouncementRead, Notification, SectionAnnouncement
from enrollment.models import CourseEnrollment


def _user_role_slugs(user):
	if not user.is_authenticated:
		return set()
	return set(user.user_roles.values_list('role__slug', flat=True))


def _announcement_queryset_for_user(user):
	queryset = SectionAnnouncement.objects.select_related(
		'section__course',
		'section__academic_term',
		'created_by__user',
	).order_by('-is_pinned', '-published_at', '-id')

	if user.is_superuser:
		return queryset

	roles = _user_role_slugs(user)
	if roles.intersection({'admin', 'faculty_admin', 'department_admin', 'employee'}):
		return queryset

	section_ids = set()
	if 'professor' in roles:
		section_ids.update(
			user.professor_profile.sections.values_list('id', flat=True)
			if hasattr(user, 'professor_profile')
			else []
		)
	if 'student' in roles:
		section_ids.update(
			CourseEnrollment.objects.filter(student__user=user)
			.exclude(status=CourseEnrollment.EnrollmentStatus.DROPPED)
			.values_list('section_id', flat=True)
		)

	if not section_ids:
		return queryset.none()
	return queryset.filter(section_id__in=section_ids)


class SharedAnnouncementsView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		queryset = _announcement_queryset_for_user(request.user)

		section_id = request.query_params.get('section_id')
		if section_id:
			queryset = queryset.filter(section_id=section_id)

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
			for read in AnnouncementRead.objects.filter(user=request.user, announcement_id__in=announcement_ids)
		}

		data = [
			{
				'id': announcement.id,
				'title': announcement.title,
				'body': announcement.body,
				'is_pinned': announcement.is_pinned,
				'published_at': announcement.published_at,
				'updated_at': announcement.updated_at,
				'is_read': announcement.id in read_map,
				'read_at': read_map.get(announcement.id),
				'section': {
					'id': announcement.section.id,
					'course': {
						'id': announcement.section.course.id,
						'code': announcement.section.course.code,
						'name': announcement.section.course.name,
					},
					'academic_term': {
						'id': announcement.section.academic_term.id,
						'name': announcement.section.academic_term.name,
					},
				},
				'created_by': {
					'id': announcement.created_by.id,
					'name': announcement.created_by.user.get_full_name() or announcement.created_by.user.username,
					'staff_number': announcement.created_by.staff_number,
				},
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
		announcement = _announcement_queryset_for_user(request.user).filter(id=announcement_id).first()
		if announcement is None:
			return Response(
				{'status': 'error', 'message': 'Announcement not found'},
				status=status.HTTP_404_NOT_FOUND,
			)

		read, _created = AnnouncementRead.objects.get_or_create(
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
