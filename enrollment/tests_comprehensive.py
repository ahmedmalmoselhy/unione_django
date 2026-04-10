from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from academics.models import (
    AcademicTerm,
    AttendanceRecord,
    AttendanceSession,
    Course,
    CourseRating,
    EnrollmentWaitlist,
    Grade,
    Notification,
    Section,
    SectionAnnouncement,
)
from accounts.models import Role, UserRole
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
