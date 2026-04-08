from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import AccountProfile, Role, UserRole
from accounts.permissions import HasAnyRole
from academics.models import Webhook, WebhookDelivery

User = get_user_model()


class AdminOnlyPermission(HasAnyRole):
    required_roles = ['admin', 'faculty_admin', 'department_admin']


class SuperAdminOnlyPermission(HasAnyRole):
    required_roles = ['admin']


def _is_super_admin(user):
    return user.is_superuser or user.user_roles.filter(role__slug='admin').exists()


def _user_has_scoped_role(user, role_slug, scope=None, scope_id=None):
    queryset = user.user_roles.filter(role__slug=role_slug)
    if scope is not None:
        queryset = queryset.filter(scope=scope, scope_id=scope_id)
    return queryset.exists()


def _get_user_scopes(user):
    """Return dict of scopes the user has admin access to."""
    scopes = {'is_super': _is_super_admin(user), 'faculties': set(), 'departments': set()}
    for ur in user.user_roles.select_related('role'):
        if ur.role.slug == 'faculty_admin' and ur.scope == 'faculty' and ur.scope_id:
            scopes['faculties'].add(ur.scope_id)
        elif ur.role.slug == 'department_admin' and ur.scope == 'department' and ur.scope_id:
            scopes['departments'].add(ur.scope_id)
    return scopes


def _user_to_dict(user, include_roles=True):
    data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'is_active': user.is_active,
        'date_joined': user.date_joined,
        'last_login': user.last_login,
    }
    if include_roles:
        roles = []
        for ur in user.user_roles.select_related('role'):
            roles.append({
                'role': ur.role.slug,
                'scope': ur.scope,
                'scope_id': ur.scope_id,
            })
        data['roles'] = roles
        try:
            profile = user.account_profile
            data['profile'] = {
                'phone': profile.phone,
                'date_of_birth': profile.date_of_birth,
                'avatar_path': profile.avatar_path,
            }
        except AccountProfile.DoesNotExist:
            data['profile'] = None
    return data


def _webhook_queryset_for_user(user):
    queryset = Webhook.objects.filter(deleted_at__isnull=True)
    if user.is_superuser:
        return queryset.order_by('-created_at', '-id')
    return queryset.filter(created_by=user).order_by('-created_at', '-id')


