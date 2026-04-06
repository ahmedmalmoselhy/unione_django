from django.urls import path

from .views import (
    ChangePasswordView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    MeView,
    ProfileUpdateView,
    ResetPasswordView,
    TokenDestroyView,
    TokenListDestroyAllView,
)

urlpatterns = [
    path('login', LoginView.as_view(), name='auth-login'),
    path('logout', LogoutView.as_view(), name='auth-logout'),
    path('me', MeView.as_view(), name='auth-me'),
    path('forgot-password', ForgotPasswordView.as_view(), name='auth-forgot-password'),
    path('reset-password', ResetPasswordView.as_view(), name='auth-reset-password'),
    path('change-password', ChangePasswordView.as_view(), name='auth-change-password'),
    path('profile', ProfileUpdateView.as_view(), name='auth-profile-update'),
    path('tokens', TokenListDestroyAllView.as_view(), name='auth-tokens'),
    path('tokens/<str:token_id>', TokenDestroyView.as_view(), name='auth-token-destroy'),
]
