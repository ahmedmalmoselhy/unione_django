import csv
from io import StringIO

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import AuditLog, Course, Grade
from accounts.models import Role, UserRole
from accounts.permissions import HasAnyRole
from enrollment.models import CourseEnrollment

User = get_user_model()


class AdminOnlyPermission(HasAnyRole):
    required_roles = ['admin', 'faculty_admin', 'department_admin']


def _is_super_admin(user):
    return user.is_superuser or user.user_roles.filter(role__slug='admin').exists()


def _get_user_scopes(user):
    scopes = {'is_super': _is_super_admin(user), 'faculties': set(), 'departments': set()}
    for user_role in user.user_roles.select_related('role'):
        if user_role.role.slug == 'faculty_admin' and user_role.scope == 'faculty' and user_role.scope_id:
            scopes['faculties'].add(user_role.scope_id)
        elif user_role.role.slug == 'department_admin' and user_role.scope == 'department' and user_role.scope_id:
            scopes['departments'].add(user_role.scope_id)
    return scopes


def _to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y'}


def _load_rows_from_request(request):
    payload = request.data if isinstance(request.data, dict) else {}
    if 'rows' in payload and isinstance(payload['rows'], list):
        return payload['rows']

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return None

    decoded = uploaded_file.read().decode('utf-8-sig')
    reader = csv.DictReader(StringIO(decoded))
    return list(reader)


def _create_audit_entry(request, action, entity_type, description, old_values=None, new_values=None):
    AuditLog.objects.create(
        user=request.user,
        action=action,
        entity_type=entity_type,
        description=description,
        old_values=old_values or {},
        new_values=new_values or {},
        ip_address=_get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
    )


