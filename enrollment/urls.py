from django.urls import path

from .views import (
	StudentAcademicTermsView,
	StudentAcademicHistoryView,
	StudentEnrollmentView,
	StudentGradeView,
	StudentProfileView,
	StudentScheduleICSView,
	StudentScheduleView,
	StudentSectionsView,
	StudentTranscriptView,
)

urlpatterns = [
	path('profile', StudentProfileView.as_view(), name='student-profile'),
	path('enrollments', StudentEnrollmentView.as_view(), name='student-enrollments'),
	path('grades', StudentGradeView.as_view(), name='student-grades'),
	path('academic-terms', StudentAcademicTermsView.as_view(), name='student-academic-terms'),
	path('sections', StudentSectionsView.as_view(), name='student-sections'),
	path('transcript', StudentTranscriptView.as_view(), name='student-transcript'),
	path('academic-history', StudentAcademicHistoryView.as_view(), name='student-academic-history'),
	path('schedule', StudentScheduleView.as_view(), name='student-schedule'),
	path('schedule/ics', StudentScheduleICSView.as_view(), name='student-schedule-ics'),
]
