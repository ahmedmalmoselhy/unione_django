# UniOne Django Dependencies Setup

## Runtime Dependencies

- Django>=5.0
- djangorestframework
- django-filter
- drf-spectacular
- psycopg[binary]
- python-dotenv

## Development Dependencies

- pytest
- pytest-django
- factory-boy
- coverage
- ruff
- black

## Optional Integrations

- celery
- redis

## Setup Commands

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install django djangorestframework django-filter drf-spectacular psycopg[binary] python-dotenv
pip install pytest pytest-django factory-boy coverage ruff black
```

## Suggested requirements files

- requirements.txt (runtime)
- requirements-dev.txt (development)
