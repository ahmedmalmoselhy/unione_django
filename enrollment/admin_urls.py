from django.urls import path

from .admin_views import (
    AdminUserDetailView,
    AdminUsersView,
    AdminWebhookDeliveriesView,
    AdminWebhookDetailView,
    AdminWebhooksView,
)
from .analytics_views import (
    AttendanceAnalyticsView,
    EnrollmentAnalyticsView,
    GradesAnalyticsView,
    ProfessorStatisticsView,
    StudentStatisticsView,
    WebhookMetricsView,
)
from .organization_admin_views import (
    AdminAcademicTermDetailView,
    AdminAcademicTermsView,
    AdminCourseDetailView,
    AdminCoursesView,
    AdminDepartmentDetailView,
    AdminDepartmentsView,
    AdminFacultiesView,
    AdminFacultyDetailView,
    AdminSectionDetailView,
    AdminSectionsView,
)

urlpatterns = [
    path('users', AdminUsersView.as_view(), name='admin-users'),
    path('users/<int:user_id>', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('webhooks', AdminWebhooksView.as_view(), name='admin-webhooks'),
    path('webhooks/<int:webhook_id>', AdminWebhookDetailView.as_view(), name='admin-webhook-detail'),
    path('webhooks/<int:webhook_id>/deliveries', AdminWebhookDeliveriesView.as_view(), name='admin-webhook-deliveries'),
    path('faculties', AdminFacultiesView.as_view(), name='admin-faculties'),
    path('faculties/<int:faculty_id>', AdminFacultyDetailView.as_view(), name='admin-faculty-detail'),
    path('departments', AdminDepartmentsView.as_view(), name='admin-departments'),
    path('departments/<int:department_id>', AdminDepartmentDetailView.as_view(), name='admin-department-detail'),
    path('academic-terms', AdminAcademicTermsView.as_view(), name='admin-academic-terms'),
    path('academic-terms/<int:term_id>', AdminAcademicTermDetailView.as_view(), name='admin-academic-term-detail'),
    path('courses', AdminCoursesView.as_view(), name='admin-courses'),
    path('courses/<int:course_id>', AdminCourseDetailView.as_view(), name='admin-course-detail'),
    path('sections', AdminSectionsView.as_view(), name='admin-sections'),
    path('sections/<int:section_id>', AdminSectionDetailView.as_view(), name='admin-section-detail'),
    path('analytics/enrollment', EnrollmentAnalyticsView.as_view(), name='admin-analytics-enrollment'),
    path('analytics/grades', GradesAnalyticsView.as_view(), name='admin-analytics-grades'),
    path('analytics/attendance', AttendanceAnalyticsView.as_view(), name='admin-analytics-attendance'),
    path('analytics/webhooks', WebhookMetricsView.as_view(), name='admin-analytics-webhooks'),
    path('analytics/students', StudentStatisticsView.as_view(), name='admin-analytics-students'),
    path('analytics/professors', ProfessorStatisticsView.as_view(), name='admin-analytics-professors'),
]
