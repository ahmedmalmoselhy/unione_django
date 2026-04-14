"""WebSocket consumers for real-time features."""
import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from academics.models import Notification

User = get_user_model()


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for real-time notifications.
    
    Groups:
    - user_{user_id}: Personal notifications for specific user
    - role_{role}: Notifications for all users with specific role
    - section_{section_id}: Notifications for users enrolled in section
    """
    
    async def connect(self):
        self.user = self.scope["user"]
        
        if self.user.is_anonymous:
            await self.close()
            return
        
        # Add to user-specific group
        self.user_group_name = f'user_{self.user.id}'
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        
        # Add to role-based groups
        self.role_groups = []
        user_roles = await self.get_user_roles()
        for role in user_roles:
            role_group = f'role_{role}'
            self.role_groups.append(role_group)
            await self.channel_layer.group_add(
                role_group,
                self.channel_name
            )
        
        await self.accept()
        
        # Send welcome message with unread notification count
        unread_count = await self.get_unread_notification_count()
        await self.send_json({
            'type': 'connection_established',
            'user_id': self.user.id,
            'unread_notifications': unread_count,
        })
    
    async def disconnect(self, close_code):
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )
        
        for role_group in getattr(self, 'role_groups', []):
            await self.channel_layer.group_discard(
                role_group,
                self.channel_name
            )
    
    async def receive_json(self, content):
        """Handle incoming WebSocket messages."""
        message_type = content.get('type')
        
        if message_type == 'mark_notifications_read':
            await self.mark_notifications_read()
            await self.send_json({
                'type': 'notifications_marked_read',
            })
        
        elif message_type == 'join_section':
            section_id = content.get('section_id')
            if section_id:
                section_group = f'section_{section_id}'
                await self.channel_layer.group_add(
                    section_group,
                    self.channel_name
                )
    
    # Notification event handlers
    async def notification_message(self, event):
        """Send notification to WebSocket client."""
        await self.send_json({
            'type': 'notification',
            'id': event.get('id'),
            'title': event.get('title'),
            'body': event.get('body'),
            'notification_type': event.get('notification_type'),
            'payload': event.get('payload'),
            'created_at': event.get('created_at'),
        })
    
    async def grade_updated(self, event):
        """Send grade update notification."""
        await self.send_json({
            'type': 'grade_updated',
            'course_code': event.get('course_code'),
            'course_name': event.get('course_name'),
            'grade': event.get('grade'),
        })
    
    async def announcement_posted(self, event):
        """Send announcement notification."""
        await self.send_json({
            'type': 'announcement',
            'id': event.get('id'),
            'title': event.get('title'),
            'body': event.get('body'),
            'scope': event.get('scope'),
        })
    
    async def enrollment_updated(self, event):
        """Send enrollment update notification."""
        await self.send_json({
            'type': 'enrollment_updated',
            'message': event.get('message'),
            'enrollment_id': event.get('enrollment_id'),
        })
    
    @database_sync_to_async
    def get_user_roles(self):
        """Get user's role slugs."""
        return list(self.user.user_roles.values_list('role__slug', flat=True))
    
    @database_sync_to_async
    def get_unread_notification_count(self):
        """Get count of unread notifications."""
        return Notification.objects.filter(
            user=self.user,
            read_at__isnull=True
        ).count()
    
    @database_sync_to_async
    def mark_notifications_read(self):
        """Mark all notifications as read."""
        Notification.objects.filter(
            user=self.user,
            read_at__isnull=True
        ).update(read_at=django.utils.timezone.now())


def send_notification_to_user(user_id, title, body, notification_type='info', payload=None):
    """
    Send notification to specific user via WebSocket.
    
    Usage:
        from enrollment.consumers import send_notification_to_user
        send_notification_to_user(user_id, 'New Grade', 'Your grade has been posted')
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'user_{user_id}',
        {
            'type': 'notification_message',
            'id': None,
            'title': title,
            'body': body,
            'notification_type': notification_type,
            'payload': payload or {},
            'created_at': django.utils.timezone.now().isoformat(),
        }
    )


def send_grade_update_to_user(user_id, course_code, course_name, grade):
    """Send grade update notification to user."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'user_{user_id}',
        {
            'type': 'grade_updated',
            'course_code': course_code,
            'course_name': course_name,
            'grade': grade,
        }
    )


def send_announcement_to_group(group_name, title, body, scope='university'):
    """Send announcement to group (role, section, or all users)."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'announcement_posted',
            'id': None,
            'title': title,
            'body': body,
            'scope': scope,
        }
    )


def send_enrollment_update_to_user(user_id, message, enrollment_id=None):
    """Send enrollment update notification to user."""
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'user_{user_id}',
        {
            'type': 'enrollment_updated',
            'message': message,
            'enrollment_id': enrollment_id,
        }
    )
