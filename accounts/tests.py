from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class AuthEndpointsTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username='student1',
			email='student1@example.com',
			password='Pass1234!@#',
		)

	def test_login_with_email_returns_token(self):
		response = self.client.post(
			reverse('auth-login'),
			{'email': 'student1@example.com', 'password': 'Pass1234!@#'},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['status'], 'success')
		self.assertIn('token', response.data['data'])

	def test_me_requires_authentication(self):
		response = self.client.get(reverse('auth-me'))
		self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

	def test_logout_revokes_token(self):
		login = self.client.post(
			reverse('auth-login'),
			{'email': 'student1@example.com', 'password': 'Pass1234!@#'},
			format='json',
		)
		token = login.data['data']['token']
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

		response = self.client.post(reverse('auth-logout'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)

	def test_change_password_requires_current_password(self):
		login = self.client.post(
			reverse('auth-login'),
			{'email': 'student1@example.com', 'password': 'Pass1234!@#'},
			format='json',
		)
		token = login.data['data']['token']
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

		response = self.client.post(
			reverse('auth-change-password'),
			{'current_password': 'wrong', 'password': 'NewPass123!@#'},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_forgot_and_reset_password_flow(self):
		forgot_response = self.client.post(
			reverse('auth-forgot-password'),
			{'email': 'student1@example.com'},
			format='json',
		)
		self.assertEqual(forgot_response.status_code, status.HTTP_200_OK)

		uid = forgot_response.data['data']['uid']
		token = forgot_response.data['data']['token']
		reset_response = self.client.post(
			reverse('auth-reset-password'),
			{'uid': uid, 'token': token, 'password': 'BrandNew123!@#'},
			format='json',
		)
		self.assertEqual(reset_response.status_code, status.HTTP_200_OK)

		login_response = self.client.post(
			reverse('auth-login'),
			{'email': 'student1@example.com', 'password': 'BrandNew123!@#'},
			format='json',
		)
		self.assertEqual(login_response.status_code, status.HTTP_200_OK)

	def test_profile_patch_updates_name_and_email(self):
		login = self.client.post(
			reverse('auth-login'),
			{'email': 'student1@example.com', 'password': 'Pass1234!@#'},
			format='json',
		)
		token = login.data['data']['token']
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

		response = self.client.patch(
			reverse('auth-profile-update'),
			{'first_name': 'Ali', 'last_name': 'Hassan', 'email': 'ali.hassan@example.com'},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['data']['user']['first_name'], 'Ali')
		self.assertEqual(response.data['data']['user']['email'], 'ali.hassan@example.com')

		self.user.refresh_from_db()
		self.assertEqual(self.user.first_name, 'Ali')
		self.assertEqual(self.user.last_name, 'Hassan')
		self.assertEqual(self.user.email, 'ali.hassan@example.com')

	def test_profile_patch_rejects_duplicate_email(self):
		User.objects.create_user(username='another', email='another@example.com', password='Pass1234!@#')
		login = self.client.post(
			reverse('auth-login'),
			{'email': 'student1@example.com', 'password': 'Pass1234!@#'},
			format='json',
		)
		token = login.data['data']['token']
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

		response = self.client.patch(
			reverse('auth-profile-update'),
			{'email': 'another@example.com'},
			format='json',
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

	def test_tokens_index_and_revoke_specific(self):
		login = self.client.post(
			reverse('auth-login'),
			{'email': 'student1@example.com', 'password': 'Pass1234!@#'},
			format='json',
		)
		token = login.data['data']['token']
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

		self.client.post(
			reverse('auth-login'),
			{'email': 'student1@example.com', 'password': 'Pass1234!@#'},
			format='json',
		)

		list_response = self.client.get(reverse('auth-tokens'))
		self.assertEqual(list_response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(list_response.data['data']['tokens']), 2)
		tokens = list_response.data['data']['tokens']
		current_token = next(t for t in tokens if t['is_current'])
		token_id = current_token['id']

		revoke_response = self.client.delete(reverse('auth-token-destroy', kwargs={'token_id': token_id}))
		self.assertEqual(revoke_response.status_code, status.HTTP_200_OK)

		me_response = self.client.get(reverse('auth-me'))
		self.assertEqual(me_response.status_code, status.HTTP_401_UNAUTHORIZED)

	def test_tokens_destroy_unknown_token_returns_404(self):
		login = self.client.post(
			reverse('auth-login'),
			{'email': 'student1@example.com', 'password': 'Pass1234!@#'},
			format='json',
		)
		token = login.data['data']['token']
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

		response = self.client.delete(reverse('auth-token-destroy', kwargs={'token_id': 999999}))
		self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

	def test_profile_patch_updates_extended_profile_fields(self):
		login = self.client.post(
			reverse('auth-login'),
			{'email': 'student1@example.com', 'password': 'Pass1234!@#'},
			format='json',
		)
		token = login.data['data']['token']
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

		response = self.client.patch(
			reverse('auth-profile-update'),
			{
				'phone': '+201234567890',
				'date_of_birth': '1998-05-21',
				'avatar_path': '/avatars/user1.png',
			},
			format='json',
		)
		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(response.data['data']['user']['phone'], '+201234567890')
		self.assertEqual(response.data['data']['user']['avatar_path'], '/avatars/user1.png')

	def test_tokens_destroy_all(self):
		login = self.client.post(
			reverse('auth-login'),
			{'email': 'student1@example.com', 'password': 'Pass1234!@#'},
			format='json',
		)
		token = login.data['data']['token']
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')

		response = self.client.delete(reverse('auth-tokens'))
		self.assertEqual(response.status_code, status.HTTP_200_OK)

		me_response = self.client.get(reverse('auth-me'))
		self.assertEqual(me_response.status_code, status.HTTP_401_UNAUTHORIZED)
