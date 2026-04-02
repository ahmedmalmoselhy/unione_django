from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserRole
from organization.models import Department, Faculty, University


class OrganizationEndpointsTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(username='facadmin', email='facadmin@example.com', password='Pass1234!@#')
		self.role = Role.objects.create(name='Faculty Admin', slug='faculty_admin', permissions={})

		self.university_1 = University.objects.create(
			name='Uni One',
			code='U1',
			country='EG',
			city='Cairo',
			established_year=1990,
		)
		self.university_2 = University.objects.create(
			name='Uni Two',
			code='U2',
			country='EG',
			city='Giza',
			established_year=1995,
		)
		self.faculty_1 = Faculty.objects.create(university=self.university_1, name='Engineering', code='ENG')
		self.faculty_2 = Faculty.objects.create(university=self.university_2, name='Medicine', code='MED')
		Department.objects.create(faculty=self.faculty_1, name='Computer Science', code='CS')
		Department.objects.create(faculty=self.faculty_2, name='Surgery', code='SUR')

		UserRole.objects.create(user=self.user, role=self.role, scope='faculty', scope_id=self.faculty_1.id)
		token = Token.objects.create(user=self.user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def test_university_endpoint_requires_auth(self):
		self.client.credentials()
		response = self.client.get(reverse('organization-university'))
		self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

	def test_faculty_scope_filters_faculties(self):
		response = self.client.get(reverse('organization-faculties'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['data']), 1)
		self.assertEqual(response.data['data'][0]['code'], 'ENG')

	def test_faculty_scope_filters_universities(self):
		response = self.client.get(reverse('organization-university'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['data']), 1)
		self.assertEqual(response.data['data'][0]['code'], 'U1')

	def test_faculty_scope_filters_departments(self):
		response = self.client.get(reverse('organization-departments'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data['data']), 1)
		self.assertEqual(response.data['data'][0]['code'], 'CS')
