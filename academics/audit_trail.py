from datetime import date, datetime
from decimal import Decimal

from django.db.models.signals import post_delete, post_save, pre_save

from academics.models import AcademicTerm, AttendanceRecord, AuditLog, Course, Grade, Section
from accounts.models import UserRole
from enrollment.models import CourseEnrollment
from organization.models import Department, Faculty


TRACKED_MODELS = [
    CourseEnrollment,
    Grade,
    AttendanceRecord,
    Faculty,
    Department,
    Course,
    Section,
    AcademicTerm,
    UserRole,
]

_REGISTERED = False


def _serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


def _snapshot(instance):
    data = {}
    for field in instance._meta.fields:
        if field.is_relation and hasattr(field, 'attname'):
            key = field.attname
            value = getattr(instance, key, None)
        else:
            key = field.name
            value = getattr(instance, field.name, None)
        data[key] = _serialize(value)
    return data


def _resolve_related_user(instance):
    if hasattr(instance, 'user'):
        return instance.user
    if hasattr(instance, 'student') and hasattr(instance.student, 'user'):
        return instance.student.user
    if hasattr(instance, 'enrollment') and hasattr(instance.enrollment, 'student') and hasattr(instance.enrollment.student, 'user'):
        return instance.enrollment.student.user
    return None


def _capture_old_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._audit_old_values = {}
        return
    previous = sender.objects.filter(pk=instance.pk).first()
    instance._audit_old_values = _snapshot(previous) if previous else {}


def _log_save(sender, instance, created, **kwargs):
    old_values = getattr(instance, '_audit_old_values', {})
    new_values = _snapshot(instance)

    if not created and old_values == new_values:
        return

    AuditLog.objects.create(
        user=_resolve_related_user(instance),
        action=AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE,
        entity_type=sender.__name__,
        entity_id=str(instance.pk),
        description=f'{sender.__name__} {"created" if created else "updated"} via model signal',
        old_values={} if created else old_values,
        new_values=new_values,
    )


def _log_delete(sender, instance, **kwargs):
    AuditLog.objects.create(
        user=_resolve_related_user(instance),
        action=AuditLog.Action.DELETE,
        entity_type=sender.__name__,
        entity_id=str(instance.pk),
        description=f'{sender.__name__} deleted via model signal',
        old_values=_snapshot(instance),
        new_values={},
    )


def register_signals():
    global _REGISTERED
    if _REGISTERED:
        return

    for model in TRACKED_MODELS:
        model_key = model._meta.label_lower
        pre_save.connect(_capture_old_state, sender=model, weak=False, dispatch_uid=f'audit_pre_save_{model_key}')
        post_save.connect(_log_save, sender=model, weak=False, dispatch_uid=f'audit_post_save_{model_key}')
        post_delete.connect(_log_delete, sender=model, weak=False, dispatch_uid=f'audit_post_delete_{model_key}')

    _REGISTERED = True
