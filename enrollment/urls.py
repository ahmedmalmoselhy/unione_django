from django.urls import path

from .views import (
	StudentAcademicTermsView,
	StudentEnrollmentView,
	StudentGradeView,
	StudentProfileView,
	StudentSectionsView,
)

urlpatterns = [
	path('profile', StudentProfileView.as_view(), name='student-profile'),
	path('enrollments', StudentEnrollmentView.as_view(), name='student-enrollments'),
	path('grades', StudentGradeView.as_view(), name='student-grades'),
	path('academic-terms', StudentAcademicTermsView.as_view(), name='student-academic-terms'),
	path('sections', StudentSectionsView.as_view(), name='student-sections'),
]