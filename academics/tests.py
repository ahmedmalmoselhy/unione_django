import io
import os
import tempfile
from urllib.error import HTTPError
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from accounts.models import Role, UserRole
from academics.models import AcademicTerm, AuditLog, Course, Grade, Section, Webhook, WebhookDelivery
from academics.webhook_delivery import enqueue_webhook_deliveries, process_single_delivery
from enrollment.models import CourseEnrollment, ProfessorProfile, StudentProfile
from organization.models import Department, Faculty, University


class _MockHTTPResponse:
	def __init__(self, status=200, body='ok'):
		self.status = status
		self._body = body.encode('utf-8')

	def read(self):
		return self._body

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc, tb):
		return False


class WebhookDeliveryTests(TestCase):
	def setUp(self):
		self.webhook_enrollment = Webhook.objects.create(
			name='Enrollment Hook',
			target_url='https://example.test/enrollment',
			events=['enrollment.created'],
			is_active=True,
		)
		self.webhook_all_events = Webhook.objects.create(
			name='All Events Hook',
			target_url='https://example.test/all',
			events=[],
			is_active=True,
		)
		self.webhook_inactive = Webhook.objects.create(
			name='Inactive Hook',
			target_url='https://example.test/inactive',
			events=['enrollment.created'],
			is_active=False,
		)

	def test_enqueue_webhook_deliveries_filters_active_and_event_match(self):
		created = enqueue_webhook_deliveries('enrollment.created', payload={'id': 10})
		self.assertEqual(created, 2)

		deliveries = WebhookDelivery.objects.order_by('id')
		self.assertEqual(deliveries.count(), 2)
		self.assertEqual(deliveries[0].webhook_id, self.webhook_enrollment.id)
		self.assertEqual(deliveries[1].webhook_id, self.webhook_all_events.id)
		self.assertEqual(deliveries[0].status, WebhookDelivery.DeliveryStatus.PENDING)

	@patch('academics.webhook_delivery.request.urlopen')
	def test_process_single_delivery_marks_success(self, mocked_urlopen):
		delivery = WebhookDelivery.objects.create(
			webhook=self.webhook_enrollment,
			event_name='enrollment.created',
			payload={'id': 11},
			status=WebhookDelivery.DeliveryStatus.PENDING,
		)
		mocked_urlopen.return_value = _MockHTTPResponse(status=200, body='accepted')

		result = process_single_delivery(delivery.id, max_attempts=3, base_retry_seconds=1)
		self.assertEqual(result['status'], 'success')

		delivery.refresh_from_db()
		self.webhook_enrollment.refresh_from_db()
		self.assertEqual(delivery.status, WebhookDelivery.DeliveryStatus.SUCCESS)
		self.assertEqual(delivery.attempt_count, 1)
		self.assertEqual(delivery.response_status_code, 200)
		self.assertEqual(delivery.response_body, 'accepted')
		self.assertIsNotNone(delivery.delivered_at)
		self.assertIsNotNone(self.webhook_enrollment.last_triggered_at)

	@patch('academics.webhook_delivery.request.urlopen')
	def test_process_single_delivery_retries_then_fails(self, mocked_urlopen):
		delivery = WebhookDelivery.objects.create(
			webhook=self.webhook_enrollment,
			event_name='enrollment.created',
			payload={'id': 12},
			status=WebhookDelivery.DeliveryStatus.PENDING,
		)

		http_error = HTTPError(
			url='https://example.test/enrollment',
			code=503,
			msg='Service Unavailable',
			hdrs=None,
			fp=io.BytesIO(b'temporary outage'),
		)
		mocked_urlopen.side_effect = [http_error, http_error]

		first = process_single_delivery(delivery.id, max_attempts=2, base_retry_seconds=1)
		self.assertEqual(first['status'], WebhookDelivery.DeliveryStatus.RETRY)
		delivery.refresh_from_db()
		self.assertEqual(delivery.attempt_count, 1)
		self.assertIsNotNone(delivery.next_retry_at)
		self.assertEqual(delivery.response_status_code, 503)

		delivery.next_retry_at = timezone.now()
		delivery.save(update_fields=['next_retry_at', 'updated_at'])

		second = process_single_delivery(delivery.id, max_attempts=2, base_retry_seconds=1)
		self.assertEqual(second['status'], WebhookDelivery.DeliveryStatus.FAILED)
		delivery.refresh_from_db()
		self.assertEqual(delivery.attempt_count, 2)
		self.assertEqual(delivery.status, WebhookDelivery.DeliveryStatus.FAILED)
		self.assertIsNone(delivery.next_retry_at)


