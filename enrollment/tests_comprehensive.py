from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from academics.models import (
    AcademicTerm,
    Announcement,
    AuditLog,
    AttendanceRecord,
    AttendanceSession,
    Course,
    CourseRating,
    ExamSchedule,
    EnrollmentWaitlist,
    GlobalAnnouncementRead,
    Grade,
    GroupProject,
    Notification,
    Section,
    SectionAnnouncement,
    SectionTeachingAssistant,
    Webhook,
    WebhookDelivery,
)
from accounts.models import Role, UserRole
from enrollment.admin_views import _get_user_scopes as _admin_get_user_scopes
from enrollment.admin_views import _user_has_scoped_role
from enrollment.audit_log_views import _is_super_admin as _audit_is_super_admin
from enrollment.models import CourseEnrollment, ProfessorProfile, StudentProfile
from enrollment.services import (
    _parse_hhmm,
    _safe_grade_points,
    build_student_academic_history,
    build_student_schedule,
    build_student_schedule_ics,
    build_student_transcript,
    build_student_transcript_pdf_bytes,
)
from enrollment.shared_views import _user_role_slugs
from organization.models import Department, Faculty, University


class _BaseEnrollmentSetup:
    def setUp(self):
        self.university = University.objects.create(
            name='Uni Comprehensive',
            code='UC1',
            country='EG',
            city='Cairo',
            established_year=1990,
        )
        self.faculty = Faculty.objects.create(university=self.university, name='Engineering', code='ENGC')
        self.other_faculty = Faculty.objects.create(university=self.university, name='Business', code='BUSC')
        self.department = Department.objects.create(faculty=self.faculty, name='Computer Science', code='CSC')
        self.other_department = Department.objects.create(faculty=self.other_faculty, name='Finance', code='FINC')

        self.admin_role = Role.objects.create(name='Admin Comprehensive', slug='admin', permissions={})
        self.student_role = Role.objects.create(name='Student Comprehensive', slug='student', permissions={})
        self.prof_role = Role.objects.create(name='Professor Comprehensive', slug='professor', permissions={})
        self.faculty_admin_role = Role.objects.create(name='Faculty Admin Comprehensive', slug='faculty_admin', permissions={})
        self.department_admin_role = Role.objects.create(name='Department Admin Comprehensive', slug='department_admin', permissions={})

        self.admin_user = User.objects.create_user(username='admin_comp', email='admin_comp@example.com', password='Pass1234!@#')
        UserRole.objects.create(user=self.admin_user, role=self.admin_role)

        self.student_user = User.objects.create_user(username='student_comp', email='student_comp@example.com', password='Pass1234!@#')
        UserRole.objects.create(user=self.student_user, role=self.student_role)

        self.prof_user = User.objects.create_user(username='prof_comp', email='prof_comp@example.com', password='Pass1234!@#')
        UserRole.objects.create(user=self.prof_user, role=self.prof_role)

        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            student_number='S-COMP-1',
            faculty=self.faculty,
            department=self.department,
            academic_year=2,
            semester=1,
            enrolled_at='2024-09-01',
        )
        self.professor = ProfessorProfile.objects.create(
            user=self.prof_user,
            staff_number='P-COMP-1',
            department=self.department,
            hired_at='2020-01-01',
        )

        self.term = AcademicTerm.objects.create(
            name='Fall 2026',
            start_date='2026-09-01',
            end_date='2027-01-15',
            registration_start='2026-08-01',
            registration_end='2026-08-25',
            is_active=True,
        )
        self.next_term = AcademicTerm.objects.create(
            name='Spring 2027',
            start_date='2027-02-01',
            end_date='2027-06-15',
            registration_start='2027-01-01',
            registration_end='2027-01-20',
            is_active=False,
        )

        self.course = Course.objects.create(code='CSC101', name='Comprehensive 101', credit_hours=3, lecture_hours=3, lab_hours=0, level=100)
        self.course_two = Course.objects.create(code='CSC201', name='Comprehensive 201', credit_hours=4, lecture_hours=3, lab_hours=1, level=200)

        self.section = Section.objects.create(
            course=self.course,
            professor=self.professor,
            academic_term=self.term,
            semester=1,
            capacity=1,
            schedule={'days': [1, 3], 'start_time': '09:00', 'end_time': '10:30'},
        )
        self.section_two = Section.objects.create(
            course=self.course_two,
            professor=self.professor,
            academic_term=self.next_term,
            semester=2,
            capacity=30,
            schedule={'days': [2, 5], 'start_time': '11:00', 'end_time': '12:30'},
        )

        self.active_enrollment = CourseEnrollment.objects.create(
            student=self.student_profile,
            section=self.section,
            academic_term=self.term,
            status=CourseEnrollment.EnrollmentStatus.ACTIVE,
        )
        self.dropped_enrollment = CourseEnrollment.objects.create(
            student=self.student_profile,
            section=self.section_two,
            academic_term=self.next_term,
            status=CourseEnrollment.EnrollmentStatus.DROPPED,
        )
        Grade.objects.create(enrollment=self.active_enrollment, points=95, letter_grade='A', status=Grade.Status.COMPLETE)

    def _auth(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')


class ServiceLayerComprehensiveTests(_BaseEnrollmentSetup, TestCase):
    def test_safe_grade_points_paths(self):
        self.assertEqual(_safe_grade_points('A-', None), 3.7)
        self.assertEqual(_safe_grade_points(None, 80), 3.2)
        self.assertEqual(_safe_grade_points(None, 'invalid'), None)
        self.assertEqual(_safe_grade_points(None, 120), 4.0)

    def test_parse_hhmm_fallback(self):
        self.assertEqual(_parse_hhmm('08:30', 9).hour, 8)
        self.assertEqual(_parse_hhmm('xx', 9).hour, 9)

    def test_transcript_history_schedule_and_pdf_builders(self):
        transcript = build_student_transcript(self.student_profile)
        self.assertEqual(transcript['summary']['attempted_credit_hours'], 3)
        self.assertEqual(transcript['summary']['earned_credit_hours'], 3)
        self.assertEqual(transcript['summary']['cumulative_gpa'], 4.0)
        self.assertEqual(len(transcript['terms']), 1)

        history = build_student_academic_history(self.student_profile)
        self.assertEqual(len(history['records']), 1)
        self.assertEqual(history['records'][0]['course']['code'], 'CSC101')

        schedule = build_student_schedule(self.student_profile)
        self.assertEqual(len(schedule), 1)
        self.assertEqual(schedule[0]['section']['course']['code'], 'CSC101')

        ics_content = build_student_schedule_ics(self.student_profile)
        self.assertIn('BEGIN:VCALENDAR', ics_content)
        self.assertIn('RRULE:FREQ=WEEKLY', ics_content)
        self.assertIn('CSC101 - Comprehensive 101', ics_content)

        pdf_bytes = build_student_transcript_pdf_bytes(self.student_profile)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-1.4'))
        self.assertGreater(len(pdf_bytes), 200)


class StudentViewsComprehensiveTests(_BaseEnrollmentSetup, APITestCase):
    def setUp(self):
        super().setUp()
        self._auth(self.student_user)

    def test_student_transcript_pdf_schedule_and_attendance_endpoints(self):
        transcript_response = self.client.get(reverse('student-transcript'))
        self.assertEqual(transcript_response.status_code, status.HTTP_200_OK)
        self.assertIn('summary', transcript_response.data['data'])

        pdf_response = self.client.get(reverse('student-transcript-pdf'))
        self.assertEqual(pdf_response.status_code, status.HTTP_200_OK)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')

        schedule_response = self.client.get(reverse('student-schedule'))
        self.assertEqual(schedule_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(schedule_response.data['data']), 1)

        ics_response = self.client.get(reverse('student-schedule-ics'))
        self.assertEqual(ics_response.status_code, status.HTTP_200_OK)
        self.assertIn('text/calendar', ics_response['Content-Type'])

        session = AttendanceSession.objects.create(
            section=self.section,
            created_by=self.professor,
            session_date='2026-10-01',
            title='Week 1',
        )
        AttendanceRecord.objects.create(
            session=session,
            enrollment=self.active_enrollment,
            status=AttendanceRecord.Status.PRESENT,
        )
        attendance_response = self.client.get(reverse('student-attendance'))
        self.assertEqual(attendance_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(attendance_response.data['data']), 1)

    def test_student_waitlist_delete_paths(self):
        missing_response = self.client.delete(reverse('student-waitlist-delete', kwargs={'section_id': self.section_two.id}))
        self.assertEqual(missing_response.status_code, status.HTTP_404_NOT_FOUND)

        full_section = Section.objects.create(
            course=self.course_two,
            professor=self.professor,
            academic_term=self.next_term,
            semester=2,
            capacity=1,
            schedule={'days': [4], 'start_time': '13:00', 'end_time': '14:30'},
        )

        full_student_user = User.objects.create_user(username='seat_user', email='seat_user@example.com', password='Pass1234!@#')
        UserRole.objects.create(user=full_student_user, role=self.student_role)
        full_student_profile = StudentProfile.objects.create(
            user=full_student_user,
            student_number='S-COMP-2',
            faculty=self.faculty,
            department=self.department,
            academic_year=2,
            semester=1,
            enrolled_at='2024-09-01',
        )
        CourseEnrollment.objects.create(
            student=full_student_profile,
            section=full_section,
            academic_term=self.next_term,
            status=CourseEnrollment.EnrollmentStatus.ACTIVE,
        )

        response = self.client.post(reverse('student-enrollments'), {'section_id': full_section.id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        delete_response = self.client.delete(reverse('student-waitlist-delete', kwargs={'section_id': full_section.id}))
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)

    def test_student_ratings_validation_and_upsert(self):
        missing_response = self.client.post(reverse('student-ratings'), {}, format='json')
        self.assertEqual(missing_response.status_code, status.HTTP_400_BAD_REQUEST)

        bad_type_response = self.client.post(
            reverse('student-ratings'),
            {'course_id': 'x', 'rating': 'y'},
            format='json',
        )
        self.assertEqual(bad_type_response.status_code, status.HTTP_400_BAD_REQUEST)

        bad_range_response = self.client.post(
            reverse('student-ratings'),
            {'course_id': self.course.id, 'rating': 9},
            format='json',
        )
        self.assertEqual(bad_range_response.status_code, status.HTTP_400_BAD_REQUEST)

        unknown_course_response = self.client.post(
            reverse('student-ratings'),
            {'course_id': 99999, 'rating': 4},
            format='json',
        )
        self.assertEqual(unknown_course_response.status_code, status.HTTP_400_BAD_REQUEST)

        save_response = self.client.post(
            reverse('student-ratings'),
            {'course_id': self.course.id, 'section_id': self.section.id, 'rating': 5, 'comment': 'Excellent'},
            format='json',
        )
        self.assertEqual(save_response.status_code, status.HTTP_200_OK)

        update_response = self.client.post(
            reverse('student-ratings'),
            {'course_id': self.course.id, 'section_id': self.section.id, 'rating': 4, 'comment': 'Updated'},
            format='json',
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(CourseRating.objects.filter(student=self.student_profile, course=self.course).count(), 1)

    def test_student_enrollment_validation_paths(self):
        response = self.client.post(reverse('student-enrollments'), {'section_id': 'abc'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        duplicate_response = self.client.post(reverse('student-enrollments'), {'section_id': self.section.id}, format='json')
        self.assertEqual(duplicate_response.status_code, status.HTTP_400_BAD_REQUEST)

        self.active_enrollment.status = CourseEnrollment.EnrollmentStatus.DROPPED
        self.active_enrollment.save(update_fields=['status', 'updated_at'])
        dropped_delete = self.client.delete(reverse('student-enrollment-delete', kwargs={'enrollment_id': self.active_enrollment.id}))
        self.assertEqual(dropped_delete.status_code, status.HTTP_400_BAD_REQUEST)


class ProfessorViewsComprehensiveTests(_BaseEnrollmentSetup, APITestCase):
    def setUp(self):
        super().setUp()
        self._auth(self.prof_user)

    def test_professor_profile_missing_and_sections_schedule(self):
        no_profile_user = User.objects.create_user(username='prof_np', email='prof_np@example.com', password='Pass1234!@#')
        UserRole.objects.create(user=no_profile_user, role=self.prof_role)
        self._auth(no_profile_user)
        missing_profile_response = self.client.get(reverse('professor-profile'))
        self.assertEqual(missing_profile_response.status_code, status.HTTP_404_NOT_FOUND)

        self._auth(self.prof_user)
        sections_response = self.client.get(reverse('professor-sections'), {'academic_term_id': self.term.id})
        self.assertEqual(sections_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(sections_response.data['data']), 1)

        schedule_response = self.client.get(reverse('professor-schedule'))
        self.assertEqual(schedule_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(schedule_response.data['data'][0]['slots']), 1)

    def test_professor_section_students_and_grades_paths(self):
        missing_section_response = self.client.get(reverse('professor-section-students', kwargs={'section_id': 9999}))
        self.assertEqual(missing_section_response.status_code, status.HTTP_404_NOT_FOUND)

        students_response = self.client.get(reverse('professor-section-students', kwargs={'section_id': self.section.id}))
        self.assertEqual(students_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(students_response.data['data']['students']), 1)

        empty_grades_payload = self.client.post(
            reverse('professor-section-grades', kwargs={'section_id': self.section.id}),
            {'grades': []},
            format='json',
        )
        self.assertEqual(empty_grades_payload.status_code, status.HTTP_400_BAD_REQUEST)

        missing_enrollment_id = self.client.post(
            reverse('professor-section-grades', kwargs={'section_id': self.section.id}),
            {'grades': [{'points': 88, 'letter_grade': 'B+'}]},
            format='json',
        )
        self.assertEqual(missing_enrollment_id.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_status_response = self.client.post(
            reverse('professor-section-grades', kwargs={'section_id': self.section.id}),
            {'grades': [{'enrollment_id': self.active_enrollment.id, 'points': 88, 'letter_grade': 'B+', 'status': 'weird'}]},
            format='json',
        )
        self.assertEqual(invalid_status_response.status_code, status.HTTP_400_BAD_REQUEST)

        success_response = self.client.post(
            reverse('professor-section-grades', kwargs={'section_id': self.section.id}),
            {'grades': [{'enrollment_id': self.active_enrollment.id, 'points': 88, 'letter_grade': 'B+', 'status': Grade.Status.COMPLETE}]},
            format='json',
        )
        self.assertEqual(success_response.status_code, status.HTTP_200_OK)
        self.assertEqual(Grade.objects.get(enrollment=self.active_enrollment).points, 88)

    def test_professor_attendance_create_detail_update_paths(self):
        invalid_date_response = self.client.post(
            reverse('professor-section-attendance', kwargs={'section_id': self.section.id}),
            {'session_date': 'bad-date'},
            format='json',
        )
        self.assertEqual(invalid_date_response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_status_response = self.client.post(
            reverse('professor-section-attendance', kwargs={'section_id': self.section.id}),
            {
                'session_date': '2026-10-01',
                'records': [{'enrollment_id': self.active_enrollment.id, 'status': 'wrong'}],
            },
            format='json',
        )
        self.assertEqual(invalid_status_response.status_code, status.HTTP_400_BAD_REQUEST)

        created_response = self.client.post(
            reverse('professor-section-attendance', kwargs={'section_id': self.section.id}),
            {'session_date': '2026-10-02', 'title': 'Week 2'},
            format='json',
        )
        self.assertEqual(created_response.status_code, status.HTTP_201_CREATED)
        session_id = created_response.data['data']['id']

        get_detail_response = self.client.get(
            reverse('professor-section-attendance-detail', kwargs={'section_id': self.section.id, 'session_id': session_id})
        )
        self.assertEqual(get_detail_response.status_code, status.HTTP_200_OK)

        invalid_put_date = self.client.put(
            reverse('professor-section-attendance-detail', kwargs={'section_id': self.section.id, 'session_id': session_id}),
            {'session_date': 'bad'},
            format='json',
        )
        self.assertEqual(invalid_put_date.status_code, status.HTTP_400_BAD_REQUEST)

        success_put = self.client.put(
            reverse('professor-section-attendance-detail', kwargs={'section_id': self.section.id, 'session_id': session_id}),
            {
                'title': 'Week 2 Updated',
                'records': [
                    {'enrollment_id': self.active_enrollment.id, 'status': AttendanceRecord.Status.LATE, 'note': 'Traffic'}
                ],
            },
            format='json',
        )
        self.assertEqual(success_put.status_code, status.HTTP_200_OK)

    def test_professor_announcements_create_list_delete_paths(self):
        missing_fields_response = self.client.post(
            reverse('professor-section-announcements', kwargs={'section_id': self.section.id}),
            {'title': 'Only title'},
            format='json',
        )
        self.assertEqual(missing_fields_response.status_code, status.HTTP_400_BAD_REQUEST)

        create_response = self.client.post(
            reverse('professor-section-announcements', kwargs={'section_id': self.section.id}),
            {'title': 'Quiz', 'body': 'Quiz on Sunday', 'is_pinned': True},
            format='json',
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        ann_id = create_response.data['data']['id']

        list_response = self.client.get(reverse('professor-section-announcements', kwargs={'section_id': self.section.id}))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data['data']), 1)
        self.assertGreaterEqual(Notification.objects.filter(notification_type='section_announcement').count(), 1)

        missing_delete = self.client.delete(
            reverse('professor-section-announcement-delete', kwargs={'section_id': self.section.id, 'announcement_id': 99999})
        )
        self.assertEqual(missing_delete.status_code, status.HTTP_404_NOT_FOUND)

        delete_response = self.client.delete(
            reverse('professor-section-announcement-delete', kwargs={'section_id': self.section.id, 'announcement_id': ann_id})
        )
        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertFalse(SectionAnnouncement.objects.filter(id=ann_id).exists())


class AdminOrganizationScopedAccessComprehensiveTests(_BaseEnrollmentSetup, APITestCase):
    def setUp(self):
        super().setUp()
        self.faculty_admin_user = User.objects.create_user(username='fac_admin_comp', email='fac_admin_comp@example.com', password='Pass1234!@#')
        self.department_admin_user = User.objects.create_user(username='dep_admin_comp', email='dep_admin_comp@example.com', password='Pass1234!@#')

        UserRole.objects.create(
            user=self.faculty_admin_user,
            role=self.faculty_admin_role,
            scope='faculty',
            scope_id=self.faculty.id,
        )
        UserRole.objects.create(
            user=self.department_admin_user,
            role=self.department_admin_role,
            scope='department',
            scope_id=self.department.id,
        )

    def test_faculty_admin_scope_and_forbidden_writes(self):
        self._auth(self.faculty_admin_user)

        list_faculties_response = self.client.get(reverse('admin-faculties'))
        self.assertEqual(list_faculties_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_faculties_response.data['data']), 1)
        self.assertEqual(list_faculties_response.data['data'][0]['id'], self.faculty.id)

        forbidden_create_faculty = self.client.post(
            reverse('admin-faculties'),
            {'name': 'Medicine', 'code': 'MED', 'university_id': self.university.id},
            format='json',
        )
        self.assertEqual(forbidden_create_faculty.status_code, status.HTTP_403_FORBIDDEN)

        allowed_department_create = self.client.post(
            reverse('admin-departments'),
            {'name': 'AI', 'code': 'AI', 'faculty_id': self.faculty.id},
            format='json',
        )
        self.assertEqual(allowed_department_create.status_code, status.HTTP_201_CREATED)

        forbidden_other_faculty_department_create = self.client.post(
            reverse('admin-departments'),
            {'name': 'Marketing', 'code': 'MKT', 'faculty_id': self.other_faculty.id},
            format='json',
        )
        self.assertEqual(forbidden_other_faculty_department_create.status_code, status.HTTP_403_FORBIDDEN)

    def test_department_admin_scope_and_permissions(self):
        self._auth(self.department_admin_user)

        list_departments_response = self.client.get(reverse('admin-departments'))
        self.assertEqual(list_departments_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_departments_response.data['data']), 1)
        self.assertEqual(list_departments_response.data['data'][0]['id'], self.department.id)

        forbidden_department_create = self.client.post(
            reverse('admin-departments'),
            {'name': 'SecOps', 'code': 'SEC', 'faculty_id': self.faculty.id},
            format='json',
        )
        self.assertEqual(forbidden_department_create.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_required_and_detail_edge_cases(self):
        self._auth(self.admin_user)

        duplicate_course = self.client.post(
            reverse('admin-courses'),
            {'code': self.course.code, 'name': 'Duplicate', 'credit_hours': 3},
            format='json',
        )
        self.assertEqual(duplicate_course.status_code, status.HTTP_400_BAD_REQUEST)

        missing_university = self.client.post(
            reverse('admin-faculties'),
            {'name': 'Health', 'code': 'HLT', 'university_id': 99999},
            format='json',
        )
        self.assertEqual(missing_university.status_code, status.HTTP_404_NOT_FOUND)

        section_patch_invalid_prof = self.client.patch(
            reverse('admin-section-detail', kwargs={'section_id': self.section.id}),
            {'professor_id': 99999},
            format='json',
        )
        self.assertEqual(section_patch_invalid_prof.status_code, status.HTTP_404_NOT_FOUND)

        missing_term_required = self.client.post(
            reverse('admin-academic-terms'),
            {'name': 'Incomplete Term'},
            format='json',
        )
        self.assertEqual(missing_term_required.status_code, status.HTTP_400_BAD_REQUEST)

    def test_faculty_and_department_detail_scope_paths(self):
        self._auth(self.faculty_admin_user)

        own_faculty = self.client.get(reverse('admin-faculty-detail', kwargs={'faculty_id': self.faculty.id}))
        self.assertEqual(own_faculty.status_code, status.HTTP_200_OK)

        foreign_faculty = self.client.get(reverse('admin-faculty-detail', kwargs={'faculty_id': self.other_faculty.id}))
        self.assertEqual(foreign_faculty.status_code, status.HTTP_403_FORBIDDEN)

        own_department = self.client.get(reverse('admin-department-detail', kwargs={'department_id': self.department.id}))
        self.assertEqual(own_department.status_code, status.HTTP_200_OK)

        foreign_department = self.client.get(reverse('admin-department-detail', kwargs={'department_id': self.other_department.id}))
        self.assertEqual(foreign_department.status_code, status.HTTP_403_FORBIDDEN)

        patched_department = self.client.patch(
            reverse('admin-department-detail', kwargs={'department_id': self.department.id}),
            {'name': 'Computer Science Updated', 'is_mandatory': True},
            format='json',
        )
        self.assertEqual(patched_department.status_code, status.HTTP_200_OK)

        temp_department = Department.objects.create(
            faculty=self.faculty,
            name='Temp Deletable Department',
            code='TMPDEL',
            scope=Department.Scope.DEPARTMENT,
        )
        delete_department = self.client.delete(
            reverse('admin-department-detail', kwargs={'department_id': temp_department.id})
        )
        self.assertEqual(delete_department.status_code, status.HTTP_200_OK)

        self._auth(self.department_admin_user)
        own_department_dep_admin = self.client.get(reverse('admin-department-detail', kwargs={'department_id': self.department.id}))
        self.assertEqual(own_department_dep_admin.status_code, status.HTTP_200_OK)

        dep_admin_patch = self.client.patch(
            reverse('admin-department-detail', kwargs={'department_id': self.department.id}),
            {'required_credit_hours': 120},
            format='json',
        )
        self.assertEqual(dep_admin_patch.status_code, status.HTTP_200_OK)

        dep_admin_delete_denied = self.client.delete(
            reverse('admin-department-detail', kwargs={'department_id': self.department.id})
        )
        self.assertEqual(dep_admin_delete_denied.status_code, status.HTTP_403_FORBIDDEN)

    def test_super_admin_org_crud_and_filter_paths(self):
        self._auth(self.admin_user)

        faculties_filtered = self.client.get(reverse('admin-faculties'), {'search': 'Engineering'})
        self.assertEqual(faculties_filtered.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(faculties_filtered.data['data']), 1)

        duplicate_faculty_code = self.client.post(
            reverse('admin-faculties'),
            {'name': 'Engineering Duplicate', 'code': self.faculty.code, 'university_id': self.university.id},
            format='json',
        )
        self.assertEqual(duplicate_faculty_code.status_code, status.HTTP_400_BAD_REQUEST)

        patch_faculty = self.client.patch(
            reverse('admin-faculty-detail', kwargs={'faculty_id': self.faculty.id}),
            {'name': 'Engineering Prime'},
            format='json',
        )
        self.assertEqual(patch_faculty.status_code, status.HTTP_200_OK)

        terms_filtered = self.client.get(reverse('admin-academic-terms'), {'is_active': 'true'})
        self.assertEqual(terms_filtered.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(terms_filtered.data['data']), 1)

        term_create = self.client.post(
            reverse('admin-academic-terms'),
            {
                'name': 'Summer 2027',
                'start_date': '2027-06-20',
                'end_date': '2027-08-30',
                'registration_start': '2027-06-01',
                'registration_end': '2027-06-15',
                'is_active': False,
            },
            format='json',
        )
        self.assertEqual(term_create.status_code, status.HTTP_201_CREATED)
        term_id = term_create.data['data']['id']

        term_patch = self.client.patch(
            reverse('admin-academic-term-detail', kwargs={'term_id': term_id}),
            {'is_active': True},
            format='json',
        )
        self.assertEqual(term_patch.status_code, status.HTTP_200_OK)

        term_delete = self.client.delete(reverse('admin-academic-term-detail', kwargs={'term_id': term_id}))
        self.assertEqual(term_delete.status_code, status.HTTP_200_OK)

        term_delete_missing = self.client.delete(reverse('admin-academic-term-detail', kwargs={'term_id': term_id}))
        self.assertEqual(term_delete_missing.status_code, status.HTTP_404_NOT_FOUND)

        course_missing_required = self.client.post(
            reverse('admin-courses'),
            {'code': 'NEWX100'},
            format='json',
        )
        self.assertEqual(course_missing_required.status_code, status.HTTP_400_BAD_REQUEST)

        course_create = self.client.post(
            reverse('admin-courses'),
            {'code': 'NEWX100', 'name': 'New Course X', 'credit_hours': 3, 'is_active': False, 'level': 400},
            format='json',
        )
        self.assertEqual(course_create.status_code, status.HTTP_201_CREATED)
        new_course_id = course_create.data['data']['id']

        courses_filtered = self.client.get(reverse('admin-courses'), {'is_active': 'false', 'level': 400, 'search': 'NEWX'})
        self.assertEqual(courses_filtered.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(courses_filtered.data['data']), 1)

        course_detail = self.client.get(reverse('admin-course-detail', kwargs={'course_id': new_course_id}))
        self.assertEqual(course_detail.status_code, status.HTTP_200_OK)

        course_patch = self.client.patch(
            reverse('admin-course-detail', kwargs={'course_id': new_course_id}),
            {'is_active': True, 'credit_hours': 4},
            format='json',
        )
        self.assertEqual(course_patch.status_code, status.HTTP_200_OK)

        section_missing_required = self.client.post(
            reverse('admin-sections'),
            {'course_id': self.course.id},
            format='json',
        )
        self.assertEqual(section_missing_required.status_code, status.HTTP_400_BAD_REQUEST)

        section_missing_course = self.client.post(
            reverse('admin-sections'),
            {'course_id': 99999, 'professor_id': self.professor.id, 'academic_term_id': self.term.id},
            format='json',
        )
        self.assertEqual(section_missing_course.status_code, status.HTTP_404_NOT_FOUND)

        section_missing_professor = self.client.post(
            reverse('admin-sections'),
            {'course_id': self.course.id, 'professor_id': 99999, 'academic_term_id': self.term.id},
            format='json',
        )
        self.assertEqual(section_missing_professor.status_code, status.HTTP_404_NOT_FOUND)

        section_missing_term = self.client.post(
            reverse('admin-sections'),
            {'course_id': self.course.id, 'professor_id': self.professor.id, 'academic_term_id': 99999},
            format='json',
        )
        self.assertEqual(section_missing_term.status_code, status.HTTP_404_NOT_FOUND)

        section_create = self.client.post(
            reverse('admin-sections'),
            {
                'course_id': self.course.id,
                'professor_id': self.professor.id,
                'academic_term_id': self.term.id,
                'semester': 2,
                'capacity': 35,
                'schedule': {'days': [2], 'start_time': '15:00', 'end_time': '16:30'},
            },
            format='json',
        )
        self.assertEqual(section_create.status_code, status.HTTP_201_CREATED)
        new_section_id = section_create.data['data']['id']

        sections_filtered = self.client.get(
            reverse('admin-sections'),
            {'course_id': self.course.id, 'academic_term_id': self.term.id, 'professor_id': self.professor.id},
        )
        self.assertEqual(sections_filtered.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(sections_filtered.data['data']), 1)

        section_detail = self.client.get(reverse('admin-section-detail', kwargs={'section_id': new_section_id}))
        self.assertEqual(section_detail.status_code, status.HTTP_200_OK)

        ta_user = User.objects.create_user(
            username='ta_prof_comp',
            email='ta_prof_comp@example.com',
            password='Pass1234!@#',
        )
        UserRole.objects.create(user=ta_user, role=self.prof_role)
        ta_professor = ProfessorProfile.objects.create(
            user=ta_user,
            staff_number='P-COMP-TA',
            department=self.department,
            hired_at='2021-01-01',
        )

        ta_assign_missing = self.client.post(
            reverse('admin-section-teaching-assistants', kwargs={'section_id': new_section_id}),
            {},
            format='json',
        )
        self.assertEqual(ta_assign_missing.status_code, status.HTTP_400_BAD_REQUEST)

        ta_assign = self.client.post(
            reverse('admin-section-teaching-assistants', kwargs={'section_id': new_section_id}),
            {'professor_id': ta_professor.id},
            format='json',
        )
        self.assertEqual(ta_assign.status_code, status.HTTP_201_CREATED)
        ta_assignment_id = ta_assign.data['data']['id']

        ta_assign_duplicate = self.client.post(
            reverse('admin-section-teaching-assistants', kwargs={'section_id': new_section_id}),
            {'professor_id': ta_professor.id},
            format='json',
        )
        self.assertEqual(ta_assign_duplicate.status_code, status.HTTP_200_OK)

        ta_list = self.client.get(reverse('admin-section-teaching-assistants', kwargs={'section_id': new_section_id}))
        self.assertEqual(ta_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(ta_list.data['data']), 1)
        self.assertTrue(
            SectionTeachingAssistant.objects.filter(id=ta_assignment_id, section_id=new_section_id).exists()
        )

        ta_delete_missing = self.client.delete(
            reverse('admin-section-teaching-assistant-detail', kwargs={'section_id': new_section_id, 'ta_id': 99999})
        )
        self.assertEqual(ta_delete_missing.status_code, status.HTTP_404_NOT_FOUND)

        ta_delete = self.client.delete(
            reverse('admin-section-teaching-assistant-detail', kwargs={'section_id': new_section_id, 'ta_id': ta_assignment_id})
        )
        self.assertEqual(ta_delete.status_code, status.HTTP_200_OK)
        self.assertFalse(SectionTeachingAssistant.objects.filter(id=ta_assignment_id).exists())

        exam_get_missing = self.client.get(
            reverse('admin-section-exam-schedule', kwargs={'section_id': new_section_id})
        )
        self.assertEqual(exam_get_missing.status_code, status.HTTP_404_NOT_FOUND)

        exam_create_missing_fields = self.client.post(
            reverse('admin-section-exam-schedule', kwargs={'section_id': new_section_id}),
            {'exam_date': '2027-01-15'},
            format='json',
        )
        self.assertEqual(exam_create_missing_fields.status_code, status.HTTP_400_BAD_REQUEST)

        exam_create = self.client.post(
            reverse('admin-section-exam-schedule', kwargs={'section_id': new_section_id}),
            {
                'exam_date': '2027-01-15',
                'start_time': '09:00:00',
                'end_time': '11:00:00',
                'location': 'Main Hall',
            },
            format='json',
        )
        self.assertEqual(exam_create.status_code, status.HTTP_201_CREATED)
        exam_schedule_id = exam_create.data['data']['id']

        exam_create_duplicate = self.client.post(
            reverse('admin-section-exam-schedule', kwargs={'section_id': new_section_id}),
            {
                'exam_date': '2027-01-16',
                'start_time': '10:00:00',
                'end_time': '12:00:00',
            },
            format='json',
        )
        self.assertEqual(exam_create_duplicate.status_code, status.HTTP_409_CONFLICT)

        exam_get = self.client.get(reverse('admin-section-exam-schedule', kwargs={'section_id': new_section_id}))
        self.assertEqual(exam_get.status_code, status.HTTP_200_OK)
        self.assertEqual(exam_get.data['data']['id'], exam_schedule_id)

        exam_publish = self.client.post(reverse('admin-section-exam-schedule-publish', kwargs={'section_id': new_section_id}))
        self.assertEqual(exam_publish.status_code, status.HTTP_200_OK)
        self.assertTrue(exam_publish.data['data']['is_published'])

        exam_patch = self.client.patch(
            reverse('admin-section-exam-schedule', kwargs={'section_id': new_section_id}),
            {'location': 'Hall B'},
            format='json',
        )
        self.assertEqual(exam_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(ExamSchedule.objects.get(id=exam_schedule_id).location, 'Hall B')
        self.assertFalse(ExamSchedule.objects.get(id=exam_schedule_id).is_published)

        group_list_empty = self.client.get(reverse('admin-section-group-projects', kwargs={'section_id': new_section_id}))
        self.assertEqual(group_list_empty.status_code, status.HTTP_200_OK)
        self.assertEqual(len(group_list_empty.data['data']), 0)

        group_create_missing = self.client.post(
            reverse('admin-section-group-projects', kwargs={'section_id': new_section_id}),
            {'description': 'Missing title'},
            format='json',
        )
        self.assertEqual(group_create_missing.status_code, status.HTTP_400_BAD_REQUEST)

        group_create = self.client.post(
            reverse('admin-section-group-projects', kwargs={'section_id': new_section_id}),
            {
                'title': 'Capstone Team Project',
                'description': 'Build an end-to-end prototype',
                'max_members': 2,
            },
            format='json',
        )
        self.assertEqual(group_create.status_code, status.HTTP_201_CREATED)
        group_project_id = group_create.data['data']['id']

        CourseEnrollment.objects.create(
            student=self.student_profile,
            section_id=new_section_id,
            academic_term=self.term,
            status=CourseEnrollment.EnrollmentStatus.ACTIVE,
        )

        outsider_user = User.objects.create_user(
            username='group_outsider',
            email='group_outsider@example.com',
            password='Pass1234!@#',
        )
        UserRole.objects.create(user=outsider_user, role=self.student_role)
        outsider_student = StudentProfile.objects.create(
            user=outsider_user,
            student_number='S-COMP-OUT',
            faculty=self.faculty,
            department=self.department,
            academic_year=2,
            semester=1,
            enrolled_at='2024-09-01',
        )

        group_member_add_missing = self.client.post(
            reverse(
                'admin-section-group-project-members',
                kwargs={'section_id': new_section_id, 'project_id': group_project_id},
            ),
            {},
            format='json',
        )
        self.assertEqual(group_member_add_missing.status_code, status.HTTP_400_BAD_REQUEST)

        group_member_add_not_enrolled = self.client.post(
            reverse(
                'admin-section-group-project-members',
                kwargs={'section_id': new_section_id, 'project_id': group_project_id},
            ),
            {'student_id': outsider_student.id},
            format='json',
        )
        self.assertEqual(group_member_add_not_enrolled.status_code, status.HTTP_400_BAD_REQUEST)

        group_member_add = self.client.post(
            reverse(
                'admin-section-group-project-members',
                kwargs={'section_id': new_section_id, 'project_id': group_project_id},
            ),
            {'student_id': self.student_profile.id},
            format='json',
        )
        self.assertEqual(group_member_add.status_code, status.HTTP_201_CREATED)
        group_member_id = group_member_add.data['data']['id']

        group_member_duplicate = self.client.post(
            reverse(
                'admin-section-group-project-members',
                kwargs={'section_id': new_section_id, 'project_id': group_project_id},
            ),
            {'student_id': self.student_profile.id},
            format='json',
        )
        self.assertEqual(group_member_duplicate.status_code, status.HTTP_200_OK)

        group_list = self.client.get(reverse('admin-section-group-projects', kwargs={'section_id': new_section_id}))
        self.assertEqual(group_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(group_list.data['data']), 1)
        self.assertEqual(len(group_list.data['data'][0]['members']), 1)

        group_patch = self.client.patch(
            reverse('admin-section-group-project-detail', kwargs={'section_id': new_section_id, 'project_id': group_project_id}),
            {'title': 'Updated Capstone Project', 'max_members': 3, 'is_active': False},
            format='json',
        )
        self.assertEqual(group_patch.status_code, status.HTTP_200_OK)

        group_member_delete_missing = self.client.delete(
            reverse(
                'admin-section-group-project-member-detail',
                kwargs={'section_id': new_section_id, 'project_id': group_project_id, 'member_id': 99999},
            )
        )
        self.assertEqual(group_member_delete_missing.status_code, status.HTTP_404_NOT_FOUND)

        group_member_delete = self.client.delete(
            reverse(
                'admin-section-group-project-member-detail',
                kwargs={'section_id': new_section_id, 'project_id': group_project_id, 'member_id': group_member_id},
            )
        )
        self.assertEqual(group_member_delete.status_code, status.HTTP_200_OK)

        group_delete = self.client.delete(
            reverse('admin-section-group-project-detail', kwargs={'section_id': new_section_id, 'project_id': group_project_id})
        )
        self.assertEqual(group_delete.status_code, status.HTTP_200_OK)
        self.assertFalse(GroupProject.objects.filter(id=group_project_id).exists())

        section_patch = self.client.patch(
            reverse('admin-section-detail', kwargs={'section_id': new_section_id}),
            {'semester': 3, 'capacity': 40},
            format='json',
        )
        self.assertEqual(section_patch.status_code, status.HTTP_200_OK)

        section_delete = self.client.delete(reverse('admin-section-detail', kwargs={'section_id': new_section_id}))
        self.assertEqual(section_delete.status_code, status.HTTP_200_OK)

        section_delete_missing = self.client.delete(reverse('admin-section-detail', kwargs={'section_id': new_section_id}))
        self.assertEqual(section_delete_missing.status_code, status.HTTP_404_NOT_FOUND)

        course_delete = self.client.delete(reverse('admin-course-detail', kwargs={'course_id': new_course_id}))
        self.assertEqual(course_delete.status_code, status.HTTP_200_OK)

        course_delete_missing = self.client.delete(reverse('admin-course-detail', kwargs={'course_id': new_course_id}))
        self.assertEqual(course_delete_missing.status_code, status.HTTP_404_NOT_FOUND)


class AdminAnalyticsAndImportExportComprehensiveTests(_BaseEnrollmentSetup, APITestCase):
    def setUp(self):
        super().setUp()
        self.other_faculty_admin_user = User.objects.create_user(
            username='fac_other_comp',
            email='fac_other_comp@example.com',
            password='Pass1234!@#',
        )
        self.no_scope_faculty_admin_user = User.objects.create_user(
            username='fac_noscope_comp',
            email='fac_noscope_comp@example.com',
            password='Pass1234!@#',
        )
        self.department_scoped_admin_user = User.objects.create_user(
            username='dep_scope_comp',
            email='dep_scope_comp@example.com',
            password='Pass1234!@#',
        )
        UserRole.objects.create(
            user=self.other_faculty_admin_user,
            role=self.faculty_admin_role,
            scope='faculty',
            scope_id=self.other_faculty.id,
        )
        UserRole.objects.create(
            user=self.no_scope_faculty_admin_user,
            role=self.faculty_admin_role,
        )
        UserRole.objects.create(
            user=self.department_scoped_admin_user,
            role=self.department_admin_role,
            scope='department',
            scope_id=self.department.id,
        )

    def test_admin_user_and_webhook_validation_branches(self):
        self._auth(self.admin_user)

        missing_user_field = self.client.post(
            reverse('admin-users'),
            {'username': 'missing_email', 'password': 'Pass1234!@#'},
            format='json',
        )
        self.assertEqual(missing_user_field.status_code, status.HTTP_400_BAD_REQUEST)

        roles_not_list = self.client.post(
            reverse('admin-users'),
            {'username': 'bad_roles', 'email': 'bad_roles@example.com', 'password': 'Pass1234!@#', 'roles': 'student'},
            format='json',
        )
        self.assertEqual(roles_not_list.status_code, status.HTTP_400_BAD_REQUEST)

        created_user = self.client.post(
            reverse('admin-users'),
            {'username': 'ops_user', 'email': 'ops_user@example.com', 'password': 'Pass1234!@#', 'roles': ['student']},
            format='json',
        )
        self.assertEqual(created_user.status_code, status.HTTP_201_CREATED)
        created_user_id = created_user.data['data']['id']

        patch_roles_not_list = self.client.patch(
            reverse('admin-user-detail', kwargs={'user_id': created_user_id}),
            {'roles': 'student'},
            format='json',
        )
        self.assertEqual(patch_roles_not_list.status_code, status.HTTP_400_BAD_REQUEST)

        cannot_delete_self = self.client.delete(reverse('admin-user-detail', kwargs={'user_id': self.admin_user.id}))
        self.assertEqual(cannot_delete_self.status_code, status.HTTP_400_BAD_REQUEST)

        webhook_missing_required = self.client.post(
            reverse('admin-webhooks'),
            {'name': 'No target'},
            format='json',
        )
        self.assertEqual(webhook_missing_required.status_code, status.HTTP_400_BAD_REQUEST)

        webhook_bad_events = self.client.post(
            reverse('admin-webhooks'),
            {'name': 'Bad events', 'target_url': 'https://example.com/hook', 'events': 'event.name'},
            format='json',
        )
        self.assertEqual(webhook_bad_events.status_code, status.HTTP_400_BAD_REQUEST)

        created_webhook = self.client.post(
            reverse('admin-webhooks'),
            {
                'name': 'Ops Hook',
                'target_url': 'https://example.com/hook',
                'events': ['enrollment.created'],
                'headers': {'x-token': 'abc'},
            },
            format='json',
        )
        self.assertEqual(created_webhook.status_code, status.HTTP_201_CREATED)
        webhook_id = created_webhook.data['data']['id']

        webhook = Webhook.objects.get(id=webhook_id)
        WebhookDelivery.objects.create(
            webhook=webhook,
            event_name='enrollment.created',
            payload={'id': 1},
            status=WebhookDelivery.DeliveryStatus.PENDING,
            attempt_count=0,
        )

        invalid_limit = self.client.get(
            reverse('admin-webhook-deliveries', kwargs={'webhook_id': webhook_id}),
            {'limit': 'abc'},
        )
        self.assertEqual(invalid_limit.status_code, status.HTTP_400_BAD_REQUEST)

        no_fields_patch = self.client.patch(
            reverse('admin-webhook-detail', kwargs={'webhook_id': webhook_id}),
            {},
            format='json',
        )
        self.assertEqual(no_fields_patch.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_events_patch = self.client.patch(
            reverse('admin-webhook-detail', kwargs={'webhook_id': webhook_id}),
            {'events': 'bad'},
            format='json',
        )
        self.assertEqual(invalid_events_patch.status_code, status.HTTP_400_BAD_REQUEST)

        valid_patch = self.client.patch(
            reverse('admin-webhook-detail', kwargs={'webhook_id': webhook_id}),
            {'name': 'Ops Hook Updated', 'events': ['enrollment.created', 'enrollment.updated']},
            format='json',
        )
        self.assertEqual(valid_patch.status_code, status.HTTP_200_OK)

        deleted = self.client.delete(reverse('admin-webhook-detail', kwargs={'webhook_id': webhook_id}))
        self.assertEqual(deleted.status_code, status.HTTP_200_OK)

        missing_after_delete = self.client.get(reverse('admin-webhook-deliveries', kwargs={'webhook_id': webhook_id}))
        self.assertEqual(missing_after_delete.status_code, status.HTTP_404_NOT_FOUND)

    def test_import_export_and_analytics_scope_branches(self):
        self._auth(self.no_scope_faculty_admin_user)

        empty_enrollment_export = self.client.get(reverse('admin-export-enrollments'))
        self.assertEqual(empty_enrollment_export.status_code, status.HTTP_200_OK)
        self.assertEqual(len(empty_enrollment_export.content.decode('utf-8').strip().splitlines()), 1)

        empty_grades_export = self.client.get(reverse('admin-export-grades'))
        self.assertEqual(empty_grades_export.status_code, status.HTTP_200_OK)
        self.assertEqual(len(empty_grades_export.content.decode('utf-8').strip().splitlines()), 1)

        self._auth(self.admin_user)

        missing_import_payload = self.client.post(reverse('admin-import-users'), {}, format='json')
        self.assertEqual(missing_import_payload.status_code, status.HTTP_400_BAD_REQUEST)

        missing_courses_import_payload = self.client.post(reverse('admin-import-courses'), {}, format='json')
        self.assertEqual(missing_courses_import_payload.status_code, status.HTTP_400_BAD_REQUEST)

        import_users_response = self.client.post(
            reverse('admin-import-users'),
            {
                'rows': [
                    {'username': '', 'email': 'invalid@example.com'},
                    {'username': 'bulk_user_1', 'email': 'bulk_user_1@example.com', 'roles': 'student|faculty_admin'},
                    {'username': 'bulk_user_1', 'email': 'bulk_user_1@example.com'},
                ]
            },
            format='json',
        )
        self.assertEqual(import_users_response.status_code, status.HTTP_200_OK)
        self.assertEqual(import_users_response.data['data']['created'], 1)
        self.assertEqual(import_users_response.data['data']['skipped'], 2)

        import_users_with_bool_and_role_list = self.client.post(
            reverse('admin-import-users'),
            {
                'rows': [
                    {
                        'username': 'bulk_user_2',
                        'email': 'bulk_user_2@example.com',
                        'is_superuser': 'yes',
                        'is_staff': True,
                        'roles': ['student', 'professor'],
                    }
                ]
            },
            format='json',
            HTTP_X_FORWARDED_FOR='10.1.1.1, 10.1.1.2',
        )
        self.assertEqual(import_users_with_bool_and_role_list.status_code, status.HTTP_200_OK)
        self.assertTrue(User.objects.get(username='bulk_user_2').is_staff)
        self.assertTrue(User.objects.get(username='bulk_user_2').is_superuser)

        import_courses_response = self.client.post(
            reverse('admin-import-courses'),
            {
                'rows': [
                    {'code': '', 'name': 'Missing Code', 'credit_hours': '3'},
                    {'code': 'BULK101', 'name': 'Bulk Course Bad', 'credit_hours': 'x'},
                    {'code': 'BULK101', 'name': 'Bulk Course Good', 'credit_hours': '3', 'lecture_hours': '2', 'lab_hours': '1'},
                    {'code': 'BULK101', 'name': 'Bulk Course Dup', 'credit_hours': '3'},
                ]
            },
            format='json',
        )
        self.assertEqual(import_courses_response.status_code, status.HTTP_200_OK)
        self.assertEqual(import_courses_response.data['data']['created'], 1)
        self.assertEqual(import_courses_response.data['data']['skipped'], 3)

        self._auth(self.department_scoped_admin_user)
        export_enrollments_filtered = self.client.get(
            reverse('admin-export-enrollments'),
            {
                'academic_term_id': self.term.id,
                'course_id': self.course.id,
                'status': CourseEnrollment.EnrollmentStatus.ACTIVE,
            },
            HTTP_X_FORWARDED_FOR='10.2.2.2, 10.2.2.3',
        )
        self.assertEqual(export_enrollments_filtered.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(export_enrollments_filtered.content.decode('utf-8').strip().splitlines()), 2)

        export_grades_filtered = self.client.get(
            reverse('admin-export-grades'),
            {
                'academic_term_id': self.term.id,
                'course_id': self.course.id,
            },
            HTTP_X_FORWARDED_FOR='10.3.3.3, 10.3.3.4',
        )
        self.assertEqual(export_grades_filtered.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(export_grades_filtered.content.decode('utf-8').strip().splitlines()), 2)

        self._auth(self.other_faculty_admin_user)
        faculty_scoped_enrollments_export = self.client.get(reverse('admin-export-enrollments'))
        self.assertEqual(faculty_scoped_enrollments_export.status_code, status.HTTP_200_OK)

        faculty_scoped_grades_export = self.client.get(reverse('admin-export-grades'))
        self.assertEqual(faculty_scoped_grades_export.status_code, status.HTTP_200_OK)

        self._auth(self.other_faculty_admin_user)

        enrollment_analytics_scoped = self.client.get(reverse('admin-analytics-enrollment'))
        self.assertEqual(enrollment_analytics_scoped.status_code, status.HTTP_200_OK)
        self.assertEqual(enrollment_analytics_scoped.data['data']['summary']['total'], 0)

        grades_analytics_scoped = self.client.get(reverse('admin-analytics-grades'))
        self.assertEqual(grades_analytics_scoped.status_code, status.HTTP_200_OK)
        self.assertEqual(grades_analytics_scoped.data['data']['summary']['total'], 0)

        attendance_analytics_scoped = self.client.get(reverse('admin-analytics-attendance'))
        self.assertEqual(attendance_analytics_scoped.status_code, status.HTTP_200_OK)
        self.assertEqual(attendance_analytics_scoped.data['data']['summary']['total_records'], 0)

        students_analytics_scoped = self.client.get(reverse('admin-analytics-students'))
        self.assertEqual(students_analytics_scoped.status_code, status.HTTP_200_OK)
        self.assertEqual(students_analytics_scoped.data['data']['summary']['total_students'], 0)

        professors_analytics_scoped = self.client.get(reverse('admin-analytics-professors'))
        self.assertEqual(professors_analytics_scoped.status_code, status.HTTP_200_OK)
        self.assertEqual(professors_analytics_scoped.data['data']['summary']['total_professors'], 0)

        webhook_analytics_empty = self.client.get(reverse('admin-analytics-webhooks'))
        self.assertEqual(webhook_analytics_empty.status_code, status.HTTP_200_OK)
        self.assertEqual(webhook_analytics_empty.data['data']['summary']['total_deliveries'], 0)

        self._auth(self.admin_user)
        session = AttendanceSession.objects.create(
            section=self.section,
            created_by=self.professor,
            session_date='2026-10-11',
            title='Coverage Session',
        )
        AttendanceRecord.objects.create(
            session=session,
            enrollment=self.active_enrollment,
            status=AttendanceRecord.Status.PRESENT,
        )

        attendance_analytics = self.client.get(reverse('admin-analytics-attendance'))
        self.assertEqual(attendance_analytics.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(attendance_analytics.data['data']['summary']['total_records'], 1)

        webhook = Webhook.objects.create(
            name='Metrics Hook',
            target_url='https://example.com/metrics',
            events=['grade.updated'],
            created_by=self.admin_user,
        )
        WebhookDelivery.objects.create(
            webhook=webhook,
            event_name='grade.updated',
            payload={'grade_id': 1},
            status=WebhookDelivery.DeliveryStatus.SUCCESS,
            attempt_count=1,
        )
        WebhookDelivery.objects.create(
            webhook=webhook,
            event_name='grade.updated',
            payload={'grade_id': 2},
            status=WebhookDelivery.DeliveryStatus.FAILED,
            attempt_count=3,
            error_message='timeout',
        )

        webhook_analytics = self.client.get(reverse('admin-analytics-webhooks'), {'webhook_id': webhook.id})
        self.assertEqual(webhook_analytics.status_code, status.HTTP_200_OK)
        self.assertEqual(webhook_analytics.data['data']['summary']['total_deliveries'], 2)
        self.assertEqual(len(webhook_analytics.data['data']['recent_failures']), 1)

        grades_analytics = self.client.get(reverse('admin-analytics-grades'))
        self.assertEqual(grades_analytics.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(grades_analytics.data['data']['summary']['total'], 1)

    def test_analytics_filter_query_paths_for_admin_and_department_scope(self):
        self._auth(self.admin_user)

        enrollment_filtered = self.client.get(
            reverse('admin-analytics-enrollment'),
            {
                'academic_term_id': self.term.id,
                'faculty_id': self.faculty.id,
                'department_id': self.department.id,
            },
        )
        self.assertEqual(enrollment_filtered.status_code, status.HTTP_200_OK)

        grades_filtered = self.client.get(
            reverse('admin-analytics-grades'),
            {
                'academic_term_id': self.term.id,
                'course_id': self.course.id,
                'faculty_id': self.faculty.id,
            },
        )
        self.assertEqual(grades_filtered.status_code, status.HTTP_200_OK)

        attendance_filtered = self.client.get(
            reverse('admin-analytics-attendance'),
            {
                'academic_term_id': self.term.id,
                'section_id': self.section.id,
                'faculty_id': self.faculty.id,
            },
        )
        self.assertEqual(attendance_filtered.status_code, status.HTTP_200_OK)

        self._auth(self.department_scoped_admin_user)

        dep_enrollment = self.client.get(reverse('admin-analytics-enrollment'))
        self.assertEqual(dep_enrollment.status_code, status.HTTP_200_OK)

        dep_grades = self.client.get(reverse('admin-analytics-grades'))
        self.assertEqual(dep_grades.status_code, status.HTTP_200_OK)

        dep_attendance = self.client.get(reverse('admin-analytics-attendance'))
        self.assertEqual(dep_attendance.status_code, status.HTTP_200_OK)

        dep_students = self.client.get(reverse('admin-analytics-students'))
        self.assertEqual(dep_students.status_code, status.HTTP_200_OK)

        dep_professors = self.client.get(reverse('admin-analytics-professors'))
        self.assertEqual(dep_professors.status_code, status.HTTP_200_OK)


class SharedAdminAndAuditCoverageTests(_BaseEnrollmentSetup, APITestCase):
    def setUp(self):
        super().setUp()
        self.faculty_admin_user = User.objects.create_user(
            username='fac_admin_shared_cov',
            email='fac_admin_shared_cov@example.com',
            password='Pass1234!@#',
        )
        self.department_admin_user = User.objects.create_user(
            username='dep_admin_shared_cov',
            email='dep_admin_shared_cov@example.com',
            password='Pass1234!@#',
        )
        UserRole.objects.create(
            user=self.faculty_admin_user,
            role=self.faculty_admin_role,
            scope='faculty',
            scope_id=self.faculty.id,
        )
        UserRole.objects.create(
            user=self.department_admin_user,
            role=self.department_admin_role,
            scope='department',
            scope_id=self.department.id,
        )

    def test_helper_functions_and_admin_user_edge_paths(self):
        self.assertIn('student', _user_role_slugs(self.student_user))
        self.assertEqual(_user_role_slugs(AnonymousUser()), set())

        self.assertTrue(_user_has_scoped_role(self.faculty_admin_user, 'faculty_admin', 'faculty', self.faculty.id))
        self.assertFalse(_user_has_scoped_role(self.faculty_admin_user, 'faculty_admin', 'faculty', self.other_faculty.id))

        scopes = _admin_get_user_scopes(self.faculty_admin_user)
        self.assertFalse(scopes['is_super'])
        self.assertIn(self.faculty.id, scopes['faculties'])

        department_scopes = _admin_get_user_scopes(self.department_admin_user)
        self.assertIn(self.department.id, department_scopes['departments'])

        self.assertTrue(_audit_is_super_admin(self.admin_user))
        self.assertFalse(_audit_is_super_admin(self.student_user))

        self._auth(self.admin_user)

        duplicate_username = self.client.post(
            reverse('admin-users'),
            {'username': self.student_user.username, 'email': 'newdup@example.com', 'password': 'Pass1234!@#'},
            format='json',
        )
        self.assertEqual(duplicate_username.status_code, status.HTTP_400_BAD_REQUEST)

        duplicate_email = self.client.post(
            reverse('admin-users'),
            {'username': 'newdupuser', 'email': self.student_user.email, 'password': 'Pass1234!@#'},
            format='json',
        )
        self.assertEqual(duplicate_email.status_code, status.HTTP_400_BAD_REQUEST)

        created_user = self.client.post(
            reverse('admin-users'),
            {
                'username': 'admin_cov_user',
                'email': 'admin_cov_user@example.com',
                'password': 'Pass1234!@#',
                'roles': [
                    {'role': 'faculty_admin', 'scope': 'faculty', 'scope_id': self.faculty.id},
                    123,
                ],
            },
            format='json',
        )
        self.assertEqual(created_user.status_code, status.HTTP_201_CREATED)
        managed_user_id = created_user.data['data']['id']

        filtered_list = self.client.get(
            reverse('admin-users'),
            {'role': 'faculty_admin', 'is_active': 'true', 'search': 'admin_cov_user', 'limit': 'bad'},
        )
        self.assertEqual(filtered_list.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(filtered_list.data['data']), 1)

        patch_user = self.client.patch(
            reverse('admin-user-detail', kwargs={'user_id': managed_user_id}),
            {
                'password': 'NewPass1234!@#',
                'is_staff': True,
                'profile': {'phone': '+2010000000', 'avatar_path': '/avatars/1.png'},
                'roles': [
                    'student',
                    {'role': 'department_admin', 'scope': 'department', 'scope_id': self.department.id},
                    None,
                ],
            },
            format='json',
        )
        self.assertEqual(patch_user.status_code, status.HTTP_200_OK)

        managed_detail = self.client.get(reverse('admin-user-detail', kwargs={'user_id': managed_user_id}))
        self.assertEqual(managed_detail.status_code, status.HTTP_200_OK)

        self.assertEqual(
            UserRole.objects.filter(user_id=managed_user_id, role__slug='department_admin', scope='department', scope_id=self.department.id).count(),
            1,
        )

        missing_detail = self.client.get(reverse('admin-user-detail', kwargs={'user_id': 999999}))
        self.assertEqual(missing_detail.status_code, status.HTTP_404_NOT_FOUND)

        missing_patch = self.client.patch(
            reverse('admin-user-detail', kwargs={'user_id': 999999}),
            {'first_name': 'x'},
            format='json',
        )
        self.assertEqual(missing_patch.status_code, status.HTTP_404_NOT_FOUND)

        missing_delete = self.client.delete(reverse('admin-user-detail', kwargs={'user_id': 999999}))
        self.assertEqual(missing_delete.status_code, status.HTTP_404_NOT_FOUND)

    def test_webhook_delivery_list_shared_endpoints_and_audit_filters(self):
        self._auth(self.admin_user)

        bad_headers = self.client.post(
            reverse('admin-webhooks'),
            {'name': 'Bad Headers Hook', 'target_url': 'https://example.com/bad', 'headers': 'x'},
            format='json',
        )
        self.assertEqual(bad_headers.status_code, status.HTTP_400_BAD_REQUEST)

        create_hook = self.client.post(
            reverse('admin-webhooks'),
            {
                'name': 'Deliveries Hook',
                'target_url': 'https://example.com/deliveries',
                'events': ['grade.updated'],
                'headers': {'x-source': 'tests'},
            },
            format='json',
        )
        self.assertEqual(create_hook.status_code, status.HTTP_201_CREATED)
        hook_id = create_hook.data['data']['id']
        hook = Webhook.objects.get(id=hook_id)

        WebhookDelivery.objects.create(
            webhook=hook,
            event_name='grade.updated',
            status=WebhookDelivery.DeliveryStatus.PENDING,
            attempt_count=1,
        )
        WebhookDelivery.objects.create(
            webhook=hook,
            event_name='grade.updated',
            status=WebhookDelivery.DeliveryStatus.FAILED,
            attempt_count=2,
            error_message='boom',
        )

        filtered_deliveries = self.client.get(
            reverse('admin-webhook-deliveries', kwargs={'webhook_id': hook_id}),
            {'status': WebhookDelivery.DeliveryStatus.FAILED, 'limit': '1'},
        )
        self.assertEqual(filtered_deliveries.status_code, status.HTTP_200_OK)
        self.assertEqual(len(filtered_deliveries.data['data']['deliveries']), 1)

        bad_patch_headers = self.client.patch(
            reverse('admin-webhook-detail', kwargs={'webhook_id': hook_id}),
            {'headers': 'wrong'},
            format='json',
        )
        self.assertEqual(bad_patch_headers.status_code, status.HTTP_400_BAD_REQUEST)

        super_user = User.objects.create_superuser(
            username='root_cov',
            email='root_cov@example.com',
            password='Pass1234!@#',
        )
        root_token = Token.objects.create(user=super_user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {root_token.key}')
        superuser_hook_list = self.client.get(reverse('admin-webhooks'))
        self.assertEqual(superuser_hook_list.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(superuser_hook_list.data['data']), 1)

        self._auth(self.prof_user)
        Notification.objects.create(recipient=self.prof_user, title='N1', body='Body', notification_type='general')
        notif = Notification.objects.create(recipient=self.prof_user, title='N2', body='Body', notification_type='general')

        shared_notifs = self.client.get(reverse('shared-notifications'), {'unread_only': 'yes', 'per_page': 'x', 'page': 'x'})
        self.assertEqual(shared_notifs.status_code, status.HTTP_200_OK)
        self.assertEqual(shared_notifs.data['meta']['current_page'], 1)

        read_missing = self.client.post(reverse('shared-notification-read', kwargs={'notification_id': 999999}))
        self.assertEqual(read_missing.status_code, status.HTTP_404_NOT_FOUND)

        read_first = self.client.post(reverse('shared-notification-read', kwargs={'notification_id': notif.id}))
        self.assertEqual(read_first.status_code, status.HTTP_200_OK)
        read_second = self.client.post(reverse('shared-notification-read', kwargs={'notification_id': notif.id}))
        self.assertEqual(read_second.status_code, status.HTTP_200_OK)

        read_all = self.client.post(reverse('shared-notifications-read-all'))
        self.assertEqual(read_all.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(read_all.data['data']['updated_count'], 0)

        delete_missing = self.client.delete(reverse('shared-notification-delete', kwargs={'notification_id': 999999}))
        self.assertEqual(delete_missing.status_code, status.HTTP_404_NOT_FOUND)

        deletable = Notification.objects.create(recipient=self.prof_user, title='N3', body='Body', notification_type='general')
        delete_existing = self.client.delete(reverse('shared-notification-delete', kwargs={'notification_id': deletable.id}))
        self.assertEqual(delete_existing.status_code, status.HTTP_200_OK)

        published = Announcement.objects.create(
            title='Prof Visible',
            body='Prof Body',
            type='general',
            visibility=Announcement.Visibility.DEPARTMENT,
            target_id=self.department.id,
            published_at=timezone.now(),
            author=self.admin_user,
        )
        future_announcement = Announcement.objects.create(
            title='Future Hidden',
            body='Hidden',
            type='general',
            visibility=Announcement.Visibility.UNIVERSITY,
            published_at=timezone.now() + timezone.timedelta(days=1),
            author=self.admin_user,
        )
        self.assertIsNotNone(future_announcement)

        ann_list = self.client.get(reverse('shared-announcements'), {'section_id': self.section.id, 'per_page': 'x', 'page': 'x'})
        self.assertEqual(ann_list.status_code, status.HTTP_200_OK)
        self.assertEqual(ann_list.data['meta']['current_page'], 1)

        ann_read_missing = self.client.post(reverse('shared-announcement-read', kwargs={'announcement_id': 999999}))
        self.assertEqual(ann_read_missing.status_code, status.HTTP_404_NOT_FOUND)

        ann_read_ok = self.client.post(reverse('shared-announcement-read', kwargs={'announcement_id': published.id}))
        self.assertEqual(ann_read_ok.status_code, status.HTTP_200_OK)
        self.assertTrue(GlobalAnnouncementRead.objects.filter(user=self.prof_user, announcement=published).exists())

        self._auth(self.admin_user)
        now = timezone.now()
        old_log = AuditLog.objects.create(
            user=self.admin_user,
            action=AuditLog.Action.OTHER,
            entity_type='batch',
            entity_id='old1',
            description='old log',
        )
        AuditLog.objects.filter(id=old_log.id).update(created_at=now - timezone.timedelta(days=2))

        new_log = AuditLog.objects.create(
            user=self.admin_user,
            action=AuditLog.Action.EXPORT,
            entity_type='batch',
            entity_id='new1',
            description='new log',
        )

        bad_audit_create = self.client.post(reverse('admin-audit-logs'), {'entity_type': 'x'}, format='json')
        self.assertEqual(bad_audit_create.status_code, status.HTTP_400_BAD_REQUEST)

        ok_audit_create = self.client.post(
            reverse('admin-audit-logs'),
            {
                'entity_type': 'batch',
                'description': 'forwarded ip check',
                'action': AuditLog.Action.OTHER,
            },
            format='json',
            HTTP_X_FORWARDED_FOR='192.168.10.5, 172.16.1.10',
        )
        self.assertEqual(ok_audit_create.status_code, status.HTTP_201_CREATED)
        created_log = AuditLog.objects.get(id=ok_audit_create.data['data']['id'])
        self.assertEqual(created_log.ip_address, '192.168.10.5')

        list_filtered = self.client.get(
            reverse('admin-audit-logs'),
            {
                'user_id': self.admin_user.id,
                'action': AuditLog.Action.EXPORT,
                'entity_type': 'batch',
                'entity_id': 'new1',
                'date_from': (now - timezone.timedelta(days=1)).isoformat(),
                'date_to': (now + timezone.timedelta(days=1)).isoformat(),
                'limit': 'bad',
            },
        )
        self.assertEqual(list_filtered.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(list_filtered.data['data']), 1)

        detail_missing = self.client.get(reverse('admin-audit-log-detail', kwargs={'log_id': 999999}))
        self.assertEqual(detail_missing.status_code, status.HTTP_404_NOT_FOUND)

        detail_existing = self.client.get(reverse('admin-audit-log-detail', kwargs={'log_id': new_log.id}))
        self.assertEqual(detail_existing.status_code, status.HTTP_200_OK)
