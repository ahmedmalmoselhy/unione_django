"""GDPR Compliance Views for data export and anonymization."""
import json
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.contrib.auth import get_user_model
from academics.models import AuditLog, CourseRating, Grade, Notification
from enrollment.models import CourseEnrollment, StudentProfile

User = get_user_model()


class GDPRDataExportView(APIView):
    """
    GET /api/student/gdpr/export
    Export all personal data (GDPR Article 20 - Data Portability).
    Returns JSON file with all user's personal data.
    """
    def get(self, request):
        user = request.user

        # Collect user data
        data = {
            'export_date': timezone.now().isoformat(),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'date_joined': user.date_joined.isoformat(),
                'last_login': user.last_login.isoformat() if user.last_login else None,
            },
            'roles': list(user.user_roles.values('role__slug', 'scope', 'scope_id')),
            'audit_logs': list(AuditLog.objects.filter(user=user).values('action', 'entity_type', 'description', 'created_at')),
            'notifications': list(Notification.objects.filter(user=user).values('title', 'body', 'type', 'read_at', 'created_at')),
        }

        # Add student data if exists
        try:
            student = user.student_profile
            data['student_profile'] = {
                'student_number': student.student_number,
                'faculty': student.faculty.name if student.faculty else None,
                'department': student.department.name if student.department else None,
                'academic_year': student.academic_year,
                'semester': student.semester,
                'enrollment_status': student.enrollment_status,
                'gpa': str(student.gpa) if student.gpa else None,
                'academic_standing': student.academic_standing,
                'enrolled_at': student.enrolled_at.isoformat() if student.enrolled_at else None,
            }

            # Add enrollments
            enrollments = CourseEnrollment.objects.filter(student=student).select_related(
                'section__course', 'academic_term'
            )
            data['enrollments'] = [
                {
                    'course': {
                        'code': e.section.course.code,
                        'name': e.section.course.name,
                    },
                    'term': e.academic_term.name,
                    'status': e.status,
                    'registered_at': e.registered_at.isoformat() if e.registered_at else None,
                }
                for e in enrollments
            ]

            # Add grades
            grades = Grade.objects.filter(enrollment__student=student)
            data['grades'] = [
                {
                    'course': g.enrollment.section.course.code,
                    'points': g.points,
                    'letter_grade': g.letter_grade,
                    'status': g.status,
                }
                for g in grades
            ]

            # Add ratings given by student
            data['ratings_given'] = list(CourseRating.objects.filter(student=student).values('rating', 'comment', 'created_at'))

        except StudentProfile.DoesNotExist:
            pass

        # Create JSON response
        json_data = json.dumps(data, indent=2, default=str)
        response = HttpResponse(json_data, content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="personal_data_{user.username}_{timezone.now().strftime("%Y%m%d")}.json"'

        # Log the export
        AuditLog.objects.create(
            user=user,
            action='EXPORT',
            entity_type='User',
            description='User exported personal data (GDPR)',
        )

        return response


class GDPRAnonymizeView(APIView):
    """
    POST /api/student/gdpr/anonymize
    Anonymize user data (GDPR Article 17 - Right to be Forgotten).
    Replaces personal data with anonymized placeholders.
    """
    def post(self, request):
        user = request.user
        payload = request.data if isinstance(request.data, dict) else {}

        if payload.get('confirmation') != 'I_UNDERSTAND_THIS_IS_IRREVERSIBLE':
            return Response(
                {'status': 'error', 'message': 'Confirmation required'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Anonymize user
        user.username = f'anon_{user.id}'
        user.email = f'anonymized_{user.id}@deleted.local'
        user.first_name = 'Deleted'
        user.last_name = 'User'
        user.is_active = False
        user.save()

        # Anonymize student profile if exists
        try:
            student = user.student_profile
            student.student_number = f'ANON_{student.id}'
            student.save()
        except StudentProfile.DoesNotExist:
            pass

        # Delete notifications
        Notification.objects.filter(user=user).delete()

        # Log the anonymization
        AuditLog.objects.create(
            user=user,
            action='ANONYMIZE',
            entity_type='User',
            description='User anonymized personal data (GDPR)',
        )

        return Response({
            'status': 'success',
            'message': 'Your account has been anonymized. All personal data has been removed.',
        })