class AdminWebhookAccessParityTests(APITestCase):
	def setUp(self):
		self.faculty_admin_role = Role.objects.create(name='Faculty Admin', slug='faculty_admin', permissions={})
		self.department_admin_role = Role.objects.create(name='Department Admin', slug='department_admin', permissions={})

		self.owner_user = User.objects.create_user(username='owner_admin', email='owner_admin@example.com', password='Pass1234!@#')
		self.other_user = User.objects.create_user(username='other_admin', email='other_admin@example.com', password='Pass1234!@#')

		UserRole.objects.create(user=self.owner_user, role=self.faculty_admin_role)
		UserRole.objects.create(user=self.other_user, role=self.department_admin_role)

		self.owner_token = Token.objects.create(user=self.owner_user)
		self.other_token = Token.objects.create(user=self.other_user)

	def test_faculty_admin_can_list_and_create_webhooks(self):
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.owner_token.key}')

		create_response = self.client.post(
			reverse('admin-webhooks'),
			{'name': 'Owner Hook', 'target_url': 'https://example.test/hook', 'events': ['enrollment.created']},
			format='json',
		)
		self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

		list_response = self.client.get(reverse('admin-webhooks'))
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data['data']), 1)

	def test_admin_webhook_access_is_owner_scoped(self):
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.owner_token.key}')
		create_response = self.client.post(
			reverse('admin-webhooks'),
			{'name': 'Private Hook', 'target_url': 'https://example.test/private', 'events': ['announcement.created']},
			format='json',
		)
		webhook_id = create_response.data['data']['id']

		self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.other_token.key}')
		patch_response = self.client.patch(
			reverse('admin-webhook-detail', kwargs={'webhook_id': webhook_id}),
			{'name': 'Hijacked'},
			format='json',
		)
		self.assertEqual(patch_response.status_code, status.HTTP_404_NOT_FOUND)

		delete_response = self.client.delete(reverse('admin-webhook-detail', kwargs={'webhook_id': webhook_id}))
		self.assertEqual(delete_response.status_code, status.HTTP_404_NOT_FOUND)


class WebhookCleanupCommandTests(TestCase):
	def test_cleanup_archives_and_deletes_old_records(self):
		webhook = Webhook.objects.create(
			name='Cleanup Hook',
			target_url='https://example.test/cleanup',
			events=['enrollment.created'],
		)
		old_delivery = WebhookDelivery.objects.create(
			webhook=webhook,
			event_name='enrollment.created',
			payload={'id': 1},
			status=WebhookDelivery.DeliveryStatus.SUCCESS,
		)
		WebhookDelivery.objects.filter(id=old_delivery.id).update(
			created_at=timezone.now() - timezone.timedelta(days=45),
		)

		with tempfile.TemporaryDirectory() as temp_dir:
			call_command(
				'cleanup_webhook_deliveries',
				archive_days=30,
				purge_days=90,
				output_dir=temp_dir,
			)

			self.assertFalse(WebhookDelivery.objects.filter(id=old_delivery.id).exists())
			archive_files = [name for name in os.listdir(temp_dir) if name.endswith('.jsonl')]
			self.assertEqual(len(archive_files), 1)


