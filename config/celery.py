"""Celery configuration for background job processing."""
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('unione_django')

# Use Redis as broker and backend
app.config_from_object({
    'broker_url': os.getenv('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0'),
    'result_backend': os.getenv('CELERY_RESULT_BACKEND', 'redis://127.0.0.1:6379/0'),
    'accept_content': ['json'],
    'task_serializer': 'json',
    'result_serializer': 'json',
    'timezone': os.getenv('CELERY_TIMEZONE', 'UTC'),
    'enable_utc': True,
    'task_track_started': True,
    'task_acks_late': True,
    'worker_prefetch_multiplier': 1,
    'task_default_retry_delay': 60,
    'task_max_retries': 5,
})

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()
