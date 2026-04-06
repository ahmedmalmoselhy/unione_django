from django.urls import path

from .views import (
	ProfessorProfileView,
	ProfessorScheduleView,
	ProfessorSectionsView,
	ProfessorSectionStudentsView,
	ProfessorSectionGradesView,
	ProfessorSectionAttendanceView,
)

urlpatterns = [
	path('profile', ProfessorProfileView.as_view(), name='professor-profile'),
	path('schedule', ProfessorScheduleView.as_view(), name='professor-schedule'),
	path('sections', ProfessorSectionsView.as_view(), name='professor-sections'),
	path('sections/<int:section_id>/students', ProfessorSectionStudentsView.as_view(), name='professor-section-students'),
	path('sections/<int:section_id>/grades', ProfessorSectionGradesView.as_view(), name='professor-section-grades'),
	path('sections/<int:section_id>/attendance', ProfessorSectionAttendanceView.as_view(), name='professor-section-attendance'),
]
