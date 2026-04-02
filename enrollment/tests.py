from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from academics.models import AcademicTerm, Course, Grade, Section
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
