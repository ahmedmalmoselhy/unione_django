import time

from django.conf import settings
from django.core.management.base import BaseCommand

from academics.webhook_delivery import process_pending_deliveries


class Command(BaseCommand):
    help = 'Run a periodic webhook delivery scheduler loop.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval-seconds',
            type=int,
            default=settings.WEBHOOK_WORKER_INTERVAL_SECONDS,
            help='Delay between processing cycles',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=settings.WEBHOOK_DELIVERY_BATCH_LIMIT,
            help='Maximum deliveries processed per cycle',
        )
        parser.add_argument(
            '--timeout-seconds',
            type=int,
            default=settings.WEBHOOK_DELIVERY_TIMEOUT_SECONDS,
            help='HTTP timeout for each delivery',
        )
        parser.add_argument(
            '--max-attempts',
            type=int,
            default=settings.WEBHOOK_DELIVERY_MAX_ATTEMPTS,
            help='Max attempts before marking a delivery as failed',
        )
        parser.add_argument(
            '--retry-base-seconds',
            type=int,
            default=settings.WEBHOOK_DELIVERY_RETRY_BASE_SECONDS,
            help='Base retry delay; actual delay uses exponential backoff',
        )
        parser.add_argument(
            '--run-once',
            action='store_true',
            help='Run a single processing cycle and exit',
        )

    def handle(self, *args, **options):
        interval_seconds = max(1, int(options['interval_seconds']))
        limit = max(1, int(options['limit']))
        timeout_seconds = max(1, int(options['timeout_seconds']))
        max_attempts = max(1, int(options['max_attempts']))
        retry_base_seconds = max(1, int(options['retry_base_seconds']))
        run_once = bool(options['run_once'])

        self.stdout.write(
            self.style.SUCCESS(
                f'Webhook scheduler started (interval={interval_seconds}s, limit={limit}, run_once={run_once})'
            )
        )

        while True:
            summary = process_pending_deliveries(
                limit=limit,
                timeout_seconds=timeout_seconds,
                max_attempts=max_attempts,
                base_retry_seconds=retry_base_seconds,
            )
            self.stdout.write(
                'Cycle summary: processed={processed}, success={success}, retry={retry}, failed={failed}, skipped={skipped}, missing={missing}'.format(
                    **summary
                )
            )

            if run_once:
                break

            try:
                time.sleep(interval_seconds)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING('Webhook scheduler stopped by user'))
                break
