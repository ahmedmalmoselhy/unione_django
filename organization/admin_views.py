from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.contrib.auth import get_user_model
from organization.models import University, UniversityVicePresident
from accounts.permissions import HasAnyRole

User = get_user_model()


class AdminOnlyPermission(HasAnyRole):
    required_roles = ['admin']


class AdminVicePresidentsView(APIView):
    """List and create university vice presidents."""
    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        """GET /api/admin/universities/{university_id}/vice-presidents"""
        university_id = request.query_params.get('university_id')
        if not university_id:
            return Response(
                {'status': 'error', 'message': 'university_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = UniversityVicePresident.objects.select_related('user', 'university').filter(
            university_id=university_id
        ).order_by('-start_date')

        data = [
            {
                'id': vp.id,
                'title': vp.title,
                'start_date': str(vp.start_date),
                'end_date': str(vp.end_date) if vp.end_date else None,
                'is_active': vp.is_active,
                'university': {
                    'id': vp.university.id,
                    'name': vp.university.name,
                    'code': vp.university.code,
                },
                'user': {
                    'id': vp.user.id,
                    'username': vp.user.username,
                    'email': vp.user.email,
                    'first_name': vp.user.first_name,
                    'last_name': vp.user.last_name,
                },
            }
            for vp in queryset
        ]
        return Response({'status': 'success', 'data': data})

    def post(self, request):
        """POST /api/admin/universities/{university_id}/vice-presidents"""
        payload = request.data if isinstance(request.data, dict) else {}
        university_id = payload.get('university_id')

        if not university_id:
            return Response(
                {'status': 'error', 'message': 'university_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        university = University.objects.filter(id=university_id).first()
        if not university:
            return Response(
                {'status': 'error', 'message': 'University not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Validate required fields
        required = ['user_id', 'title', 'start_date']
        for field in required:
            if not payload.get(field):
                return Response(
                    {'status': 'error', 'message': f'{field} is required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        user = User.objects.filter(id=payload['user_id']).first()
        if not user:
            return Response(
                {'status': 'error', 'message': 'User not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if user is already a VP
        if UniversityVicePresident.objects.filter(user=user, is_active=True).exists():
            return Response(
                {'status': 'error', 'message': 'User is already an active vice president'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        vp = UniversityVicePresident.objects.create(
            university=university,
            user=user,
            title=payload['title'],
            start_date=payload['start_date'],
            end_date=payload.get('end_date'),
            is_active=payload.get('is_active', True),
        )

        return Response(
            {
                'status': 'success',
                'message': 'Vice president created successfully',
                'data': {
                    'id': vp.id,
                    'title': vp.title,
                    'start_date': str(vp.start_date),
                    'user': {'id': user.id, 'username': user.username},
                },
            },
            status=status.HTTP_201_CREATED,
        )


class AdminVicePresidentDetailView(APIView):
    """Get, update, or delete a specific vice president."""
    permission_classes = [AdminOnlyPermission]

    def get(self, request, vp_id):
        """GET /api/admin/vice-presidents/{id}"""
        vp = UniversityVicePresident.objects.select_related('user', 'university').filter(id=vp_id).first()
        if not vp:
            return Response(
                {'status': 'error', 'message': 'Vice president not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({
            'status': 'success',
            'data': {
                'id': vp.id,
                'title': vp.title,
                'start_date': str(vp.start_date),
                'end_date': str(vp.end_date) if vp.end_date else None,
                'is_active': vp.is_active,
                'university': {'id': vp.university.id, 'name': vp.university.name},
                'user': {
                    'id': vp.user.id,
                    'username': vp.user.username,
                    'email': vp.user.email,
                    'first_name': vp.user.first_name,
                    'last_name': vp.user.last_name,
                },
            },
        })

    def patch(self, request, vp_id):
        """PATCH /api/admin/vice-presidents/{id}"""
        vp = UniversityVicePresident.objects.filter(id=vp_id).first()
        if not vp:
            return Response(
                {'status': 'error', 'message': 'Vice president not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        payload = request.data if isinstance(request.data, dict) else {}

        if 'title' in payload:
            vp.title = payload['title']
        if 'start_date' in payload:
            vp.start_date = payload['start_date']
        if 'end_date' in payload:
            vp.end_date = payload['end_date']
        if 'is_active' in payload:
            vp.is_active = payload['is_active']

        vp.save()

        return Response({
            'status': 'success',
            'message': 'Vice president updated successfully',
            'data': {'id': vp.id, 'title': vp.title, 'is_active': vp.is_active},
        })

    def delete(self, request, vp_id):
        """DELETE /api/admin/vice-presidents/{id} - Soft delete (deactivate)"""
        vp = UniversityVicePresident.objects.filter(id=vp_id).first()
        if not vp:
            return Response(
                {'status': 'error', 'message': 'Vice president not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        vp.is_active = False
        vp.save()

        return Response({
            'status': 'success',
            'message': 'Vice president deactivated successfully',
        })
