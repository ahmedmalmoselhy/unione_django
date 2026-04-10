from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from datetime import timedelta

from django.utils import timezone

from academics.models import Announcement, AcademicTerm, AttendanceRecord, AttendanceSession, Course, EnrollmentWaitlist, GlobalAnnouncementRead, Grade, Notification, Section, SectionAnnouncement
from accounts.models import Role, UserRole
from enrollment.models import CourseEnrollment, ProfessorProfile, StudentProfile
from organization.models import Department, Faculty, University


class StudentReadAPITests(APITestCase):
	def setUp(self):
		self.university = University.objects.create(
			name='Uni One',
			code='U1',
			country='EG',
			city='Cairo',
			established_year=1990,
		)
		self.faculty = Faculty.objects.create(university=self.university, name='Engineering', code='ENG')
		self.department = Department.objects.create(faculty=self.faculty, name='Computer Science', code='CS')
		self.student_user = User.objects.create_user(username='student1', email='student1@example.com', password='Pass1234!@#')
		self.prof_user = User.objects.create_user(username='prof1', email='prof1@example.com', password='Pass1234!@#')
		self.student_role = Role.objects.create(name='Student', slug='student', permissions={})
		UserRole.objects.create(user=self.student_user, role=self.student_role)
		self.student_profile = StudentProfile.objects.create(
			user=self.student_user,
			student_number='S1001',
			faculty=self.faculty,
			department=self.department,
			academic_year=2,
			semester=1,
			enrolled_at='2024-09-01',
		)
		self.professor_profile = ProfessorProfile.objects.create(
			user=self.prof_user,
			staff_number='P1001',
			department=self.department,
			hired_at='2020-01-01',
		)
		self.term = AcademicTerm.objects.create(
			name='Fall 2025',
			start_date='2025-09-01',
			end_date='2026-01-15',
			registration_start='2025-08-01',
			registration_end='2025-08-25',
			is_active=True,
		)
		self.term_2 = AcademicTerm.objects.create(
			name='Spring 2026',
			start_date='2026-02-01',
			end_date='2026-06-15',
			registration_start='2026-01-01',
			registration_end='2026-01-25',
			is_active=False,
		)
		self.course = Course.objects.create(code='CS101', name='Intro to CS', credit_hours=3, lecture_hours=3, lab_hours=0, level=100)
		self.course_2 = Course.objects.create(code='CS201', name='Data Structures', credit_hours=3, lecture_hours=3, lab_hours=0, level=200)
		self.section = Section.objects.create(course=self.course, professor=self.professor_profile, academic_term=self.term, semester=1, capacity=30, schedule={'days': [1, 3], 'start_time': '09:00', 'end_time': '10:30'})
		self.section_2 = Section.objects.create(course=self.course_2, professor=self.professor_profile, academic_term=self.term_2, semester=2, capacity=25, schedule={'days': [2, 4], 'start_time': '11:00', 'end_time': '12:30'})
		self.enrollment = CourseEnrollment.objects.create(student=self.student_profile, section=self.section, academic_term=self.term, status='active')
		self.grade = Grade.objects.create(enrollment=self.enrollment, points=92, letter_grade='A', status='complete')
		token = Token.objects.create(user=self.student_user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def test_student_profile_returns_core_data(self):
		response = self.client.get(reverse('student-profile'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['data']['student_number'], 'S1001')
		self.assertEqual(response.data['data']['faculty'], 'Engineering')

	def test_student_enrollments_returns_nested_section(self):
		response = self.client.get(reverse('student-enrollments'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['data']), 1)
		self.assertEqual(response.data['data'][0]['section']['course']['code'], 'CS101')

	def test_student_grades_returns_grade_data(self):
		response = self.client.get(reverse('student-grades'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['data']), 1)
		self.assertEqual(response.data['data'][0]['letter_grade'], 'A')

	def test_student_grades_filter_by_term(self):
		response = self.client.get(reverse('student-grades'), {'academic_term_id': self.term.id})
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['data']), 1)

	def test_student_academic_terms_returns_terms(self):
		response = self.client.get(reverse('student-academic-terms'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['data']), 2)
		self.assertEqual(response.data['data'][0]['name'], 'Spring 2026')

	def test_student_sections_returns_sections(self):
		response = self.client.get(reverse('student-sections'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['data']), 2)
		self.assertEqual(response.data['data'][0]['course']['code'], 'CS101')

	def test_student_sections_filter_by_term(self):
		response = self.client.get(reverse('student-sections'), {'academic_term_id': self.term_2.id})
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['data']), 1)
		self.assertEqual(response.data['data'][0]['course']['code'], 'CS201')

	def test_student_enrollment_post_creates_enrollment(self):
		response = self.client.post(
			reverse('student-enrollments'),
			{'section_id': self.section_2.id},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		enrollment = CourseEnrollment.objects.filter(student=self.student_profile, section=self.section_2).first()
		self.assertIsNotNone(enrollment)
		self.assertEqual(enrollment.status, CourseEnrollment.EnrollmentStatus.ACTIVE)

	def test_student_enrollment_post_full_section_adds_waitlist(self):
		occupied_user = User.objects.create_user(username='seat_owner', email='seat_owner@example.com', password='Pass1234!@#')
		UserRole.objects.create(user=occupied_user, role=self.student_role)
		occupied_profile = StudentProfile.objects.create(
			user=occupied_user,
			student_number='S1002',
			faculty=self.faculty,
			department=self.department,
			academic_year=2,
			semester=1,
			enrolled_at='2024-09-01',
		)
		full_section = Section.objects.create(
			course=self.course_2,
			professor=self.professor_profile,
			academic_term=self.term_2,
			semester=2,
			capacity=1,
			schedule={'days': [1], 'start_time': '08:00', 'end_time': '09:00'},
		)
		CourseEnrollment.objects.create(
			student=occupied_profile,
			section=full_section,
			academic_term=self.term_2,
			status=CourseEnrollment.EnrollmentStatus.ACTIVE,
		)

		response = self.client.post(
			reverse('student-enrollments'),
			{'section_id': full_section.id},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
		waitlist = EnrollmentWaitlist.objects.filter(student=self.student_profile, section=full_section).first()
		self.assertIsNotNone(waitlist)
		self.assertEqual(waitlist.status, EnrollmentWaitlist.WaitlistStatus.ACTIVE)
		self.assertEqual(waitlist.position, 1)

	def test_student_enrollment_delete_promotes_waitlisted_student(self):
		section = Section.objects.create(
			course=self.course_2,
			professor=self.professor_profile,
			academic_term=self.term_2,
			semester=2,
			capacity=1,
			schedule={'days': [2], 'start_time': '13:00', 'end_time': '14:00'},
		)
		active_enrollment = CourseEnrollment.objects.create(
			student=self.student_profile,
			section=section,
			academic_term=self.term_2,
			status=CourseEnrollment.EnrollmentStatus.ACTIVE,
		)

		waitlisted_user = User.objects.create_user(username='waitlisted', email='waitlisted@example.com', password='Pass1234!@#')
		UserRole.objects.create(user=waitlisted_user, role=self.student_role)
		waitlisted_profile = StudentProfile.objects.create(
			user=waitlisted_user,
			student_number='S1003',
			faculty=self.faculty,
			department=self.department,
			academic_year=2,
			semester=1,
			enrolled_at='2024-09-01',
		)
		waitlisted_token = Token.objects.create(user=waitlisted_user)

		self.client.credentials(HTTP_AUTHORIZATION=f'Token {waitlisted_token.key}')
		self.client.post(reverse('student-enrollments'), {'section_id': section.id}, format='json')

		self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.get(user=self.student_user).key}')
		response = self.client.delete(reverse('student-enrollment-delete', kwargs={'enrollment_id': active_enrollment.id}))

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		active_enrollment.refresh_from_db()
		self.assertEqual(active_enrollment.status, CourseEnrollment.EnrollmentStatus.DROPPED)

		promoted = CourseEnrollment.objects.filter(student=waitlisted_profile, section=section).first()
		self.assertIsNotNone(promoted)
		self.assertEqual(promoted.status, CourseEnrollment.EnrollmentStatus.ACTIVE)

		waitlist_entry = EnrollmentWaitlist.objects.get(student=waitlisted_profile, section=section)
		self.assertEqual(waitlist_entry.status, EnrollmentWaitlist.WaitlistStatus.ENROLLED)


class SectionAnnouncementsParityTests(APITestCase):
	def setUp(self):
		self.university = University.objects.create(
			name='Uni One',
			code='U1P',
			country='EG',
			city='Cairo',
			established_year=1990,
		)
		self.faculty = Faculty.objects.create(university=self.university, name='Engineering', code='ENGP')
		self.department = Department.objects.create(faculty=self.faculty, name='Computer Science', code='CSP')

		self.student_user = User.objects.create_user(username='student_parity', email='student_parity@example.com', password='Pass1234!@#')
		self.prof_user = User.objects.create_user(username='prof_parity', email='prof_parity@example.com', password='Pass1234!@#')

		student_role = Role.objects.create(name='Student', slug='student', permissions={})
		prof_role = Role.objects.create(name='Professor', slug='professor', permissions={})
		UserRole.objects.create(user=self.student_user, role=student_role)
		UserRole.objects.create(user=self.prof_user, role=prof_role)

		self.student_profile = StudentProfile.objects.create(
			user=self.student_user,
			student_number='SP1001',
			faculty=self.faculty,
			department=self.department,
			academic_year=2,
			semester=1,
			enrolled_at='2024-09-01',
		)
		self.professor_profile = ProfessorProfile.objects.create(
			user=self.prof_user,
			staff_number='PP1001',
			department=self.department,
			hired_at='2020-01-01',
		)

		self.term = AcademicTerm.objects.create(
			name='Fall 2025',
			start_date='2025-09-01',
			end_date='2026-01-15',
			registration_start='2025-08-01',
			registration_end='2025-08-25',
			is_active=True,
		)
		self.course = Course.objects.create(code='CS301P', name='Software Engineering', credit_hours=3, lecture_hours=3, lab_hours=0, level=300)
		self.section = Section.objects.create(
			course=self.course,
			professor=self.professor_profile,
			academic_term=self.term,
			semester=1,
			capacity=30,
			schedule={'days': [1, 3], 'start_time': '09:00', 'end_time': '10:30'},
		)
		self.enrollment = CourseEnrollment.objects.create(
			student=self.student_profile,
			section=self.section,
			academic_term=self.term,
			status=CourseEnrollment.EnrollmentStatus.ACTIVE,
		)

	def test_student_section_announcements_requires_enrollment(self):
		non_student_user = User.objects.create_user(username='outsider', email='outsider@example.com', password='Pass1234!@#')
		student_role = Role.objects.get(slug='student')
		UserRole.objects.create(user=non_student_user, role=student_role)
		non_student_profile = StudentProfile.objects.create(
			user=non_student_user,
			student_number='SP2001',
			faculty=self.faculty,
			department=self.department,
			academic_year=2,
			semester=1,
			enrolled_at='2024-09-01',
		)
		self.assertIsNotNone(non_student_profile)

		token = Token.objects.create(user=non_student_user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

		response = self.client.get(reverse('student-section-announcements', kwargs={'section_id': self.section.id}))
		self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

	def test_student_section_announcements_returns_section_data(self):
		SectionAnnouncement.objects.create(
			section=self.section,
			created_by=self.professor_profile,
			title='Midterm date',
			body='Midterm is next week',
		)

		token = Token.objects.create(user=self.student_user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

		response = self.client.get(reverse('student-section-announcements', kwargs={'section_id': self.section.id}))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['data']), 1)
		self.assertEqual(response.data['data'][0]['title'], 'Midterm date')

	def test_professor_announcement_creates_student_notifications(self):
		prof_token = Token.objects.create(user=self.prof_user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {prof_token.key}')

		response = self.client.post(
			reverse('professor-section-announcements', kwargs={'section_id': self.section.id}),
			{'title': 'Lab update', 'body': 'Lab moved to Thursday'},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_201_CREATED)

		notification = Notification.objects.filter(recipient=self.student_user, notification_type='section_announcement').first()
		self.assertIsNotNone(notification)
		self.assertIn('Lab update', notification.title)


class SharedEndpointsParityTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='shared_user', email='shared_user@example.com', password='Pass1234!@#')
		role = Role.objects.create(name='Admin Shared', slug='admin', permissions={})
		UserRole.objects.create(user=self.user, role=role)
		token = Token.objects.create(user=self.user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

		for idx in range(1, 4):
			Notification.objects.create(
				recipient=self.user,
				title=f'N{idx}',
				body='Body',
				notification_type='general',
			)

	def _build_student_context(self):
		university = University.objects.create(name='Uni Shared', code='US', country='EG', city='Cairo', established_year=1990)
		faculty = Faculty.objects.create(university=university, name='Engineering', code='ENGS')
		department = Department.objects.create(faculty=faculty, name='Computer Science', code='CSS')
		prof_user = User.objects.create_user(username='prof_shared', email='prof_shared@example.com', password='Pass1234!@#')
		prof_role = Role.objects.create(name='Professor Shared', slug='professor', permissions={})
		UserRole.objects.create(user=prof_user, role=prof_role)
		prof_profile = ProfessorProfile.objects.create(user=prof_user, staff_number='PSH-01', department=department, hired_at='2020-01-01')
		term = AcademicTerm.objects.create(
			name='Spring Shared',
			start_date='2026-02-01',
			end_date='2026-06-30',
			registration_start='2026-01-01',
			registration_end='2026-01-20',
			is_active=True,
		)
		course = Course.objects.create(code='SHR101', name='Shared Course', credit_hours=3, lecture_hours=3, lab_hours=0, level=100)
		section = Section.objects.create(course=course, professor=prof_profile, academic_term=term, semester=1, capacity=20, schedule={})

		student_role = Role.objects.get(slug='admin')
		student_profile = StudentProfile.objects.create(
			user=self.user,
			student_number='SH1001',
			faculty=faculty,
			department=department,
			academic_year=1,
			semester=1,
			enrolled_at='2025-09-01',
		)
		self.assertIsNotNone(student_role)
		CourseEnrollment.objects.create(student=student_profile, section=section, academic_term=term, status=CourseEnrollment.EnrollmentStatus.ACTIVE)

		return faculty, department, section

	def test_notifications_support_unread_alias_and_meta(self):
		response = self.client.get(reverse('shared-notifications'), {'unread': '1', 'per_page': 2, 'page': 1})
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn('meta', response.data)
		self.assertEqual(response.data['meta']['current_page'], 1)
		self.assertEqual(response.data['meta']['per_page'], 2)
		self.assertEqual(response.data['meta']['total'], 3)
		self.assertEqual(response.data['meta']['unread_count'], 3)
		self.assertEqual(len(response.data['data']), 2)

	def test_announcements_include_meta_payload(self):
		response = self.client.get(reverse('shared-announcements'), {'per_page': 5, 'page': 1})
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn('meta', response.data)
		self.assertEqual(response.data['meta']['current_page'], 1)
		self.assertEqual(response.data['meta']['per_page'], 5)

	def test_announcements_visibility_rules_and_read_tracking(self):
		faculty, department, section = self._build_student_context()
		now = timezone.now()

		univ_announcement = Announcement.objects.create(
			title='Uni Notice',
			body='For everyone',
			type='general',
			visibility=Announcement.Visibility.UNIVERSITY,
			published_at=now,
		)
		Announcement.objects.create(
			title='Faculty Notice',
			body='For faculty',
			type='general',
			visibility=Announcement.Visibility.FACULTY,
			target_id=faculty.id,
			published_at=now,
		)
		Announcement.objects.create(
			title='Department Notice',
			body='For department',
			type='general',
			visibility=Announcement.Visibility.DEPARTMENT,
			target_id=department.id,
			published_at=now,
		)
		Announcement.objects.create(
			title='Section Notice',
			body='For section',
			type='general',
			visibility=Announcement.Visibility.SECTION,
			target_id=section.id,
			published_at=now,
		)
		Announcement.objects.create(
			title='Expired Notice',
			body='Expired',
			visibility=Announcement.Visibility.UNIVERSITY,
			published_at=now,
			expires_at=now - timedelta(minutes=1),
		)

		list_response = self.client.get(reverse('shared-announcements'))
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		titles = [item['title'] for item in list_response.data['data']]
		self.assertIn('Uni Notice', titles)
		self.assertIn('Faculty Notice', titles)
		self.assertIn('Department Notice', titles)
		self.assertIn('Section Notice', titles)
		self.assertNotIn('Expired Notice', titles)

		read_response = self.client.post(reverse('shared-announcement-read', kwargs={'announcement_id': univ_announcement.id}))
		self.assertEqual(read_response.status_code, status.HTTP_200_OK)
		self.assertTrue(GlobalAnnouncementRead.objects.filter(user=self.user, announcement=univ_announcement).exists())


class AdminManagementAPITests(APITestCase):
	def setUp(self):
		self.university = University.objects.create(
			name='Uni Admin',
			code='UA1',
			country='EG',
			city='Cairo',
			established_year=1990,
		)
		self.faculty = Faculty.objects.create(university=self.university, name='Engineering', code='ENGA')
		self.department = Department.objects.create(faculty=self.faculty, name='Computer Science', code='CSA')

		self.admin_role = Role.objects.create(name='Admin', slug='admin', permissions={})
		self.student_role = Role.objects.create(name='Student', slug='student', permissions={})
		self.prof_role = Role.objects.create(name='Professor', slug='professor', permissions={})

		self.admin_user = User.objects.create_user(username='admin_mgmt', email='admin_mgmt@example.com', password='Pass1234!@#')
		UserRole.objects.create(user=self.admin_user, role=self.admin_role)

		self.prof_user = User.objects.create_user(username='prof_mgmt', email='prof_mgmt@example.com', password='Pass1234!@#')
		UserRole.objects.create(user=self.prof_user, role=self.prof_role)
		self.professor = ProfessorProfile.objects.create(
			user=self.prof_user,
			staff_number='P-MGMT-1',
			department=self.department,
			hired_at='2020-01-01',
		)

		self.student_user = User.objects.create_user(username='student_mgmt', email='student_mgmt@example.com', password='Pass1234!@#')
		UserRole.objects.create(user=self.student_user, role=self.student_role)
		self.student_profile = StudentProfile.objects.create(
			user=self.student_user,
			student_number='S-MGMT-1',
			faculty=self.faculty,
			department=self.department,
			academic_year=2,
			semester=1,
			enrolled_at='2024-09-01',
		)

		self.term = AcademicTerm.objects.create(
			name='Fall 2026',
			start_date='2026-09-01',
			end_date='2027-01-15',
			registration_start='2026-08-01',
			registration_end='2026-08-25',
			is_active=True,
		)
		self.course = Course.objects.create(code='CSMG101', name='Admin Testing', credit_hours=3, lecture_hours=3, lab_hours=0, level=100)
		self.section = Section.objects.create(
			course=self.course,
			professor=self.professor,
			academic_term=self.term,
			semester=1,
			capacity=30,
			schedule={'days': [1, 3], 'start_time': '09:00', 'end_time': '10:30'},
		)
		self.enrollment = CourseEnrollment.objects.create(
			student=self.student_profile,
			section=self.section,
			academic_term=self.term,
			status=CourseEnrollment.EnrollmentStatus.ACTIVE,
		)
		self.grade = Grade.objects.create(enrollment=self.enrollment, points=90, letter_grade='A', status='complete')

		self.attendance_session = AttendanceSession.objects.create(
			section=self.section,
			created_by=self.professor,
			session_date='2026-10-01',
			title='Week 1',
		)
		AttendanceRecord.objects.create(
			session=self.attendance_session,
			enrollment=self.enrollment,
			status=AttendanceRecord.Status.PRESENT,
		)

		token = Token.objects.create(user=self.admin_user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def test_admin_users_crud_flow(self):
		create_response = self.client.post(
			reverse('admin-users'),
			{
				'username': 'managed_user',
				'email': 'managed_user@example.com',
				'password': 'Pass1234!@#',
				'roles': ['student'],
			},
			format='json',
		)
		self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
		user_id = create_response.data['data']['id']

		list_response = self.client.get(reverse('admin-users'))
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertGreaterEqual(len(list_response.data['data']), 1)

		patch_response = self.client.patch(
			reverse('admin-user-detail', kwargs={'user_id': user_id}),
			{'first_name': 'Managed'},
			format='json',
		)
		self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
		self.assertEqual(patch_response.data['data']['first_name'], 'Managed')

		delete_response = self.client.delete(reverse('admin-user-detail', kwargs={'user_id': user_id}))
		self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
		self.assertFalse(User.objects.get(id=user_id).is_active)

	def test_admin_organization_write_endpoints(self):
		faculty_response = self.client.post(
			reverse('admin-faculties'),
			{'name': 'Business', 'code': 'BUS', 'university_id': self.university.id},
			format='json',
		)
		self.assertEqual(faculty_response.status_code, status.HTTP_201_CREATED)
		new_faculty_id = faculty_response.data['data']['id']

		department_response = self.client.post(
			reverse('admin-departments'),
			{'name': 'Finance', 'code': 'FIN', 'faculty_id': new_faculty_id},
			format='json',
		)
		self.assertEqual(department_response.status_code, status.HTTP_201_CREATED)

		course_response = self.client.post(
			reverse('admin-courses'),
			{'code': 'BUS101', 'name': 'Intro Business', 'credit_hours': 3},
			format='json',
		)
		self.assertEqual(course_response.status_code, status.HTTP_201_CREATED)

		term_response = self.client.post(
			reverse('admin-academic-terms'),
			{
				'name': 'Spring 2027',
				'start_date': '2027-02-01',
				'end_date': '2027-06-15',
				'registration_start': '2027-01-01',
				'registration_end': '2027-01-20',
				'is_active': False,
			},
			format='json',
		)
		self.assertEqual(term_response.status_code, status.HTTP_201_CREATED)

		section_response = self.client.post(
			reverse('admin-sections'),
			{
				'course_id': self.course.id,
				'professor_id': self.professor.id,
				'academic_term_id': self.term.id,
				'semester': 1,
				'capacity': 40,
			},
			format='json',
		)
		self.assertEqual(section_response.status_code, status.HTTP_201_CREATED)

	def test_admin_analytics_endpoints_return_expected_shape(self):
		enrollment_response = self.client.get(reverse('admin-analytics-enrollment'))
		self.assertEqual(enrollment_response.status_code, status.HTTP_200_OK)
		self.assertIn('summary', enrollment_response.data['data'])
		self.assertGreaterEqual(enrollment_response.data['data']['summary']['total'], 1)

		grades_response = self.client.get(reverse('admin-analytics-grades'))
		self.assertEqual(grades_response.status_code, status.HTTP_200_OK)
		self.assertIn('summary', grades_response.data['data'])
		self.assertGreaterEqual(grades_response.data['data']['summary']['total'], 1)

		attendance_response = self.client.get(reverse('admin-analytics-attendance'))
		self.assertEqual(attendance_response.status_code, status.HTTP_200_OK)
		self.assertIn('summary', attendance_response.data['data'])
		self.assertGreaterEqual(attendance_response.data['data']['summary']['total_records'], 1)

	def test_admin_audit_log_create_list_and_detail(self):
		create_response = self.client.post(
			reverse('admin-audit-logs'),
			{
				'entity_type': 'manual_check',
				'description': 'manual audit event',
				'action': 'other',
			},
			format='json',
		)
		self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
		log_id = create_response.data['data']['id']

		list_response = self.client.get(reverse('admin-audit-logs'))
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertGreaterEqual(len(list_response.data['data']), 1)

		detail_response = self.client.get(reverse('admin-audit-log-detail', kwargs={'log_id': log_id}))
		self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
		self.assertEqual(detail_response.data['data']['id'], log_id)
