from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AccountProfile, Role, UserRole
from accounts.permissions import HasAnyRole
from enrollment.models import EmployeeProfile
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


def _employee_to_dict(employee):
    """Convert EmployeeProfile to dictionary."""
    data = {
        'id': employee.id,
        'staff_number': employee.staff_number,
        'job_title': employee.job_title,
        'department': None,
        'employment_type': employee.employment_type,
        'salary': str(employee.salary) if employee.salary else None,
        'hired_at': str(employee.hired_at),
        'terminated_at': str(employee.terminated_at) if employee.terminated_at else None,
        'is_active': employee.is_active,
        'created_at': str(employee.created_at),
        'updated_at': str(employee.updated_at),
        'user': {
            'id': employee.user.id,
            'username': employee.user.username,
            'email': employee.user.email,
            'first_name': employee.user.first_name,
            'last_name': employee.user.last_name,
            'is_active': employee.user.is_active,
        }
    }
    if employee.department:
        data['department'] = {
            'id': employee.department.id,
            'name': employee.department.name,
            'code': employee.department.code,
        }
    return data


class AdminEmployeesView(APIView):
    """List and create employees."""
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        """GET /api/admin/employees - List employees with filters."""
        queryset = EmployeeProfile.objects.select_related('user', 'department').order_by('-created_at')

        # Filter by department
        department_id = request.query_params.get('department_id')
        if department_id:
            queryset = queryset.filter(department_id=department_id)

        # Filter by employment type
        employment_type = request.query_params.get('employment_type')
        if employment_type:
            queryset = queryset.filter(employment_type=employment_type)

        # Filter by active status
        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        # Search by staff number or job title
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                staff_number__icontains=search
            ) | queryset.filter(
                job_title__icontains=search
            ) | queryset.filter(
                user__first_name__icontains=search
            ) | queryset.filter(
                user__last_name__icontains=search
            )

        data = [_employee_to_dict(emp) for emp in queryset]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        """POST /api/admin/employees - Create employee."""
        payload = request.data if isinstance(request.data, dict) else {}

        # Validate required fields
        required = ['staff_number', 'job_title', 'hired_at', 'username', 'email']
        for field in required:
            if not payload.get(field):
                return Response(
                    {'status': 'error', 'message': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Check if staff number already exists
        if EmployeeProfile.objects.filter(staff_number=payload['staff_number']).exists():
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

        # Validate department if provided
        department = None
        if payload.get('department_id'):
            department = Department.objects.filter(id=payload['department_id']).first()
            if not department:
                return Response(
                    {'status': 'error', 'message': 'Department not found'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # Create user and employee profile in transaction
        try:
            user = User.objects.create_user(
                username=payload['username'],
                email=payload['email'],
                password=payload.get('password', 'password123'),
                first_name=payload.get('first_name', ''),
                last_name=payload.get('last_name', ''),
            )

            employee = EmployeeProfile.objects.create(
                user=user,
                staff_number=payload['staff_number'],
                job_title=payload['job_title'],
                department=department,
                employment_type=payload.get('employment_type', 'full_time'),
                salary=payload.get('salary'),
                hired_at=payload['hired_at'],
                is_active=payload.get('is_active', True),
            )

            # Assign employee role
            employee_role = Role.objects.filter(slug='employee').first()
            if employee_role:
                UserRole.objects.create(
                    user=user,
                    role=employee_role,
                    scope='university',
                    scope_id=None,
                )

            return Response(
                {
                    'status': 'success',
                    'message': 'Employee created successfully',
                    'data': _employee_to_dict(employee),
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AdminEmployeeDetailView(APIView):
    """Get, update, or delete a specific employee."""
    permission_classes = [AdminOnlyPermission]

    def get(self, request, employee_id):
        """GET /api/admin/employees/{id} - Get employee details."""
        employee = EmployeeProfile.objects.select_related('user', 'department').filter(id=employee_id).first()
        if not employee:
            return Response(
                {'status': 'error', 'message': 'Employee not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({'status': 'success', 'data': _employee_to_dict(employee)})

    def patch(self, request, employee_id):
        """PATCH /api/admin/employees/{id} - Update employee."""
        employee = EmployeeProfile.objects.select_related('user').filter(id=employee_id).first()
        if not employee:
            return Response(
                {'status': 'error', 'message': 'Employee not found'},
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
            employee.department = department

        # Update fields
        if 'job_title' in payload:
            employee.job_title = payload['job_title']
        if 'employment_type' in payload:
            employee.employment_type = payload['employment_type']
        if 'salary' in payload:
            employee.salary = payload['salary']
        if 'hired_at' in payload:
            employee.hired_at = payload['hired_at']
        if 'terminated_at' in payload:
            employee.terminated_at = payload['terminated_at']
        if 'is_active' in payload:
            employee.is_active = payload['is_active']

        # Update user fields
        user = employee.user
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
        employee.save()

        return Response(
            {
                'status': 'success',
                'message': 'Employee updated successfully',
                'data': _employee_to_dict(employee),
            }
        )

    def delete(self, request, employee_id):
        """DELETE /api/admin/employees/{id} - Deactivate employee (soft delete)."""
        employee = EmployeeProfile.objects.filter(id=employee_id).first()
        if not employee:
            return Response(
                {'status': 'error', 'message': 'Employee not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Soft delete: deactivate user and employee
        employee.is_active = False
        employee.terminated_at = employee.terminated_at or timezone.now().date()
        employee.save()

        employee.user.is_active = False
        employee.user.save()

        return Response(
            {
                'status': 'success',
                'message': 'Employee deactivated successfully',
            }
        )
