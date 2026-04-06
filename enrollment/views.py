import logging

from django.http import HttpResponse
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.permissions import HasAnyRole
from academics.models import (
	AcademicTerm,
	AttendanceRecord,
	AttendanceSession,
	CourseRating,
	EnrollmentWaitlist,
	Grade,
	Notification,
	Section,
	SectionAnnouncement,
)
from academics.webhook_delivery import enqueue_webhook_deliveries

from .models import CourseEnrollment
from .services import (
	build_student_academic_history,
	build_student_schedule,
	build_student_schedule_ics,
	build_student_transcript,
	build_student_transcript_pdf_bytes,
)
from .serializers import EnrollmentSerializer, GradeSerializer, StudentProfileSerializer


logger = logging.getLogger(__name__)


class StudentOnlyPermission(HasAnyRole):
	required_roles = ['student']


class ProfessorOnlyPermission(HasAnyRole):
	required_roles = ['professor']


def _get_professor_profile_or_none(user):
	try:
		return user.professor_profile
	except Exception:
		return None


def _normalize_schedule_slots(schedule):
	if not isinstance(schedule, dict):
		return []

	days = schedule.get('days')
	if not isinstance(days, list):
		return []

	day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
	start_time = schedule.get('start_time')
	end_time = schedule.get('end_time')

	slots = []
	for raw_day in days:
		try:
			day_value = int(raw_day)
		except (TypeError, ValueError):
			continue

		if 1 <= day_value <= 7:
			day_index = day_value - 1
		elif 0 <= day_value <= 6:
			day_index = day_value
		else:
			continue

		slots.append(
			{
				'day_index': day_index,
				'day_name': day_names[day_index],
				'start_time': start_time,
				'end_time': end_time,
			}
		)

	return slots


def _get_professor_section_or_none(profile, section_id):
	return (
		Section.objects.select_related('course', 'academic_term')
		.filter(id=section_id, professor=profile)
		.first()
	)


def _attendance_records_payload(session):
	records = []
	for record in session.records.select_related('enrollment__student__user').order_by('enrollment__student__student_number'):
		student = record.enrollment.student
		records.append(
			{
				'id': record.id,
				'enrollment_id': record.enrollment_id,
				'status': record.status,
				'note': record.note,
				'marked_at': record.marked_at,
				'updated_at': record.updated_at,
				'student': {
					'id': student.id,
					'student_number': student.student_number,
					'name': student.user.get_full_name() or student.user.username,
					'email': student.user.email,
				},
			}
		)
	return records


def _enqueue_webhook_event(event_name, payload):
	try:
		enqueue_webhook_deliveries(event_name, payload=payload)
	except Exception:
		logger.exception('Failed to enqueue webhook event: %s', event_name)


def _reindex_waitlist_positions(section):
	entries = EnrollmentWaitlist.objects.filter(
		section=section,
		status=EnrollmentWaitlist.WaitlistStatus.ACTIVE,
	).order_by('position', 'created_at', 'id')

	for index, entry in enumerate(entries, start=1):
		if entry.position != index:
			entry.position = index
			entry.save(update_fields=['position', 'updated_at'])


def _waitlist_entry_to_payload(entry):
	return {
		'id': entry.id,
		'section_id': entry.section_id,
		'position': entry.position,
		'status': entry.status,
		'created_at': entry.created_at,
	}


def _promote_next_waitlisted_student(section):
	with transaction.atomic():
		candidate = (
			EnrollmentWaitlist.objects.select_related('student__user')
			.select_for_update()
			.filter(section=section, status=EnrollmentWaitlist.WaitlistStatus.ACTIVE)
			.order_by('position', 'created_at', 'id')
			.first()
		)
		if candidate is None:
			return None

		enrollment = CourseEnrollment.objects.filter(
			student=candidate.student,
			section=section,
			academic_term=section.academic_term,
		).first()

		if enrollment is None:
			enrollment = CourseEnrollment.objects.create(
				student=candidate.student,
				section=section,
				academic_term=section.academic_term,
				status=CourseEnrollment.EnrollmentStatus.ACTIVE,
			)
		elif enrollment.status == CourseEnrollment.EnrollmentStatus.DROPPED:
			enrollment.status = CourseEnrollment.EnrollmentStatus.ACTIVE
			enrollment.dropped_at = None
			enrollment.save(update_fields=['status', 'dropped_at', 'updated_at'])
		else:
			candidate.status = EnrollmentWaitlist.WaitlistStatus.CANCELLED
			candidate.save(update_fields=['status', 'updated_at'])
			_reindex_waitlist_positions(section)
			return _promote_next_waitlisted_student(section)

		candidate.status = EnrollmentWaitlist.WaitlistStatus.ENROLLED
		candidate.save(update_fields=['status', 'updated_at'])
		_reindex_waitlist_positions(section)

		Notification.objects.create(
			recipient=candidate.student.user,
			title='Enrollment available',
			body=f'You have been enrolled in section {section.id} from the waitlist.',
			notification_type='waitlist_promotion',
			payload={'section_id': section.id, 'enrollment_id': enrollment.id},
		)
		_enqueue_webhook_event(
			'enrollment.waitlist_promoted',
			{
				'section_id': section.id,
				'academic_term_id': section.academic_term_id,
				'student_id': candidate.student_id,
				'enrollment_id': enrollment.id,
				'waitlist_entry_id': candidate.id,
			},
		)

		return {
			'waitlist_entry_id': candidate.id,
			'enrollment_id': enrollment.id,
			'student_id': candidate.student_id,
		}


class StudentProfileView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request):
		student = request.user.student_profile
		data = StudentProfileSerializer(
			{
				'student_number': student.student_number,
				'faculty': student.faculty.name,
				'department': student.department.name,
				'gpa': student.gpa,
				'standing': student.academic_standing,
			}
		).data
		return Response({'status': 'success', 'data': data})


