import json
from datetime import timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from academics.models import WebhookDelivery


class Command(BaseCommand):
    help = 'Archive old webhook deliveries to JSONL and purge old archive files.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--archive-days',
            type=int,
            default=settings.WEBHOOK_DELIVERY_ARCHIVE_AFTER_DAYS,
            help='Archive deliveries older than this many days',
        )
        parser.add_argument(
            '--purge-days',
            type=int,
            default=settings.WEBHOOK_DELIVERY_ARCHIVE_RETENTION_DAYS,
            help='Delete archive files older than this many days',
        )
        parser.add_argument(
            '--output-dir',
            type=str,
            default=str(settings.WEBHOOK_ARCHIVE_DIR),
            help='Directory where archive files are written',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=5000,
            help='Maximum number of deliveries to archive in this run',
        )

    def handle(self, *args, **options):
        archive_days = max(1, int(options['archive_days']))
        purge_days = max(1, int(options['purge_days']))
        limit = max(1, int(options['limit']))
        output_dir = Path(options['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)

        now = timezone.now()
        archive_cutoff = now - timezone.timedelta(days=archive_days)
        purge_cutoff = now - timezone.timedelta(days=purge_days)

        archiveable = WebhookDelivery.objects.filter(
            created_at__lt=archive_cutoff,
            status__in=[WebhookDelivery.DeliveryStatus.SUCCESS, WebhookDelivery.DeliveryStatus.FAILED],
        ).order_by('id')[:limit]
        archiveable_ids = list(archiveable.values_list('id', flat=True))

        archived_count = 0
        if archiveable_ids:
            records = list(
                WebhookDelivery.objects.filter(id__in=archiveable_ids).values(
                    'id',
                    'webhook_id',
                    'event_name',
                    'payload',
                    'request_headers',
                    'response_status_code',
                    'response_body',
                    'status',
                    'attempt_count',
                    'error_message',
                    'delivered_at',
                    'next_retry_at',
                    'created_at',
                    'updated_at',
                )
            )
            archive_file = output_dir / f'webhook_deliveries_{now.strftime("%Y%m%d_%H%M%S")}.jsonl'
            with archive_file.open('w', encoding='utf-8') as handle:
                for record in records:
                    handle.write(json.dumps(record, default=str))
                    handle.write('\n')

            archived_count = len(records)
            WebhookDelivery.objects.filter(id__in=archiveable_ids).delete()

        purged_files = 0
        for file_path in output_dir.glob('webhook_deliveries_*.jsonl'):
            modified_at = timezone.datetime.fromtimestamp(file_path.stat().st_mtime, tz=dt_timezone.utc)
            if file_path.is_file() and modified_at < purge_cutoff:
                file_path.unlink(missing_ok=True)
                purged_files += 1

        self.stdout.write(
            self.style.SUCCESS(
                'Archived {archived} deliveries and purged {purged} archive files'.format(
                    archived=archived_count,
                    purged=purged_files,
                )
            )
        )
