from django.conf import settings
from django.db import models


class Role(models.Model):
	name = models.CharField(max_length=100, unique=True)
	slug = models.SlugField(max_length=100, unique=True)
	permissions = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.slug


class UserRole(models.Model):
	class Scope(models.TextChoices):
		UNIVERSITY = 'university', 'University'
		FACULTY = 'faculty', 'Faculty'
		DEPARTMENT = 'department', 'Department'

	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_roles')
	role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='user_roles')
	scope = models.CharField(max_length=20, choices=Scope.choices, null=True, blank=True)
	scope_id = models.PositiveIntegerField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=['user', 'role', 'scope', 'scope_id'],
				name='uniq_user_role_scope',
			)
		]

	def __str__(self):
		return f'{self.user_id}:{self.role.slug}'
