from django.db import models


class University(models.Model):
	name = models.CharField(max_length=255)
	code = models.CharField(max_length=50, unique=True)
	country = models.CharField(max_length=100)
	city = models.CharField(max_length=100)
	established_year = models.PositiveIntegerField()
	logo_path = models.CharField(max_length=255, null=True, blank=True)
	phone = models.CharField(max_length=30, null=True, blank=True)
	email = models.EmailField(null=True, blank=True)
	website = models.URLField(null=True, blank=True)
	address = models.TextField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.code


class Faculty(models.Model):
	university = models.ForeignKey(University, on_delete=models.CASCADE, related_name='faculties')
	name = models.CharField(max_length=255)
	name_ar = models.CharField(max_length=255, null=True, blank=True)
	code = models.CharField(max_length=50)
	logo_path = models.CharField(max_length=255, null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=['university', 'code'], name='uniq_faculty_code_per_university')
		]

	def __str__(self):
		return f'{self.university.code}-{self.code}'


class Department(models.Model):
	class Scope(models.TextChoices):
		UNIVERSITY = 'university', 'University'
		FACULTY = 'faculty', 'Faculty'
		DEPARTMENT = 'department', 'Department'

	faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='departments')
	name = models.CharField(max_length=255)
	name_ar = models.CharField(max_length=255, null=True, blank=True)
	code = models.CharField(max_length=50)
	scope = models.CharField(max_length=20, choices=Scope.choices, null=True, blank=True)
	is_mandatory = models.BooleanField(default=False)
	required_credit_hours = models.PositiveIntegerField(null=True, blank=True)
	logo_path = models.CharField(max_length=255, null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=['faculty', 'code'], name='uniq_department_code_per_faculty')
		]

	def __str__(self):
		return f'{self.faculty.code}-{self.code}'