class StudentEnrollmentView(APIView):
	permission_classes = [StudentOnlyPermission]
	throttle_classes = [ScopedRateThrottle]

	def get_throttles(self):
		if self.request.method.upper() == 'POST':
			self.throttle_scope = 'api_enroll'
			return super().get_throttles()
		return []

	def get(self, request):
		queryset = CourseEnrollment.objects.select_related(
			'section',
			'section__course',
			'section__professor__user',
			'section__academic_term',
		).filter(student=request.user.student_profile).order_by('-registered_at')

		status_filter = request.query_params.get('status')
		academic_term_id = request.query_params.get('academic_term_id')
		if status_filter:
			queryset = queryset.filter(status=status_filter)
		if academic_term_id:
			queryset = queryset.filter(academic_term_id=academic_term_id)

		data = []
		for enrollment in queryset:
			section = enrollment.section
			professor = section.professor
			data.append(
				{
					'id': enrollment.id,
					'status': enrollment.status,
					'registered_at': enrollment.registered_at,
					'section': {
						'id': section.id,
						'course': {
							'id': section.course.id,
							'code': section.course.code,
							'name': section.course.name,
						},
						'professor': {
							'id': professor.id,
							'name': professor.user.get_full_name() or professor.user.username,
							'staff_number': professor.staff_number,
						},
						'schedule': section.schedule,
						'academic_term': section.academic_term.name,
					},
				}
			)

		return Response({'status': 'success', 'data': EnrollmentSerializer(data, many=True).data})

	def post(self, request):
		student = request.user.student_profile
		payload = request.data if isinstance(request.data, dict) else {}

		section_id = payload.get('section_id')
		if section_id is None:
			return Response(
				{'status': 'error', 'message': 'section_id is required'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		try:
			section_id = int(section_id)
		except (TypeError, ValueError):
			return Response(
				{'status': 'error', 'message': 'section_id must be an integer'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		section = (
			Section.objects.select_related('course', 'professor__user', 'academic_term')
			.filter(id=section_id)
			.first()
		)
		if section is None:
			return Response(
				{'status': 'error', 'message': 'Section not found'},
				status=status.HTTP_404_NOT_FOUND,
			)

		existing = CourseEnrollment.objects.filter(
			student=student,
			section=section,
			academic_term=section.academic_term,
		).first()
		if existing is not None and existing.status != CourseEnrollment.EnrollmentStatus.DROPPED:
			return Response(
				{'status': 'error', 'message': 'Already enrolled in this section'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		active_count = CourseEnrollment.objects.filter(
			section=section,
			status=CourseEnrollment.EnrollmentStatus.ACTIVE,
		).count()
		if section.capacity and active_count >= section.capacity:
			existing_waitlist = EnrollmentWaitlist.objects.filter(student=student, section=section).first()
			if existing_waitlist and existing_waitlist.status == EnrollmentWaitlist.WaitlistStatus.ACTIVE:
				return Response(
					{
						'status': 'success',
						'message': 'Already on waitlist for this section',
						'data': _waitlist_entry_to_payload(existing_waitlist),
					},
					status=status.HTTP_200_OK,
				)

			if existing_waitlist is None:
				next_position = (
					EnrollmentWaitlist.objects.filter(
						section=section,
						status=EnrollmentWaitlist.WaitlistStatus.ACTIVE,
					)
					.count()
					+ 1
				)
				existing_waitlist = EnrollmentWaitlist.objects.create(
					student=student,
					section=section,
					academic_term=section.academic_term,
					position=next_position,
					status=EnrollmentWaitlist.WaitlistStatus.ACTIVE,
				)
			else:
				existing_waitlist.academic_term = section.academic_term
				existing_waitlist.position = (
					EnrollmentWaitlist.objects.filter(
						section=section,
						status=EnrollmentWaitlist.WaitlistStatus.ACTIVE,
					)
					.exclude(id=existing_waitlist.id)
					.count()
					+ 1
				)
				existing_waitlist.status = EnrollmentWaitlist.WaitlistStatus.ACTIVE
				existing_waitlist.save(update_fields=['academic_term', 'position', 'status', 'updated_at'])

			_reindex_waitlist_positions(section)
			existing_waitlist.refresh_from_db(fields=['position'])
			_enqueue_webhook_event(
				'enrollment.waitlist_added',
				{
					'section_id': section.id,
					'academic_term_id': section.academic_term_id,
					'student_id': student.id,
					'waitlist_entry_id': existing_waitlist.id,
					'position': existing_waitlist.position,
				},
			)

			return Response(
				{
					'status': 'success',
					'message': 'Section is full, added to waitlist',
					'data': _waitlist_entry_to_payload(existing_waitlist),
				},
				status=status.HTTP_202_ACCEPTED,
			)

		if existing is None:
			enrollment = CourseEnrollment.objects.create(
				student=student,
				section=section,
				academic_term=section.academic_term,
				status=CourseEnrollment.EnrollmentStatus.ACTIVE,
			)
		else:
			existing.status = CourseEnrollment.EnrollmentStatus.ACTIVE
			existing.dropped_at = None
			existing.save(update_fields=['status', 'dropped_at', 'updated_at'])
			enrollment = existing

		EnrollmentWaitlist.objects.filter(
			student=student,
			section=section,
			status=EnrollmentWaitlist.WaitlistStatus.ACTIVE,
		).update(status=EnrollmentWaitlist.WaitlistStatus.ENROLLED)
		_reindex_waitlist_positions(section)
		_enqueue_webhook_event(
			'enrollment.created',
			{
				'enrollment_id': enrollment.id,
				'section_id': section.id,
				'academic_term_id': section.academic_term_id,
				'student_id': student.id,
				'status': enrollment.status,
			},
		)

		return Response(
			{
				'status': 'success',
				'message': 'Enrolled successfully',
				'data': {
					'id': enrollment.id,
					'status': enrollment.status,
					'registered_at': enrollment.registered_at,
					'section': {
						'id': section.id,
						'course': {
							'id': section.course.id,
							'code': section.course.code,
							'name': section.course.name,
						},
						'professor': {
							'id': section.professor.id,
							'name': section.professor.user.get_full_name() or section.professor.user.username,
							'staff_number': section.professor.staff_number,
						},
						'schedule': section.schedule,
						'academic_term': section.academic_term.name,
					},
				},
			},
			status=status.HTTP_201_CREATED,
		)


class StudentEnrollmentDeleteView(APIView):
	permission_classes = [StudentOnlyPermission]
	throttle_classes = [ScopedRateThrottle]
	throttle_scope = 'api_enroll'

	def delete(self, request, enrollment_id):
		student = request.user.student_profile
		enrollment = CourseEnrollment.objects.filter(id=enrollment_id, student=student).first()
		if enrollment is None:
			return Response(
				{'status': 'error', 'message': 'Enrollment not found'},
				status=status.HTTP_404_NOT_FOUND,
			)

		if enrollment.status == CourseEnrollment.EnrollmentStatus.DROPPED:
			return Response(
				{'status': 'error', 'message': 'Enrollment already dropped'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		enrollment.status = CourseEnrollment.EnrollmentStatus.DROPPED
		enrollment.dropped_at = timezone.now()
		enrollment.save(update_fields=['status', 'dropped_at', 'updated_at'])

		promoted = _promote_next_waitlisted_student(enrollment.section)
		_enqueue_webhook_event(
			'enrollment.dropped',
			{
				'enrollment_id': enrollment.id,
				'section_id': enrollment.section_id,
				'academic_term_id': enrollment.academic_term_id,
				'student_id': student.id,
				'promoted_waitlist': promoted,
			},
		)
		data = {'promoted_waitlist': promoted} if promoted else None

		return Response({'status': 'success', 'message': 'Enrollment dropped successfully', 'data': data})


class StudentGradeView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request):
		queryset = Grade.objects.select_related(
			'enrollment',
			'enrollment__section',
			'enrollment__section__course',
			'enrollment__academic_term',
			'enrollment__student',
		).filter(enrollment__student=request.user.student_profile).order_by('-updated_at')

		academic_term_id = request.query_params.get('academic_term_id')
		department_id = request.query_params.get('department_id')
		if academic_term_id:
			queryset = queryset.filter(enrollment__academic_term_id=academic_term_id)
		if department_id:
			queryset = queryset.filter(enrollment__student__department_id=department_id)

		data = []
		for grade in queryset:
			course = grade.enrollment.section.course
			academic_term = grade.enrollment.academic_term
			data.append(
				{
					'id': grade.id,
					'points': grade.points,
					'letter_grade': grade.letter_grade,
					'status': grade.status,
					'academic_term': {'id': academic_term.id, 'name': academic_term.name},
					'course': {'id': course.id, 'code': course.code, 'name': course.name},
				}
			)

		return Response({'status': 'success', 'data': GradeSerializer(data, many=True).data})


class StudentAcademicTermsView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, _request):
		queryset = AcademicTerm.objects.all().order_by('-start_date')
		data = [
			{
				'id': term.id,
				'name': term.name,
				'start_date': term.start_date,
				'end_date': term.end_date,
				'registration_start': term.registration_start,
				'registration_end': term.registration_end,
				'is_active': term.is_active,
			}
			for term in queryset
		]
		return Response({'status': 'success', 'data': data})


class StudentSectionsView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request):
		queryset = Section.objects.select_related(
			'course',
			'professor__user',
			'academic_term',
		).order_by('id')

		academic_term_id = request.query_params.get('academic_term_id')
		if academic_term_id:
			queryset = queryset.filter(academic_term_id=academic_term_id)

		data = []
		for section in queryset:
			professor = section.professor
			data.append(
				{
					'id': section.id,
					'semester': section.semester,
					'capacity': section.capacity,
					'schedule': section.schedule,
					'course': {
						'id': section.course.id,
						'code': section.course.code,
						'name': section.course.name,
						'credit_hours': section.course.credit_hours,
					},
					'professor': {
						'id': professor.id,
						'name': professor.user.get_full_name() or professor.user.username,
						'staff_number': professor.staff_number,
					},
					'academic_term': {
						'id': section.academic_term.id,
						'name': section.academic_term.name,
					},
				}
			)

		return Response({'status': 'success', 'data': data})


class StudentTranscriptView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request):
		academic_term_id = request.query_params.get('academic_term_id')
		data = build_student_transcript(request.user.student_profile, academic_term_id=academic_term_id)
		return Response({'status': 'success', 'data': data})


class StudentTranscriptPDFView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request):
		academic_term_id = request.query_params.get('academic_term_id')
		pdf_bytes = build_student_transcript_pdf_bytes(request.user.student_profile, academic_term_id=academic_term_id)
		response = HttpResponse(pdf_bytes, content_type='application/pdf')
		response['Content-Disposition'] = (
			f'attachment; filename="student-{request.user.student_profile.student_number}-transcript.pdf"'
		)
		return response


class StudentAcademicHistoryView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request):
		data = build_student_academic_history(request.user.student_profile)
		return Response({'status': 'success', 'data': data})


class StudentScheduleView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request):
		academic_term_id = request.query_params.get('academic_term_id')
		data = build_student_schedule(request.user.student_profile, academic_term_id=academic_term_id)
		return Response({'status': 'success', 'data': data})


class StudentScheduleICSView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request):
		academic_term_id = request.query_params.get('academic_term_id')
		ics_content = build_student_schedule_ics(request.user.student_profile, academic_term_id=academic_term_id)
		response = HttpResponse(ics_content, content_type='text/calendar; charset=utf-8')
		response['Content-Disposition'] = f'attachment; filename="student-{request.user.student_profile.student_number}-schedule.ics"'
		return response


