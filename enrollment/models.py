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
	academic_rank = models.CharField(max_length=30, choices=AcademicRank.choices, default=AcademicRank.ASSISTANT, db_index=True)
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
	academic_year = models.PositiveSmallIntegerField(default=1, db_index=True)
	semester = models.PositiveSmallIntegerField(default=1)
	enrollment_status = models.CharField(max_length=20, choices=EnrollmentStatus.choices, default=EnrollmentStatus.ACTIVE, db_index=True)
	gpa = models.DecimalField(max_digits=3, decimal_places=2, default=0, db_index=True)
	academic_standing = models.CharField(max_length=20, choices=AcademicStanding.choices, default=AcademicStanding.GOOD)
	enrolled_at = models.DateField()
	graduated_at = models.DateField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return self.student_number

	class Meta:
		indexes = [
			models.Index(fields=['faculty', 'enrollment_status']),
			models.Index(fields=['department', 'academic_year']),
		]


class CourseEnrollment(models.Model):
	class EnrollmentStatus(models.TextChoices):
		ACTIVE = 'active', 'Active'
		COMPLETED = 'completed', 'Completed'
		DROPPED = 'dropped', 'Dropped'

	student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='enrollments')
	section = models.ForeignKey('academics.Section', on_delete=models.CASCADE, related_name='enrollments')
	academic_term = models.ForeignKey('academics.AcademicTerm', on_delete=models.CASCADE, related_name='enrollments')
	status = models.CharField(max_length=20, choices=EnrollmentStatus.choices, default=EnrollmentStatus.ACTIVE, db_index=True)
	registered_at = models.DateTimeField(auto_now_add=True, db_index=True)
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
		indexes = [
			models.Index(fields=['status', 'registered_at']),
			models.Index(fields=['academic_term', 'status']),
		]

	def __str__(self):
		return f'{self.student.student_number}:{self.section_id}'


class EmployeeProfile(models.Model):
	class EmploymentType(models.TextChoices):
		FULL_TIME = 'full_time', 'Full Time'
		PART_TIME = 'part_time', 'Part Time'
		CONTRACT = 'contract', 'Contract'
		INTERN = 'intern', 'Intern'

	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='employee_profile')
	staff_number = models.CharField(max_length=50, unique=True)
	job_title = models.CharField(max_length=255)
	department = models.ForeignKey('organization.Department', on_delete=models.PROTECT, related_name='employees', null=True, blank=True)
	employment_type = models.CharField(max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME)
	salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	hired_at = models.DateField()
	terminated_at = models.DateField(null=True, blank=True)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'{self.staff_number} - {self.job_title}'

	class Meta:
		indexes = [
			models.Index(fields=['staff_number']),
			models.Index(fields=['employment_type']),
			models.Index(fields=['is_active']),
		]


class StudentDepartmentHistory(models.Model):
	student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='department_history')
	from_department = models.ForeignKey('organization.Department', on_delete=models.SET_NULL, related_name='transfers_from', null=True, blank=True)
	to_department = models.ForeignKey('organization.Department', on_delete=models.PROTECT, related_name='transfers_to')
	changed_at = models.DateTimeField(auto_now_add=True)
	changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
	note = models.TextField(blank=True, null=True)

	def __str__(self):
		return f'{self.student.student_number} transferred to {self.to_department.name}'

	class Meta:
		ordering = ['-changed_at']