class AdminUsersView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = User.objects.select_related().prefetch_related('user_roles__role').order_by('-date_joined')

        role_filter = request.query_params.get('role')
        if role_filter:
            queryset = queryset.filter(user_roles__role__slug=role_filter).distinct()

        is_active = request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(username__icontains=search)
                | models.Q(email__icontains=search)
                | models.Q(first_name__icontains=search)
                | models.Q(last_name__icontains=search)
            )

        limit = request.query_params.get('limit', '50')
        try:
            limit_num = min(int(limit), 200)
        except (TypeError, ValueError):
            limit_num = 50

        users = list(queryset[:limit_num])
        data = [_user_to_dict(u) for u in users]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        required = ['username', 'email', 'password']
        for field in required:
            if not payload.get(field):
                return Response(
                    {'status': 'error', 'message': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        username = payload.get('username')
        email = payload.get('email')
        password = payload.get('password')

        if User.objects.filter(username=username).exists():
            return Response(
                {'status': 'error', 'message': 'Username already exists'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(email=email).exists():
            return Response(
                {'status': 'error', 'message': 'Email already exists'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        roles_data = payload.get('roles', [])
        if not isinstance(roles_data, list):
            return Response(
                {'status': 'error', 'message': 'roles must be a list'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=payload.get('first_name', ''),
                last_name=payload.get('last_name', ''),
                is_staff=payload.get('is_staff', False),
                is_superuser=payload.get('is_superuser', False),
            )

            profile_data = payload.get('profile', {})
            if isinstance(profile_data, dict):
                AccountProfile.objects.create(
                    user=user,
                    phone=profile_data.get('phone'),
                    date_of_birth=profile_data.get('date_of_birth'),
                    avatar_path=profile_data.get('avatar_path'),
                )

            for role_item in roles_data:
                if isinstance(role_item, dict):
                    role_slug = role_item.get('role')
                    scope = role_item.get('scope')
                    scope_id = role_item.get('scope_id')
                elif isinstance(role_item, str):
                    role_slug = role_item
                    scope = None
                    scope_id = None
                else:
                    continue

                role = Role.objects.filter(slug=role_slug).first()
                if role:
                    UserRole.objects.create(
                        user=user,
                        role=role,
                        scope=scope,
                        scope_id=scope_id,
                    )

        return Response(
            {'status': 'success', 'message': 'User created successfully', 'data': _user_to_dict(user)},
            status=status.HTTP_201_CREATED,
        )


class AdminUserDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({'status': 'error', 'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'status': 'success', 'data': _user_to_dict(user)})

    def patch(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({'status': 'error', 'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        updatable_user_fields = ['first_name', 'last_name', 'email', 'is_staff', 'is_active']
        user_updated = []

        for field in updatable_user_fields:
            if field in payload:
                setattr(user, field, payload[field])
                user_updated.append(field)

        if 'password' in payload:
            user.set_password(payload['password'])
            user_updated.append('password')

        if user_updated:
            user.save(update_fields=user_updated)

        if 'profile' in payload and isinstance(payload['profile'], dict):
            profile, _ = AccountProfile.objects.get_or_create(user=user)
            profile_fields = ['phone', 'date_of_birth', 'avatar_path']
            profile_updated = []
            for field in profile_fields:
                if field in payload['profile']:
                    setattr(profile, field, payload['profile'][field])
                    profile_updated.append(field)
            if profile_updated:
                profile.save(update_fields=profile_updated + ['updated_at'])

        if 'roles' in payload:
            if not isinstance(payload['roles'], list):
                return Response(
                    {'status': 'error', 'message': 'roles must be a list'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.user_roles.all().delete()
            for role_item in payload['roles']:
                if isinstance(role_item, dict):
                    role_slug = role_item.get('role')
                    scope = role_item.get('scope')
                    scope_id = role_item.get('scope_id')
                elif isinstance(role_item, str):
                    role_slug = role_item
                    scope = None
                    scope_id = None
                else:
                    continue
                role = Role.objects.filter(slug=role_slug).first()
                if role:
                    UserRole.objects.create(user=user, role=role, scope=scope, scope_id=scope_id)

        return Response({'status': 'success', 'message': 'User updated successfully', 'data': _user_to_dict(user)})

    def delete(self, request, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({'status': 'error', 'message': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if user.id == request.user.id:
            return Response(
                {'status': 'error', 'message': 'Cannot delete yourself'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_active = False
        user.save(update_fields=['is_active'])
        return Response({'status': 'success', 'message': 'User deactivated successfully'})


class AdminWebhooksView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, _request):
        queryset = _webhook_queryset_for_user(_request.user)
        data = [
            {
                'id': webhook.id,
                'name': webhook.name,
                'target_url': webhook.target_url,
                'events': webhook.events,
                'headers': webhook.headers,
                'is_active': webhook.is_active,
                'last_triggered_at': webhook.last_triggered_at,
                'created_at': webhook.created_at,
                'updated_at': webhook.updated_at,
            }
            for webhook in queryset
        ]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        name = payload.get('name')
        target_url = payload.get('target_url')
        if not name or not target_url:
            return Response(
                {'status': 'error', 'message': 'name and target_url are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        events = payload.get('events', [])
        if not isinstance(events, list):
            return Response(
                {'status': 'error', 'message': 'events must be a list'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = payload.get('headers', {})
        if not isinstance(headers, dict):
            return Response(
                {'status': 'error', 'message': 'headers must be an object'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        webhook = Webhook.objects.create(
            name=str(name).strip(),
            target_url=str(target_url).strip(),
            events=events,
            headers=headers,
            secret=payload.get('secret'),
            is_active=bool(payload.get('is_active', True)),
            created_by=request.user,
        )

        return Response(
            {
                'status': 'success',
                'message': 'Webhook created successfully',
                'data': {
                    'id': webhook.id,
                    'name': webhook.name,
                    'target_url': webhook.target_url,
                    'events': webhook.events,
                    'headers': webhook.headers,
                    'is_active': webhook.is_active,
                    'created_at': webhook.created_at,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class AdminWebhookDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def patch(self, request, webhook_id):
        webhook = _webhook_queryset_for_user(request.user).filter(id=webhook_id).first()
        if webhook is None:
            return Response({'status': 'error', 'message': 'Webhook not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        if 'events' in payload and not isinstance(payload.get('events'), list):
            return Response(
                {'status': 'error', 'message': 'events must be a list'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if 'headers' in payload and not isinstance(payload.get('headers'), dict):
            return Response(
                {'status': 'error', 'message': 'headers must be an object'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updatable_fields = {'name', 'target_url', 'events', 'headers', 'secret', 'is_active'}
        updated_fields = []
        for key in updatable_fields:
            if key in payload:
                setattr(webhook, key, payload.get(key))
                updated_fields.append(key)

        if not updated_fields:
            return Response(
                {'status': 'error', 'message': 'No supported fields provided for update'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        webhook.save(update_fields=updated_fields + ['updated_at'])
        return Response(
            {
                'status': 'success',
                'message': 'Webhook updated successfully',
                'data': {
                    'id': webhook.id,
                    'name': webhook.name,
                    'target_url': webhook.target_url,
                    'events': webhook.events,
                    'headers': webhook.headers,
                    'is_active': webhook.is_active,
                    'updated_at': webhook.updated_at,
                },
            }
        )

    def delete(self, _request, webhook_id):
        webhook = _webhook_queryset_for_user(_request.user).filter(id=webhook_id).first()
        if webhook is None:
            return Response({'status': 'error', 'message': 'Webhook not found'}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        webhook.deleted_at = now
        webhook.is_active = False
        webhook.save(update_fields=['deleted_at', 'is_active', 'updated_at'])
        return Response({'status': 'success', 'message': 'Webhook deleted successfully'})


class AdminWebhookDeliveriesView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, webhook_id):
        webhook = _webhook_queryset_for_user(request.user).filter(id=webhook_id).first()
        if webhook is None:
            return Response({'status': 'error', 'message': 'Webhook not found'}, status=status.HTTP_404_NOT_FOUND)

        queryset = WebhookDelivery.objects.filter(webhook=webhook).order_by('-created_at', '-id')
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        limit = request.query_params.get('limit')
        if limit:
            try:
                limit_num = int(limit)
            except (TypeError, ValueError):
                return Response(
                    {'status': 'error', 'message': 'limit must be an integer'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if limit_num > 0:
                queryset = queryset[: min(limit_num, 200)]

        data = [
            {
                'id': delivery.id,
                'event_name': delivery.event_name,
                'status': delivery.status,
                'attempt_count': delivery.attempt_count,
                'response_status_code': delivery.response_status_code,
                'error_message': delivery.error_message,
                'delivered_at': delivery.delivered_at,
                'next_retry_at': delivery.next_retry_at,
                'created_at': delivery.created_at,
                'updated_at': delivery.updated_at,
            }
            for delivery in queryset
        ]

        return Response(
            {
                'status': 'success',
                'data': {
                    'webhook': {
                        'id': webhook.id,
                        'name': webhook.name,
                        'target_url': webhook.target_url,
                    },
                    'deliveries': data,
                },
            }
        )
