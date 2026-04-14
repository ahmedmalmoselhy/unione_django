from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AccountProfile, Role, UserRole
from accounts.permissions import HasAnyRole
from enrollment.models import StudentProfile
from organization.models import Department, Faculty

from django.contrib.auth import get_user_model

User = get_user_model()


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


def _filter_students_by_scope(queryset, user):
    """Filter students by admin scope."""
    scopes = _get_user_scopes(user)
    if scopes['is_super']:
        return queryset
    if scopes['departments']:
        return queryset.filter(department_id__in=scopes['departments'])
    if scopes['faculties']:
        return queryset.filter(faculty_id__in=scopes['faculties'])
    return queryset.none()


def _student_to_dict(student):
    """Convert StudentProfile to dictionary."""
    data = {
        'id': student.id,
        'student_number': student.student_number,
        'faculty': None,
        'department': None,
        'academic_year': student.academic_year,
        'semester': student.semester,
        'enrollment_status': student.enrollment_status,
        'gpa': str(student.gpa) if student.gpa else None,
        'academic_standing': student.academic_standing,
        'enrolled_at': str(student.enrolled_at),
        'graduated_at': str(student.graduated_at) if student.graduated_at else None,
        'created_at': str(student.created_at),
        'updated_at': str(student.updated_at),
        'user': {
            'id': student.user.id,
            'username': student.user.username,
            'email': student.user.email,
            'first_name': student.user.first_name,
            'last_name': student.user.last_name,
            'is_active': student.user.is_active,
        }
    }
    if student.faculty:
        data['faculty'] = {
            'id': student.faculty.id,
            'name': student.faculty.name,
            'code': student.faculty.code,
        }
    if student.department:
        data['department'] = {
            'id': student.department.id,
            'name': student.department.name,
            'code': student.department.code,
        }
    return data


