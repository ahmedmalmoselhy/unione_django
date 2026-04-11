import logging

from django.conf import settings
from django.core.mail import send_mass_mail

logger = logging.getLogger(__name__)


def _default_from_email():
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@unione.local')


def _normalize_emails(emails):
    normalized = []
    seen = set()
    for email in emails or []:
        if not email:
            continue
        value = str(email).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _send_messages(message_tuples):
    if not message_tuples:
        return 0

    try:
        return send_mass_mail(tuple(message_tuples), fail_silently=True)
    except Exception as exc:  # pragma: no cover
        logger.warning('Failed to send email batch: %s', exc)
        return 0


def send_section_announcement_emails(section, announcement, recipient_emails):
    recipients = _normalize_emails(recipient_emails)
    if not recipients:
        return 0

    subject = f'New announcement: {section.course.code}'
    body = '\n'.join(
        [
            'A new section announcement has been posted.',
            f'Course: {section.course.code} - {section.course.name}',
            f'Title: {announcement.title}',
            '',
            str(announcement.body or ''),
        ]
    )

    return _send_messages([(subject, body, _default_from_email(), [email]) for email in recipients])


def send_exam_schedule_published_emails(section, schedule, recipient_emails):
    recipients = _normalize_emails(recipient_emails)
    if not recipients:
        return 0

    subject = f'Exam schedule published: {section.course.code}'
    body = '\n'.join(
        [
            'The exam schedule for your section has been published.',
            f'Course: {section.course.code} - {section.course.name}',
            f'Date: {schedule.exam_date}',
            f'Time: {schedule.start_time} - {schedule.end_time}',
            f'Location: {schedule.location or "TBA"}',
        ]
    )

    return _send_messages([(subject, body, _default_from_email(), [email]) for email in recipients])


def send_final_grade_emails(section, grade_rows):
    messages = []

    for row in grade_rows or []:
        email = str(row.get('email') or '').strip().lower()
        if not email:
            continue

        student_name = row.get('student_name') or row.get('student_number') or 'Student'
        letter_grade = row.get('letter_grade')
        points = row.get('points')

        if letter_grade:
            grade_text = f'Your final grade is {letter_grade}'
            if points is not None:
                grade_text = f'{grade_text} ({points}/100).'
            else:
                grade_text = f'{grade_text}.'
        elif points is not None:
            grade_text = f'Your final score is {points}/100.'
        else:
            grade_text = 'Your final grade has been published.'

        subject = f'Final grade published: {section.course.code}'
        body = '\n'.join(
            [
                f'Hello {student_name},',
                '',
                f'Course: {section.course.code} - {section.course.name}',
                grade_text,
            ]
        )

        messages.append((subject, body, _default_from_email(), [email]))

    return _send_messages(messages)
