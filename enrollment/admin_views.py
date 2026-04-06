from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasAnyRole
from academics.models import Webhook, WebhookDelivery


class AdminOnlyPermission(HasAnyRole):
	required_roles = ['admin']


def _webhook_queryset():
	return Webhook.objects.filter(deleted_at__isnull=True).order_by('-created_at', '-id')


class AdminWebhooksView(APIView):
	permission_classes = [AdminOnlyPermission]

	def get(self, _request):
		queryset = _webhook_queryset()
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
		webhook = _webhook_queryset().filter(id=webhook_id).first()
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
			},
		)

	def delete(self, _request, webhook_id):
		webhook = _webhook_queryset().filter(id=webhook_id).first()
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
		webhook = _webhook_queryset().filter(id=webhook_id).first()
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