class StudentAttendanceView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request):
		student = request.user.student_profile
		queryset = (
			AttendanceRecord.objects.select_related(
				'session',
				'session__section',
				'session__section__course',
				'session__section__academic_term',
				'enrollment',
			)
			.filter(enrollment__student=student)
			.order_by('-session__session_date', '-session_id')
		)

		academic_term_id = request.query_params.get('academic_term_id')
		section_id = request.query_params.get('section_id')
		if academic_term_id:
			queryset = queryset.filter(session__section__academic_term_id=academic_term_id)
		if section_id:
			queryset = queryset.filter(session__section_id=section_id)

		data = [
			{
				'id': record.id,
				'status': record.status,
				'note': record.note,
				'marked_at': record.marked_at,
				'session': {
					'id': record.session.id,
					'session_date': record.session.session_date,
					'title': record.session.title,
					'section_id': record.session.section.id,
				},
				'course': {
					'id': record.session.section.course.id,
					'code': record.session.section.course.code,
					'name': record.session.section.course.name,
				},
				'academic_term': {
					'id': record.session.section.academic_term.id,
					'name': record.session.section.academic_term.name,
				},
			}
			for record in queryset
		]

		return Response({'status': 'success', 'data': data})


class StudentWaitlistView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request):
		student = request.user.student_profile
		queryset = (
			EnrollmentWaitlist.objects.select_related('section__course', 'academic_term')
			.filter(student=student, status=EnrollmentWaitlist.WaitlistStatus.ACTIVE)
			.order_by('position', 'created_at')
		)

		data = [
			{
				'id': entry.id,
				'position': entry.position,
				'status': entry.status,
				'notes': entry.notes,
				'created_at': entry.created_at,
				'section': {
					'id': entry.section.id,
					'semester': entry.section.semester,
					'course': {
						'id': entry.section.course.id,
						'code': entry.section.course.code,
						'name': entry.section.course.name,
					},
				},
				'academic_term': {
					'id': entry.academic_term.id,
					'name': entry.academic_term.name,
				},
			}
			for entry in queryset
		]

		return Response({'status': 'success', 'data': data})


