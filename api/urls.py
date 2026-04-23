from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import CreateUserView, get_current_user, UserProfileRetrieveUpdateView, change_password

urlpatterns = [
    path('user/register/', CreateUserView.as_view(), name='register'),
    path('user/me/', get_current_user, name='get_current_user'),
    path('user/profile/', UserProfileRetrieveUpdateView.as_view(), name='user_profile'),
    path('user/change-password/', change_password, name='change_password'),
    path('token/', TokenObtainPairView.as_view(), name='get_token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='refresh'),
]