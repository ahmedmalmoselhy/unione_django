from django.urls import path

from .admin_views import (
    AdminUserDetailView,
    AdminUsersView,
    AdminWebhookDeliveriesView,
    AdminWebhookDetailView,
    AdminWebhooksView,
)
from .admin_employee_views import (
    AdminEmployeeDetailView,
    AdminEmployeesView,
)
from .admin_student_views import (
    AdminStudentDetailView,
    AdminStudentsView,
)
from .admin_professor_views import (
    AdminProfessorDetailView,
    AdminProfessorsView,
)
from .analytics_views import (
    AttendanceAnalyticsView,
    EnrollmentAnalyticsView,
    GradesAnalyticsView,
    ProfessorStatisticsView,
    StudentStatisticsView,
    WebhookMetricsView,
)
from .audit_log_views import AuditLogDetailView, AuditLogListView
from .import_export_views import (
    AdminExportEnrollmentsView,
    AdminExportGradesView,
    AdminImportCoursesView,
    AdminImportUsersView,
)
from .organization_admin_views import (
    AdminAcademicTermDetailView,
    AdminAcademicTermsView,
    AdminCourseDetailView,
    AdminCoursesView,
    AdminDepartmentDetailView,
    AdminDepartmentsView,
    AdminSectionGroupProjectDetailView,
    AdminSectionGroupProjectMemberDetailView,
    AdminSectionGroupProjectMembersView,
    AdminSectionGroupProjectsView,
    AdminSectionExamSchedulePublishView,
    AdminSectionExamScheduleView,
    AdminFacultiesView,
    AdminFacultyDetailView,
    AdminSectionTeachingAssistantDetailView,
    AdminSectionTeachingAssistantsView,
    AdminSectionDetailView,
    AdminSectionsView,
)

urlpatterns = [
    path('users', AdminUsersView.as_view(), name='admin-users'),
    path('users/<int:user_id>', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('employees', AdminEmployeesView.as_view(), name='admin-employees'),
    path('employees/<int:employee_id>', AdminEmployeeDetailView.as_view(), name='admin-employee-detail'),
    path('students', AdminStudentsView.as_view(), name='admin-students'),
    path('students/<int:student_id>', AdminStudentDetailView.as_view(), name='admin-student-detail'),
    path('professors', AdminProfessorsView.as_view(), name='admin-professors'),
    path('professors/<int:professor_id>', AdminProfessorDetailView.as_view(), name='admin-professor-detail'),
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
    path(
        'sections/<int:section_id>/exam-schedule',
        AdminSectionExamScheduleView.as_view(),
        name='admin-section-exam-schedule',
    ),
    path(
        'sections/<int:section_id>/exam-schedule/publish',
        AdminSectionExamSchedulePublishView.as_view(),
        name='admin-section-exam-schedule-publish',
    ),
    path(
        'sections/<int:section_id>/teaching-assistants',
        AdminSectionTeachingAssistantsView.as_view(),
        name='admin-section-teaching-assistants',
    ),
    path(
        'sections/<int:section_id>/teaching-assistants/<int:ta_id>',
        AdminSectionTeachingAssistantDetailView.as_view(),
        name='admin-section-teaching-assistant-detail',
    ),
    path(
        'sections/<int:section_id>/group-projects',
        AdminSectionGroupProjectsView.as_view(),
        name='admin-section-group-projects',
    ),
    path(
        'sections/<int:section_id>/group-projects/<int:project_id>',
        AdminSectionGroupProjectDetailView.as_view(),
        name='admin-section-group-project-detail',
    ),
    path(
        'sections/<int:section_id>/group-projects/<int:project_id>/members',
        AdminSectionGroupProjectMembersView.as_view(),
        name='admin-section-group-project-members',
    ),
    path(
        'sections/<int:section_id>/group-projects/<int:project_id>/members/<int:member_id>',
        AdminSectionGroupProjectMemberDetailView.as_view(),
        name='admin-section-group-project-member-detail',
    ),
    path('analytics/enrollment', EnrollmentAnalyticsView.as_view(), name='admin-analytics-enrollment'),
    path('analytics/grades', GradesAnalyticsView.as_view(), name='admin-analytics-grades'),
    path('analytics/attendance', AttendanceAnalyticsView.as_view(), name='admin-analytics-attendance'),
    path('analytics/webhooks', WebhookMetricsView.as_view(), name='admin-analytics-webhooks'),
    path('analytics/students', StudentStatisticsView.as_view(), name='admin-analytics-students'),
    path('analytics/professors', ProfessorStatisticsView.as_view(), name='admin-analytics-professors'),
    path('audit-logs', AuditLogListView.as_view(), name='admin-audit-logs'),
    path('audit-logs/<int:log_id>', AuditLogDetailView.as_view(), name='admin-audit-log-detail'),
    path('import/users', AdminImportUsersView.as_view(), name='admin-import-users'),
    path('import/courses', AdminImportCoursesView.as_view(), name='admin-import-courses'),
    path('export/enrollments', AdminExportEnrollmentsView.as_view(), name='admin-export-enrollments'),
    path('export/grades', AdminExportGradesView.as_view(), name='admin-export-grades'),
]
