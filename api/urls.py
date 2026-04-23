from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import (
    CreateUserView, 
    get_current_user, 
    UserProfileRetrieveUpdateView, 
    change_password,
    get_active_sessions,
    revoke_session,
    revoke_all_sessions,
    get_refresh_tokens,
    revoke_token,
)

urlpatterns = [
    path('user/register/', CreateUserView.as_view(), name='register'),
    path('user/me/', get_current_user, name='get_current_user'),
    path('user/profile/', UserProfileRetrieveUpdateView.as_view(), name='user_profile'),
    path('user/change-password/', change_password, name='change_password'),
    path('user/sessions/', get_active_sessions, name='get_active_sessions'),
    path('user/sessions/<int:session_id>/revoke/', revoke_session, name='revoke_session'),
    path('user/sessions/revoke-all/', revoke_all_sessions, name='revoke_all_sessions'),
    path('user/tokens/', get_refresh_tokens, name='get_refresh_tokens'),
    path('user/tokens/<int:token_id>/revoke/', revoke_token, name='revoke_token'),
    path('token/', TokenObtainPairView.as_view(), name='get_token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='refresh'),
]