from django.conf import settings
from django.core.management.base import BaseCommand

from academics.webhook_delivery import process_pending_deliveries


class Command(BaseCommand):
    help = 'Process pending webhook deliveries and schedule retries with backoff.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=settings.WEBHOOK_DELIVERY_BATCH_LIMIT, help='Maximum deliveries to process in this run')
        parser.add_argument('--timeout-seconds', type=int, default=settings.WEBHOOK_DELIVERY_TIMEOUT_SECONDS, help='HTTP timeout for each delivery')
        parser.add_argument('--max-attempts', type=int, default=settings.WEBHOOK_DELIVERY_MAX_ATTEMPTS, help='Max attempts before marking a delivery as failed')
        parser.add_argument('--retry-base-seconds', type=int, default=settings.WEBHOOK_DELIVERY_RETRY_BASE_SECONDS, help='Base retry delay; actual delay uses exponential backoff')

    def handle(self, *args, **options):
        summary = process_pending_deliveries(
            limit=max(1, int(options['limit'])),
            timeout_seconds=max(1, int(options['timeout_seconds'])),
            max_attempts=max(1, int(options['max_attempts'])),
            base_retry_seconds=max(1, int(options['retry_base_seconds'])),
        )

        self.stdout.write(
            self.style.SUCCESS(
                'Processed {processed} deliveries (success={success}, retry={retry}, failed={failed}, skipped={skipped}, missing={missing})'.format(
                    **summary,
                )
            )
        )
