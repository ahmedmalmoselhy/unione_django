from rest_framework import permissions


class HasAnyRole(permissions.BasePermission):
    required_roles = []

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        user_roles = set(request.user.user_roles.values_list('role__slug', flat=True))
        return bool(user_roles.intersection(set(self.required_roles)))


class CanViewOrganization(HasAnyRole):
    required_roles = [
        'admin',
        'faculty_admin',
        'department_admin',
        'professor',
        'student',
        'employee',
    ]
