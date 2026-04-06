from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from academics.models import AcademicTerm, Course, Grade, Section
from accounts.models import Role, UserRole
from enrollment.models import CourseEnrollment, ProfessorProfile, StudentProfile
from organization.models import Department, Faculty, University


class Command(BaseCommand):
    help = 'Seed baseline phase 2 fixtures (organization, academics, and starter enrollment data).'

    def add_arguments(self, parser):
        parser.add_argument('--password', default='Pass1234!@#', help='Password used for created demo users')

    def _ensure_user(self, username, email, first_name, last_name, password):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
            },
        )
        if created:
            user.set_password(password)
            user.save(update_fields=['password'])
        return user, created

    def handle(self, *args, **options):
        password = options['password']

        university, _ = University.objects.get_or_create(
            code='UNI1',
            defaults={
                'name': 'UniOne University',
                'country': 'Egypt',
                'city': 'Cairo',
                'established_year': 2005,
                'email': 'info@unione.local',
                'website': 'https://unione.local',
            },
        )

        faculty, _ = Faculty.objects.get_or_create(
            university=university,
            code='ENG',
            defaults={
                'name': 'Faculty of Engineering',
            },
        )

        business_faculty, _ = Faculty.objects.get_or_create(
            university=university,
            code='BUS',
            defaults={
                'name': 'Faculty of Business',
            },
        )

        department, _ = Department.objects.get_or_create(
            faculty=faculty,
            code='CSE',
            defaults={
                'name': 'Computer Science and Engineering',
                'scope': Department.Scope.DEPARTMENT,
            },
        )

        ai_department, _ = Department.objects.get_or_create(
            faculty=faculty,
            code='AIE',
            defaults={
                'name': 'Artificial Intelligence Engineering',
                'scope': Department.Scope.DEPARTMENT,
            },
        )

        business_department, _ = Department.objects.get_or_create(
            faculty=business_faculty,
            code='MGT',
            defaults={
                'name': 'Management',
                'scope': Department.Scope.DEPARTMENT,
            },
        )

        active_term, _ = AcademicTerm.objects.get_or_create(
            name='Spring 2026',
            defaults={
                'start_date': date(2026, 2, 1),
                'end_date': date(2026, 6, 30),
                'registration_start': date(2026, 1, 1),
                'registration_end': date(2026, 1, 31),
                'is_active': True,
            },
        )

        archived_term, _ = AcademicTerm.objects.get_or_create(
            name='Fall 2025',
            defaults={
                'start_date': date(2025, 9, 1),
                'end_date': date(2026, 1, 15),
                'registration_start': date(2025, 8, 1),
                'registration_end': date(2025, 8, 31),
                'is_active': False,
            },
        )

        summer_term, _ = AcademicTerm.objects.get_or_create(
            name='Summer 2026',
            defaults={
                'start_date': date(2026, 7, 1),
                'end_date': date(2026, 8, 31),
                'registration_start': date(2026, 6, 1),
                'registration_end': date(2026, 6, 20),
                'is_active': False,
            },
        )

        course_intro, _ = Course.objects.get_or_create(
            code='CSE101',
            defaults={
                'name': 'Introduction to Programming',
                'credit_hours': 3,
                'lecture_hours': 2,
                'lab_hours': 2,
                'level': 100,
            },
        )

        course_data, _ = Course.objects.get_or_create(
            code='CSE201',
            defaults={
                'name': 'Data Structures',
                'credit_hours': 3,
                'lecture_hours': 2,
                'lab_hours': 2,
                'level': 200,
            },
        )

        course_db, _ = Course.objects.get_or_create(
            code='CSE305',
            defaults={
                'name': 'Database Systems',
                'credit_hours': 3,
                'lecture_hours': 2,
                'lab_hours': 2,
                'level': 300,
            },
        )

        course_ml, _ = Course.objects.get_or_create(
            code='AIE310',
            defaults={
                'name': 'Machine Learning Fundamentals',
                'credit_hours': 3,
                'lecture_hours': 2,
                'lab_hours': 2,
                'level': 300,
            },
        )

        course_mgmt, _ = Course.objects.get_or_create(
            code='MGT101',
            defaults={
                'name': 'Principles of Management',
                'credit_hours': 2,
                'lecture_hours': 2,
                'lab_hours': 0,
                'level': 100,
            },
        )

        professor_user, professor_user_created = self._ensure_user(
            username='professor1',
            email='professor1@unione.local',
            first_name='Mona',
            last_name='Hassan',
            password=password,
        )

        professor_user_2, professor_user_2_created = self._ensure_user(
            username='professor2',
            email='professor2@unione.local',
            first_name='Karim',
            last_name='Adel',
            password=password,
        )

        student_user, student_user_created = self._ensure_user(
            username='student1',
            email='student1@unione.local',
            first_name='Ali',
            last_name='Youssef',
            password=password,
        )

        student_user_2, student_user_2_created = self._ensure_user(
            username='student2',
            email='student2@unione.local',
            first_name='Sara',
            last_name='Nabil',
            password=password,
        )

        professor_profile, _ = ProfessorProfile.objects.get_or_create(
            user=professor_user,
            defaults={
                'staff_number': 'PROF-0001',
                'department': department,
                'specialization': 'Computer Science',
                'academic_rank': ProfessorProfile.AcademicRank.ASSISTANT,
                'hired_at': date(2021, 9, 1),
            },
        )

        professor_profile_2, _ = ProfessorProfile.objects.get_or_create(
            user=professor_user_2,
            defaults={
                'staff_number': 'PROF-0002',
                'department': ai_department,
                'specialization': 'Machine Learning',
                'academic_rank': ProfessorProfile.AcademicRank.ASSOCIATE,
                'hired_at': date(2019, 9, 1),
            },
        )

        student_profile, _ = StudentProfile.objects.get_or_create(
            user=student_user,
            defaults={
                'student_number': 'STD-0001',
                'faculty': faculty,
                'department': department,
                'academic_year': 2,
                'semester': 1,
                'enrolled_at': date(2024, 9, 1),
            },
        )

        student_profile_2, _ = StudentProfile.objects.get_or_create(
            user=student_user_2,
            defaults={
                'student_number': 'STD-0002',
                'faculty': business_faculty,
                'department': business_department,
                'academic_year': 1,
                'semester': 2,
                'enrolled_at': date(2025, 9, 1),
            },
        )

        section_intro, _ = Section.objects.get_or_create(
            course=course_intro,
            professor=professor_profile,
            academic_term=active_term,
            semester=2,
            defaults={
                'capacity': 35,
                'schedule': {'days': [1, 3], 'start_time': '10:00', 'end_time': '11:30', 'room': 'B201'},
            },
        )

        section_db_active, _ = Section.objects.get_or_create(
            course=course_db,
            professor=professor_profile,
            academic_term=active_term,
            semester=2,
            defaults={
                'capacity': 40,
                'schedule': {'days': [2, 4], 'start_time': '09:00', 'end_time': '10:30', 'room': 'C102'},
            },
        )

        section_data_archived, _ = Section.objects.get_or_create(
            course=course_data,
            professor=professor_profile,
            academic_term=archived_term,
            semester=1,
            defaults={
                'capacity': 30,
                'schedule': {'days': [2, 4], 'start_time': '12:00', 'end_time': '13:30', 'room': 'A110'},
            },
        )

        Section.objects.get_or_create(
            course=course_ml,
            professor=professor_profile_2,
            academic_term=summer_term,
            semester=1,
            defaults={
                'capacity': 20,
                'schedule': {'days': [0, 2], 'start_time': '15:00', 'end_time': '16:30', 'room': 'AI-01'},
            },
        )

        section_mgmt, _ = Section.objects.get_or_create(
            course=course_mgmt,
            professor=professor_profile,
            academic_term=active_term,
            semester=2,
            defaults={
                'capacity': 50,
                'schedule': {'days': [1], 'start_time': '13:00', 'end_time': '15:00', 'room': 'M201'},
            },
        )

        active_enrollment, _ = CourseEnrollment.objects.get_or_create(
            student=student_profile,
            section=section_intro,
            academic_term=active_term,
            defaults={'status': CourseEnrollment.EnrollmentStatus.ACTIVE},
        )

        archived_enrollment, _ = CourseEnrollment.objects.get_or_create(
            student=student_profile,
            section=section_data_archived,
            academic_term=archived_term,
            defaults={'status': CourseEnrollment.EnrollmentStatus.COMPLETED},
        )

        CourseEnrollment.objects.get_or_create(
            student=student_profile,
            section=section_db_active,
            academic_term=active_term,
            defaults={'status': CourseEnrollment.EnrollmentStatus.ACTIVE},
        )

        CourseEnrollment.objects.get_or_create(
            student=student_profile_2,
            section=section_mgmt,
            academic_term=active_term,
            defaults={'status': CourseEnrollment.EnrollmentStatus.ACTIVE},
        )

        Grade.objects.get_or_create(
            enrollment=archived_enrollment,
            defaults={
                'points': 88,
                'letter_grade': 'B+',
                'status': Grade.Status.COMPLETE,
            },
        )

        Grade.objects.get_or_create(
            enrollment=active_enrollment,
            defaults={
                'points': 92,
                'letter_grade': 'A',
                'status': Grade.Status.COMPLETE,
            },
        )

        student_role = Role.objects.filter(slug='student').first()
        professor_role = Role.objects.filter(slug='professor').first()
        if student_role is None:
            student_role = Role.objects.create(name='Student', slug='student', permissions={})
        if professor_role is None:
            professor_role = Role.objects.create(name='Professor', slug='professor', permissions={})

        if student_role:
            UserRole.objects.get_or_create(user=student_user, role=student_role, scope=None, scope_id=None)
            UserRole.objects.get_or_create(user=student_user_2, role=student_role, scope=None, scope_id=None)
        if professor_role:
            UserRole.objects.get_or_create(user=professor_user, role=professor_role, scope=None, scope_id=None)
            UserRole.objects.get_or_create(user=professor_user_2, role=professor_role, scope=None, scope_id=None)

        created_users = []
        if professor_user_created:
            created_users.append('professor1')
        if student_user_created:
            created_users.append('student1')

        if created_users:
            self.stdout.write(self.style.SUCCESS(f'Created demo users: {", ".join(created_users)}'))

        self.stdout.write(self.style.SUCCESS('Phase 2 baseline seed completed'))
