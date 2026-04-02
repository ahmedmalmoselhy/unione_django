from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes, force_str
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
	ChangePasswordSerializer,
	ForgotPasswordSerializer,
	LoginSerializer,
	ResetPasswordSerializer,
	UserSummarySerializer,
)

User = get_user_model()


def _user_role_slugs(user):
	return [ur.role.slug for ur in user.user_roles.select_related('role').all()]


class LoginView(APIView):
	permission_classes = [permissions.AllowAny]

	def post(self, request):
		serializer = LoginSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		email = serializer.validated_data.get('email')
		username = serializer.validated_data.get('username')
		password = serializer.validated_data['password']

		auth_username = username
		if email and not username:
			user = User.objects.filter(email=email).first()
			if user is not None:
				auth_username = user.username

		user = authenticate(request=request, username=auth_username, password=password)
		if user is None:
			return Response(
				{'status': 'error', 'message': 'Invalid credentials'},
				status=status.HTTP_401_UNAUTHORIZED,
			)

		token, _ = Token.objects.get_or_create(user=user)
		return Response(
			{
				'status': 'success',
				'message': 'Login successful',
				'data': {
					'token': token.key,
					'user': UserSummarySerializer(user).data,
				},
			},
			status=status.HTTP_200_OK,
		)


class LogoutView(APIView):
	def post(self, request):
		if request.auth:
			request.auth.delete()
		return Response({'status': 'success', 'message': 'Logged out'}, status=status.HTTP_200_OK)


class MeView(APIView):
	def get(self, request):
		user_data = UserSummarySerializer(request.user).data
		user_data['roles'] = _user_role_slugs(request.user)
		return Response(
			{
				'status': 'success',
				'data': {
					'user': user_data,
				},
			},
			status=status.HTTP_200_OK,
		)


class ForgotPasswordView(APIView):
	permission_classes = [permissions.AllowAny]

	def post(self, request):
		serializer = ForgotPasswordSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		email = serializer.validated_data['email']
		user = User.objects.filter(email=email).first()
		if user is None:
			return Response(
				{'status': 'success', 'message': 'If the account exists, reset instructions were generated.'},
				status=status.HTTP_200_OK,
			)

		token = PasswordResetTokenGenerator().make_token(user)
		uid = urlsafe_base64_encode(force_bytes(user.pk))
		return Response(
			{
				'status': 'success',
				'message': 'Reset token generated',
				'data': {'uid': uid, 'token': token},
			},
			status=status.HTTP_200_OK,
		)


class ResetPasswordView(APIView):
	permission_classes = [permissions.AllowAny]

	def post(self, request):
		serializer = ResetPasswordSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		uid = serializer.validated_data['uid']
		token = serializer.validated_data['token']
		password = serializer.validated_data['password']

		try:
			user_id = force_str(urlsafe_base64_decode(uid))
			user = User.objects.get(pk=user_id)
		except (User.DoesNotExist, ValueError, TypeError, OverflowError):
			return Response({'status': 'error', 'message': 'Invalid reset payload'}, status=status.HTTP_400_BAD_REQUEST)

		generator = PasswordResetTokenGenerator()
		if not generator.check_token(user, token):
			return Response({'status': 'error', 'message': 'Invalid or expired token'}, status=status.HTTP_400_BAD_REQUEST)

		user.set_password(password)
		user.save(update_fields=['password'])
		Token.objects.filter(user=user).delete()

		return Response({'status': 'success', 'message': 'Password reset successful'}, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
	def post(self, request):
		serializer = ChangePasswordSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		if not request.user.check_password(serializer.validated_data['current_password']):
			return Response({'status': 'error', 'message': 'Current password is incorrect'}, status=status.HTTP_400_BAD_REQUEST)

		request.user.set_password(serializer.validated_data['password'])
		request.user.save(update_fields=['password'])
		Token.objects.filter(user=request.user).delete()

		return Response({'status': 'success', 'message': 'Password changed successfully'}, status=status.HTTP_200_OK)
