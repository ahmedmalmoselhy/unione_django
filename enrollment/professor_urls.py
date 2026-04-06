from django.urls import path

from .views import ProfessorProfileView, ProfessorSectionsView

urlpatterns = [
	path('profile', ProfessorProfileView.as_view(), name='professor-profile'),
	path('sections', ProfessorSectionsView.as_view(), name='professor-sections'),
]
