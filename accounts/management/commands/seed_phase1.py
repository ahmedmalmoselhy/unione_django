from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import Role, UserRole


class Command(BaseCommand):
    help = 'Seed Phase 1 baseline roles and optionally create an admin user.'

    def add_arguments(self, parser):
        parser.add_argument('--create-admin', action='store_true', help='Create admin user if it does not exist.')
        parser.add_argument('--admin-username', default='admin', help='Admin username')
        parser.add_argument('--admin-email', default='admin@unione.local', help='Admin email')
        parser.add_argument('--admin-password', default='Admin1234!@#', help='Admin password')

    def handle(self, *args, **options):
        roles = [
            ('Admin', 'admin'),
            ('Faculty Admin', 'faculty_admin'),
            ('Department Admin', 'department_admin'),
            ('Professor', 'professor'),
            ('Student', 'student'),
            ('Employee', 'employee'),
        ]

        for name, slug in roles:
            role, created = Role.objects.get_or_create(slug=slug, defaults={'name': name, 'permissions': {}})
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created role: {slug}'))

        if options['create_admin']:
            User = get_user_model()
            admin_user, created = User.objects.get_or_create(
                username=options['admin_username'],
                defaults={
                    'email': options['admin_email'],
                    'is_staff': True,
                    'is_superuser': True,
                },
            )
            if created:
                admin_user.set_password(options['admin_password'])
                admin_user.save(update_fields=['password'])
                self.stdout.write(self.style.SUCCESS(f'Created admin user: {admin_user.username}'))

            admin_role = Role.objects.get(slug='admin')
            UserRole.objects.get_or_create(user=admin_user, role=admin_role, scope=None, scope_id=None)
            self.stdout.write(self.style.SUCCESS('Linked admin role to admin user'))

        self.stdout.write(self.style.SUCCESS('Phase 1 seed completed'))
