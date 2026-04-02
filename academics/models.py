from django.db import models


class AcademicTerm(models.Model):
	name = models.CharField(max_length=100)
	start_date = models.DateField()
	end_date = models.DateField()
	registration_start = models.DateField()
	registration_end = models.DateField()
	is_active = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.name


class Course(models.Model):
	code = models.CharField(max_length=50, unique=True)
	name = models.CharField(max_length=255)
	name_ar = models.CharField(max_length=255, null=True, blank=True)
	description = models.TextField(null=True, blank=True)
	credit_hours = models.PositiveSmallIntegerField()
	lecture_hours = models.PositiveSmallIntegerField(default=0)
	lab_hours = models.PositiveSmallIntegerField(default=0)
	level = models.PositiveSmallIntegerField(default=100)
	is_elective = models.BooleanField(default=False)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.code


class Section(models.Model):
	course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sections')
	professor = models.ForeignKey('enrollment.ProfessorProfile', on_delete=models.CASCADE, related_name='sections')
	academic_term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE, related_name='sections')
	semester = models.PositiveSmallIntegerField(default=1)
	capacity = models.PositiveIntegerField(default=0)
	schedule = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'{self.course.code}-T{self.academic_term_id}-S{self.id}'


class Grade(models.Model):
	class Status(models.TextChoices):
		COMPLETE = 'complete', 'Complete'
		INCOMPLETE = 'incomplete', 'Incomplete'

	enrollment = models.OneToOneField('enrollment.CourseEnrollment', on_delete=models.CASCADE, related_name='grade')
	points = models.PositiveSmallIntegerField()
	letter_grade = models.CharField(max_length=2)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETE)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'{self.enrollment_id}:{self.letter_grade}'
