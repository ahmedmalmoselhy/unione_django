from django.db import models
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import AuditLog
from accounts.permissions import HasAnyRole


class AdminOnlyPermission(HasAnyRole):
    required_roles = ['admin', 'faculty_admin', 'department_admin']


def _is_super_admin(user):
    return user.is_superuser or user.user_roles.filter(role__slug='admin').exists()


class AuditLogListView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        queryset = AuditLog.objects.select_related('user').order_by('-created_at')

        user_id = request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        action = request.query_params.get('action')
        if action:
            queryset = queryset.filter(action=action)

        entity_type = request.query_params.get('entity_type')
        if entity_type:
            queryset = queryset.filter(entity_type=entity_type)

        entity_id = request.query_params.get('entity_id')
        if entity_id:
            queryset = queryset.filter(entity_id=entity_id)

        date_from = request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__lte=date_to)

        limit = request.query_params.get('limit', '50')
        try:
            limit_num = min(int(limit), 200)
        except (TypeError, ValueError):
            limit_num = 50

        logs = list(queryset[:limit_num])
        data = [
            {
                'id': log.id,
                'user': {
                    'id': log.user.id,
                    'username': log.user.username,
                    'email': log.user.email,
                }
                if log.user
                else None,
                'action': log.action,
                'entity_type': log.entity_type,
                'entity_id': log.entity_id,
                'description': log.description,
                'ip_address': log.ip_address,
                'created_at': log.created_at,
            }
            for log in logs
        ]

        return Response({'status': 'success', 'data': data})

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}

        if not payload.get('entity_type') or not payload.get('description'):
            return Response(
                {'status': 'error', 'message': 'entity_type and description are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log = AuditLog.objects.create(
            user=request.user,
            action=payload.get('action', AuditLog.Action.OTHER),
            entity_type=payload['entity_type'],
            entity_id=payload.get('entity_id'),
            description=payload['description'],
            old_values=payload.get('old_values', {}),
            new_values=payload.get('new_values', {}),
            ip_address=self._get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        )

        return Response(
            {
                'status': 'success',
                'message': 'Audit log entry created',
                'data': {'id': log.id},
            },
            status=status.HTTP_201_CREATED,
        )

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class AuditLogDetailView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request, log_id):
        log = AuditLog.objects.filter(id=log_id).select_related('user').first()
        if not log:
            return Response({'status': 'error', 'message': 'Audit log entry not found'}, status=status.HTTP_404_NOT_FOUND)

        data = {
            'id': log.id,
            'user': {
                'id': log.user.id,
                'username': log.user.username,
                'email': log.user.email,
                'first_name': log.user.first_name,
                'last_name': log.user.last_name,
            }
            if log.user
            else None,
            'action': log.action,
            'entity_type': log.entity_type,
            'entity_id': log.entity_id,
            'description': log.description,
            'old_values': log.old_values,
            'new_values': log.new_values,
            'ip_address': log.ip_address,
            'user_agent': log.user_agent,
            'created_at': log.created_at,
        }
        return Response({'status': 'success', 'data': data})
