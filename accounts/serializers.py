from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import AccountProfile

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    username = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if not attrs.get('email') and not attrs.get('username'):
            raise serializers.ValidationError('Either email or username is required.')
        return attrs


class UserSummarySerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'roles']

    def get_roles(self, obj):
        return [ur.role.slug for ur in obj.user_roles.select_related('role').all()]


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, min_length=8)


class UpdateProfileSerializer(serializers.Serializer):
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=20)
    date_of_birth = serializers.DateField(required=False)
    avatar_path = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_email(self, value):
        user = self.instance
        if value and User.objects.exclude(pk=user.pk).filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def update(self, instance, validated_data):
        user_fields = ['first_name', 'last_name', 'email']
        account_fields = ['phone', 'date_of_birth', 'avatar_path']

        user_updated_fields = []
        for field in user_fields:
            if field in validated_data:
                setattr(instance, field, validated_data[field])
                user_updated_fields.append(field)

        if user_updated_fields:
            instance.save(update_fields=user_updated_fields)

        profile_payload = {field: validated_data[field] for field in account_fields if field in validated_data}
        if profile_payload:
            profile, _ = AccountProfile.objects.get_or_create(user=instance)
            for key, value in profile_payload.items():
                setattr(profile, key, value)
            profile.save(update_fields=list(profile_payload.keys()) + ['updated_at'])

        return instance
