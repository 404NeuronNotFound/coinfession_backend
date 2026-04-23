from django.shortcuts import render
from django.contrib.auth.models import User
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from .serializers import UserSerializers, UserProfileSerializer, UserProfileUpdateSerializer, ChangePasswordSerializer, UserSessionSerializer, RefreshTokenSerializer
from .models import UserProfile, UserSession, RefreshToken


class CreateUserView(generics.CreateAPIView):
    """
    POST /api/user/register/
    Create a new user account.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializers
    permission_classes = [AllowAny]


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    """
    GET /api/user/me/
    Get the current authenticated user's basic profile.
    """
    serializer = UserSerializers(request.user)
    return Response(serializer.data)


class UserProfileRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """
    GET /api/user/profile/
    Retrieve the authenticated user's full profile with preferences.
    
    PATCH /api/user/profile/
    Update the authenticated user's profile information.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    
    def get_object(self):
        """
        Get or create the UserProfile for the authenticated user.
        Ensures every user has a profile.
        """
        profile, created = UserProfile.objects.get_or_create(user=self.request.user)
        return profile
    
    def get_serializer_class(self):
        """
        Use different serializers for GET vs PATCH/PUT.
        GET returns full profile with read-only fields.
        PATCH/PUT only allows updating specific fields.
        """
        if self.request.method in ['PATCH', 'PUT']:
            return UserProfileUpdateSerializer
        return UserProfileSerializer
    
    def update(self, request, *args, **kwargs):
        """
        Override update to provide better response messages.
        """
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Return full profile after update
        return Response(
            UserProfileSerializer(instance).data,
            status=status.HTTP_200_OK
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    POST /api/user/change-password/
    Change the authenticated user's password.
    
    Request body:
    {
        "current_password": "old_password",
        "new_password": "new_password_123",
        "confirm_password": "new_password_123"
    }
    
    Response:
    {
        "message": "Password changed successfully.",
        "status": "success"
    }
    """
    serializer = ChangePasswordSerializer(
        data=request.data,
        context={'request': request}
    )
    
    if serializer.is_valid():
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        return Response(
            {
                'message': 'Password changed successfully.',
                'status': 'success'
            },
            status=status.HTTP_200_OK
        )
    
    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST
    )



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_active_sessions(request):
    """
    GET /api/user/sessions/
    Get all active sessions for the authenticated user.
    
    Response:
    [
        {
            "id": 1,
            "device_id": "device-123",
            "browser": "Chrome",
            "os": "Windows",
            "ip_address": "192.168.1.1",
            "location": "Davao, PH",
            "created_at": "2024-04-20T10:30:00Z",
            "last_active": "2024-04-23T15:45:00Z",
            "is_current": true
        }
    ]
    """
    sessions = UserSession.objects.filter(user=request.user).order_by('-last_active')
    serializer = UserSessionSerializer(sessions, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def revoke_session(request, session_id):
    """
    POST /api/user/sessions/{session_id}/revoke/
    Revoke a specific session and all its associated tokens.
    
    Response:
    {
        "message": "Session revoked successfully.",
        "status": "success"
    }
    """
    try:
        session = UserSession.objects.get(id=session_id, user=request.user)
    except UserSession.DoesNotExist:
        return Response(
            {'error': 'Session not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Revoke all tokens associated with this session
    from django.utils import timezone
    RefreshToken.objects.filter(session=session).update(revoked_at=timezone.now())
    
    # Delete the session
    session.delete()
    
    return Response(
        {
            'message': 'Session revoked successfully.',
            'status': 'success'
        },
        status=status.HTTP_200_OK
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def revoke_all_sessions(request):
    """
    POST /api/user/sessions/revoke-all/
    Revoke all sessions except the current one.
    
    Response:
    {
        "message": "All other sessions revoked successfully.",
        "status": "success",
        "revoked_count": 2
    }
    """
    from django.utils import timezone
    
    # Get current session from request (you'll need to track this)
    current_device_id = request.data.get('current_device_id')
    
    # Revoke all tokens for all sessions except current
    if current_device_id:
        sessions_to_revoke = UserSession.objects.filter(
            user=request.user
        ).exclude(device_id=current_device_id)
    else:
        sessions_to_revoke = UserSession.objects.filter(user=request.user)
    
    revoked_count = sessions_to_revoke.count()
    
    # Revoke all tokens for these sessions
    RefreshToken.objects.filter(
        session__in=sessions_to_revoke
    ).update(revoked_at=timezone.now())
    
    # Delete the sessions
    sessions_to_revoke.delete()
    
    return Response(
        {
            'message': 'All other sessions revoked successfully.',
            'status': 'success',
            'revoked_count': revoked_count
        },
        status=status.HTTP_200_OK
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_refresh_tokens(request):
    """
    GET /api/user/tokens/
    Get all active refresh tokens for the authenticated user.
    
    Response:
    [
        {
            "id": 1,
            "token_suffix": "xk4T",
            "created_at": "2024-04-20T10:30:00Z",
            "expires_at": "2024-04-27T10:30:00Z",
            "revoked_at": null,
            "last_used": "2024-04-23T15:45:00Z"
        }
    ]
    """
    tokens = RefreshToken.objects.filter(user=request.user).order_by('-created_at')
    serializer = RefreshTokenSerializer(tokens, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def revoke_token(request, token_id):
    """
    POST /api/user/tokens/{token_id}/revoke/
    Revoke a specific refresh token.
    
    Response:
    {
        "message": "Token revoked successfully.",
        "status": "success"
    }
    """
    try:
        token = RefreshToken.objects.get(id=token_id, user=request.user)
    except RefreshToken.DoesNotExist:
        return Response(
            {'error': 'Token not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    from django.utils import timezone
    token.revoked_at = timezone.now()
    token.save()
    
    return Response(
        {
            'message': 'Token revoked successfully.',
            'status': 'success'
        },
        status=status.HTTP_200_OK
    )
