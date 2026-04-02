from django.urls import path

from .views import StudentEnrollmentView, StudentGradeView, StudentProfileView

urlpatterns = [
	path('profile', StudentProfileView.as_view(), name='student-profile'),
	path('enrollments', StudentEnrollmentView.as_view(), name='student-enrollments'),
	path('grades', StudentGradeView.as_view(), name='student-grades'),
]