class AdminImportExportTests(APITestCase):
	def setUp(self):
		self.university = University.objects.create(name='Uni Admin', code='UA', country='EG', city='Cairo', established_year=1990)
		self.faculty = Faculty.objects.create(university=self.university, name='Engineering', code='ENGA')
		self.department = Department.objects.create(faculty=self.faculty, name='Computer Science', code='CSA')

		self.admin_role = Role.objects.create(name='Admin', slug='admin', permissions={})
		self.student_role = Role.objects.create(name='Student', slug='student', permissions={})
		self.prof_role = Role.objects.create(name='Professor', slug='professor', permissions={})

		self.admin_user = User.objects.create_user(username='admin_ie', email='admin_ie@example.com', password='Pass1234!@#')
		UserRole.objects.create(user=self.admin_user, role=self.admin_role)

		self.prof_user = User.objects.create_user(username='prof_ie', email='prof_ie@example.com', password='Pass1234!@#')
		UserRole.objects.create(user=self.prof_user, role=self.prof_role)
		self.professor = ProfessorProfile.objects.create(
			user=self.prof_user,
			staff_number='P-IE-1',
			department=self.department,
			hired_at='2020-01-01',
		)

		self.student_user = User.objects.create_user(username='student_ie', email='student_ie@example.com', password='Pass1234!@#')
		UserRole.objects.create(user=self.student_user, role=self.student_role)
		self.student_profile = StudentProfile.objects.create(
			user=self.student_user,
			student_number='S-IE-1',
			faculty=self.faculty,
			department=self.department,
			academic_year=2,
			semester=1,
			enrolled_at='2024-09-01',
		)

		self.term = AcademicTerm.objects.create(
			name='Fall IE',
			start_date='2025-09-01',
			end_date='2026-01-15',
			registration_start='2025-08-01',
			registration_end='2025-08-25',
			is_active=True,
		)
		self.course = Course.objects.create(code='CS-IE-1', name='IE Course', credit_hours=3, lecture_hours=3, lab_hours=0, level=100)
		self.section = Section.objects.create(course=self.course, professor=self.professor, academic_term=self.term, semester=1, capacity=30, schedule={})
		self.enrollment = CourseEnrollment.objects.create(student=self.student_profile, section=self.section, academic_term=self.term, status='active')
		self.grade = Grade.objects.create(enrollment=self.enrollment, points=95, letter_grade='A', status='complete')

		token = Token.objects.create(user=self.admin_user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def test_import_users_endpoint_accepts_csv_file(self):
		csv_content = 'username,email,password,roles\nnew_user,new_user@example.com,Pass1234!@#,student\n'
		upload = SimpleUploadedFile('users.csv', csv_content.encode('utf-8'), content_type='text/csv')

		response = self.client.post(reverse('admin-import-users'), {'file': upload}, format='multipart')
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['data']['created'], 1)
		self.assertTrue(User.objects.filter(username='new_user').exists())

	def test_export_enrollments_returns_csv_attachment(self):
		response = self.client.get(reverse('admin-export-enrollments'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response['Content-Type'], 'text/csv')
		self.assertIn('attachment; filename=', response['Content-Disposition'])
		self.assertIn('enrollment_id,student_number', response.content.decode('utf-8'))

	def test_export_grades_returns_csv_attachment(self):
		response = self.client.get(reverse('admin-export-grades'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response['Content-Type'], 'text/csv')
		self.assertIn('grade_id,enrollment_id', response.content.decode('utf-8'))


class AuditTrailSignalTests(TestCase):
	def setUp(self):
		self.university = University.objects.create(name='Uni Audit', code='UAD', country='EG', city='Cairo', established_year=1990)
		self.faculty = Faculty.objects.create(university=self.university, name='Engineering', code='ENGD')
		self.department = Department.objects.create(faculty=self.faculty, name='Computer Science', code='CSD')

		self.student_role = Role.objects.create(name='Student Audit', slug='student_audit', permissions={})
		self.prof_role = Role.objects.create(name='Professor Audit', slug='professor_audit', permissions={})

		self.student_user = User.objects.create_user(username='student_audit', email='student_audit@example.com', password='Pass1234!@#')
		self.prof_user = User.objects.create_user(username='prof_audit', email='prof_audit@example.com', password='Pass1234!@#')

		UserRole.objects.create(user=self.student_user, role=self.student_role)
		UserRole.objects.create(user=self.prof_user, role=self.prof_role)

		self.student_profile = StudentProfile.objects.create(
			user=self.student_user,
			student_number='SA-1',
			faculty=self.faculty,
			department=self.department,
			academic_year=2,
			semester=1,
			enrolled_at='2024-09-01',
		)
		self.professor = ProfessorProfile.objects.create(
			user=self.prof_user,
			staff_number='PA-1',
			department=self.department,
			hired_at='2020-01-01',
		)
		self.term = AcademicTerm.objects.create(
			name='Fall Audit',
			start_date='2025-09-01',
			end_date='2026-01-15',
			registration_start='2025-08-01',
			registration_end='2025-08-25',
			is_active=True,
		)
		self.course = Course.objects.create(code='CS-AUD', name='Audit Course', credit_hours=3)
		self.section = Section.objects.create(course=self.course, professor=self.professor, academic_term=self.term, semester=1, capacity=30, schedule={})

	def test_course_enrollment_create_and_update_writes_audit_log(self):
		enrollment = CourseEnrollment.objects.create(
			student=self.student_profile,
			section=self.section,
			academic_term=self.term,
			status=CourseEnrollment.EnrollmentStatus.ACTIVE,
		)
		self.assertTrue(
			AuditLog.objects.filter(entity_type='CourseEnrollment', entity_id=str(enrollment.id), action=AuditLog.Action.CREATE).exists()
		)

		enrollment.status = CourseEnrollment.EnrollmentStatus.DROPPED
		enrollment.save(update_fields=['status', 'updated_at'])
		self.assertTrue(
			AuditLog.objects.filter(entity_type='CourseEnrollment', entity_id=str(enrollment.id), action=AuditLog.Action.UPDATE).exists()
		)
