"""Celery tasks for background job processing."""
from config.celery import app

from django.utils import timezone
from academics.webhook_delivery import process_single_delivery, enqueue_webhook_deliveries
from enrollment.email_delivery import (
    send_section_announcement_emails,
    send_exam_schedule_published_emails,
    send_final_grade_emails,
)
import logging

logger = logging.getLogger(__name__)


@app.task(bind=True, max_retries=5, default_retry_delay=60)
def send_announcement_email_task(self, announcement_id):
    """Send announcement emails asynchronously."""
    try:
        send_section_announcement_emails(announcement_id)
    except Exception as exc:
        logger.exception(f'Failed to send announcement emails for {announcement_id}')
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=5, default_retry_delay=60)
def send_exam_schedule_email_task(self, section_id):
    """Send exam schedule emails asynchronously."""
    try:
        send_exam_schedule_published_emails(section_id)
    except Exception as exc:
        logger.exception(f'Failed to send exam schedule emails for section {section_id}')
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=5, default_retry_delay=60)
def send_final_grade_email_task(self, enrollment_ids):
    """Send final grade emails asynchronously."""
    try:
        send_final_grade_emails(enrollment_ids)
    except Exception as exc:
        logger.exception(f'Failed to send final grade emails for enrollments {enrollment_ids}')
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=5, default_retry_delay=120)
def process_webhook_delivery_task(self, delivery_id):
    """Process webhook delivery asynchronously."""
    try:
        process_single_delivery(delivery_id)
    except Exception as exc:
        logger.exception(f'Failed to process webhook delivery {delivery_id}')
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=3, default_retry_delay=300)
def enqueue_webhook_event_task(self, event, payload):
    """Enqueue webhook deliveries for an event."""
    try:
        enqueue_webhook_deliveries(event, payload)
    except Exception as exc:
        logger.exception(f'Failed to enqueue webhook for event {event}')
        raise self.retry(exc=exc)


# Periodic tasks (use Celery Beat for scheduling)
@app.task
def cleanup_old_webhook_deliveries():
    """Clean up old webhook deliveries (runs daily)."""
    from academics.models import WebhookDelivery
    from django.utils import timezone

    cutoff = timezone.now() - timezone.timedelta(days=30)
    deleted, _ = WebhookDelivery.objects.filter(created_at__lt=cutoff).delete()
    logger.info(f'Cleaned up {deleted} old webhook deliveries')
    return deleted


@app.task
def archive_old_notifications():
    """Archive old read notifications (runs weekly)."""
    from academics.models import Notification
    from django.utils import timezone

    cutoff = timezone.now() - timezone.timedelta(days=90)
    archived = Notification.objects.filter(read_at__lt=cutoff).count()
    # Could move to archive table or delete
    logger.info(f'Found {archived} old notifications to archive')
    return archived