class AdminStudentsView(APIView):
    """List and create students."""
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        """GET /api/admin/students - List students with filters."""
        queryset = StudentProfile.objects.select_related('user', 'faculty', 'department').order_by('-created_at')
        queryset = _filter_students_by_scope(queryset, request.user)

        # Filter by faculty
        faculty_id = request.query_params.get('faculty_id')
        if faculty_id:
            queryset = queryset.filter(faculty_id=faculty_id)

        # Filter by department
        department_id = request.query_params.get('department_id')
        if department_id:
            queryset = queryset.filter(department_id=department_id)

        # Filter by enrollment status
        enrollment_status = request.query_params.get('enrollment_status')
        if enrollment_status:
            queryset = queryset.filter(enrollment_status=enrollment_status)

        # Filter by academic year
        academic_year = request.query_params.get('academic_year')
        if academic_year:
            queryset = queryset.filter(academic_year=academic_year)

        # Search by student number or name
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                student_number__icontains=search
            ) | queryset.filter(
                user__first_name__icontains=search
            ) | queryset.filter(
                user__last_name__icontains=search
            )

        data = [_student_to_dict(s) for s in queryset]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        """POST /api/admin/students - Create student."""
        payload = request.data if isinstance(request.data, dict) else {}

        # Validate required fields
        required = ['student_number', 'username', 'email', 'faculty_id', 'department_id', 'enrolled_at']
        for field in required:
            if not payload.get(field):
                return Response(
                    {'status': 'error', 'message': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Check if student number already exists
        if StudentProfile.objects.filter(student_number=payload['student_number']).exists():
            return Response(
                {'status': 'error', 'message': 'Student number already exists'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if username already exists
        if User.objects.filter(username=payload['username']).exists():
            return Response(
                {'status': 'error', 'message': 'Username already exists'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if email already exists
        if User.objects.filter(email=payload['email']).exists():
            return Response(
                {'status': 'error', 'message': 'Email already exists'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate faculty and department
        faculty = Faculty.objects.filter(id=payload['faculty_id']).first()
        if not faculty:
            return Response(
                {'status': 'error', 'message': 'Faculty not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        department = Department.objects.filter(id=payload['department_id']).first()
        if not department:
            return Response(
                {'status': 'error', 'message': 'Department not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create user and student profile in transaction
        try:
            user = User.objects.create_user(
                username=payload['username'],
                email=payload['email'],
                password=payload.get('password', 'password123'),
                first_name=payload.get('first_name', ''),
                last_name=payload.get('last_name', ''),
            )

            student = StudentProfile.objects.create(
                user=user,
                student_number=payload['student_number'],
                faculty=faculty,
                department=department,
                academic_year=payload.get('academic_year', 1),
                semester=payload.get('semester', 1),
                enrollment_status=payload.get('enrollment_status', 'active'),
                gpa=payload.get('gpa', 0),
                academic_standing=payload.get('academic_standing', 'good'),
                enrolled_at=payload['enrolled_at'],
                graduated_at=payload.get('graduated_at'),
            )

            # Assign student role
            student_role = Role.objects.filter(slug='student').first()
            if student_role:
                UserRole.objects.create(
                    user=user,
                    role=student_role,
                    scope='department',
                    scope_id=department.id,
                )

            return Response(
                {
                    'status': 'success',
                    'message': 'Student created successfully',
                    'data': _student_to_dict(student),
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AdminStudentDetailView(APIView):
    """Get, update, or delete a specific student."""
    permission_classes = [AdminOnlyPermission]

    def get(self, request, student_id):
        """GET /api/admin/students/{id} - Get student details."""
        student = StudentProfile.objects.select_related('user', 'faculty', 'department').filter(id=student_id).first()
        if not student:
            return Response(
                {'status': 'error', 'message': 'Student not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({'status': 'success', 'data': _student_to_dict(student)})

    def patch(self, request, student_id):
        """PATCH /api/admin/students/{id} - Update student."""
        student = StudentProfile.objects.select_related('user').filter(id=student_id).first()
        if not student:
            return Response(
                {'status': 'error', 'message': 'Student not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = request.data if isinstance(request.data, dict) else {}

        # Validate faculty if provided
        if payload.get('faculty_id'):
            faculty = Faculty.objects.filter(id=payload['faculty_id']).first()
            if not faculty:
                return Response(
                    {'status': 'error', 'message': 'Faculty not found'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            student.faculty = faculty

        # Validate department if provided
        if payload.get('department_id'):
            department = Department.objects.filter(id=payload['department_id']).first()
            if not department:
                return Response(
                    {'status': 'error', 'message': 'Department not found'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            student.department = department

        # Update student fields
        if 'academic_year' in payload:
            student.academic_year = payload['academic_year']
        if 'semester' in payload:
            student.semester = payload['semester']
        if 'enrollment_status' in payload:
            student.enrollment_status = payload['enrollment_status']
        if 'gpa' in payload:
            student.gpa = payload['gpa']
        if 'academic_standing' in payload:
            student.academic_standing = payload['academic_standing']
        if 'enrolled_at' in payload:
            student.enrolled_at = payload['enrolled_at']
        if 'graduated_at' in payload:
            student.graduated_at = payload['graduated_at']

        # Update user fields
        user = student.user
        if 'first_name' in payload:
            user.first_name = payload['first_name']
        if 'last_name' in payload:
            user.last_name = payload['last_name']
        if 'email' in payload:
            if User.objects.filter(email=payload['email']).exclude(id=user.id).exists():
                return Response(
                    {'status': 'error', 'message': 'Email already exists'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.email = payload['email']
        if 'password' in payload:
            user.set_password(payload['password'])

        user.save()
        student.save()

        return Response(
            {
                'status': 'success',
                'message': 'Student updated successfully',
                'data': _student_to_dict(student),
            }
        )

    def delete(self, request, student_id):
        """DELETE /api/admin/students/{id} - Deactivate student (soft delete)."""
        student = StudentProfile.objects.filter(id=student_id).first()
        if not student:
            return Response(
                {'status': 'error', 'message': 'Student not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Soft delete: deactivate user
        student.user.is_active = False
        student.user.save()

        # Update enrollment status
        student.enrollment_status = 'suspended'
        student.save()

        return Response(
            {
                'status': 'success',
                'message': 'Student deactivated successfully',
            }
        )
