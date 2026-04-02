from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasAnyRole
from academics.models import Grade

from .models import CourseEnrollment
from .serializers import EnrollmentSerializer, GradeSerializer, StudentProfileSerializer


class StudentOnlyPermission(HasAnyRole):
	required_roles = ['student']


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
