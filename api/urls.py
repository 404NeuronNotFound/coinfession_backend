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
    ai_feedback_preview,
    ai_feedback_generate,
    ai_feedback_list,
    ai_feedback_delete,
    dashboard_overview,
    danger_zone_status,
    reset_portfolio_snapshots,
    clear_report_cache,
    delete_ai_feedback_all,
    delete_all_trades,
    delete_account,
    open_positions,
    funding_fee_log_views,
    trading_chat,
    trading_chat_stream,
    trading_chat_status,
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
    path('trades/open-positions/', open_positions, name='open_positions'),
    path('trades/', TradeListCreateView.as_view(), name='trade_list_create'),
    path('trades/<int:trade_pk>/funding-fees/', funding_fee_log_views, name='funding_fee_log_views'),
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
    
    # AI Feedback (preview and generate must come before <int:pk>)
    path('ai-feedback/preview/', ai_feedback_preview, name='ai_feedback_preview'),
    path('ai-feedback/generate/', ai_feedback_generate, name='ai_feedback_generate'),
    path('ai-feedback/', ai_feedback_list, name='ai_feedback_list'),
    path('ai-feedback/<int:pk>/', ai_feedback_delete, name='ai_feedback_delete'),
    
    # Dashboard
    path('dashboard/', dashboard_overview, name='dashboard_overview'),
    
    # Danger Zone
    path('danger-zone/status/', danger_zone_status, name='danger_zone_status'),
    path('danger-zone/reset-snapshots/', reset_portfolio_snapshots, name='reset_portfolio_snapshots'),
    path('danger-zone/clear-reports/', clear_report_cache, name='clear_report_cache'),
    path('danger-zone/delete-ai-feedback/', delete_ai_feedback_all, name='delete_ai_feedback_all'),
    path('danger-zone/delete-trades/', delete_all_trades, name='delete_all_trades'),
    path('danger-zone/delete-account/', delete_account, name='delete_account'),
    
    # Trading Chat (Ollama LLM)
    path('trading-chat/', trading_chat, name='trading_chat'),
    path('trading-chat/stream/', trading_chat_stream, name='trading_chat_stream'),
    path('trading-chat/status/', trading_chat_status, name='trading_chat_status'),
]
