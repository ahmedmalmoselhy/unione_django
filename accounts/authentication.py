from django.utils import timezone
from rest_framework import authentication, exceptions

from .models import AccessToken


class AccessTokenAuthentication(authentication.BaseAuthentication):
    keyword = 'Token'

    def authenticate_header(self, request):
        return self.keyword

    def authenticate(self, request):
        auth = authentication.get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword.lower().encode('utf-8'):
            return None

        if len(auth) == 1:
            raise exceptions.AuthenticationFailed('Invalid token header. No credentials provided.')
        if len(auth) > 2:
            raise exceptions.AuthenticationFailed('Invalid token header. Token string should not contain spaces.')

        try:
            token_key = auth[1].decode('utf-8')
        except UnicodeError as exc:
            raise exceptions.AuthenticationFailed('Invalid token header. Token string should be UTF-8.') from exc

        token = AccessToken.objects.select_related('user').filter(token_key=token_key).first()
        if token is None:
            # Allow subsequent authentication classes (e.g. DRF TokenAuthentication)
            # to attempt authenticating this token.
            return None

        if token.revoked_at is not None:
            raise exceptions.AuthenticationFailed('Token revoked.')

        if not token.user.is_active:
            raise exceptions.AuthenticationFailed('User inactive or deleted.')

        token.last_used_at = timezone.now()
        token.save(update_fields=['last_used_at', 'updated_at'])

        return (token.user, token)