class StudentWaitlistDeleteView(APIView):
	permission_classes = [StudentOnlyPermission]

	def delete(self, request, section_id):
		student = request.user.student_profile
		entry = EnrollmentWaitlist.objects.filter(
			student=student,
			section_id=section_id,
			status=EnrollmentWaitlist.WaitlistStatus.ACTIVE,
		).first()
		if entry is None:
			return Response(
				{'status': 'error', 'message': 'Waitlist entry not found'},
				status=status.HTTP_404_NOT_FOUND,
			)

		entry.status = EnrollmentWaitlist.WaitlistStatus.CANCELLED
		entry.save(update_fields=['status', 'updated_at'])
		_reindex_waitlist_positions(entry.section)
		return Response({'status': 'success', 'message': 'Waitlist entry removed successfully'})


class StudentSectionAnnouncementsView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request, section_id):
		student = request.user.student_profile
		enrolled = CourseEnrollment.objects.filter(
			student=student,
			section_id=section_id,
		).exclude(status=CourseEnrollment.EnrollmentStatus.DROPPED).exists()
		if not enrolled:
			return Response(
				{'status': 'error', 'message': 'You are not enrolled in this section.'},
				status=status.HTTP_403_FORBIDDEN,
			)

		announcements = (
			SectionAnnouncement.objects.select_related('created_by__user')
			.filter(section_id=section_id)
			.order_by('-published_at', '-id')
		)

		data = [
			{
				'id': announcement.id,
				'title': announcement.title,
				'body': announcement.body,
				'is_pinned': announcement.is_pinned,
				'published_at': announcement.published_at,
				'updated_at': announcement.updated_at,
				'created_by': {
					'id': announcement.created_by.id,
					'name': announcement.created_by.user.get_full_name() or announcement.created_by.user.username,
					'staff_number': announcement.created_by.staff_number,
				},
			}
			for announcement in announcements
		]
		return Response({'status': 'success', 'data': data}, status=status.HTTP_200_OK)


