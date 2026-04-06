import hashlib
import hmac
import json
from datetime import timedelta
from urllib import error, request

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Webhook, WebhookDelivery


DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_RETRY_BASE_SECONDS = 60


def _event_matches(webhook, event_name):
    events = webhook.events or []
    if not events:
        return True
    return event_name in events


def _build_payload_body(event_name, payload):
    body = {
        'event': event_name,
        'occurred_at': timezone.now().isoformat(),
        'payload': payload or {},
    }
    return json.dumps(body, separators=(',', ':')).encode('utf-8')


def _build_headers(webhook, event_name, payload_bytes):
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'UniOne-Django-Webhook/1.0',
        'X-UniOne-Event': event_name,
    }

    configured_headers = webhook.headers or {}
    if isinstance(configured_headers, dict):
        for key, value in configured_headers.items():
            headers[str(key)] = str(value)

    if webhook.secret:
        signature = hmac.new(
            webhook.secret.encode('utf-8'),
            payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()
        headers['X-UniOne-Signature'] = f'sha256={signature}'

    return headers


def enqueue_webhook_deliveries(event_name, payload=None):
    payload = payload or {}
    created = 0

    for webhook in Webhook.objects.filter(is_active=True, deleted_at__isnull=True).order_by('id'):
        if not _event_matches(webhook, event_name):
            continue

        WebhookDelivery.objects.create(
            webhook=webhook,
            event_name=event_name,
            payload=payload,
            request_headers=webhook.headers if isinstance(webhook.headers, dict) else {},
            status=WebhookDelivery.DeliveryStatus.PENDING,
            attempt_count=0,
        )
        created += 1

    return created


def _calculate_next_retry(attempt_count, base_retry_seconds):
    delay_seconds = base_retry_seconds * (2 ** max(0, attempt_count - 1))
    return timezone.now() + timedelta(seconds=delay_seconds)


def _mark_delivery_success(delivery, response_code, response_body):
    now = timezone.now()
    delivery.status = WebhookDelivery.DeliveryStatus.SUCCESS
    delivery.response_status_code = response_code
    delivery.response_body = response_body
    delivery.error_message = None
    delivery.delivered_at = now
    delivery.next_retry_at = None
    delivery.save(
        update_fields=[
            'status',
            'response_status_code',
            'response_body',
            'error_message',
            'delivered_at',
            'next_retry_at',
            'updated_at',
            'attempt_count',
        ]
    )

    delivery.webhook.last_triggered_at = now
    delivery.webhook.save(update_fields=['last_triggered_at', 'updated_at'])


def _mark_delivery_retry_or_failed(delivery, response_code, error_message, max_attempts, base_retry_seconds):
    delivery.response_status_code = response_code
    delivery.error_message = error_message[:2000] if error_message else None

    if delivery.attempt_count >= max_attempts:
        delivery.status = WebhookDelivery.DeliveryStatus.FAILED
        delivery.next_retry_at = None
    else:
        delivery.status = WebhookDelivery.DeliveryStatus.RETRY
        delivery.next_retry_at = _calculate_next_retry(delivery.attempt_count, base_retry_seconds)

    delivery.save(
        update_fields=[
            'status',
            'response_status_code',
            'error_message',
            'next_retry_at',
            'updated_at',
            'attempt_count',
        ]
    )


def process_single_delivery(delivery_id, *, timeout_seconds=DEFAULT_TIMEOUT_SECONDS, max_attempts=DEFAULT_MAX_ATTEMPTS, base_retry_seconds=DEFAULT_RETRY_BASE_SECONDS):
    with transaction.atomic():
        delivery = (
            WebhookDelivery.objects.select_for_update()
            .select_related('webhook')
            .filter(id=delivery_id)
            .first()
        )
        if delivery is None:
            return {'status': 'missing', 'delivery_id': delivery_id}

        if delivery.status == WebhookDelivery.DeliveryStatus.SUCCESS:
            return {'status': 'skipped', 'delivery_id': delivery.id}

        if not delivery.webhook.is_active or delivery.webhook.deleted_at is not None:
            delivery.status = WebhookDelivery.DeliveryStatus.FAILED
            delivery.error_message = 'Webhook is inactive or deleted'
            delivery.next_retry_at = None
            delivery.save(update_fields=['status', 'error_message', 'next_retry_at', 'updated_at'])
            return {'status': 'failed', 'delivery_id': delivery.id}

        payload_bytes = _build_payload_body(delivery.event_name, delivery.payload)
        headers = _build_headers(delivery.webhook, delivery.event_name, payload_bytes)
        delivery.attempt_count += 1

        req = request.Request(
            url=delivery.webhook.target_url,
            data=payload_bytes,
            headers=headers,
            method='POST',
        )

        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                response_body = response.read().decode('utf-8', errors='replace')
                response_code = int(getattr(response, 'status', 200))

            if 200 <= response_code < 300:
                _mark_delivery_success(delivery, response_code, response_body)
                return {'status': 'success', 'delivery_id': delivery.id, 'response_status_code': response_code}

            _mark_delivery_retry_or_failed(
                delivery,
                response_code,
                f'Non-success response code: {response_code}',
                max_attempts,
                base_retry_seconds,
            )
            return {'status': delivery.status, 'delivery_id': delivery.id, 'response_status_code': response_code}
        except error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace') if hasattr(exc, 'read') else ''
            _mark_delivery_retry_or_failed(
                delivery,
                int(exc.code),
                body or f'HTTPError: {exc}',
                max_attempts,
                base_retry_seconds,
            )
            return {'status': delivery.status, 'delivery_id': delivery.id, 'response_status_code': int(exc.code)}
        except Exception as exc:
            _mark_delivery_retry_or_failed(
                delivery,
                None,
                f'{type(exc).__name__}: {exc}',
                max_attempts,
                base_retry_seconds,
            )
            return {'status': delivery.status, 'delivery_id': delivery.id}


def process_pending_deliveries(*, limit=100, timeout_seconds=DEFAULT_TIMEOUT_SECONDS, max_attempts=DEFAULT_MAX_ATTEMPTS, base_retry_seconds=DEFAULT_RETRY_BASE_SECONDS):
    now = timezone.now()
    pending_ids = list(
        WebhookDelivery.objects.filter(
            Q(status=WebhookDelivery.DeliveryStatus.PENDING)
            | Q(status=WebhookDelivery.DeliveryStatus.RETRY, next_retry_at__isnull=True)
            | Q(status=WebhookDelivery.DeliveryStatus.RETRY, next_retry_at__lte=now)
        )
        .order_by('id')
        .values_list('id', flat=True)[: max(1, limit)]
    )

    summary = {
        'processed': 0,
        'success': 0,
        'retry': 0,
        'failed': 0,
        'skipped': 0,
        'missing': 0,
    }

    for delivery_id in pending_ids:
        result = process_single_delivery(
            delivery_id,
            timeout_seconds=timeout_seconds,
            max_attempts=max_attempts,
            base_retry_seconds=base_retry_seconds,
        )
        summary['processed'] += 1
        status_key = result.get('status')
        if status_key in summary:
            summary[status_key] += 1

    return summary
