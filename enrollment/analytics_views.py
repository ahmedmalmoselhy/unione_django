from django.db.models import Avg, Case, CharField, Count, F, Q, Sum, When
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import AcademicTerm, AttendanceRecord, Grade, Section, Webhook, WebhookDelivery
from accounts.permissions import HasAnyRole
from enrollment.models import CourseEnrollment, ProfessorProfile, StudentProfile
from organization.models import Department, Faculty


class AdminOnlyPermission(HasAnyRole):
    required_roles = ['admin', 'faculty_admin', 'department_admin']


def _is_super_admin(user):
    return user.is_superuser or user.user_roles.filter(role__slug='admin').exists()


def _get_user_scopes(user):
    """Return dict of scopes the user has admin access to."""
    scopes = {'is_super': _is_super_admin(user), 'faculties': set(), 'departments': set()}
    for ur in user.user_roles.select_related('role'):
        if ur.role.slug == 'faculty_admin' and ur.scope == 'faculty' and ur.scope_id:
            scopes['faculties'].add(ur.scope_id)
        elif ur.role.slug == 'department_admin' and ur.scope == 'department' and ur.scope_id:
            scopes['departments'].add(ur.scope_id)
    return scopes


class EnrollmentAnalyticsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        scopes = _get_user_scopes(request.user)

        term_id = request.query_params.get('academic_term_id')
        faculty_id = request.query_params.get('faculty_id')
        department_id = request.query_params.get('department_id')

        enrollments = CourseEnrollment.objects.select_related(
            'section__course', 'section__academic_term', 'student__department', 'student__faculty'
        )

        if term_id:
            enrollments = enrollments.filter(academic_term_id=term_id)
        if faculty_id:
            enrollments = enrollments.filter(student__faculty_id=faculty_id)
        if department_id:
            enrollments = enrollments.filter(student__department_id=department_id)

        if not scopes['is_super']:
            if scopes['faculties']:
                enrollments = enrollments.filter(student__faculty_id__in=scopes['faculties'])
            elif scopes['departments']:
                enrollments = enrollments.filter(student__department_id__in=scopes['departments'])

        status_counts = enrollments.values('status').annotate(count=Count('id'))
        status_summary = {s['status']: s['count'] for s in status_counts}

        faculty_stats = (
            enrollments.values('student__faculty__name')
            .annotate(
                total=Count('id'),
                active=Count('id', filter=Q(status='active')),
                completed=Count('id', filter=Q(status='completed')),
            )
            .order_by('student__faculty__name')
        )

        department_stats = (
            enrollments.values('student__department__name', 'student__faculty__name')
            .annotate(
                total=Count('id'),
                active=Count('id', filter=Q(status='active')),
            )
            .order_by('student__faculty__name', 'student__department__name')[:50]
        )

        term_stats = (
            enrollments.values('academic_term__name')
            .annotate(
                total=Count('id'),
                active=Count('id', filter=Q(status='active')),
                dropped=Count('id', filter=Q(status='dropped')),
            )
            .order_by('-academic_term__start_date')[:10]
        )

        data = {
            'summary': {
                'total': sum(status_summary.values()),
                'by_status': status_summary,
            },
            'by_faculty': [
                {
                    'faculty': s['student__faculty__name'],
                    'total': s['total'],
                    'active': s['active'],
                    'completed': s['completed'],
                }
                for s in faculty_stats
            ],
            'by_department': [
                {
                    'department': s['student__department__name'],
                    'faculty': s['student__faculty__name'],
                    'total': s['total'],
                    'active': s['active'],
                }
                for s in department_stats
            ],
            'by_term': [
                {
                    'term': s['academic_term__name'],
                    'total': s['total'],
                    'active': s['active'],
                    'dropped': s['dropped'],
                }
                for s in term_stats
            ],
        }

        return Response({'status': 'success', 'data': data})


class GradesAnalyticsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        scopes = _get_user_scopes(request.user)

        term_id = request.query_params.get('academic_term_id')
        course_id = request.query_params.get('course_id')
        faculty_id = request.query_params.get('faculty_id')

        grades = Grade.objects.select_related(
            'enrollment__section__course',
            'enrollment__section__academic_term',
            'enrollment__student__department',
        )

        if term_id:
            grades = grades.filter(enrollment__academic_term_id=term_id)
        if course_id:
            grades = grades.filter(enrollment__section__course_id=course_id)
        if faculty_id:
            grades = grades.filter(enrollment__student__faculty_id=faculty_id)

        if not scopes['is_super']:
            if scopes['faculties']:
                grades = grades.filter(enrollment__student__faculty_id__in=scopes['faculties'])
            elif scopes['departments']:
                grades = grades.filter(enrollment__student__department_id__in=scopes['departments'])

        total_count = grades.count()
        if total_count == 0:
            return Response({'status': 'success', 'data': {'summary': {'total': 0}, 'distribution': []}})

        avg_points = grades.aggregate(avg=Avg('points'))['avg'] or 0

        distribution = (
            grades.values('letter_grade')
            .annotate(count=Count('id'))
            .order_by('letter_grade')
        )

        grade_order = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'F']
        grade_counts = {d['letter_grade']: d['count'] for d in distribution}
        sorted_dist = [{'grade': g, 'count': grade_counts.get(g, 0)} for g in grade_order if g in grade_counts]

        course_stats = (
            grades.values('enrollment__section__course__code', 'enrollment__section__course__name')
            .annotate(
                total=Count('id'),
                avg_points=Avg('points'),
            )
            .order_by('-avg_points')[:20]
        )

        data = {
            'summary': {
                'total': total_count,
                'average_points': round(avg_points, 2),
            },
            'distribution': sorted_dist,
            'by_course': [
                {
                    'course_code': s['enrollment__section__course__code'],
                    'course_name': s['enrollment__section__course__name'],
                    'total_grades': s['total'],
                    'average_points': round(s['avg_points'], 2),
                }
                for s in course_stats
            ],
        }

        return Response({'status': 'success', 'data': data})


class AttendanceAnalyticsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        scopes = _get_user_scopes(request.user)

        term_id = request.query_params.get('academic_term_id')
        section_id = request.query_params.get('section_id')
        faculty_id = request.query_params.get('faculty_id')

        records = AttendanceRecord.objects.select_related(
            'session__section__course',
            'enrollment__student__department',
        )

        if section_id:
            records = records.filter(session__section_id=section_id)
        if term_id:
            records = records.filter(session__section__academic_term_id=term_id)
        if faculty_id:
            records = records.filter(enrollment__student__faculty_id=faculty_id)

        if not scopes['is_super']:
            if scopes['faculties']:
                records = records.filter(enrollment__student__faculty_id__in=scopes['faculties'])
            elif scopes['departments']:
                records = records.filter(enrollment__student__department_id__in=scopes['departments'])

        total = records.count()
        if total == 0:
            return Response({'status': 'success', 'data': {'summary': {'total_records': 0}}})

        status_counts = records.values('status').annotate(count=Count('id'))
        status_summary = {s['status']: s['count'] for s in status_counts}

        present_pct = (status_summary.get('present', 0) / total * 100) if total else 0
        absent_pct = (status_summary.get('absent', 0) / total * 100) if total else 0

        session_stats = (
            AttendanceRecord.objects.values('session__section__course__code')
            .annotate(
                total_sessions=Count('session_id', distinct=True),
                avg_attendance=Count('id', filter=Q(status='present')) * 100.0 / Count('id'),
            )
            .order_by('-avg_attendance')[:20]
        )

        data = {
            'summary': {
                'total_records': total,
                'present_count': status_summary.get('present', 0),
                'absent_count': status_summary.get('absent', 0),
                'late_count': status_summary.get('late', 0),
                'excused_count': status_summary.get('excused', 0),
                'present_percentage': round(present_pct, 2),
                'absent_percentage': round(absent_pct, 2),
            },
            'by_status': status_summary,
            'by_course': [
                {
                    'course_code': s['session__section__course__code'],
                    'total_sessions': s['total_sessions'],
                    'average_attendance_pct': round(s['avg_attendance'], 2),
                }
                for s in session_stats
            ],
        }

        return Response({'status': 'success', 'data': data})


class WebhookMetricsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        webhook_id = request.query_params.get('webhook_id')

        deliveries = WebhookDelivery.objects.all()
        if webhook_id:
            deliveries = deliveries.filter(webhook_id=webhook_id)

        total = deliveries.count()
        if total == 0:
            return Response({'status': 'success', 'data': {'summary': {'total_deliveries': 0}}})

        status_counts = deliveries.values('status').annotate(count=Count('id'))
        status_summary = {s['status']: s['count'] for s in status_counts}

        recent_failures = (
            deliveries.filter(status='failed')
            .select_related('webhook')
            .order_by('-created_at')[:20]
        )

        webhook_stats = (
            deliveries.values('webhook__id', 'webhook__name')
            .annotate(
                total=Count('id'),
                success=Count('id', filter=Q(status='success')),
                failed=Count('id', filter=Q(status='failed')),
            )
            .order_by('-total')[:20]
        )

        data = {
            'summary': {
                'total_deliveries': total,
                'pending': status_summary.get('pending', 0),
                'success': status_summary.get('success', 0),
                'failed': status_summary.get('failed', 0),
                'retry': status_summary.get('retry', 0),
            },
            'recent_failures': [
                {
                    'id': f.id,
                    'webhook_name': f.webhook.name,
                    'event_name': f.event_name,
                    'error_message': f.error_message,
                    'attempt_count': f.attempt_count,
                    'created_at': f.created_at,
                }
                for f in recent_failures
            ],
            'by_webhook': [
                {
                    'webhook_id': s['webhook__id'],
                    'webhook_name': s['webhook__name'],
                    'total': s['total'],
                    'success': s['success'],
                    'failed': s['failed'],
                }
                for s in webhook_stats
            ],
        }

        return Response({'status': 'success', 'data': data})


class StudentStatisticsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        scopes = _get_user_scopes(request.user)

        students = StudentProfile.objects.select_related('faculty', 'department', 'user')

        if not scopes['is_super']:
            if scopes['faculties']:
                students = students.filter(faculty_id__in=scopes['faculties'])
            elif scopes['departments']:
                students = students.filter(department_id__in=scopes['departments'])

        total = students.count()

        status_counts = students.values('enrollment_status').annotate(count=Count('id'))
        status_summary = {s['enrollment_status']: s['count'] for s in status_counts}

        standing_counts = students.values('academic_standing').annotate(count=Count('id'))
        standing_summary = {s['academic_standing']: s['count'] for s in standing_counts}

        by_faculty = (
            students.values('faculty__name')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        by_year = (
            students.values('academic_year')
            .annotate(count=Count('id'))
            .order_by('academic_year')
        )

        data = {
            'summary': {
                'total_students': total,
            },
            'by_status': status_summary,
            'by_academic_standing': standing_summary,
            'by_faculty': [
                {'faculty': f['faculty__name'], 'count': f['count']}
                for f in by_faculty
            ],
            'by_academic_year': [
                {'year': y['academic_year'], 'count': y['count']}
                for y in by_year
            ],
        }

        return Response({'status': 'success', 'data': data})


class ProfessorStatisticsView(APIView):
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        scopes = _get_user_scopes(request.user)

        professors = ProfessorProfile.objects.select_related('department__faculty', 'user')

        if not scopes['is_super']:
            if scopes['faculties']:
                professors = professors.filter(department__faculty_id__in=scopes['faculties'])
            elif scopes['departments']:
                professors = professors.filter(department_id__in=scopes['departments'])

        total = professors.count()

        rank_counts = professors.values('academic_rank').annotate(count=Count('id'))
        rank_summary = {r['academic_rank']: r['count'] for r in rank_counts}

        by_department = (
            professors.values('department__name', 'department__faculty__name')
            .annotate(count=Count('id'))
            .order_by('department__faculty__name', 'department__name')
        )

        section_counts = (
            Section.objects.values('professor_id')
            .annotate(section_count=Count('id'))
        )
        prof_section_map = {s['professor_id']: s['section_count'] for s in section_counts}

        top_professors = sorted(
            [
                {
                    'id': p.id,
                    'name': p.user.get_full_name() or p.user.username,
                    'staff_number': p.staff_number,
                    'department': p.department.name,
                    'section_count': prof_section_map.get(p.id, 0),
                }
                for p in professors
            ],
            key=lambda x: x['section_count'],
            reverse=True,
        )[:20]

        data = {
            'summary': {
                'total_professors': total,
            },
            'by_rank': rank_summary,
            'by_department': [
                {
                    'department': d['department__name'],
                    'faculty': d['department__faculty__name'],
                    'count': d['count'],
                }
                for d in by_department
            ],
            'top_by_sections': top_professors,
        }

        return Response({'status': 'success', 'data': data})
