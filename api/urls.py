from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
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
    CustomTokenObtainPairView,
    TradeListCreateView,
    TradeDetailView,
    trade_summary,
    export_trades_csv,
    coin_search,
    CoinListCreateView,
    EmotionTagListCreateView,
    EmotionTagDetailView,
    suggested_tags,
    portfolio_overview,
    refresh_portfolio_prices,
    emotion_journal,
    pnl_analysis,
    monthly_report_list,
    monthly_report_detail,
    api_key_list_or_save,
    api_key_delete,
    api_key_ping,
    ai_feedback_preview,
    ai_feedback_generate,
    ai_feedback_list,
    ai_feedback_delete,
)

urlpatterns = [
    # User Authentication & Profile
    path('user/register/', CreateUserView.as_view(), name='register'),
    path('user/me/', get_current_user, name='get_current_user'),
    path('user/profile/', UserProfileRetrieveUpdateView.as_view(), name='user_profile'),
    path('user/change-password/', change_password, name='change_password'),
    path('user/sessions/', get_active_sessions, name='get_active_sessions'),
    path('user/sessions/<int:session_id>/revoke/', revoke_session, name='revoke_session'),
    path('user/sessions/revoke-all/', revoke_all_sessions, name='revoke_all_sessions'),
    path('user/tokens/', get_refresh_tokens, name='get_refresh_tokens'),
    path('user/tokens/<int:token_id>/revoke/', revoke_token, name='revoke_token'),
    
    # JWT Token
    path('token/', CustomTokenObtainPairView.as_view(), name='get_token'),
    path('token/refresh/', TokenRefreshView.as_view(), name='refresh'),
    
    # Trade Log (must come before trades/<int:pk>/)
    path('trades/summary/', trade_summary, name='trade_summary'),
    path('trades/export/csv/', export_trades_csv, name='export_trades_csv'),
    path('trades/', TradeListCreateView.as_view(), name='trade_list_create'),
    path('trades/<int:pk>/', TradeDetailView.as_view(), name='trade_detail'),
    
    # Coins
    path('coins/search/', coin_search, name='coin_search'),
    path('coins/', CoinListCreateView.as_view(), name='coin_list_create'),
    
    # Emotion Tags CRUD (suggested must come before <int:pk>)
    path('emotion-tags/suggested/', suggested_tags, name='suggested_tags'),
    path('emotion-tags/', EmotionTagListCreateView.as_view(), name='emotion_tag_list_create'),
    path('emotion-tags/<int:pk>/', EmotionTagDetailView.as_view(), name='emotion_tag_detail'),
    
    # Portfolio
    path('portfolio/', portfolio_overview, name='portfolio_overview'),
    path('portfolio/refresh/', refresh_portfolio_prices, name='refresh_portfolio_prices'),
    
    # Emotion Journal
    path('emotion-journal/', emotion_journal, name='emotion_journal'),
    
    # P&L Analysis
    path('pnl-analysis/', pnl_analysis, name='pnl_analysis'),
    
    # Monthly Report
    path('monthly-reports/', monthly_report_list, name='monthly_report_list'),
    path('monthly-reports/<int:year>/<int:month>/', monthly_report_detail, name='monthly_report_detail'),
    
    # API Keys (ping must come before <str:provider> to avoid capturing "ping" as provider)
    path('api-keys/', api_key_list_or_save, name='api_key_list_or_save'),
    path('api-keys/ping/', api_key_ping, name='api_key_ping'),
    path('api-keys/<str:provider>/', api_key_delete, name='api_key_delete'),
    
    # AI Feedback (preview and generate must come before <int:pk>)
    path('ai-feedback/preview/', ai_feedback_preview, name='ai_feedback_preview'),
    path('ai-feedback/generate/', ai_feedback_generate, name='ai_feedback_generate'),
    path('ai-feedback/', ai_feedback_list, name='ai_feedback_list'),
    path('ai-feedback/<int:pk>/', ai_feedback_delete, name='ai_feedback_delete'),
]
