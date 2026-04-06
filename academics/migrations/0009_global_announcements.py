from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0008_student_waitlist_ratings'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Announcement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('body', models.TextField()),
                ('type', models.CharField(default='general', max_length=100)),
                ('visibility', models.CharField(choices=[('university', 'University'), ('faculty', 'Faculty'), ('department', 'Department'), ('section', 'Section')], default='university', max_length=20)),
                ('target_id', models.PositiveIntegerField(blank=True, null=True)),
                ('published_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='announcements', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='GlobalAnnouncementRead',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('read_at', models.DateTimeField(auto_now_add=True)),
                ('announcement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reads', to='academics.announcement')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='global_announcement_reads', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='globalannouncementread',
            constraint=models.UniqueConstraint(fields=('announcement', 'user'), name='uniq_global_announcement_read_user'),
        ),
    ]
