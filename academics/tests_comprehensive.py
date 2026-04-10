import io
from urllib.error import HTTPError
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from academics import webhook_delivery
from academics.models import Webhook, WebhookDelivery


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


class WebhookDeliveryComprehensiveTests(TestCase):
    def setUp(self):
        self.hook_scoped = Webhook.objects.create(
            name='Scoped Hook',
            target_url='https://example.test/scoped',
            events=['enrollment.created'],
            headers={'X-Test': '1'},
            secret='secret-key',
            is_active=True,
        )
        self.hook_any = Webhook.objects.create(
            name='Any Event Hook',
            target_url='https://example.test/any',
            events=[],
            headers=['invalid'],
            is_active=True,
        )
        self.hook_inactive = Webhook.objects.create(
            name='Inactive Hook',
            target_url='https://example.test/inactive',
            events=['enrollment.created'],
            is_active=False,
        )
        self.hook_deleted = Webhook.objects.create(
            name='Deleted Hook',
            target_url='https://example.test/deleted',
            events=['enrollment.created'],
            is_active=True,
            deleted_at=timezone.now(),
        )
        self.hook_mismatch = Webhook.objects.create(
            name='Mismatch Hook',
            target_url='https://example.test/mismatch',
            events=['announcement.created'],
            is_active=True,
        )

    def test_event_payload_and_header_helpers(self):
        self.assertTrue(webhook_delivery._event_matches(self.hook_scoped, 'enrollment.created'))
        self.assertFalse(webhook_delivery._event_matches(self.hook_scoped, 'grade.updated'))
        self.assertTrue(webhook_delivery._event_matches(self.hook_any, 'anything'))

        payload = webhook_delivery._build_payload_body('enrollment.created', {'id': 5})
        self.assertIn(b'"event":"enrollment.created"', payload)
        self.assertIn(b'"payload":{"id":5}', payload)

        headers = webhook_delivery._build_headers(self.hook_scoped, 'enrollment.created', payload)
        self.assertEqual(headers['X-Test'], '1')
        self.assertIn('X-UniOne-Signature', headers)
        self.assertTrue(headers['X-UniOne-Signature'].startswith('sha256='))

        headers_without_dict = webhook_delivery._build_headers(self.hook_any, 'enrollment.created', payload)
        self.assertEqual(headers_without_dict['X-UniOne-Event'], 'enrollment.created')
        self.assertNotIn('invalid', headers_without_dict)

    def test_enqueue_skips_inactive_deleted_and_normalizes_headers(self):
        created = webhook_delivery.enqueue_webhook_deliveries('enrollment.created', payload={'id': 10})
        self.assertEqual(created, 2)

        deliveries = WebhookDelivery.objects.order_by('id')
        self.assertEqual(deliveries.count(), 2)

        scoped_delivery = deliveries.filter(webhook=self.hook_scoped).first()
        any_delivery = deliveries.filter(webhook=self.hook_any).first()
        mismatch_delivery = deliveries.filter(webhook=self.hook_mismatch).first()
        self.assertIsNotNone(scoped_delivery)
        self.assertIsNotNone(any_delivery)
        self.assertIsNone(mismatch_delivery)
        self.assertEqual(any_delivery.request_headers, {})

    @patch('academics.webhook_delivery.request.urlopen')
    def test_process_single_delivery_missing_skipped_inactive_and_non_2xx(self, mocked_urlopen):
        missing = webhook_delivery.process_single_delivery(999999)
        self.assertEqual(missing['status'], 'missing')

        already_success = WebhookDelivery.objects.create(
            webhook=self.hook_scoped,
            event_name='enrollment.created',
            payload={'id': 11},
            status=WebhookDelivery.DeliveryStatus.SUCCESS,
            attempt_count=1,
        )
        skipped = webhook_delivery.process_single_delivery(already_success.id)
        self.assertEqual(skipped['status'], 'skipped')

        inactive_delivery = WebhookDelivery.objects.create(
            webhook=self.hook_inactive,
            event_name='enrollment.created',
            payload={'id': 12},
            status=WebhookDelivery.DeliveryStatus.PENDING,
        )
        inactive_result = webhook_delivery.process_single_delivery(inactive_delivery.id)
        self.assertEqual(inactive_result['status'], 'failed')
        inactive_delivery.refresh_from_db()
        self.assertEqual(inactive_delivery.error_message, 'Webhook is inactive or deleted')

        pending_delivery = WebhookDelivery.objects.create(
            webhook=self.hook_scoped,
            event_name='enrollment.created',
            payload={'id': 13},
            status=WebhookDelivery.DeliveryStatus.PENDING,
        )
        mocked_urlopen.return_value = _MockHTTPResponse(status=500, body='server-error')

        non_2xx = webhook_delivery.process_single_delivery(
            pending_delivery.id,
            max_attempts=2,
            base_retry_seconds=1,
        )
        self.assertEqual(non_2xx['status'], WebhookDelivery.DeliveryStatus.RETRY)
        pending_delivery.refresh_from_db()
        self.assertEqual(pending_delivery.status, WebhookDelivery.DeliveryStatus.RETRY)
        self.assertIsNotNone(pending_delivery.next_retry_at)

    @patch('academics.webhook_delivery.request.urlopen')
    def test_process_single_delivery_http_and_generic_exceptions(self, mocked_urlopen):
        delivery_http_error = WebhookDelivery.objects.create(
            webhook=self.hook_scoped,
            event_name='enrollment.created',
            payload={'id': 14},
            status=WebhookDelivery.DeliveryStatus.PENDING,
        )

        http_error = HTTPError(
            url='https://example.test/scoped',
            code=503,
            msg='Service Unavailable',
            hdrs=None,
            fp=io.BytesIO(b'temporary outage'),
        )
        mocked_urlopen.side_effect = http_error

        http_result = webhook_delivery.process_single_delivery(
            delivery_http_error.id,
            max_attempts=1,
            base_retry_seconds=1,
        )
        self.assertEqual(http_result['status'], WebhookDelivery.DeliveryStatus.FAILED)
        delivery_http_error.refresh_from_db()
        self.assertEqual(delivery_http_error.response_status_code, 503)
        self.assertEqual(delivery_http_error.status, WebhookDelivery.DeliveryStatus.FAILED)

        delivery_exception = WebhookDelivery.objects.create(
            webhook=self.hook_scoped,
            event_name='enrollment.created',
            payload={'id': 15},
            status=WebhookDelivery.DeliveryStatus.PENDING,
        )
        mocked_urlopen.side_effect = RuntimeError('network down')

        generic_result = webhook_delivery.process_single_delivery(
            delivery_exception.id,
            max_attempts=1,
            base_retry_seconds=1,
        )
        self.assertEqual(generic_result['status'], WebhookDelivery.DeliveryStatus.FAILED)
        delivery_exception.refresh_from_db()
        self.assertIn('RuntimeError', delivery_exception.error_message)

    @patch('academics.webhook_delivery.process_single_delivery')
    def test_process_pending_deliveries_filters_and_summary(self, mocked_process_single):
        pending = WebhookDelivery.objects.create(
            webhook=self.hook_scoped,
            event_name='enrollment.created',
            payload={'id': 21},
            status=WebhookDelivery.DeliveryStatus.PENDING,
        )
        retry_null = WebhookDelivery.objects.create(
            webhook=self.hook_scoped,
            event_name='enrollment.created',
            payload={'id': 22},
            status=WebhookDelivery.DeliveryStatus.RETRY,
            next_retry_at=None,
        )
        retry_due = WebhookDelivery.objects.create(
            webhook=self.hook_scoped,
            event_name='enrollment.created',
            payload={'id': 23},
            status=WebhookDelivery.DeliveryStatus.RETRY,
            next_retry_at=timezone.now() - timezone.timedelta(minutes=1),
        )
        WebhookDelivery.objects.create(
            webhook=self.hook_scoped,
            event_name='enrollment.created',
            payload={'id': 24},
            status=WebhookDelivery.DeliveryStatus.RETRY,
            next_retry_at=timezone.now() + timezone.timedelta(hours=1),
        )

        mocked_process_single.side_effect = [
            {'status': 'success'},
            {'status': 'retry'},
            {'status': 'failed'},
        ]

        summary = webhook_delivery.process_pending_deliveries(limit=10, max_attempts=2, base_retry_seconds=1)
        self.assertEqual(summary['processed'], 3)
        self.assertEqual(summary['success'], 1)
        self.assertEqual(summary['retry'], 1)
        self.assertEqual(summary['failed'], 1)

        self.assertEqual(mocked_process_single.call_count, 3)
        called_ids = [args[0] for args, _kwargs in mocked_process_single.call_args_list]
        self.assertIn(pending.id, called_ids)
        self.assertIn(retry_null.id, called_ids)
        self.assertIn(retry_due.id, called_ids)

    @patch('academics.webhook_delivery.process_single_delivery')
    def test_process_pending_deliveries_limit_floor(self, mocked_process_single):
        pending = WebhookDelivery.objects.create(
            webhook=self.hook_scoped,
            event_name='enrollment.created',
            payload={'id': 31},
            status=WebhookDelivery.DeliveryStatus.PENDING,
        )
        mocked_process_single.return_value = {'status': 'success'}

        summary = webhook_delivery.process_pending_deliveries(limit=0)
        self.assertEqual(summary['processed'], 1)
        self.assertEqual(summary['success'], 1)

        called_id = mocked_process_single.call_args[0][0]
        self.assertEqual(called_id, pending.id)
