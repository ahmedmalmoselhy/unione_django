from django.urls import path

from .views import (
	StudentAttendanceView,
	StudentAcademicTermsView,
	StudentAcademicHistoryView,
	StudentEnrollmentDeleteView,
	StudentEnrollmentView,
	StudentGradeView,
	StudentProfileView,
	StudentRatingsView,
	StudentScheduleICSView,
	StudentScheduleView,
	StudentSectionsView,
	StudentTranscriptPDFView,
	StudentTranscriptView,
	StudentWaitlistDeleteView,
	StudentWaitlistView,
)

urlpatterns = [
	path('profile', StudentProfileView.as_view(), name='student-profile'),
	path('enrollments', StudentEnrollmentView.as_view(), name='student-enrollments'),
	path('enrollments/<int:enrollment_id>', StudentEnrollmentDeleteView.as_view(), name='student-enrollment-delete'),
	path('grades', StudentGradeView.as_view(), name='student-grades'),
	path('academic-terms', StudentAcademicTermsView.as_view(), name='student-academic-terms'),
	path('sections', StudentSectionsView.as_view(), name='student-sections'),
	path('transcript', StudentTranscriptView.as_view(), name='student-transcript'),
	path('transcript/pdf', StudentTranscriptPDFView.as_view(), name='student-transcript-pdf'),
	path('academic-history', StudentAcademicHistoryView.as_view(), name='student-academic-history'),
	path('schedule', StudentScheduleView.as_view(), name='student-schedule'),
	path('schedule/ics', StudentScheduleICSView.as_view(), name='student-schedule-ics'),
	path('attendance', StudentAttendanceView.as_view(), name='student-attendance'),
	path('waitlist', StudentWaitlistView.as_view(), name='student-waitlist'),
	path('waitlist/<int:section_id>', StudentWaitlistDeleteView.as_view(), name='student-waitlist-delete'),
	path('ratings', StudentRatingsView.as_view(), name='student-ratings'),
]