class StudentRatingsView(APIView):
	permission_classes = [StudentOnlyPermission]

	def get(self, request):
		student = request.user.student_profile
		queryset = (
			CourseRating.objects.select_related('course', 'section', 'section__academic_term')
			.filter(student=student)
			.order_by('-updated_at', '-id')
		)

		course_id = request.query_params.get('course_id')
		if course_id:
			queryset = queryset.filter(course_id=course_id)

		data = [
			{
				'id': rating.id,
				'rating': rating.rating,
				'comment': rating.comment,
				'created_at': rating.created_at,
				'updated_at': rating.updated_at,
				'course': {
					'id': rating.course.id,
					'code': rating.course.code,
					'name': rating.course.name,
				},
				'section': {
					'id': rating.section.id,
					'academic_term': rating.section.academic_term.name,
				}
				if rating.section
				else None,
			}
			for rating in queryset
		]

		return Response({'status': 'success', 'data': data})

	def post(self, request):
		student = request.user.student_profile
		payload = request.data if isinstance(request.data, dict) else {}

		course_id = payload.get('course_id')
		rating_value = payload.get('rating')
		if course_id is None or rating_value is None:
			return Response(
				{'status': 'error', 'message': 'course_id and rating are required'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		try:
			course_id = int(course_id)
			rating_value = int(rating_value)
		except (TypeError, ValueError):
			return Response(
				{'status': 'error', 'message': 'course_id and rating must be integers'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		if rating_value < 1 or rating_value > 5:
			return Response(
				{'status': 'error', 'message': 'rating must be between 1 and 5'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		section_id = payload.get('section_id')
		enrollment_qs = CourseEnrollment.objects.filter(student=student, section__course_id=course_id).exclude(
			status=CourseEnrollment.EnrollmentStatus.DROPPED
		)
		if section_id is not None:
			enrollment_qs = enrollment_qs.filter(section_id=section_id)

		enrollment = enrollment_qs.select_related('section').first()
		if enrollment is None:
			return Response(
				{'status': 'error', 'message': 'You can only rate courses you are enrolled in'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		rating_obj, _created = CourseRating.objects.update_or_create(
			student=student,
			course_id=course_id,
			defaults={
				'section': enrollment.section,
				'rating': rating_value,
				'comment': payload.get('comment'),
			},
		)

		return Response(
			{
				'status': 'success',
				'message': 'Course rating saved successfully',
				'data': {
					'id': rating_obj.id,
					'course_id': rating_obj.course_id,
					'section_id': rating_obj.section_id,
					'rating': rating_obj.rating,
					'comment': rating_obj.comment,
					'updated_at': rating_obj.updated_at,
				},
			},
			status=status.HTTP_200_OK,
		)


class ProfessorProfileView(APIView):
	permission_classes = [ProfessorOnlyPermission]

	def get(self, request):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response(
				{'status': 'error', 'message': 'Professor profile not found'},
				status=404,
			)

		data = {
			'id': profile.id,
			'staff_number': profile.staff_number,
			'name': request.user.get_full_name() or request.user.username,
			'email': request.user.email,
			'specialization': profile.specialization,
			'academic_rank': profile.academic_rank,
			'office_location': profile.office_location,
			'hired_at': profile.hired_at,
			'department': {
				'id': profile.department.id,
				'name': profile.department.name,
				'code': profile.department.code,
				'faculty': {
					'id': profile.department.faculty.id,
					'name': profile.department.faculty.name,
					'code': profile.department.faculty.code,
				},
			},
		}
		return Response({'status': 'success', 'data': data})


class ProfessorSectionsView(APIView):
	permission_classes = [ProfessorOnlyPermission]

	def get(self, request):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response(
				{'status': 'error', 'message': 'Professor profile not found'},
				status=404,
			)

		queryset = Section.objects.select_related('course', 'academic_term').filter(professor=profile).order_by('id')

		academic_term_id = request.query_params.get('academic_term_id')
		if academic_term_id:
			queryset = queryset.filter(academic_term_id=academic_term_id)

		data = []
		for section in queryset:
			data.append(
				{
					'id': section.id,
					'semester': section.semester,
					'capacity': section.capacity,
					'schedule': section.schedule,
					'academic_term': {
						'id': section.academic_term.id,
						'name': section.academic_term.name,
						'start_date': section.academic_term.start_date,
						'end_date': section.academic_term.end_date,
					},
					'course': {
						'id': section.course.id,
						'code': section.course.code,
						'name': section.course.name,
						'credit_hours': section.course.credit_hours,
						'lecture_hours': section.course.lecture_hours,
						'lab_hours': section.course.lab_hours,
						'level': section.course.level,
					},
				}
			)

		return Response({'status': 'success', 'data': data})


class ProfessorScheduleView(APIView):
	permission_classes = [ProfessorOnlyPermission]

	def get(self, request):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response(
				{'status': 'error', 'message': 'Professor profile not found'},
				status=404,
			)

		queryset = (
			Section.objects.select_related('course', 'academic_term')
			.filter(professor=profile)
			.order_by('academic_term__start_date', 'id')
		)

		academic_term_id = request.query_params.get('academic_term_id')
		if academic_term_id:
			queryset = queryset.filter(academic_term_id=academic_term_id)

		data = []
		for section in queryset:
			data.append(
				{
					'section_id': section.id,
					'course': {
						'id': section.course.id,
						'code': section.course.code,
						'name': section.course.name,
					},
					'academic_term': {
						'id': section.academic_term.id,
						'name': section.academic_term.name,
						'start_date': section.academic_term.start_date,
						'end_date': section.academic_term.end_date,
					},
					'schedule': section.schedule,
					'slots': _normalize_schedule_slots(section.schedule),
				}
			)

		return Response({'status': 'success', 'data': data})


class ProfessorSectionStudentsView(APIView):
	permission_classes = [ProfessorOnlyPermission]

	def get(self, request, section_id):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response(
				{'status': 'error', 'message': 'Professor profile not found'},
				status=404,
			)

		section = (
			_get_professor_section_or_none(profile, section_id)
		)
		if section is None:
			return Response(
				{'status': 'error', 'message': 'Section not found for this professor'},
				status=404,
			)

		enrollments = (
			CourseEnrollment.objects.select_related(
				'student__user',
				'student__faculty',
				'student__department',
				'grade',
			)
			.filter(section=section)
			.exclude(status=CourseEnrollment.EnrollmentStatus.DROPPED)
			.order_by('student__student_number')
		)

		students = []
		for enrollment in enrollments:
			student = enrollment.student
			grade = getattr(enrollment, 'grade', None)
			students.append(
				{
					'enrollment_id': enrollment.id,
					'enrollment_status': enrollment.status,
					'registered_at': enrollment.registered_at,
					'student': {
						'id': student.id,
						'student_number': student.student_number,
						'name': student.user.get_full_name() or student.user.username,
						'email': student.user.email,
						'academic_year': student.academic_year,
						'semester': student.semester,
						'enrollment_status': student.enrollment_status,
						'gpa': student.gpa,
						'academic_standing': student.academic_standing,
						'faculty': {
							'id': student.faculty.id,
							'name': student.faculty.name,
							'code': student.faculty.code,
						},
						'department': {
							'id': student.department.id,
							'name': student.department.name,
							'code': student.department.code,
						},
					},
					'grade': {
						'points': getattr(grade, 'points', None),
						'letter_grade': getattr(grade, 'letter_grade', None),
						'status': getattr(grade, 'status', None),
					},
				}
			)

		data = {
			'section': {
				'id': section.id,
				'semester': section.semester,
				'capacity': section.capacity,
				'schedule': section.schedule,
				'course': {
					'id': section.course.id,
					'code': section.course.code,
					'name': section.course.name,
				},
				'academic_term': {
					'id': section.academic_term.id,
					'name': section.academic_term.name,
					'start_date': section.academic_term.start_date,
					'end_date': section.academic_term.end_date,
				},
			},
			'students': students,
		}

		return Response({'status': 'success', 'data': data})


class ProfessorSectionGradesView(APIView):
	permission_classes = [ProfessorOnlyPermission]
	throttle_classes = [ScopedRateThrottle]

	def get_throttles(self):
		if self.request.method.upper() == 'POST':
			self.throttle_scope = 'api_grade'
			return super().get_throttles()
		return []

	def get(self, request, section_id):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response({'status': 'error', 'message': 'Professor profile not found'}, status=status.HTTP_404_NOT_FOUND)

		section = _get_professor_section_or_none(profile, section_id)
		if section is None:
			return Response(
				{'status': 'error', 'message': 'Section not found for this professor'},
				status=status.HTTP_404_NOT_FOUND,
			)

		enrollments = (
			CourseEnrollment.objects.select_related('student__user', 'grade')
			.filter(section=section)
			.exclude(status=CourseEnrollment.EnrollmentStatus.DROPPED)
			.order_by('student__student_number')
		)

		grades = []
		for enrollment in enrollments:
			grade = getattr(enrollment, 'grade', None)
			grades.append(
				{
					'enrollment_id': enrollment.id,
					'enrollment_status': enrollment.status,
					'student': {
						'id': enrollment.student.id,
						'student_number': enrollment.student.student_number,
						'name': enrollment.student.user.get_full_name() or enrollment.student.user.username,
						'email': enrollment.student.user.email,
					},
					'grade': {
						'points': getattr(grade, 'points', None),
						'letter_grade': getattr(grade, 'letter_grade', None),
						'status': getattr(grade, 'status', None),
						'updated_at': getattr(grade, 'updated_at', None),
					},
				}
			)

		data = {
			'section': {
				'id': section.id,
				'course': {
					'id': section.course.id,
					'code': section.course.code,
					'name': section.course.name,
				},
				'academic_term': {
					'id': section.academic_term.id,
					'name': section.academic_term.name,
				},
			},
			'grades': grades,
		}
		return Response({'status': 'success', 'data': data})

	def post(self, request, section_id):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response({'status': 'error', 'message': 'Professor profile not found'}, status=status.HTTP_404_NOT_FOUND)

		section = _get_professor_section_or_none(profile, section_id)
		if section is None:
			return Response(
				{'status': 'error', 'message': 'Section not found for this professor'},
				status=status.HTTP_404_NOT_FOUND,
			)

		payload = request.data
		rows = payload.get('grades') if isinstance(payload, dict) and isinstance(payload.get('grades'), list) else [payload]

		if not rows:
			return Response({'status': 'error', 'message': 'No grade rows supplied'}, status=status.HTTP_400_BAD_REQUEST)

		enrollment_ids = []
		for row in rows:
			if not isinstance(row, dict) or 'enrollment_id' not in row:
				return Response(
					{'status': 'error', 'message': 'Each row must include enrollment_id'},
					status=status.HTTP_400_BAD_REQUEST,
				)
			try:
				enrollment_ids.append(int(row['enrollment_id']))
			except (TypeError, ValueError):
				return Response(
					{'status': 'error', 'message': 'enrollment_id must be an integer'},
					status=status.HTTP_400_BAD_REQUEST,
				)

		enrollments = {
			e.id: e
			for e in CourseEnrollment.objects.select_related('student')
			.filter(id__in=enrollment_ids, section=section)
			.exclude(status=CourseEnrollment.EnrollmentStatus.DROPPED)
		}

		missing = [eid for eid in enrollment_ids if eid not in enrollments]
		if missing:
			return Response(
				{'status': 'error', 'message': 'Invalid enrollment ids for this section', 'data': {'missing_ids': missing}},
				status=status.HTTP_400_BAD_REQUEST,
			)

		valid_statuses = {choice[0] for choice in Grade.Status.choices}
		for row in rows:
			points = row.get('points')
			letter_grade = row.get('letter_grade')
			grade_status = row.get('status', Grade.Status.COMPLETE)
			if points is None or letter_grade is None:
				return Response(
					{'status': 'error', 'message': 'points and letter_grade are required for each grade row'},
					status=status.HTTP_400_BAD_REQUEST,
				)
			if grade_status not in valid_statuses:
				return Response(
					{'status': 'error', 'message': f'Invalid grade status: {grade_status}'},
					status=status.HTTP_400_BAD_REQUEST,
				)

		updated = []
		with transaction.atomic():
			for row in rows:
				enrollment_id = int(row['enrollment_id'])
				points = row.get('points')
				letter_grade = row.get('letter_grade')
				grade_status = row.get('status', Grade.Status.COMPLETE)

				grade, _created = Grade.objects.update_or_create(
					enrollment=enrollments[enrollment_id],
					defaults={
						'points': points,
						'letter_grade': letter_grade,
						'status': grade_status,
					},
				)
				updated.append(
					{
						'enrollment_id': enrollment_id,
						'grade': {
							'points': grade.points,
							'letter_grade': grade.letter_grade,
							'status': grade.status,
							'updated_at': grade.updated_at,
						},
					}
				)

		return Response(
			{
				'status': 'success',
				'message': 'Grades updated successfully',
				'data': {
					'updated_count': len(updated),
					'grades': updated,
				},
			},
			status=status.HTTP_200_OK,
		)


class ProfessorSectionAttendanceView(APIView):
	permission_classes = [ProfessorOnlyPermission]

	def get(self, request, section_id):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response({'status': 'error', 'message': 'Professor profile not found'}, status=status.HTTP_404_NOT_FOUND)

		section = _get_professor_section_or_none(profile, section_id)
		if section is None:
			return Response(
				{'status': 'error', 'message': 'Section not found for this professor'},
				status=status.HTTP_404_NOT_FOUND,
			)

		sessions = (
			AttendanceSession.objects.filter(section=section)
			.prefetch_related('records')
			.order_by('-session_date', '-id')
		)

		data = []
		for session in sessions:
			records = list(session.records.all())
			totals = {'present': 0, 'absent': 0, 'late': 0, 'excused': 0}
			for record in records:
				if record.status in totals:
					totals[record.status] += 1

			data.append(
				{
					'id': session.id,
					'session_date': session.session_date,
					'title': session.title,
					'notes': session.notes,
					'created_at': session.created_at,
					'totals': totals,
					'recorded_count': len(records),
				}
			)

		return Response({'status': 'success', 'data': data})

	def post(self, request, section_id):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response({'status': 'error', 'message': 'Professor profile not found'}, status=status.HTTP_404_NOT_FOUND)

		section = _get_professor_section_or_none(profile, section_id)
		if section is None:
			return Response(
				{'status': 'error', 'message': 'Section not found for this professor'},
				status=status.HTTP_404_NOT_FOUND,
			)

		payload = request.data if isinstance(request.data, dict) else {}
		session_date = parse_date(payload.get('session_date') or '')
		if session_date is None:
			return Response(
				{'status': 'error', 'message': 'session_date is required in YYYY-MM-DD format'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		title = payload.get('title')
		notes = payload.get('notes')
		record_rows = payload.get('records') if isinstance(payload.get('records'), list) else []

		valid_statuses = {choice[0] for choice in AttendanceRecord.Status.choices}
		record_objects = []
		if record_rows:
			enrollment_ids = []
			for row in record_rows:
				if not isinstance(row, dict) or 'enrollment_id' not in row:
					return Response(
						{'status': 'error', 'message': 'Each attendance row must include enrollment_id'},
						status=status.HTTP_400_BAD_REQUEST,
					)
				try:
					enrollment_ids.append(int(row['enrollment_id']))
				except (TypeError, ValueError):
					return Response(
						{'status': 'error', 'message': 'enrollment_id must be an integer'},
						status=status.HTTP_400_BAD_REQUEST,
					)

			enrollments = {
				e.id: e
				for e in CourseEnrollment.objects.filter(id__in=enrollment_ids, section=section).exclude(
					status=CourseEnrollment.EnrollmentStatus.DROPPED
				)
			}

			missing = [eid for eid in enrollment_ids if eid not in enrollments]
			if missing:
				return Response(
					{'status': 'error', 'message': 'Invalid enrollment ids for this section', 'data': {'missing_ids': missing}},
					status=status.HTTP_400_BAD_REQUEST,
				)

			for row in record_rows:
				enrollment_id = int(row['enrollment_id'])
				record_status = row.get('status', AttendanceRecord.Status.ABSENT)
				if record_status not in valid_statuses:
					return Response(
						{'status': 'error', 'message': f'Invalid attendance status: {record_status}'},
						status=status.HTTP_400_BAD_REQUEST,
					)
				record_objects.append(
					{
						'enrollment': enrollments[enrollment_id],
						'status': record_status,
						'note': row.get('note'),
					}
				)
		else:
			enrollments = CourseEnrollment.objects.filter(section=section).exclude(
				status=CourseEnrollment.EnrollmentStatus.DROPPED
			)
			record_objects = [
				{
					'enrollment': enrollment,
					'status': AttendanceRecord.Status.ABSENT,
					'note': None,
				}
				for enrollment in enrollments
			]

		with transaction.atomic():
			session = AttendanceSession.objects.create(
				section=section,
				created_by=profile,
				session_date=session_date,
				title=title,
				notes=notes,
			)
			AttendanceRecord.objects.bulk_create(
				[
					AttendanceRecord(
						session=session,
						enrollment=record['enrollment'],
						status=record['status'],
						note=record['note'],
					)
					for record in record_objects
				]
			)

		created_records = session.records.count()
		_enqueue_webhook_event(
			'attendance.session_created',
			{
				'session_id': session.id,
				'section_id': section.id,
				'academic_term_id': section.academic_term_id,
				'recorded_count': created_records,
				'created_by_professor_id': profile.id,
			},
		)
		return Response(
			{
				'status': 'success',
				'message': 'Attendance session created successfully',
				'data': {
					'id': session.id,
					'session_date': session.session_date,
					'title': session.title,
					'notes': session.notes,
					'recorded_count': created_records,
				},
			},
			status=status.HTTP_201_CREATED,
		)


class ProfessorSectionAttendanceSessionDetailView(APIView):
	permission_classes = [ProfessorOnlyPermission]

	def get(self, request, section_id, session_id):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response({'status': 'error', 'message': 'Professor profile not found'}, status=status.HTTP_404_NOT_FOUND)

		section = _get_professor_section_or_none(profile, section_id)
		if section is None:
			return Response(
				{'status': 'error', 'message': 'Section not found for this professor'},
				status=status.HTTP_404_NOT_FOUND,
			)

		session = (
			AttendanceSession.objects.filter(id=session_id, section=section)
			.prefetch_related('records__enrollment__student__user')
			.first()
		)
		if session is None:
			return Response({'status': 'error', 'message': 'Attendance session not found'}, status=status.HTTP_404_NOT_FOUND)

		records = _attendance_records_payload(session)
		totals = {'present': 0, 'absent': 0, 'late': 0, 'excused': 0}
		for record in records:
			if record['status'] in totals:
				totals[record['status']] += 1

		_enqueue_webhook_event(
			'attendance.session_updated',
			{
				'session_id': session.id,
				'section_id': section.id,
				'academic_term_id': section.academic_term_id,
				'recorded_count': len(records),
				'updated_by_professor_id': profile.id,
			},
		)

		return Response(
			{
				'status': 'success',
				'data': {
					'id': session.id,
					'section_id': section.id,
					'session_date': session.session_date,
					'title': session.title,
					'notes': session.notes,
					'created_at': session.created_at,
					'updated_at': session.updated_at,
					'totals': totals,
					'recorded_count': len(records),
					'records': records,
				},
			}
		)

	def put(self, request, section_id, session_id):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response({'status': 'error', 'message': 'Professor profile not found'}, status=status.HTTP_404_NOT_FOUND)

		section = _get_professor_section_or_none(profile, section_id)
		if section is None:
			return Response(
				{'status': 'error', 'message': 'Section not found for this professor'},
				status=status.HTTP_404_NOT_FOUND,
			)

		session = AttendanceSession.objects.filter(id=session_id, section=section).first()
		if session is None:
			return Response({'status': 'error', 'message': 'Attendance session not found'}, status=status.HTTP_404_NOT_FOUND)

		payload = request.data if isinstance(request.data, dict) else {}

		new_date = parse_date(payload.get('session_date')) if payload.get('session_date') is not None else None
		if payload.get('session_date') is not None and new_date is None:
			return Response(
				{'status': 'error', 'message': 'session_date must be YYYY-MM-DD when provided'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		record_rows = payload.get('records') if isinstance(payload.get('records'), list) else None
		valid_statuses = {choice[0] for choice in AttendanceRecord.Status.choices}
		record_updates = []
		if record_rows is not None:
			enrollment_ids = []
			for row in record_rows:
				if not isinstance(row, dict) or 'enrollment_id' not in row:
					return Response(
						{'status': 'error', 'message': 'Each attendance row must include enrollment_id'},
						status=status.HTTP_400_BAD_REQUEST,
					)
				try:
					enrollment_ids.append(int(row['enrollment_id']))
				except (TypeError, ValueError):
					return Response(
						{'status': 'error', 'message': 'enrollment_id must be an integer'},
						status=status.HTTP_400_BAD_REQUEST,
					)

			enrollments = {
				e.id: e
				for e in CourseEnrollment.objects.filter(id__in=enrollment_ids, section=section).exclude(
					status=CourseEnrollment.EnrollmentStatus.DROPPED
				)
			}
			missing = [eid for eid in enrollment_ids if eid not in enrollments]
			if missing:
				return Response(
					{'status': 'error', 'message': 'Invalid enrollment ids for this section', 'data': {'missing_ids': missing}},
					status=status.HTTP_400_BAD_REQUEST,
				)

			for row in record_rows:
				enrollment_id = int(row['enrollment_id'])
				record_status = row.get('status', AttendanceRecord.Status.ABSENT)
				if record_status not in valid_statuses:
					return Response(
						{'status': 'error', 'message': f'Invalid attendance status: {record_status}'},
						status=status.HTTP_400_BAD_REQUEST,
					)
				record_updates.append(
					{
						'enrollment': enrollments[enrollment_id],
						'status': record_status,
						'note': row.get('note'),
					}
				)

		with transaction.atomic():
			if new_date is not None:
				session.session_date = new_date
			if 'title' in payload:
				session.title = payload.get('title')
			if 'notes' in payload:
				session.notes = payload.get('notes')
			session.save()

			if record_updates is not None and len(record_updates) > 0:
				for row in record_updates:
					AttendanceRecord.objects.update_or_create(
						session=session,
						enrollment=row['enrollment'],
						defaults={
							'status': row['status'],
							'note': row['note'],
						},
					)

		session = AttendanceSession.objects.filter(id=session.id).prefetch_related('records__enrollment__student__user').first()
		records = _attendance_records_payload(session)
		totals = {'present': 0, 'absent': 0, 'late': 0, 'excused': 0}
		for record in records:
			if record['status'] in totals:
				totals[record['status']] += 1

		return Response(
			{
				'status': 'success',
				'message': 'Attendance session updated successfully',
				'data': {
					'id': session.id,
					'session_date': session.session_date,
					'title': session.title,
					'notes': session.notes,
					'totals': totals,
					'recorded_count': len(records),
				},
			}
		)


class ProfessorSectionAnnouncementsView(APIView):
	permission_classes = [ProfessorOnlyPermission]

	def get(self, request, section_id):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response({'status': 'error', 'message': 'Professor profile not found'}, status=status.HTTP_404_NOT_FOUND)

		section = _get_professor_section_or_none(profile, section_id)
		if section is None:
			return Response(
				{'status': 'error', 'message': 'Section not found for this professor'},
				status=status.HTTP_404_NOT_FOUND,
			)

		announcements = (
			SectionAnnouncement.objects.select_related('created_by__user')
			.filter(section=section)
			.order_by('-is_pinned', '-published_at', '-id')
		)

		data = [
			{
				'id': ann.id,
				'title': ann.title,
				'body': ann.body,
				'is_pinned': ann.is_pinned,
				'published_at': ann.published_at,
				'updated_at': ann.updated_at,
				'created_by': {
					'id': ann.created_by.id,
					'name': ann.created_by.user.get_full_name() or ann.created_by.user.username,
					'staff_number': ann.created_by.staff_number,
				},
			}
			for ann in announcements
		]
		return Response({'status': 'success', 'data': data})

	def post(self, request, section_id):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response({'status': 'error', 'message': 'Professor profile not found'}, status=status.HTTP_404_NOT_FOUND)

		section = _get_professor_section_or_none(profile, section_id)
		if section is None:
			return Response(
				{'status': 'error', 'message': 'Section not found for this professor'},
				status=status.HTTP_404_NOT_FOUND,
			)

		payload = request.data if isinstance(request.data, dict) else {}
		title = payload.get('title')
		body = payload.get('body')
		if not title or not body:
			return Response(
				{'status': 'error', 'message': 'title and body are required'},
				status=status.HTTP_400_BAD_REQUEST,
			)

		announcement = SectionAnnouncement.objects.create(
			section=section,
			created_by=profile,
			title=str(title).strip(),
			body=str(body),
			is_pinned=bool(payload.get('is_pinned', False)),
		)

		enrolled_student_user_ids = list(
			CourseEnrollment.objects.filter(section=section)
			.exclude(status=CourseEnrollment.EnrollmentStatus.DROPPED)
			.values_list('student__user_id', flat=True)
		)
		Notification.objects.bulk_create(
			[
				Notification(
					recipient_id=user_id,
					title=f'New announcement: {announcement.title}',
					body=announcement.body,
					notification_type='section_announcement',
					payload={
						'announcement_id': announcement.id,
						'section_id': section.id,
						'course_id': section.course_id,
					},
				)
				for user_id in enrolled_student_user_ids
			],
		)
		_enqueue_webhook_event(
			'announcement.created',
			{
				'announcement_id': announcement.id,
				'section_id': section.id,
				'academic_term_id': section.academic_term_id,
				'created_by_professor_id': profile.id,
				'is_pinned': announcement.is_pinned,
			},
		)

		return Response(
			{
				'status': 'success',
				'message': 'Announcement created successfully',
				'data': {
					'id': announcement.id,
					'title': announcement.title,
					'body': announcement.body,
					'is_pinned': announcement.is_pinned,
					'published_at': announcement.published_at,
				},
			},
			status=status.HTTP_201_CREATED,
		)


class ProfessorSectionAnnouncementDeleteView(APIView):
	permission_classes = [ProfessorOnlyPermission]

	def delete(self, request, section_id, announcement_id):
		profile = _get_professor_profile_or_none(request.user)
		if profile is None:
			return Response({'status': 'error', 'message': 'Professor profile not found'}, status=status.HTTP_404_NOT_FOUND)

		section = _get_professor_section_or_none(profile, section_id)
		if section is None:
			return Response(
				{'status': 'error', 'message': 'Section not found for this professor'},
				status=status.HTTP_404_NOT_FOUND,
			)

		announcement = SectionAnnouncement.objects.filter(id=announcement_id, section=section).first()
		if announcement is None:
			return Response({'status': 'error', 'message': 'Announcement not found'}, status=status.HTTP_404_NOT_FOUND)

		event_payload = {
			'announcement_id': announcement.id,
			'section_id': section.id,
			'academic_term_id': section.academic_term_id,
			'deleted_by_professor_id': profile.id,
		}

		announcement.delete()
		_enqueue_webhook_event('announcement.deleted', event_payload)
		return Response({'status': 'success', 'message': 'Announcement deleted successfully'}, status=status.HTTP_200_OK)
