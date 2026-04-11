from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import (
    AcademicTerm,
    Course,
    ExamSchedule,
    GroupProject,
    GroupProjectMember,
    Section,
    SectionTeachingAssistant,
)
from accounts.permissions import HasAnyRole
from enrollment.models import CourseEnrollment, ProfessorProfile, StudentProfile
from organization.models import Department, Faculty, University


class AdminOnlyPermission(HasAnyRole):
    required_roles = ['admin', 'faculty_admin', 'department_admin']


def _is_super_admin(user):
    return user.is_superuser or user.user_roles.filter(role__slug='admin').exists()


def _get_user_scopes(user):
    """Return dict of scopes the user has admin access to."""
    scopes = {'is_super': _is_super_admin(user), 'faculties': set(), 'departments': set()}
    for ur in user.user_roles.select_related('role'):
        if ur.role.slug == 'faculty_admin' and ur.scope == 'faculty' and ur.scope_id:
            scopes['faculties'].add(ur.scope_id)
        elif ur.role.slug == 'department_admin' and ur.scope == 'department' and ur.scope_id:
            scopes['departments'].add(ur.scope_id)
    return scopes


def _filter_faculties_by_scope(queryset, user):
    scopes = _get_user_scopes(user)
    if scopes['is_super']:
        return queryset
    if scopes['faculties']:
        return queryset.filter(id__in=scopes['faculties'])
    return queryset.none()


def _filter_departments_by_scope(queryset, user):
    scopes = _get_user_scopes(user)
    if scopes['is_super']:
        return queryset
    if scopes['departments']:
        return queryset.filter(id__in=scopes['departments'])
    if scopes['faculties']:
        return queryset.filter(faculty_id__in=scopes['faculties'])
    return queryset.none()


