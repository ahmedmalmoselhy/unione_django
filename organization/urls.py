from django.urls import path

from .views import DepartmentView, FacultyView, UniversityView

urlpatterns = [
    path('university', UniversityView.as_view(), name='organization-university'),
    path('faculties', FacultyView.as_view(), name='organization-faculties'),
    path('departments', DepartmentView.as_view(), name='organization-departments'),
]
