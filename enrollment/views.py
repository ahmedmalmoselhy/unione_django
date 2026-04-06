from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasAnyRole
from academics.models import AcademicTerm, Grade, Section

from .models import CourseEnrollment
from .services import (
	build_student_academic_history,
	build_student_schedule,
	build_student_schedule_ics,
	build_student_transcript,
	build_student_transcript_pdf_bytes,
)
from .serializers import EnrollmentSerializer, GradeSerializer, StudentProfileSerializer


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
			Section.objects.select_related('course', 'academic_term')
			.filter(id=section_id, professor=profile)
			.first()
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