class AdminFacultiesView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = Faculty.objects.select_related('university').order_by('name')
        queryset = _filter_faculties_by_scope(queryset, request.user)

        university_id = request.query_params.get('university_id')
        if university_id:
            queryset = queryset.filter(university_id=university_id)

        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)

        data = [
            {
                'id': f.id,
                'name': f.name,
                'name_ar': f.name_ar,
                'code': f.code,
                'university': {'id': f.university.id, 'name': f.university.name, 'code': f.university.code},
                'created_at': f.created_at,
                'updated_at': f.updated_at,
            }
            for f in queryset
        ]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        if not _is_super_admin(request.user):
            return Response(
                {'status': 'error', 'message': 'Super admin required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = request.data if isinstance(request.data, dict) else {}
        required = ['name', 'code', 'university_id']
        for field in required:
            if not payload.get(field):
                return Response(
                    {'status': 'error', 'message': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        university = University.objects.filter(id=payload['university_id']).first()
        if not university:
            return Response(
                {'status': 'error', 'message': 'University not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if Faculty.objects.filter(university=university, code=payload['code']).exists():
            return Response(
                {'status': 'error', 'message': 'Faculty code already exists for this university'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        faculty = Faculty.objects.create(
            university=university,
            name=payload['name'],
            name_ar=payload.get('name_ar'),
            code=payload['code'],
            logo_path=payload.get('logo_path'),
        )

        return Response(
            {
                'status': 'success',
                'message': 'Faculty created successfully',
                'data': {
                    'id': faculty.id,
                    'name': faculty.name,
                    'code': faculty.code,
                    'university_id': faculty.university_id,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class AdminFacultyDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, faculty_id):
        faculty = Faculty.objects.filter(id=faculty_id).select_related('university').first()
        if not faculty:
            return Response({'status': 'error', 'message': 'Faculty not found'}, status=status.HTTP_404_NOT_FOUND)

        scopes = _get_user_scopes(request.user)
        if not scopes['is_super'] and faculty.id not in scopes['faculties']:
            return Response({'status': 'error', 'message': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        data = {
            'id': faculty.id,
            'name': faculty.name,
            'name_ar': faculty.name_ar,
            'code': faculty.code,
            'logo_path': faculty.logo_path,
            'university': {'id': faculty.university.id, 'name': faculty.university.name},
            'created_at': faculty.created_at,
            'updated_at': faculty.updated_at,
        }
        return Response({'status': 'success', 'data': data})

    def patch(self, request, faculty_id):
        if not _is_super_admin(request.user):
            return Response(
                {'status': 'error', 'message': 'Super admin required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        faculty = Faculty.objects.filter(id=faculty_id).first()
        if not faculty:
            return Response({'status': 'error', 'message': 'Faculty not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        updatable = ['name', 'name_ar', 'logo_path']
        updated = []
        for field in updatable:
            if field in payload:
                setattr(faculty, field, payload[field])
                updated.append(field)

        if updated:
            faculty.save(update_fields=updated + ['updated_at'])

        return Response({'status': 'success', 'message': 'Faculty updated successfully'})

    def delete(self, request, faculty_id):
        if not _is_super_admin(request.user):
            return Response(
                {'status': 'error', 'message': 'Super admin required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        faculty = Faculty.objects.filter(id=faculty_id).first()
        if not faculty:
            return Response({'status': 'error', 'message': 'Faculty not found'}, status=status.HTTP_404_NOT_FOUND)

        faculty.delete()
        return Response({'status': 'success', 'message': 'Faculty deleted successfully'})


class AdminDepartmentsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = Department.objects.select_related('faculty__university').order_by('faculty__name', 'name')
        queryset = _filter_departments_by_scope(queryset, request.user)

        faculty_id = request.query_params.get('faculty_id')
        if faculty_id:
            queryset = queryset.filter(faculty_id=faculty_id)

        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)

        data = [
            {
                'id': d.id,
                'name': d.name,
                'name_ar': d.name_ar,
                'code': d.code,
                'scope': d.scope,
                'is_mandatory': d.is_mandatory,
                'required_credit_hours': d.required_credit_hours,
                'faculty': {'id': d.faculty.id, 'name': d.faculty.name, 'code': d.faculty.code},
                'created_at': d.created_at,
                'updated_at': d.updated_at,
            }
            for d in queryset
        ]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        scopes = _get_user_scopes(request.user)
        if not scopes['is_super'] and not scopes['faculties']:
            return Response(
                {'status': 'error', 'message': 'Permission denied'},
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = request.data if isinstance(request.data, dict) else {}
        required = ['name', 'code', 'faculty_id']
        for field in required:
            if not payload.get(field):
                return Response(
                    {'status': 'error', 'message': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        faculty_id = payload['faculty_id']
        if not scopes['is_super'] and faculty_id not in scopes['faculties']:
            return Response(
                {'status': 'error', 'message': 'Cannot create department in this faculty'},
                status=status.HTTP_403_FORBIDDEN,
            )

        faculty = Faculty.objects.filter(id=faculty_id).first()
        if not faculty:
            return Response(
                {'status': 'error', 'message': 'Faculty not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if Department.objects.filter(faculty=faculty, code=payload['code']).exists():
            return Response(
                {'status': 'error', 'message': 'Department code already exists for this faculty'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        department = Department.objects.create(
            faculty=faculty,
            name=payload['name'],
            name_ar=payload.get('name_ar'),
            code=payload['code'],
            scope=payload.get('scope', Department.Scope.DEPARTMENT),
            is_mandatory=payload.get('is_mandatory', False),
            required_credit_hours=payload.get('required_credit_hours'),
            logo_path=payload.get('logo_path'),
        )

        return Response(
            {
                'status': 'success',
                'message': 'Department created successfully',
                'data': {
                    'id': department.id,
                    'name': department.name,
                    'code': department.code,
                    'faculty_id': department.faculty_id,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class AdminDepartmentDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, department_id):
        dept = Department.objects.filter(id=department_id).select_related('faculty__university').first()
        if not dept:
            return Response({'status': 'error', 'message': 'Department not found'}, status=status.HTTP_404_NOT_FOUND)

        scopes = _get_user_scopes(request.user)
        if not scopes['is_super'] and dept.id not in scopes['departments'] and dept.faculty_id not in scopes['faculties']:
            return Response({'status': 'error', 'message': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        data = {
            'id': dept.id,
            'name': dept.name,
            'name_ar': dept.name_ar,
            'code': dept.code,
            'scope': dept.scope,
            'is_mandatory': dept.is_mandatory,
            'required_credit_hours': dept.required_credit_hours,
            'faculty': {'id': dept.faculty.id, 'name': dept.faculty.name},
            'created_at': dept.created_at,
            'updated_at': dept.updated_at,
        }
        return Response({'status': 'success', 'data': data})

    def patch(self, request, department_id):
        dept = Department.objects.filter(id=department_id).first()
        if not dept:
            return Response({'status': 'error', 'message': 'Department not found'}, status=status.HTTP_404_NOT_FOUND)

        scopes = _get_user_scopes(request.user)
        if not scopes['is_super'] and dept.id not in scopes['departments'] and dept.faculty_id not in scopes['faculties']:
            return Response({'status': 'error', 'message': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data if isinstance(request.data, dict) else {}
        updatable = ['name', 'name_ar', 'scope', 'is_mandatory', 'required_credit_hours', 'logo_path']
        updated = []
        for field in updatable:
            if field in payload:
                setattr(dept, field, payload[field])
                updated.append(field)

        if updated:
            dept.save(update_fields=updated + ['updated_at'])

        return Response({'status': 'success', 'message': 'Department updated successfully'})

    def delete(self, request, department_id):
        dept = Department.objects.filter(id=department_id).first()
        if not dept:
            return Response({'status': 'error', 'message': 'Department not found'}, status=status.HTTP_404_NOT_FOUND)

        scopes = _get_user_scopes(request.user)
        if not scopes['is_super'] and dept.faculty_id not in scopes['faculties']:
            return Response({'status': 'error', 'message': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)

        dept.delete()
        return Response({'status': 'success', 'message': 'Department deleted successfully'})


class AdminAcademicTermsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = AcademicTerm.objects.order_by('-start_date')

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        data = [
            {
                'id': t.id,
                'name': t.name,
                'start_date': t.start_date,
                'end_date': t.end_date,
                'registration_start': t.registration_start,
                'registration_end': t.registration_end,
                'is_active': t.is_active,
                'created_at': t.created_at,
                'updated_at': t.updated_at,
            }
            for t in queryset
        ]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        if not _is_super_admin(request.user):
            return Response(
                {'status': 'error', 'message': 'Super admin required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = request.data if isinstance(request.data, dict) else {}
        required = ['name', 'start_date', 'end_date', 'registration_start', 'registration_end']
        for field in required:
            if not payload.get(field):
                return Response(
                    {'status': 'error', 'message': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        term = AcademicTerm.objects.create(
            name=payload['name'],
            start_date=payload['start_date'],
            end_date=payload['end_date'],
            registration_start=payload['registration_start'],
            registration_end=payload['registration_end'],
            is_active=payload.get('is_active', False),
        )

        return Response(
            {
                'status': 'success',
                'message': 'Academic term created successfully',
                'data': {
                    'id': term.id,
                    'name': term.name,
                    'is_active': term.is_active,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class AdminAcademicTermDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, term_id):
        term = AcademicTerm.objects.filter(id=term_id).first()
        if not term:
            return Response({'status': 'error', 'message': 'Academic term not found'}, status=status.HTTP_404_NOT_FOUND)

        data = {
            'id': term.id,
            'name': term.name,
            'start_date': term.start_date,
            'end_date': term.end_date,
            'registration_start': term.registration_start,
            'registration_end': term.registration_end,
            'is_active': term.is_active,
            'created_at': term.created_at,
            'updated_at': term.updated_at,
        }
        return Response({'status': 'success', 'data': data})

    def patch(self, request, term_id):
        if not _is_super_admin(request.user):
            return Response(
                {'status': 'error', 'message': 'Super admin required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        term = AcademicTerm.objects.filter(id=term_id).first()
        if not term:
            return Response({'status': 'error', 'message': 'Academic term not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        updatable = ['name', 'start_date', 'end_date', 'registration_start', 'registration_end', 'is_active']
        updated = []
        for field in updatable:
            if field in payload:
                setattr(term, field, payload[field])
                updated.append(field)

        if updated:
            term.save(update_fields=updated + ['updated_at'])

        return Response({'status': 'success', 'message': 'Academic term updated successfully'})

    def delete(self, request, term_id):
        if not _is_super_admin(request.user):
            return Response(
                {'status': 'error', 'message': 'Super admin required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        term = AcademicTerm.objects.filter(id=term_id).first()
        if not term:
            return Response({'status': 'error', 'message': 'Academic term not found'}, status=status.HTTP_404_NOT_FOUND)

        term.delete()
        return Response({'status': 'success', 'message': 'Academic term deleted successfully'})


class AdminCoursesView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = Course.objects.order_by('code')

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        level = request.query_params.get('level')
        if level:
            queryset = queryset.filter(level=level)

        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search) | queryset.filter(code__icontains=search)

        data = [
            {
                'id': c.id,
                'code': c.code,
                'name': c.name,
                'name_ar': c.name_ar,
                'description': c.description,
                'credit_hours': c.credit_hours,
                'lecture_hours': c.lecture_hours,
                'lab_hours': c.lab_hours,
                'level': c.level,
                'is_elective': c.is_elective,
                'is_active': c.is_active,
                'created_at': c.created_at,
                'updated_at': c.updated_at,
            }
            for c in queryset
        ]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        required = ['code', 'name', 'credit_hours']
        for field in required:
            if not payload.get(field):
                return Response(
                    {'status': 'error', 'message': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if Course.objects.filter(code=payload['code']).exists():
            return Response(
                {'status': 'error', 'message': 'Course code already exists'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        course = Course.objects.create(
            code=payload['code'],
            name=payload['name'],
            name_ar=payload.get('name_ar'),
            description=payload.get('description'),
            credit_hours=payload['credit_hours'],
            lecture_hours=payload.get('lecture_hours', 0),
            lab_hours=payload.get('lab_hours', 0),
            level=payload.get('level', 100),
            is_elective=payload.get('is_elective', False),
            is_active=payload.get('is_active', True),
        )

        return Response(
            {
                'status': 'success',
                'message': 'Course created successfully',
                'data': {'id': course.id, 'code': course.code, 'name': course.name},
            },
            status=status.HTTP_201_CREATED,
        )


class AdminCourseDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, course_id):
        course = Course.objects.filter(id=course_id).first()
        if not course:
            return Response({'status': 'error', 'message': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        data = {
            'id': course.id,
            'code': course.code,
            'name': course.name,
            'name_ar': course.name_ar,
            'description': course.description,
            'credit_hours': course.credit_hours,
            'lecture_hours': course.lecture_hours,
            'lab_hours': course.lab_hours,
            'level': course.level,
            'is_elective': course.is_elective,
            'is_active': course.is_active,
            'created_at': course.created_at,
            'updated_at': course.updated_at,
        }
        return Response({'status': 'success', 'data': data})

    def patch(self, request, course_id):
        course = Course.objects.filter(id=course_id).first()
        if not course:
            return Response({'status': 'error', 'message': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        updatable = ['name', 'name_ar', 'description', 'credit_hours', 'lecture_hours', 'lab_hours', 'level', 'is_elective', 'is_active']
        updated = []
        for field in updatable:
            if field in payload:
                setattr(course, field, payload[field])
                updated.append(field)

        if updated:
            course.save(update_fields=updated + ['updated_at'])

        return Response({'status': 'success', 'message': 'Course updated successfully'})

    def delete(self, request, course_id):
        if not _is_super_admin(request.user):
            return Response(
                {'status': 'error', 'message': 'Super admin required'},
                status=status.HTTP_403_FORBIDDEN,
            )

        course = Course.objects.filter(id=course_id).first()
        if not course:
            return Response({'status': 'error', 'message': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)

        course.delete()
        return Response({'status': 'success', 'message': 'Course deleted successfully'})


class AdminSectionsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = Section.objects.select_related('course', 'academic_term', 'professor__user').order_by('-id')

        course_id = request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        term_id = request.query_params.get('academic_term_id')
        if term_id:
            queryset = queryset.filter(academic_term_id=term_id)

        professor_id = request.query_params.get('professor_id')
        if professor_id:
            queryset = queryset.filter(professor_id=professor_id)

        data = [
            {
                'id': s.id,
                'course': {'id': s.course.id, 'code': s.course.code, 'name': s.course.name},
                'academic_term': {'id': s.academic_term.id, 'name': s.academic_term.name},
                'professor': {
                    'id': s.professor.id,
                    'name': s.professor.user.get_full_name() or s.professor.user.username,
                    'staff_number': s.professor.staff_number,
                },
                'semester': s.semester,
                'capacity': s.capacity,
                'schedule': s.schedule,
                'created_at': s.created_at,
                'updated_at': s.updated_at,
            }
            for s in queryset
        ]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        required = ['course_id', 'professor_id', 'academic_term_id']
        for field in required:
            if not payload.get(field):
                return Response(
                    {'status': 'error', 'message': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        course = Course.objects.filter(id=payload['course_id']).first()
        if not course:
            return Response(
                {'status': 'error', 'message': 'Course not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        professor = ProfessorProfile.objects.filter(id=payload['professor_id']).first()
        if not professor:
            return Response(
                {'status': 'error', 'message': 'Professor not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        term = AcademicTerm.objects.filter(id=payload['academic_term_id']).first()
        if not term:
            return Response(
                {'status': 'error', 'message': 'Academic term not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        section = Section.objects.create(
            course=course,
            professor=professor,
            academic_term=term,
            semester=payload.get('semester', 1),
            capacity=payload.get('capacity', 0),
            schedule=payload.get('schedule', {}),
        )

        return Response(
            {
                'status': 'success',
                'message': 'Section created successfully',
                'data': {'id': section.id, 'course_id': section.course_id, 'academic_term_id': section.academic_term_id},
            },
            status=status.HTTP_201_CREATED,
        )


class AdminSectionDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, section_id):
        section = Section.objects.filter(id=section_id).select_related('course', 'academic_term', 'professor__user').first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        data = {
            'id': section.id,
            'course': {'id': section.course.id, 'code': section.course.code, 'name': section.course.name},
            'academic_term': {'id': section.academic_term.id, 'name': section.academic_term.name},
            'professor': {
                'id': section.professor.id,
                'name': section.professor.user.get_full_name() or section.professor.user.username,
                'staff_number': section.professor.staff_number,
            },
            'semester': section.semester,
            'capacity': section.capacity,
            'schedule': section.schedule,
            'created_at': section.created_at,
            'updated_at': section.updated_at,
        }
        return Response({'status': 'success', 'data': data})

    def patch(self, request, section_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}

        if 'professor_id' in payload:
            professor = ProfessorProfile.objects.filter(id=payload['professor_id']).first()
            if not professor:
                return Response(
                    {'status': 'error', 'message': 'Professor not found'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            section.professor = professor

        updatable = ['semester', 'capacity', 'schedule']
        updated = []
        for field in updatable:
            if field in payload:
                setattr(section, field, payload[field])
                updated.append(field)

        if updated or 'professor_id' in payload:
            section.save(update_fields=['professor'] + updated + ['updated_at'])

        return Response({'status': 'success', 'message': 'Section updated successfully'})

    def delete(self, request, section_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        section.delete()
        return Response({'status': 'success', 'message': 'Section deleted successfully'})


class AdminSectionTeachingAssistantsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, section_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        assignments = (
            SectionTeachingAssistant.objects
            .filter(section_id=section_id)
            .select_related('professor__user')
            .order_by('id')
        )
        data = [
            {
                'id': assignment.id,
                'section_id': assignment.section_id,
                'professor': {
                    'id': assignment.professor_id,
                    'staff_number': assignment.professor.staff_number,
                    'name': assignment.professor.user.get_full_name() or assignment.professor.user.username,
                },
                'assigned_by_user_id': assignment.assigned_by_id,
                'created_at': assignment.created_at,
                'updated_at': assignment.updated_at,
            }
            for assignment in assignments
        ]
        return Response({'status': 'success', 'data': data})

    def post(self, request, section_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        professor_id = payload.get('professor_id')
        if not professor_id:
            return Response(
                {'status': 'error', 'message': 'professor_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        professor = ProfessorProfile.objects.filter(id=professor_id).select_related('user').first()
        if not professor:
            return Response(
                {'status': 'error', 'message': 'Professor not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        assignment, created = SectionTeachingAssistant.objects.get_or_create(
            section=section,
            professor=professor,
            defaults={'assigned_by': request.user},
        )

        message = 'Teaching assistant assigned successfully' if created else 'Teaching assistant already assigned'
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            {
                'status': 'success',
                'message': message,
                'data': {
                    'id': assignment.id,
                    'section_id': assignment.section_id,
                    'professor_id': assignment.professor_id,
                },
            },
            status=response_status,
        )


class AdminSectionTeachingAssistantDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def delete(self, request, section_id, ta_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        assignment = SectionTeachingAssistant.objects.filter(id=ta_id, section_id=section_id).first()
        if not assignment:
            return Response(
                {'status': 'error', 'message': 'Teaching assistant assignment not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        assignment.delete()
        return Response({'status': 'success', 'message': 'Teaching assistant removed successfully'})


class AdminSectionExamScheduleView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, section_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        schedule = ExamSchedule.objects.filter(section_id=section_id).first()
        if not schedule:
            return Response({'status': 'error', 'message': 'Exam schedule not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response(
            {
                'status': 'success',
                'data': {
                    'id': schedule.id,
                    'section_id': schedule.section_id,
                    'exam_date': schedule.exam_date,
                    'start_time': schedule.start_time,
                    'end_time': schedule.end_time,
                    'location': schedule.location,
                    'is_published': schedule.is_published,
                    'published_at': schedule.published_at,
                    'created_at': schedule.created_at,
                    'updated_at': schedule.updated_at,
                },
            }
        )

    def post(self, request, section_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        if ExamSchedule.objects.filter(section_id=section_id).exists():
            return Response(
                {'status': 'error', 'message': 'Exam schedule already exists for this section'},
                status=status.HTTP_409_CONFLICT,
            )

        payload = request.data if isinstance(request.data, dict) else {}
        required = ['exam_date', 'start_time', 'end_time']
        for field in required:
            if not payload.get(field):
                return Response(
                    {'status': 'error', 'message': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        schedule = ExamSchedule.objects.create(
            section=section,
            exam_date=payload['exam_date'],
            start_time=payload['start_time'],
            end_time=payload['end_time'],
            location=payload.get('location'),
        )

        return Response(
            {
                'status': 'success',
                'message': 'Exam schedule created successfully',
                'data': {'id': schedule.id, 'section_id': schedule.section_id, 'is_published': schedule.is_published},
            },
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request, section_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        schedule = ExamSchedule.objects.filter(section_id=section_id).first()
        if not schedule:
            return Response({'status': 'error', 'message': 'Exam schedule not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        updatable = ['exam_date', 'start_time', 'end_time', 'location']
        updated = []
        for field in updatable:
            if field in payload:
                setattr(schedule, field, payload[field])
                updated.append(field)

        if updated:
            if schedule.is_published:
                schedule.is_published = False
                schedule.published_at = None
                updated.extend(['is_published', 'published_at'])
            schedule.save(update_fields=list(dict.fromkeys(updated + ['updated_at'])))

        return Response({'status': 'success', 'message': 'Exam schedule updated successfully'})


class AdminSectionExamSchedulePublishView(APIView):
    permission_classes = [AdminOnlyPermission]

    def post(self, request, section_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        schedule = ExamSchedule.objects.filter(section_id=section_id).first()
        if not schedule:
            return Response({'status': 'error', 'message': 'Exam schedule not found'}, status=status.HTTP_404_NOT_FOUND)

        schedule.is_published = True
        schedule.published_at = timezone.now()
        schedule.save(update_fields=['is_published', 'published_at', 'updated_at'])

        return Response(
            {
                'status': 'success',
                'message': 'Exam schedule published successfully',
                'data': {
                    'id': schedule.id,
                    'section_id': schedule.section_id,
                    'is_published': schedule.is_published,
                    'published_at': schedule.published_at,
                },
            }
        )


class AdminSectionGroupProjectsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, section_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        projects = (
            GroupProject.objects
            .filter(section_id=section_id)
            .prefetch_related('members__student__user')
            .order_by('id')
        )

        data = [
            {
                'id': project.id,
                'section_id': project.section_id,
                'title': project.title,
                'description': project.description,
                'due_at': project.due_at,
                'max_members': project.max_members,
                'is_active': project.is_active,
                'created_by_user_id': project.created_by_id,
                'created_at': project.created_at,
                'updated_at': project.updated_at,
                'members': [
                    {
                        'id': member.id,
                        'student_id': member.student_id,
                        'student_number': member.student.student_number,
                        'student_name': member.student.user.get_full_name() or member.student.user.username,
                        'joined_at': member.joined_at,
                    }
                    for member in project.members.all().order_by('id')
                ],
            }
            for project in projects
        ]

        return Response({'status': 'success', 'data': data})

    def post(self, request, section_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        title = payload.get('title')
        if not title:
            return Response({'status': 'error', 'message': 'title is required'}, status=status.HTTP_400_BAD_REQUEST)

        max_members_raw = payload.get('max_members', 5)
        try:
            max_members = int(max_members_raw)
            if max_members <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response({'status': 'error', 'message': 'max_members must be a positive integer'}, status=status.HTTP_400_BAD_REQUEST)

        due_at = None
        if payload.get('due_at') is not None:
            due_at = parse_datetime(str(payload.get('due_at')))
            if due_at is None:
                return Response(
                    {'status': 'error', 'message': 'due_at must be a valid ISO-8601 datetime'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        is_active = True
        if 'is_active' in payload:
            if isinstance(payload['is_active'], bool):
                is_active = payload['is_active']
            elif str(payload['is_active']).lower() in ['true', '1']:
                is_active = True
            elif str(payload['is_active']).lower() in ['false', '0']:
                is_active = False
            else:
                return Response({'status': 'error', 'message': 'is_active must be a boolean'}, status=status.HTTP_400_BAD_REQUEST)

        project = GroupProject.objects.create(
            section=section,
            title=title,
            description=payload.get('description'),
            due_at=due_at,
            max_members=max_members,
            is_active=is_active,
            created_by=request.user,
        )

        return Response(
            {
                'status': 'success',
                'message': 'Group project created successfully',
                'data': {
                    'id': project.id,
                    'section_id': project.section_id,
                    'title': project.title,
                    'max_members': project.max_members,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class AdminSectionGroupProjectDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def patch(self, request, section_id, project_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        project = GroupProject.objects.filter(id=project_id, section_id=section_id).first()
        if not project:
            return Response({'status': 'error', 'message': 'Group project not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        updated = []

        if 'title' in payload:
            if not payload['title']:
                return Response({'status': 'error', 'message': 'title cannot be empty'}, status=status.HTTP_400_BAD_REQUEST)
            project.title = payload['title']
            updated.append('title')

        if 'description' in payload:
            project.description = payload['description']
            updated.append('description')

        if 'due_at' in payload:
            if payload['due_at'] is None:
                project.due_at = None
            else:
                parsed_due_at = parse_datetime(str(payload['due_at']))
                if parsed_due_at is None:
                    return Response(
                        {'status': 'error', 'message': 'due_at must be a valid ISO-8601 datetime'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                project.due_at = parsed_due_at
            updated.append('due_at')

        if 'max_members' in payload:
            try:
                max_members = int(payload['max_members'])
                if max_members <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return Response({'status': 'error', 'message': 'max_members must be a positive integer'}, status=status.HTTP_400_BAD_REQUEST)

            current_members = GroupProjectMember.objects.filter(group_project_id=project.id).count()
            if current_members > max_members:
                return Response(
                    {'status': 'error', 'message': 'max_members cannot be less than current member count'},
                    status=status.HTTP_409_CONFLICT,
                )

            project.max_members = max_members
            updated.append('max_members')

        if 'is_active' in payload:
            if isinstance(payload['is_active'], bool):
                project.is_active = payload['is_active']
            elif str(payload['is_active']).lower() in ['true', '1']:
                project.is_active = True
            elif str(payload['is_active']).lower() in ['false', '0']:
                project.is_active = False
            else:
                return Response({'status': 'error', 'message': 'is_active must be a boolean'}, status=status.HTTP_400_BAD_REQUEST)
            updated.append('is_active')

        if updated:
            project.save(update_fields=list(dict.fromkeys(updated + ['updated_at'])))

        return Response({'status': 'success', 'message': 'Group project updated successfully'})

    def delete(self, request, section_id, project_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        project = GroupProject.objects.filter(id=project_id, section_id=section_id).first()
        if not project:
            return Response({'status': 'error', 'message': 'Group project not found'}, status=status.HTTP_404_NOT_FOUND)

        project.delete()
        return Response({'status': 'success', 'message': 'Group project deleted successfully'})


class AdminSectionGroupProjectMembersView(APIView):
    permission_classes = [AdminOnlyPermission]

    def post(self, request, section_id, project_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        project = GroupProject.objects.filter(id=project_id, section_id=section_id).first()
        if not project:
            return Response({'status': 'error', 'message': 'Group project not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        student_id = payload.get('student_id')
        if not student_id:
            return Response({'status': 'error', 'message': 'student_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        student = StudentProfile.objects.filter(id=student_id).select_related('user').first()
        if not student:
            return Response({'status': 'error', 'message': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

        if not CourseEnrollment.objects.filter(
            student=student,
            section_id=section_id,
            status__in=[
                CourseEnrollment.EnrollmentStatus.ACTIVE,
                CourseEnrollment.EnrollmentStatus.COMPLETED,
            ],
        ).exists():
            return Response(
                {'status': 'error', 'message': 'Student must be enrolled in this section'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        member, created = GroupProjectMember.objects.get_or_create(
            group_project=project,
            student=student,
        )

        if not created:
            return Response(
                {
                    'status': 'success',
                    'message': 'Student already assigned to this group project',
                    'data': {'id': member.id, 'group_project_id': project.id, 'student_id': student.id},
                }
            )

        if GroupProjectMember.objects.filter(group_project=project).count() > project.max_members:
            member.delete()
            return Response(
                {'status': 'error', 'message': 'Group project is at maximum capacity'},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {
                'status': 'success',
                'message': 'Group project member added successfully',
                'data': {'id': member.id, 'group_project_id': project.id, 'student_id': student.id},
            },
            status=status.HTTP_201_CREATED,
        )


class AdminSectionGroupProjectMemberDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def delete(self, request, section_id, project_id, member_id):
        section = Section.objects.filter(id=section_id).first()
        if not section:
            return Response({'status': 'error', 'message': 'Section not found'}, status=status.HTTP_404_NOT_FOUND)

        project = GroupProject.objects.filter(id=project_id, section_id=section_id).first()
        if not project:
            return Response({'status': 'error', 'message': 'Group project not found'}, status=status.HTTP_404_NOT_FOUND)

        member = GroupProjectMember.objects.filter(id=member_id, group_project_id=project.id).first()
        if not member:
            return Response({'status': 'error', 'message': 'Group project member not found'}, status=status.HTTP_404_NOT_FOUND)

        member.delete()
        return Response({'status': 'success', 'message': 'Group project member removed successfully'})
