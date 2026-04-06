from django.urls import path

from .views import ProfessorProfileView, ProfessorScheduleView, ProfessorSectionsView, ProfessorSectionStudentsView

urlpatterns = [
	path('profile', ProfessorProfileView.as_view(), name='professor-profile'),
	path('schedule', ProfessorScheduleView.as_view(), name='professor-schedule'),
	path('sections', ProfessorSectionsView.as_view(), name='professor-sections'),
	path('sections/<int:section_id>/students', ProfessorSectionStudentsView.as_view(), name='professor-section-students'),
]
