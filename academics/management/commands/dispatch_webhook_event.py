import json

from django.core.management.base import BaseCommand, CommandError

from academics.webhook_delivery import enqueue_webhook_deliveries


class Command(BaseCommand):
    help = 'Queue webhook deliveries for a given event.'

    def add_arguments(self, parser):
        parser.add_argument('--event', required=True, help='Event name to dispatch')
        parser.add_argument(
            '--payload',
            default='{}',
            help='JSON object payload string, e.g. {"id": 1, "type": "test"}',
        )

    def handle(self, *args, **options):
        event_name = str(options['event']).strip()
        if not event_name:
            raise CommandError('event must not be empty')

        payload_raw = options['payload']
        try:
            payload = json.loads(payload_raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f'invalid payload JSON: {exc}') from exc

        if not isinstance(payload, dict):
            raise CommandError('payload must decode to a JSON object')

        created = enqueue_webhook_deliveries(event_name, payload=payload)
        self.stdout.write(self.style.SUCCESS(f'Queued {created} webhook deliveries for event {event_name}'))