def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class AdminImportUsersView(APIView):
    permission_classes = [AdminOnlyPermission]

    def post(self, request):
        rows = _load_rows_from_request(request)
        if rows is None:
            return Response(
                {'status': 'error', 'message': 'Provide file upload (CSV) or rows[] payload'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = 0
        skipped = 0
        errors = []

        for index, row in enumerate(rows, start=1):
            username = (row.get('username') or '').strip()
            email = (row.get('email') or '').strip().lower()

            if not username or not email:
                skipped += 1
                errors.append({'row': index, 'error': 'username and email are required'})
                continue

            if User.objects.filter(username=username).exists() or User.objects.filter(email=email).exists():
                skipped += 1
                continue

            password = row.get('password') or 'Pass1234!@#'
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=(row.get('first_name') or '').strip(),
                last_name=(row.get('last_name') or '').strip(),
                is_staff=_to_bool(row.get('is_staff')),
                is_superuser=_to_bool(row.get('is_superuser')),
            )

            raw_roles = row.get('roles')
            role_slugs = []
            if isinstance(raw_roles, str):
                separators = ['|', ';']
                normalized = raw_roles
                for sep in separators:
                    normalized = normalized.replace(sep, ',')
                role_slugs = [item.strip() for item in normalized.split(',') if item.strip()]
            elif isinstance(raw_roles, list):
                role_slugs = [str(item).strip() for item in raw_roles if str(item).strip()]

            for role_slug in role_slugs:
                role = Role.objects.filter(slug=role_slug).first()
                if role:
                    UserRole.objects.get_or_create(user=user, role=role)

            created += 1

        _create_audit_entry(
            request,
            action=AuditLog.Action.IMPORT,
            entity_type='User',
            description='Bulk imported users',
            new_values={'created': created, 'skipped': skipped, 'total_rows': len(rows)},
        )

        return Response(
            {
                'status': 'success',
                'message': 'User import processed',
                'data': {
                    'created': created,
                    'skipped': skipped,
                    'errors': errors,
                },
            }
        )


class AdminImportCoursesView(APIView):
    permission_classes = [AdminOnlyPermission]

    def post(self, request):
        rows = _load_rows_from_request(request)
        if rows is None:
            return Response(
                {'status': 'error', 'message': 'Provide file upload (CSV) or rows[] payload'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = 0
        skipped = 0
        errors = []

        for index, row in enumerate(rows, start=1):
            code = (row.get('code') or '').strip()
            name = (row.get('name') or '').strip()
            credit_hours = row.get('credit_hours')

            if not code or not name or credit_hours in (None, ''):
                skipped += 1
                errors.append({'row': index, 'error': 'code, name, credit_hours are required'})
                continue

            if Course.objects.filter(code=code).exists():
                skipped += 1
                continue

            try:
                credit_hours_value = int(credit_hours)
                lecture_hours = int(row.get('lecture_hours') or 0)
                lab_hours = int(row.get('lab_hours') or 0)
                level = int(row.get('level') or 100)
            except (TypeError, ValueError):
                skipped += 1
                errors.append({'row': index, 'error': 'credit/lecture/lab/level must be integers'})
                continue

            Course.objects.create(
                code=code,
                name=name,
                name_ar=(row.get('name_ar') or None),
                description=(row.get('description') or None),
                credit_hours=credit_hours_value,
                lecture_hours=lecture_hours,
                lab_hours=lab_hours,
                level=level,
                is_elective=_to_bool(row.get('is_elective')),
                is_active=_to_bool(row.get('is_active'), default=True),
            )
            created += 1

        _create_audit_entry(
            request,
            action=AuditLog.Action.IMPORT,
            entity_type='Course',
            description='Bulk imported courses',
            new_values={'created': created, 'skipped': skipped, 'total_rows': len(rows)},
        )

        return Response(
            {
                'status': 'success',
                'message': 'Course import processed',
                'data': {
                    'created': created,
                    'skipped': skipped,
                    'errors': errors,
                },
            }
        )


class AdminExportEnrollmentsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        scopes = _get_user_scopes(request.user)
        queryset = CourseEnrollment.objects.select_related(
            'student__user',
            'student__faculty',
            'student__department',
            'section__course',
            'academic_term',
        ).order_by('-created_at')

        term_id = request.query_params.get('academic_term_id')
        if term_id:
            queryset = queryset.filter(academic_term_id=term_id)

        course_id = request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(section__course_id=course_id)

        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        if not scopes['is_super']:
            if scopes['faculties']:
                queryset = queryset.filter(student__faculty_id__in=scopes['faculties'])
            elif scopes['departments']:
                queryset = queryset.filter(student__department_id__in=scopes['departments'])
            else:
                queryset = queryset.none()

        response = HttpResponse(content_type='text/csv')
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        response['Content-Disposition'] = f'attachment; filename="enrollments_{timestamp}.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                'enrollment_id',
                'student_number',
                'student_username',
                'faculty',
                'department',
                'course_code',
                'course_name',
                'term',
                'status',
                'registered_at',
                'dropped_at',
            ]
        )
        for enrollment in queryset:
            writer.writerow(
                [
                    enrollment.id,
                    enrollment.student.student_number,
                    enrollment.student.user.username,
                    enrollment.student.faculty.name,
                    enrollment.student.department.name,
                    enrollment.section.course.code,
                    enrollment.section.course.name,
                    enrollment.academic_term.name,
                    enrollment.status,
                    enrollment.registered_at.isoformat() if enrollment.registered_at else '',
                    enrollment.dropped_at.isoformat() if enrollment.dropped_at else '',
                ]
            )

        _create_audit_entry(
            request,
            action=AuditLog.Action.EXPORT,
            entity_type='CourseEnrollment',
            description='Exported enrollment report',
            new_values={'records': queryset.count()},
        )
        return response


class AdminExportGradesView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        scopes = _get_user_scopes(request.user)
        queryset = Grade.objects.select_related(
            'enrollment__student__user',
            'enrollment__student__faculty',
            'enrollment__student__department',
            'enrollment__section__course',
            'enrollment__academic_term',
        ).order_by('-created_at')

        term_id = request.query_params.get('academic_term_id')
        if term_id:
            queryset = queryset.filter(enrollment__academic_term_id=term_id)

        course_id = request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(enrollment__section__course_id=course_id)

        if not scopes['is_super']:
            if scopes['faculties']:
                queryset = queryset.filter(enrollment__student__faculty_id__in=scopes['faculties'])
            elif scopes['departments']:
                queryset = queryset.filter(enrollment__student__department_id__in=scopes['departments'])
            else:
                queryset = queryset.none()

        response = HttpResponse(content_type='text/csv')
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        response['Content-Disposition'] = f'attachment; filename="grades_{timestamp}.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                'grade_id',
                'enrollment_id',
                'student_number',
                'student_username',
                'faculty',
                'department',
                'course_code',
                'course_name',
                'term',
                'points',
                'letter_grade',
                'status',
                'updated_at',
            ]
        )
        for grade in queryset:
            writer.writerow(
                [
                    grade.id,
                    grade.enrollment_id,
                    grade.enrollment.student.student_number,
                    grade.enrollment.student.user.username,
                    grade.enrollment.student.faculty.name,
                    grade.enrollment.student.department.name,
                    grade.enrollment.section.course.code,
                    grade.enrollment.section.course.name,
                    grade.enrollment.academic_term.name,
                    grade.points,
                    grade.letter_grade,
                    grade.status,
                    grade.updated_at.isoformat() if grade.updated_at else '',
                ]
            )

        _create_audit_entry(
            request,
            action=AuditLog.Action.EXPORT,
            entity_type='Grade',
            description='Exported grade report',
            new_values={'records': queryset.count()},
        )
        return response
