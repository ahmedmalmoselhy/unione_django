import io
from urllib.error import HTTPError
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserRole
from academics.models import Webhook, WebhookDelivery
from academics.webhook_delivery import enqueue_webhook_deliveries, process_single_delivery


class _MockHTTPResponse:
	def __init__(self, status=200, body='ok'):
		self.status = status
		self._body = body.encode('utf-8')

	def read(self):
		return self._body

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc, tb):
		return False


class WebhookDeliveryTests(TestCase):
	def setUp(self):
		self.webhook_enrollment = Webhook.objects.create(
			name='Enrollment Hook',
			target_url='https://example.test/enrollment',
			events=['enrollment.created'],
			is_active=True,
		)
		self.webhook_all_events = Webhook.objects.create(
			name='All Events Hook',
			target_url='https://example.test/all',
			events=[],
			is_active=True,
		)
		self.webhook_inactive = Webhook.objects.create(
			name='Inactive Hook',
			target_url='https://example.test/inactive',
			events=['enrollment.created'],
			is_active=False,
		)

	def test_enqueue_webhook_deliveries_filters_active_and_event_match(self):
		created = enqueue_webhook_deliveries('enrollment.created', payload={'id': 10})
		self.assertEqual(created, 2)

		deliveries = WebhookDelivery.objects.order_by('id')
		self.assertEqual(deliveries.count(), 2)
		self.assertEqual(deliveries[0].webhook_id, self.webhook_enrollment.id)
		self.assertEqual(deliveries[1].webhook_id, self.webhook_all_events.id)
		self.assertEqual(deliveries[0].status, WebhookDelivery.DeliveryStatus.PENDING)

	@patch('academics.webhook_delivery.request.urlopen')
	def test_process_single_delivery_marks_success(self, mocked_urlopen):
		delivery = WebhookDelivery.objects.create(
			webhook=self.webhook_enrollment,
			event_name='enrollment.created',
			payload={'id': 11},
			status=WebhookDelivery.DeliveryStatus.PENDING,
		)
		mocked_urlopen.return_value = _MockHTTPResponse(status=200, body='accepted')

		result = process_single_delivery(delivery.id, max_attempts=3, base_retry_seconds=1)
		self.assertEqual(result['status'], 'success')

		delivery.refresh_from_db()
		self.webhook_enrollment.refresh_from_db()
		self.assertEqual(delivery.status, WebhookDelivery.DeliveryStatus.SUCCESS)
		self.assertEqual(delivery.attempt_count, 1)
		self.assertEqual(delivery.response_status_code, 200)
		self.assertEqual(delivery.response_body, 'accepted')
		self.assertIsNotNone(delivery.delivered_at)
		self.assertIsNotNone(self.webhook_enrollment.last_triggered_at)

	@patch('academics.webhook_delivery.request.urlopen')
	def test_process_single_delivery_retries_then_fails(self, mocked_urlopen):
		delivery = WebhookDelivery.objects.create(
			webhook=self.webhook_enrollment,
			event_name='enrollment.created',
			payload={'id': 12},
			status=WebhookDelivery.DeliveryStatus.PENDING,
		)

		http_error = HTTPError(
			url='https://example.test/enrollment',
			code=503,
			msg='Service Unavailable',
			hdrs=None,
			fp=io.BytesIO(b'temporary outage'),
		)
		mocked_urlopen.side_effect = [http_error, http_error]

		first = process_single_delivery(delivery.id, max_attempts=2, base_retry_seconds=1)
		self.assertEqual(first['status'], WebhookDelivery.DeliveryStatus.RETRY)
		delivery.refresh_from_db()
		self.assertEqual(delivery.attempt_count, 1)
		self.assertIsNotNone(delivery.next_retry_at)
		self.assertEqual(delivery.response_status_code, 503)

		delivery.next_retry_at = timezone.now()
		delivery.save(update_fields=['next_retry_at', 'updated_at'])

		second = process_single_delivery(delivery.id, max_attempts=2, base_retry_seconds=1)
		self.assertEqual(second['status'], WebhookDelivery.DeliveryStatus.FAILED)
		delivery.refresh_from_db()
		self.assertEqual(delivery.attempt_count, 2)
		self.assertEqual(delivery.status, WebhookDelivery.DeliveryStatus.FAILED)
		self.assertIsNone(delivery.next_retry_at)


class AdminWebhookAccessParityTests(APITestCase):
	def setUp(self):
		self.faculty_admin_role = Role.objects.create(name='Faculty Admin', slug='faculty_admin', permissions={})
		self.department_admin_role = Role.objects.create(name='Department Admin', slug='department_admin', permissions={})

		self.owner_user = User.objects.create_user(username='owner_admin', email='owner_admin@example.com', password='Pass1234!@#')
		self.other_user = User.objects.create_user(username='other_admin', email='other_admin@example.com', password='Pass1234!@#')

		UserRole.objects.create(user=self.owner_user, role=self.faculty_admin_role)
		UserRole.objects.create(user=self.other_user, role=self.department_admin_role)

		self.owner_token = Token.objects.create(user=self.owner_user)
		self.other_token = Token.objects.create(user=self.other_user)

	def test_faculty_admin_can_list_and_create_webhooks(self):
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.owner_token.key}')

		create_response = self.client.post(
			reverse('admin-webhooks'),
			{'name': 'Owner Hook', 'target_url': 'https://example.test/hook', 'events': ['enrollment.created']},
			format='json',
		)
		self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

		list_response = self.client.get(reverse('admin-webhooks'))
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data['data']), 1)

	def test_admin_webhook_access_is_owner_scoped(self):
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.owner_token.key}')
		create_response = self.client.post(
			reverse('admin-webhooks'),
			{'name': 'Private Hook', 'target_url': 'https://example.test/private', 'events': ['announcement.created']},
			format='json',
		)
		webhook_id = create_response.data['data']['id']

		self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.other_token.key}')
		patch_response = self.client.patch(
			reverse('admin-webhook-detail', kwargs={'webhook_id': webhook_id}),
			{'name': 'Hijacked'},
			format='json',
		)
		self.assertEqual(patch_response.status_code, status.HTTP_404_NOT_FOUND)

		delete_response = self.client.delete(reverse('admin-webhook-detail', kwargs={'webhook_id': webhook_id}))
		self.assertEqual(delete_response.status_code, status.HTTP_404_NOT_FOUND)
