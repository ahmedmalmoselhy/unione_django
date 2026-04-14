from django.urls import path

from .views import DepartmentView, FacultyView, UniversityView
from .admin_views import AdminVicePresidentsView, AdminVicePresidentDetailView

urlpatterns = [
    path('university', UniversityView.as_view(), name='organization-university'),
    path('faculties', FacultyView.as_view(), name='organization-faculties'),
    path('departments', DepartmentView.as_view(), name='organization-departments'),
    path('admin/vice-presidents', AdminVicePresidentsView.as_view(), name='admin-vice-presidents'),
    path('admin/vice-presidents/<int:vp_id>', AdminVicePresidentDetailView.as_view(), name='admin-vice-president-detail'),
]
