# UniOne Django Quick Reference

## Essential Commands

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
python manage.py createsuperuser
python manage.py test
```

## Useful Management Commands

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations
python manage.py shell
```

## Environment Snapshot

- App URL: <http://127.0.0.1:8000>
- API base: /api/
- Admin: /admin/
- DB: PostgreSQL (unione_db)

## Common Issues

1. DB connection failed

- Validate DB credentials and PostgreSQL service state.

1. Migration import error

- Check INSTALLED_APPS and app config names.

1. Module not found

- Activate virtual environment and reinstall requirements.
