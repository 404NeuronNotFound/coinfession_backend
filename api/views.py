from django.shortcuts import render
from django.contrib.auth.models import User
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from .serializers import UserSerializers, UserProfileSerializer, UserProfileUpdateSerializer
from .models import UserProfile


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

