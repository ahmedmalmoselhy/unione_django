from django.core.cache import cache
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CanViewOrganization
from enrollment.caching import cache_key, get_cached, set_cached

from .models import Department, Faculty, University
from .serializers import DepartmentSerializer, FacultySerializer, UniversitySerializer


def _role_scope_ids(user, scope_name):
	return list(user.user_roles.filter(scope=scope_name).values_list('scope_id', flat=True))


class UniversityView(APIView):
	permission_classes = [CanViewOrganization]

	def get(self, request):
		queryset = University.objects.all().order_by('id')
		if not request.user.is_superuser:
			university_scope_ids = _role_scope_ids(request.user, 'university')
			faculty_scope_ids = _role_scope_ids(request.user, 'faculty')
			department_scope_ids = _role_scope_ids(request.user, 'department')
			if university_scope_ids or faculty_scope_ids or department_scope_ids:
				queryset = (
					queryset.filter(id__in=university_scope_ids)
					| queryset.filter(faculties__id__in=faculty_scope_ids)
					| queryset.filter(faculties__departments__id__in=department_scope_ids)
				).distinct()
		data = UniversitySerializer(queryset, many=True).data
		return Response({'status': 'success', 'data': data})


class FacultyView(APIView):
	permission_classes = [CanViewOrganization]

	def get(self, request):
		queryset = Faculty.objects.select_related('university').all().order_by('id')
		if not request.user.is_superuser:
			faculty_scope_ids = _role_scope_ids(request.user, 'faculty')
			university_scope_ids = _role_scope_ids(request.user, 'university')
			if faculty_scope_ids or university_scope_ids:
				queryset = queryset.filter(id__in=faculty_scope_ids) | queryset.filter(university_id__in=university_scope_ids)
		data = FacultySerializer(queryset.distinct(), many=True).data
		return Response({'status': 'success', 'data': data})


class DepartmentView(APIView):
	permission_classes = [CanViewOrganization]

	def get(self, request):
		queryset = Department.objects.select_related('faculty', 'faculty__university').all().order_by('id')
		if not request.user.is_superuser:
			department_scope_ids = _role_scope_ids(request.user, 'department')
			faculty_scope_ids = _role_scope_ids(request.user, 'faculty')
			university_scope_ids = _role_scope_ids(request.user, 'university')

			if department_scope_ids or faculty_scope_ids or university_scope_ids:
				queryset = (
					queryset.filter(id__in=department_scope_ids)
					| queryset.filter(faculty_id__in=faculty_scope_ids)
					| queryset.filter(faculty__university_id__in=university_scope_ids)
				)
		data = DepartmentSerializer(queryset.distinct(), many=True).data
		return Response({'status': 'success', 'data': data})
