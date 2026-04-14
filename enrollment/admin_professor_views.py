from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AccountProfile, Role, UserRole
from accounts.permissions import HasAnyRole
from enrollment.models import ProfessorProfile
from organization.models import Department

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


def _filter_professors_by_scope(queryset, user):
    """Filter professors by admin scope."""
    scopes = _get_user_scopes(user)
    if scopes['is_super']:
        return queryset
    if scopes['departments']:
        return queryset.filter(department_id__in=scopes['departments'])
    if scopes['faculties']:
        return queryset.filter(department__faculty_id__in=scopes['faculties'])
    return queryset.none()


def _professor_to_dict(professor):
    """Convert ProfessorProfile to dictionary."""
    data = {
        'id': professor.id,
        'staff_number': professor.staff_number,
        'department': None,
        'specialization': professor.specialization,
        'academic_rank': professor.academic_rank,
        'office_location': professor.office_location,
        'hired_at': str(professor.hired_at),
        'created_at': str(professor.created_at),
        'updated_at': str(professor.updated_at),
        'user': {
            'id': professor.user.id,
            'username': professor.user.username,
            'email': professor.user.email,
            'first_name': professor.user.first_name,
            'last_name': professor.user.last_name,
            'is_active': professor.user.is_active,
        }
    }
    if professor.department:
        data['department'] = {
            'id': professor.department.id,
            'name': professor.department.name,
            'code': professor.department.code,
            'faculty': {
                'id': professor.department.faculty.id,
                'name': professor.department.faculty.name,
            } if professor.department.faculty else None,
        }
    return data


class AdminProfessorsView(APIView):
    """List and create professors."""
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        """GET /api/admin/professors - List professors with filters."""
        queryset = ProfessorProfile.objects.select_related('user', 'department', 'department__faculty').order_by('-created_at')
        queryset = _filter_professors_by_scope(queryset, request.user)

        # Filter by department
        department_id = request.query_params.get('department_id')
        if department_id:
            queryset = queryset.filter(department_id=department_id)

        # Filter by faculty
        faculty_id = request.query_params.get('faculty_id')
        if faculty_id:
            queryset = queryset.filter(department__faculty_id=faculty_id)

        # Filter by academic rank
        academic_rank = request.query_params.get('academic_rank')
        if academic_rank:
            queryset = queryset.filter(academic_rank=academic_rank)

        # Search by staff number or name
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                staff_number__icontains=search
            ) | queryset.filter(
                user__first_name__icontains=search
            ) | queryset.filter(
                user__last_name__icontains=search
            ) | queryset.filter(
                specialization__icontains=search
            )

        data = [_professor_to_dict(p) for p in queryset]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        """POST /api/admin/professors - Create professor."""
        payload = request.data if isinstance(request.data, dict) else {}

        # Validate required fields
        required = ['staff_number', 'username', 'email', 'department_id', 'hired_at']
        for field in required:
            if not payload.get(field):
                return Response(
                    {'status': 'error', 'message': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Check if staff number already exists
        if ProfessorProfile.objects.filter(staff_number=payload['staff_number']).exists():
            return Response(
                {'status': 'error', 'message': 'Staff number already exists'},
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

        # Validate department
        department = Department.objects.filter(id=payload['department_id']).first()
        if not department:
            return Response(
                {'status': 'error', 'message': 'Department not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Create user and professor profile in transaction
        try:
            user = User.objects.create_user(
                username=payload['username'],
                email=payload['email'],
                password=payload.get('password', 'password123'),
                first_name=payload.get('first_name', ''),
                last_name=payload.get('last_name', ''),
            )

            professor = ProfessorProfile.objects.create(
                user=user,
                staff_number=payload['staff_number'],
                department=department,
                specialization=payload.get('specialization'),
                academic_rank=payload.get('academic_rank', 'assistant_professor'),
                office_location=payload.get('office_location'),
                hired_at=payload['hired_at'],
            )

            # Assign professor role
            professor_role = Role.objects.filter(slug='professor').first()
            if professor_role:
                UserRole.objects.create(
                    user=user,
                    role=professor_role,
                    scope='department',
                    scope_id=department.id,
                )

            return Response(
                {
                    'status': 'success',
                    'message': 'Professor created successfully',
                    'data': _professor_to_dict(professor),
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AdminProfessorDetailView(APIView):
    """Get, update, or delete a specific professor."""
    permission_classes = [AdminOnlyPermission]

    def get(self, request, professor_id):
        """GET /api/admin/professors/{id} - Get professor details."""
        professor = ProfessorProfile.objects.select_related('user', 'department', 'department__faculty').filter(id=professor_id).first()
        if not professor:
            return Response(
                {'status': 'error', 'message': 'Professor not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({'status': 'success', 'data': _professor_to_dict(professor)})

    def patch(self, request, professor_id):
        """PATCH /api/admin/professors/{id} - Update professor."""
        professor = ProfessorProfile.objects.select_related('user').filter(id=professor_id).first()
        if not professor:
            return Response(
                {'status': 'error', 'message': 'Professor not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = request.data if isinstance(request.data, dict) else {}

        # Validate department if provided
        if payload.get('department_id'):
            department = Department.objects.filter(id=payload['department_id']).first()
            if not department:
                return Response(
                    {'status': 'error', 'message': 'Department not found'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            professor.department = department

        # Update professor fields
        if 'specialization' in payload:
            professor.specialization = payload['specialization']
        if 'academic_rank' in payload:
            professor.academic_rank = payload['academic_rank']
        if 'office_location' in payload:
            professor.office_location = payload['office_location']
        if 'hired_at' in payload:
            professor.hired_at = payload['hired_at']

        # Update user fields
        user = professor.user
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
        professor.save()

        return Response(
            {
                'status': 'success',
                'message': 'Professor updated successfully',
                'data': _professor_to_dict(professor),
            }
        )

    def delete(self, request, professor_id):
        """DELETE /api/admin/professors/{id} - Deactivate professor (soft delete)."""
        professor = ProfessorProfile.objects.filter(id=professor_id).first()
        if not professor:
            return Response(
                {'status': 'error', 'message': 'Professor not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Soft delete: deactivate user
        professor.user.is_active = False
        professor.user.save()

        return Response(
            {
                'status': 'success',
                'message': 'Professor deactivated successfully',
            }
        )
