from django.urls import path

from .views import (
	ProfessorProfileView,
	ProfessorScheduleView,
	ProfessorSectionsView,
	ProfessorSectionStudentsView,
	ProfessorSectionGradesView,
	ProfessorSectionAttendanceView,
	ProfessorSectionAttendanceSessionDetailView,
	ProfessorSectionAnnouncementsView,
	ProfessorSectionAnnouncementDeleteView,
)

urlpatterns = [
	path('profile', ProfessorProfileView.as_view(), name='professor-profile'),
	path('schedule', ProfessorScheduleView.as_view(), name='professor-schedule'),
	path('sections', ProfessorSectionsView.as_view(), name='professor-sections'),
	path('sections/<int:section_id>/students', ProfessorSectionStudentsView.as_view(), name='professor-section-students'),
	path('sections/<int:section_id>/grades', ProfessorSectionGradesView.as_view(), name='professor-section-grades'),
	path('sections/<int:section_id>/attendance', ProfessorSectionAttendanceView.as_view(), name='professor-section-attendance'),
	path(
		'sections/<int:section_id>/attendance/<int:session_id>',
		ProfessorSectionAttendanceSessionDetailView.as_view(),
		name='professor-section-attendance-detail',
	),
	path(
		'sections/<int:section_id>/announcements',
		ProfessorSectionAnnouncementsView.as_view(),
		name='professor-section-announcements',
	),
	path(
		'sections/<int:section_id>/announcements/<int:announcement_id>',
		ProfessorSectionAnnouncementDeleteView.as_view(),
		name='professor-section-announcement-delete',
	),
]
