from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
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


class AttendanceSession(models.Model):
	section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='attendance_sessions')
	created_by = models.ForeignKey('enrollment.ProfessorProfile', on_delete=models.CASCADE, related_name='attendance_sessions')
	session_date = models.DateField()
	title = models.CharField(max_length=255, null=True, blank=True)
	notes = models.TextField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=['section', 'session_date', 'title'],
				name='uniq_attendance_session_section_date_title',
			)
		]

	def __str__(self):
		return f'section:{self.section_id} date:{self.session_date}'


class AttendanceRecord(models.Model):
	class Status(models.TextChoices):
		PRESENT = 'present', 'Present'
		ABSENT = 'absent', 'Absent'
		LATE = 'late', 'Late'
		EXCUSED = 'excused', 'Excused'

	session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
	enrollment = models.ForeignKey('enrollment.CourseEnrollment', on_delete=models.CASCADE, related_name='attendance_records')
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.ABSENT)
	note = models.CharField(max_length=255, null=True, blank=True)
	marked_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=['session', 'enrollment'],
				name='uniq_attendance_record_session_enrollment',
			)
		]

	def __str__(self):
		return f'session:{self.session_id} enrollment:{self.enrollment_id} status:{self.status}'


class SectionAnnouncement(models.Model):
	section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='announcements')
	created_by = models.ForeignKey('enrollment.ProfessorProfile', on_delete=models.CASCADE, related_name='section_announcements')
	title = models.CharField(max_length=255)
	body = models.TextField()
	is_pinned = models.BooleanField(default=False)
	published_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'section:{self.section_id} title:{self.title}'


class AnnouncementRead(models.Model):
	announcement = models.ForeignKey(SectionAnnouncement, on_delete=models.CASCADE, related_name='reads')
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='announcement_reads')
	read_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=['announcement', 'user'], name='uniq_announcement_read_user')
		]

	def __str__(self):
		return f'announcement:{self.announcement_id} user:{self.user_id}'


class Notification(models.Model):
	recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
	title = models.CharField(max_length=255)
	body = models.TextField()
	notification_type = models.CharField(max_length=100, default='general')
	payload = models.JSONField(default=dict, blank=True)
	read_at = models.DateTimeField(null=True, blank=True)
	deleted_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'notification:{self.id} recipient:{self.recipient_id}'


class Webhook(models.Model):
	name = models.CharField(max_length=255)
	target_url = models.URLField(max_length=1000)
	events = models.JSONField(default=list, blank=True)
	headers = models.JSONField(default=dict, blank=True)
	secret = models.CharField(max_length=255, null=True, blank=True)
	is_active = models.BooleanField(default=True)
	created_by = models.ForeignKey(
		settings.AUTH_USER_MODEL,
		on_delete=models.SET_NULL,
		related_name='created_webhooks',
		null=True,
		blank=True,
	)
	last_triggered_at = models.DateTimeField(null=True, blank=True)
	deleted_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'webhook:{self.id} name:{self.name}'


class WebhookDelivery(models.Model):
	class DeliveryStatus(models.TextChoices):
		PENDING = 'pending', 'Pending'
		SUCCESS = 'success', 'Success'
		FAILED = 'failed', 'Failed'
		RETRY = 'retry', 'Retry'

	webhook = models.ForeignKey(Webhook, on_delete=models.CASCADE, related_name='deliveries')
	event_name = models.CharField(max_length=100)
	payload = models.JSONField(default=dict, blank=True)
	request_headers = models.JSONField(default=dict, blank=True)
	response_status_code = models.PositiveIntegerField(null=True, blank=True)
	response_body = models.TextField(null=True, blank=True)
	status = models.CharField(max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING)
	attempt_count = models.PositiveIntegerField(default=0)
	error_message = models.TextField(null=True, blank=True)
	delivered_at = models.DateTimeField(null=True, blank=True)
	next_retry_at = models.DateTimeField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'delivery:{self.id} webhook:{self.webhook_id} status:{self.status}'


class EnrollmentWaitlist(models.Model):
	class WaitlistStatus(models.TextChoices):
		ACTIVE = 'active', 'Active'
		CANCELLED = 'cancelled', 'Cancelled'
		ENROLLED = 'enrolled', 'Enrolled'

	student = models.ForeignKey('enrollment.StudentProfile', on_delete=models.CASCADE, related_name='waitlist_entries')
	section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='waitlist_entries')
	academic_term = models.ForeignKey(AcademicTerm, on_delete=models.CASCADE, related_name='waitlist_entries')
	position = models.PositiveIntegerField(default=1)
	status = models.CharField(max_length=20, choices=WaitlistStatus.choices, default=WaitlistStatus.ACTIVE)
	notes = models.TextField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=['student', 'section'], name='uniq_waitlist_student_section')
		]

	def __str__(self):
		return f'waitlist:{self.student_id}:{self.section_id}:{self.status}'


class CourseRating(models.Model):
	student = models.ForeignKey('enrollment.StudentProfile', on_delete=models.CASCADE, related_name='course_ratings')
	course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='ratings')
	section = models.ForeignKey(Section, on_delete=models.SET_NULL, related_name='ratings', null=True, blank=True)
	rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
	comment = models.TextField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(fields=['student', 'course'], name='uniq_course_rating_student_course')
		]

	def __str__(self):
		return f'rating:{self.student_id}:{self.course_id}:{self.rating}'
