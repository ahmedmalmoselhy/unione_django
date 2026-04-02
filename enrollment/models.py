from django.conf import settings
from django.db import models


class ProfessorProfile(models.Model):
	class AcademicRank(models.TextChoices):
		ASSISTANT = 'assistant_professor', 'Assistant Professor'
		ASSOCIATE = 'associate_professor', 'Associate Professor'
		PROFESSOR = 'professor', 'Professor'

	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='professor_profile')
	staff_number = models.CharField(max_length=50, unique=True)
	department = models.ForeignKey('organization.Department', on_delete=models.PROTECT, related_name='professors')
	specialization = models.CharField(max_length=255, null=True, blank=True)
	academic_rank = models.CharField(max_length=30, choices=AcademicRank.choices, default=AcademicRank.ASSISTANT)
	office_location = models.CharField(max_length=100, null=True, blank=True)
	hired_at = models.DateField()
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.staff_number


class StudentProfile(models.Model):
	class EnrollmentStatus(models.TextChoices):
		ACTIVE = 'active', 'Active'
		GRADUATED = 'graduated', 'Graduated'
		SUSPENDED = 'suspended', 'Suspended'

	class AcademicStanding(models.TextChoices):
		GOOD = 'good', 'Good'
		PROBATION = 'probation', 'Probation'
		SUSPENSION = 'suspension', 'Suspension'

	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_profile')
	student_number = models.CharField(max_length=50, unique=True)
	faculty = models.ForeignKey('organization.Faculty', on_delete=models.PROTECT, related_name='students')
	department = models.ForeignKey('organization.Department', on_delete=models.PROTECT, related_name='students')
	academic_year = models.PositiveSmallIntegerField(default=1)
	semester = models.PositiveSmallIntegerField(default=1)
	enrollment_status = models.CharField(max_length=20, choices=EnrollmentStatus.choices, default=EnrollmentStatus.ACTIVE)
	gpa = models.DecimalField(max_digits=3, decimal_places=2, default=0)
	academic_standing = models.CharField(max_length=20, choices=AcademicStanding.choices, default=AcademicStanding.GOOD)
	enrolled_at = models.DateField()
	graduated_at = models.DateField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.student_number


class CourseEnrollment(models.Model):
	class EnrollmentStatus(models.TextChoices):
		ACTIVE = 'active', 'Active'
		COMPLETED = 'completed', 'Completed'
		DROPPED = 'dropped', 'Dropped'

	student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='enrollments')
	section = models.ForeignKey('academics.Section', on_delete=models.CASCADE, related_name='enrollments')
	academic_term = models.ForeignKey('academics.AcademicTerm', on_delete=models.CASCADE, related_name='enrollments')
	status = models.CharField(max_length=20, choices=EnrollmentStatus.choices, default=EnrollmentStatus.ACTIVE)
	registered_at = models.DateTimeField(auto_now_add=True)
	dropped_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=['student', 'section', 'academic_term'],
				name='uniq_student_section_term_enrollment',
			)
		]

	def __str__(self):
		return f'{self.student.student_number}:{self.section_id}'
