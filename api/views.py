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


# ─── Custom Token Views ────────────────────────────────────
from rest_framework_simplejwt.views import TokenObtainPairView as JWTTokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
import hashlib
from django.utils import timezone
from datetime import timedelta


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom serializer that creates a session and token record on login.
    """
    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Get user from validated credentials
        user = self.user
        
        # Extract device info from request headers
        request = self.context.get('request')
        user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')
        ip_address = self.get_client_ip(request)
        
        # Parse user agent for browser and OS (simplified)
        browser = self.parse_browser(user_agent)
        os = self.parse_os(user_agent)
        
        # Generate unique device_id for this login session
        import uuid
        device_id = hashlib.sha256(f"{ip_address}{user_agent}{uuid.uuid4()}".encode()).hexdigest()[:32]
        
        # Always create a new session on login
        session = UserSession.objects.create(
            user=user,
            device_id=device_id,
            browser=browser,
            os=os,
            ip_address=ip_address,
            location='Unknown',  # Could use IP geolocation service
            is_current=True,
        )
        
        # Mark other sessions as not current
        UserSession.objects.filter(user=user).exclude(id=session.id).update(is_current=False)
        session.is_current = True
        session.save()
        
        # Create refresh token record
        refresh_token = data.get('refresh')
        if refresh_token:
            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            token_suffix = refresh_token[-10:]
            
            RefreshToken.objects.create(
                user=user,
                session=session,
                token_hash=token_hash,
                token_suffix=token_suffix,
                expires_at=timezone.now() + timedelta(days=7),  # Match your JWT settings
            )
        
        return data
    
    @staticmethod
    def get_client_ip(request):
        """Get client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @staticmethod
    def parse_browser(user_agent):
        """Extract browser from user agent"""
        if 'Chrome' in user_agent:
            return 'Chrome'
        elif 'Safari' in user_agent:
            return 'Safari'
        elif 'Firefox' in user_agent:
            return 'Firefox'
        elif 'Edge' in user_agent:
            return 'Edge'
        else:
            return 'Unknown'
    
    @staticmethod
    def parse_os(user_agent):
        """Extract OS from user agent"""
        if 'Windows' in user_agent:
            return 'Windows'
        elif 'Mac' in user_agent:
            return 'macOS'
        elif 'Linux' in user_agent:
            return 'Linux'
        elif 'iPhone' in user_agent or 'iPad' in user_agent:
            return 'iOS'
        elif 'Android' in user_agent:
            return 'Android'
        else:
            return 'Unknown'


class CustomTokenObtainPairView(JWTTokenObtainPairView):
    """
    Custom token view that creates session and token records.
    """
    serializer_class = CustomTokenObtainPairSerializer


# ─── Trade Log Views ──────────────────────────────────────
from rest_framework.pagination import PageNumberPagination
from rest_framework.filters import SearchFilter, OrderingFilter
from .serializers import (
    TradeSerializer, TradeSummarySerializer, CoinSerializer,
    EmotionTagSerializer
)
from .models import Trade, Coin, EmotionTag, TradeEmotion
from django.db.models import Q, F, Sum, Count, Case, When, FloatField
from django.http import StreamingHttpResponse
import csv
import requests


class TradePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class TradeListCreateView(generics.ListCreateAPIView):
    """
    GET /api/trades/
    List all trades for the authenticated user with filtering and pagination.
    
    Query Parameters:
    - coin: Filter by coin symbol or name (icontains)
    - type: Filter by trade type ('buy' or 'sell')
    - emotion: Filter by emotion tag ID
    - pnl: Filter by 'profit' or 'loss'
    - date_from: Filter trades from this date (YYYY-MM-DD)
    - date_to: Filter trades until this date (YYYY-MM-DD)
    - search: Search in notes field (icontains)
    - sort: Sort by 'date', '-date', 'coin', '-coin', 'qty', '-qty', 'fee', '-fee'
    - page_size: Number of results per page (default 10, max 100)
    
    POST /api/trades/
    Create a new trade.
    """
    serializer_class = TradeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = TradePagination
    
    def get_queryset(self):
        queryset = Trade.objects.filter(user=self.request.user).select_related('coin').prefetch_related('emotions__emotion_tag')
        
        # Filter by coin
        coin_filter = self.request.query_params.get('coin')
        if coin_filter:
            queryset = queryset.filter(
                Q(coin__symbol__icontains=coin_filter) |
                Q(coin__name__icontains=coin_filter)
            )
        
        # Filter by trade type
        trade_type = self.request.query_params.get('type')
        if trade_type:
            queryset = queryset.filter(trade_type=trade_type.lower())
        
        # Filter by emotion tag
        emotion_id = self.request.query_params.get('emotion')
        if emotion_id:
            queryset = queryset.filter(emotions__emotion_tag_id=emotion_id).distinct()
        
        # Filter by date range
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(trade_date__date__gte=date_from)
        
        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(trade_date__date__lte=date_to)
        
        # Search in notes
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(notes__icontains=search)
        
        # Sorting
        sort = self.request.query_params.get('sort', '-date')
        if sort == 'date':
            queryset = queryset.order_by('trade_date')
        elif sort == '-date':
            queryset = queryset.order_by('-trade_date')
        elif sort == 'coin':
            queryset = queryset.order_by('coin__symbol')
        elif sort == '-coin':
            queryset = queryset.order_by('-coin__symbol')
        elif sort == 'qty':
            queryset = queryset.order_by('quantity')
        elif sort == '-qty':
            queryset = queryset.order_by('-quantity')
        elif sort == 'fee':
            queryset = queryset.order_by('fee')
        elif sort == '-fee':
            queryset = queryset.order_by('-fee')
        else:
            queryset = queryset.order_by('-trade_date')
        
        # Filter by P&L (profit/loss) - done in Python after evaluation
        pnl_filter = self.request.query_params.get('pnl')
        if pnl_filter:
            trades_list = []
            for trade in queryset:
                if trade.sell_price and trade.buy_price:
                    realized_pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
                    if pnl_filter == 'profit' and realized_pnl > 0:
                        trades_list.append(trade.id)
                    elif pnl_filter == 'loss' and realized_pnl < 0:
                        trades_list.append(trade.id)
            queryset = queryset.filter(id__in=trades_list)
        
        return queryset
    
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TradeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/trades/{id}/
    Retrieve a specific trade.
    
    PATCH /api/trades/{id}/
    Update a specific trade.
    
    DELETE /api/trades/{id}/
    Delete a specific trade.
    """
    serializer_class = TradeSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return Trade.objects.filter(user=self.request.user).select_related('coin').prefetch_related('emotions__emotion_tag')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def trade_summary(request):
    """
    GET /api/trades/summary/
    Get summary statistics for trades with optional filtering.
    
    Query Parameters (same as TradeListCreateView):
    - coin, type, emotion, date_from, date_to, search
    
    Response:
    {
        "total_trades": 45,
        "closed_trades": 38,
        "open_trades": 7,
        "winning_trades": 22,
        "win_rate": 57.89,
        "total_realized_pnl": 1250.50,
        "total_fees": 125.00
    }
    """
    queryset = Trade.objects.filter(user=request.user).select_related('coin')
    
    # Apply same filters as TradeListCreateView
    coin_filter = request.query_params.get('coin')
    if coin_filter:
        queryset = queryset.filter(
            Q(coin__symbol__icontains=coin_filter) |
            Q(coin__name__icontains=coin_filter)
        )
    
    trade_type = request.query_params.get('type')
    if trade_type:
        queryset = queryset.filter(trade_type=trade_type.lower())
    
    emotion_id = request.query_params.get('emotion')
    if emotion_id:
        queryset = queryset.filter(emotions__emotion_tag_id=emotion_id).distinct()
    
    date_from = request.query_params.get('date_from')
    if date_from:
        queryset = queryset.filter(trade_date__date__gte=date_from)
    
    date_to = request.query_params.get('date_to')
    if date_to:
        queryset = queryset.filter(trade_date__date__lte=date_to)
    
    search = request.query_params.get('search')
    if search:
        queryset = queryset.filter(notes__icontains=search)
    
    # Calculate statistics
    total_trades = queryset.count()
    closed_trades = queryset.filter(sell_price__isnull=False, buy_price__isnull=False).count()
    open_trades = queryset.filter(sell_price__isnull=True).count()
    
    # Calculate winning trades, total realized P&L, and hold times
    winning_trades = 0
    total_realized_pnl = 0.0
    total_fees = 0.0
    
    # For hold time calculation - simpler approach
    # For SELL trades with both buy_price and sell_price, calculate hold time from trade_date
    # This assumes each SELL trade represents a closed position
    from datetime import datetime
    from django.utils import timezone
    
    hold_times = []  # in days
    now = timezone.now()
    
    # For closed trades (SELL with both prices), we can't determine exact hold time
    # without tracking individual positions, so we'll calculate from open BUY trades
    for trade in queryset.filter(trade_type='buy'):
        # Calculate how long this BUY trade has been open
        hold_days = (now - trade.trade_date).days
        hold_times.append(hold_days)
    
    # Calculate average hold time
    avg_hold_time = sum(hold_times) / len(hold_times) if hold_times else 0.0
    
    # Calculate P&L and winning trades
    for trade in queryset:
        total_fees += trade.fee
        if trade.sell_price and trade.buy_price:
            realized_pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
            total_realized_pnl += realized_pnl
            if realized_pnl > 0:
                winning_trades += 1
    
    win_rate = (winning_trades / closed_trades * 100) if closed_trades > 0 else 0.0
    
    data = {
        'total_trades': total_trades,
        'closed_trades': closed_trades,
        'open_trades': open_trades,
        'winning_trades': winning_trades,
        'win_rate': round(win_rate, 2),
        'total_realized_pnl': round(total_realized_pnl, 2),
        'total_fees': round(total_fees, 2),
        'avg_hold_time_days': round(avg_hold_time, 1),
    }
    
    serializer = TradeSummarySerializer(data)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def coin_search(request):
    """
    GET /api/coins/search/?q=bitcoin
    Search for coins by symbol or name.
    
    First searches local database, then CoinGecko API if no results.
    
    Response:
    [
        {
            "id": 1,
            "coingecko_id": "bitcoin",
            "symbol": "BTC",
            "name": "Bitcoin"
        }
    ]
    """
    query = request.query_params.get('q')
    if not query:
        return Response(
            {'error': 'Query parameter "q" is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Search local database first
    local_coins = Coin.objects.filter(
        Q(symbol__icontains=query) |
        Q(name__icontains=query)
    )[:10]
    
    if local_coins.exists():
        serializer = CoinSerializer(local_coins, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    # Search CoinGecko API
    try:
        from django.conf import settings
        api_key = getattr(settings, 'COINGECKO_API_KEY', '')
        
        headers = {}
        if api_key:
            headers['x-cg-demo-api-key'] = api_key
        
        response = requests.get(
            'https://api.coingecko.com/api/v3/search',
            params={'query': query},
            headers=headers,
            timeout=5
        )
        response.raise_for_status()
        
        data = response.json()
        coins = data.get('coins', [])[:10]
        
        result = [
            {
                'id': None,
                'coingecko_id': coin.get('id'),
                'symbol': coin.get('symbol', '').upper(),
                'name': coin.get('name', '')
            }
            for coin in coins
        ]
        
        return Response(result, status=status.HTTP_200_OK)
    
    except requests.RequestException:
        return Response(
            {'error': 'Failed to search CoinGecko API'},
            status=status.HTTP_502_BAD_GATEWAY
        )


class CoinListCreateView(generics.ListCreateAPIView):
    """
    GET /api/coins/
    List all coins.
    
    POST /api/coins/
    Create a new coin (or return existing if coingecko_id already exists).
    """
    serializer_class = CoinSerializer
    permission_classes = [IsAuthenticated]
    queryset = Coin.objects.all().order_by('symbol')
    
    def create(self, request, *args, **kwargs):
        """
        Create a new coin or return existing one if coingecko_id already exists.
        """
        coingecko_id = request.data.get('coingecko_id')
        
        if not coingecko_id:
            return Response(
                {'error': 'coingecko_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if coin already exists
        existing_coin = Coin.objects.filter(coingecko_id=coingecko_id).first()
        if existing_coin:
            serializer = self.get_serializer(existing_coin)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        # Create new coin
        return super().create(request, *args, **kwargs)


class EmotionTagListView(generics.ListAPIView):
    """
    GET /api/emotion-tags/
    List all emotion tags for the current user.
    """
    serializer_class = EmotionTagSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return EmotionTag.objects.filter(user=self.request.user).order_by('name')



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_trades_csv(request):
    """
    GET /api/trades/export/csv/
    Export all trades as CSV file.
    
    Columns: Date, Coin, Symbol, Type, Quantity, Buy Price, Sell Price, Fee, Realized P&L, Emotions, Notes
    """
    trades = Trade.objects.filter(user=request.user).select_related('coin').prefetch_related('emotions__emotion_tag')
    
    # Create CSV response using HttpResponse (not StreamingHttpResponse)
    # because @api_view doesn't work well with StreamingHttpResponse
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="trades.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Coin', 'Symbol', 'Type', 'Quantity', 'Buy Price', 'Sell Price', 'Fee', 'Realized P&L', 'Emotions', 'Notes'])
    
    for trade in trades:
        emotions = ', '.join([et.emotion_tag.name for et in trade.emotions.all()])
        realized_pnl = None
        if trade.sell_price and trade.buy_price:
            realized_pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
        
        writer.writerow([
            trade.trade_date.strftime('%Y-%m-%d %H:%M:%S'),
            trade.coin.name,
            trade.coin.symbol,
            trade.trade_type.upper(),
            trade.quantity,
            trade.buy_price or '',
            trade.sell_price or '',
            trade.fee,
            realized_pnl or '',
            emotions,
            trade.notes or ''
        ])
    
    return response


# ─── Emotion Tags CRUD Views ──────────────────────────────────────
from .serializers import EmotionTagWriteSerializer


class EmotionTagListCreateView(generics.ListCreateAPIView):
    """
    GET /api/emotion-tags/
    List all emotion tags for the current user with statistics.
    
    POST /api/emotion-tags/
    Create a new emotion tag for the current user.
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return EmotionTag.objects.filter(user=self.request.user).order_by('name')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return EmotionTagWriteSerializer
        return EmotionTagSerializer
    
    def create(self, request, *args, **kwargs):
        """Create emotion tag for current user and return with stats"""
        serializer = EmotionTagWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        emotion_tag = serializer.save(user=request.user)
        
        # Return with stats using EmotionTagSerializer
        output_serializer = EmotionTagSerializer(emotion_tag)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class EmotionTagDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/emotion-tags/<id>/
    Retrieve a single emotion tag with statistics.
    
    PATCH /api/emotion-tags/<id>/
    Update an emotion tag.
    
    DELETE /api/emotion-tags/<id>/
    Delete an emotion tag (CASCADE deletes TradeEmotion records).
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return EmotionTag.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        if self.request.method in ['PATCH', 'PUT']:
            return EmotionTagWriteSerializer
        return EmotionTagSerializer
    
    def update(self, request, *args, **kwargs):
        """Update emotion tag and return with stats"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = EmotionTagWriteSerializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        emotion_tag = serializer.save()
        
        # Return with stats using EmotionTagSerializer
        output_serializer = EmotionTagSerializer(emotion_tag)
        return Response(output_serializer.data, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def suggested_tags(request):
    """
    GET /api/emotion-tags/suggested/
    Return hardcoded list of suggested emotion tags that don't already exist for the current user.
    """
    # Hardcoded suggestions
    suggestions = [
        {'name': 'Revenge trading', 'color': '#D85A30'},
        {'name': 'Greedy', 'color': '#EF9F27'},
        {'name': 'Fear of loss', 'color': '#E24B4A'},
        {'name': 'Confident', 'color': '#1D9E75'},
        {'name': 'Bored', 'color': '#888780'},
        {'name': 'Excited', 'color': '#7F77DD'},
        {'name': 'Calm', 'color': '#378ADD'},
        {'name': 'Rushed', 'color': '#D4537E'},
        {'name': 'Uncertain', 'color': '#A78BFA'},
        {'name': 'Euphoric', 'color': '#F472B6'},
    ]
    
    # Get existing tag names for current user (case-insensitive)
    existing_names = set(
        EmotionTag.objects.filter(user=request.user).values_list('name', flat=True)
    )
    existing_names_lower = {name.lower() for name in existing_names}
    
    # Filter out suggestions that already exist
    filtered_suggestions = [
        suggestion for suggestion in suggestions
        if suggestion['name'].lower() not in existing_names_lower
    ]
    
    return Response(filtered_suggestions, status=status.HTTP_200_OK)


# ─── Portfolio Views ──────────────────────────────────────
from .serializers import CoinHoldingSerializer, PortfolioSummarySerializer, PortfolioResponseSerializer
from .models import PortfolioSnapshot
from datetime import datetime
from django.http import HttpResponse


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def portfolio_overview(request):
    """
    GET /api/portfolio/
    Calculate and return the user's current portfolio with live prices.
    """
    user = request.user
    
    # Step 1: Calculate holdings from Trade table
    # IMPORTANT: BUY trades represent open positions (coins you hold)
    # SELL trades represent closed positions (realized P&L)
    # Portfolio should only show open BUY positions
    trades = Trade.objects.filter(user=user, trade_type='buy').select_related('coin')
    
    holdings_dict = {}
    for trade in trades:
        coin_id = trade.coin.id
        if coin_id not in holdings_dict:
            holdings_dict[coin_id] = {
                'coin': trade.coin,
                'total_quantity': 0.0,
                'total_cost': 0.0,
            }
        
        holdings_dict[coin_id]['total_quantity'] += trade.quantity
        if trade.buy_price:
            holdings_dict[coin_id]['total_cost'] += trade.quantity * trade.buy_price
    
    # Calculate holdings (only positive quantities)
    holdings = []
    for coin_id, data in holdings_dict.items():
        total_quantity = data['total_quantity']
        
        # Use epsilon comparison for floats
        if total_quantity > 0.000001:
            avg_buy_price = data['total_cost'] / total_quantity if total_quantity > 0 else 0.0
            cost_basis = data['total_cost']
            
            holdings.append({
                'coin': data['coin'],
                'total_quantity': total_quantity,
                'avg_buy_price': avg_buy_price,
                'cost_basis': cost_basis,
            })
    
    # Step 2: Fetch live prices from CoinGecko
    prices_live = True
    warning = None
    
    if holdings:
        coingecko_ids = [h['coin'].coingecko_id for h in holdings]
        ids_param = ','.join(coingecko_ids)
        
        try:
            from django.conf import settings
            api_key = getattr(settings, 'COINGECKO_API_KEY', '')
            
            headers = {}
            if api_key:
                headers['x-cg-demo-api-key'] = api_key
            
            response = requests.get(
                'https://api.coingecko.com/api/v3/simple/price',
                params={
                    'ids': ids_param,
                    'vs_currencies': 'usd',
                    'include_24hr_change': 'true'
                },
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            price_data = response.json()
            
            # Step 3: Enrich holdings with live data
            for holding in holdings:
                coingecko_id = holding['coin'].coingecko_id
                coin_price_data = price_data.get(coingecko_id, {})
                
                holding['live_price'] = coin_price_data.get('usd', 0.0)
                holding['change_24h'] = coin_price_data.get('usd_24h_change', 0.0)
                holding['current_value'] = holding['live_price'] * holding['total_quantity']
                holding['unrealized_pnl'] = holding['current_value'] - holding['cost_basis']
                holding['unrealized_pnl_pct'] = (holding['unrealized_pnl'] / holding['cost_basis'] * 100) if holding['cost_basis'] > 0 else 0.0
        
        except requests.RequestException as e:
            prices_live = False
            warning = "Could not fetch live prices from CoinGecko. Showing last known values."
            
            # Set default values
            for holding in holdings:
                holding['live_price'] = 0.0
                holding['change_24h'] = 0.0
                holding['current_value'] = 0.0
                holding['unrealized_pnl'] = 0.0
                holding['unrealized_pnl_pct'] = 0.0
    
    # Step 4: Calculate portfolio-level summary
    total_value = sum(h['current_value'] for h in holdings)
    total_cost = sum(h['cost_basis'] for h in holdings)
    total_unrealized_pnl = total_value - total_cost
    total_unrealized_pct = (total_unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0
    active_positions = len(holdings)
    last_updated = datetime.now().isoformat()
    
    # Step 5: Calculate allocation_pct per holding
    for holding in holdings:
        holding['allocation_pct'] = (holding['current_value'] / total_value * 100) if total_value > 0 else 0.0
    
    # Step 6: Save fresh PortfolioSnapshot for each holding
    if prices_live:
        try:
            from django.utils import timezone
            now = timezone.now()
            
            for holding in holdings:
                PortfolioSnapshot.objects.update_or_create(
                    user=user,
                    coin=holding['coin'],
                    defaults={
                        'total_quantity': holding['total_quantity'],
                        'avg_buy_price': holding['avg_buy_price'],
                        'unrealized_pnl': holding['unrealized_pnl'],
                        'snapshot_date': now,
                    }
                )
        except Exception as e:
            # Snapshot save failure must not prevent response
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to save portfolio snapshot: {e}")
    
    # Step 7: Sort holdings by current_value descending and format response
    holdings.sort(key=lambda x: x['current_value'], reverse=True)
    
    holdings_data = []
    for h in holdings:
        holdings_data.append({
            'coin_id': h['coin'].id,
            'symbol': h['coin'].symbol,
            'name': h['coin'].name,
            'coingecko_id': h['coin'].coingecko_id,
            'total_quantity': round(h['total_quantity'], 8),
            'avg_buy_price': round(h['avg_buy_price'], 2),
            'cost_basis': round(h['cost_basis'], 2),
            'live_price': round(h['live_price'], 2),
            'change_24h': round(h['change_24h'], 2),
            'current_value': round(h['current_value'], 2),
            'unrealized_pnl': round(h['unrealized_pnl'], 2),
            'unrealized_pnl_pct': round(h['unrealized_pnl_pct'], 2),
            'allocation_pct': round(h['allocation_pct'], 2),
        })
    
    summary_data = {
        'total_value': round(total_value, 2),
        'total_cost': round(total_cost, 2),
        'total_unrealized_pnl': round(total_unrealized_pnl, 2),
        'total_unrealized_pct': round(total_unrealized_pct, 2),
        'active_positions': active_positions,
        'last_updated': last_updated,
    }
    
    response_data = {
        'summary': summary_data,
        'holdings': holdings_data,
        'prices_live': prices_live,
        'warning': warning,
    }
    
    serializer = PortfolioResponseSerializer(response_data)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def refresh_portfolio_prices(request):
    """
    POST /api/portfolio/refresh/
    Refresh portfolio prices using existing snapshots (faster than full recalculation).
    """
    user = request.user
    
    # Step 1: Load existing snapshots
    snapshots = PortfolioSnapshot.objects.filter(user=user).select_related('coin')
    
    if not snapshots.exists():
        # No snapshots, fall back to full calculation
        return portfolio_overview(request)
    
    holdings = []
    for snapshot in snapshots:
        if snapshot.total_quantity > 0.000001:
            cost_basis = snapshot.avg_buy_price * snapshot.total_quantity
            holdings.append({
                'coin': snapshot.coin,
                'total_quantity': snapshot.total_quantity,
                'avg_buy_price': snapshot.avg_buy_price,
                'cost_basis': cost_basis,
            })
    
    # Step 2: Fetch live prices from CoinGecko
    prices_live = True
    warning = None
    
    if holdings:
        coingecko_ids = [h['coin'].coingecko_id for h in holdings]
        ids_param = ','.join(coingecko_ids)
        
        try:
            from django.conf import settings
            api_key = getattr(settings, 'COINGECKO_API_KEY', '')
            
            headers = {}
            if api_key:
                headers['x-cg-demo-api-key'] = api_key
            
            response = requests.get(
                'https://api.coingecko.com/api/v3/simple/price',
                params={
                    'ids': ids_param,
                    'vs_currencies': 'usd',
                    'include_24hr_change': 'true'
                },
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            
            price_data = response.json()
            
            # Step 3: Enrich holdings with live data
            for holding in holdings:
                coingecko_id = holding['coin'].coingecko_id
                coin_price_data = price_data.get(coingecko_id, {})
                
                holding['live_price'] = coin_price_data.get('usd', 0.0)
                holding['change_24h'] = coin_price_data.get('usd_24h_change', 0.0)
                holding['current_value'] = holding['live_price'] * holding['total_quantity']
                holding['unrealized_pnl'] = holding['current_value'] - holding['cost_basis']
                holding['unrealized_pnl_pct'] = (holding['unrealized_pnl'] / holding['cost_basis'] * 100) if holding['cost_basis'] > 0 else 0.0
        
        except requests.RequestException as e:
            prices_live = False
            warning = "Could not fetch live prices from CoinGecko. Showing last known values."
            
            # Set default values
            for holding in holdings:
                holding['live_price'] = 0.0
                holding['change_24h'] = 0.0
                holding['current_value'] = 0.0
                holding['unrealized_pnl'] = 0.0
                holding['unrealized_pnl_pct'] = 0.0
    
    # Calculate portfolio-level summary
    total_value = sum(h['current_value'] for h in holdings)
    total_cost = sum(h['cost_basis'] for h in holdings)
    total_unrealized_pnl = total_value - total_cost
    total_unrealized_pct = (total_unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0
    active_positions = len(holdings)
    last_updated = datetime.now().isoformat()
    
    # Calculate allocation_pct per holding
    for holding in holdings:
        holding['allocation_pct'] = (holding['current_value'] / total_value * 100) if total_value > 0 else 0.0
    
    # Sort holdings by current_value descending and format response
    holdings.sort(key=lambda x: x['current_value'], reverse=True)
    
    holdings_data = []
    for h in holdings:
        holdings_data.append({
            'coin_id': h['coin'].id,
            'symbol': h['coin'].symbol,
            'name': h['coin'].name,
            'coingecko_id': h['coin'].coingecko_id,
            'total_quantity': round(h['total_quantity'], 8),
            'avg_buy_price': round(h['avg_buy_price'], 2),
            'cost_basis': round(h['cost_basis'], 2),
            'live_price': round(h['live_price'], 2),
            'change_24h': round(h['change_24h'], 2),
            'current_value': round(h['current_value'], 2),
            'unrealized_pnl': round(h['unrealized_pnl'], 2),
            'unrealized_pnl_pct': round(h['unrealized_pnl_pct'], 2),
            'allocation_pct': round(h['allocation_pct'], 2),
        })
    
    summary_data = {
        'total_value': round(total_value, 2),
        'total_cost': round(total_cost, 2),
        'total_unrealized_pnl': round(total_unrealized_pnl, 2),
        'total_unrealized_pct': round(total_unrealized_pct, 2),
        'active_positions': active_positions,
        'last_updated': last_updated,
    }
    
    response_data = {
        'summary': summary_data,
        'holdings': holdings_data,
        'prices_live': prices_live,
        'warning': warning,
    }
    
    serializer = PortfolioResponseSerializer(response_data)
    return Response(serializer.data, status=status.HTTP_200_OK)


# ─── Emotion Journal View ──────────────────────────────────────
from datetime import timedelta
from .serializers import (
    EmotionStatSerializer, EmotionTradeSerializer, PatternInsightSerializer,
    HeatmapDaySerializer, EmotionJournalSerializer
)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def emotion_journal(request):
    """
    GET /api/emotion-journal/
    Get emotion journal with stats, timeline, insights, and heatmap.
    
    Query Parameters:
    - emotion_id: Filter timeline by emotion tag ID (optional)
    - weeks: Heatmap lookback period in weeks (default 12, max 52)
    """
    user = request.user
    
    # Parse query parameters
    emotion_id_filter = request.query_params.get('emotion_id')
    weeks = int(request.query_params.get('weeks', 12))
    weeks = min(weeks, 52)  # Cap at 52 weeks
    
    # ─── Step 1: Load all trades ───
    trades = Trade.objects.filter(user=user).select_related('coin').prefetch_related(
        'emotions__emotion_tag'
    ).order_by('-trade_date')
    
    # ─── Step 2: Build emotion_stats ───
    # Get all emotion tags that have at least one trade for this user
    emotion_tag_ids = TradeEmotion.objects.filter(
        trade__user=user
    ).values_list('emotion_tag_id', flat=True).distinct()
    
    emotion_stats_list = []
    
    for emotion_tag_id in emotion_tag_ids:
        emotion_tag = EmotionTag.objects.get(id=emotion_tag_id)
        
        # Get all TradeEmotion records for this emotion
        trade_emotions = TradeEmotion.objects.filter(
            emotion_tag_id=emotion_tag_id,
            trade__user=user
        ).select_related('trade')
        
        # Calculate stats
        trade_count = trade_emotions.count()
        
        closed_pnls = []
        closed_count = 0
        
        for te in trade_emotions:
            trade = te.trade
            if trade.sell_price is not None and trade.buy_price is not None:
                realized_pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
                closed_pnls.append(realized_pnl)
                closed_count += 1
        
        # Calculate win_rate
        if closed_count > 0:
            winning_count = sum(1 for pnl in closed_pnls if pnl > 0)
            win_rate = (winning_count / closed_count) * 100
        else:
            win_rate = 0.0
        
        # Calculate avg_pnl and total_pnl
        if closed_pnls:
            avg_pnl = sum(closed_pnls) / len(closed_pnls)
            total_pnl = sum(closed_pnls)
        else:
            avg_pnl = 0.0
            total_pnl = 0.0
        
        emotion_stats_list.append({
            'id': emotion_tag.id,
            'name': emotion_tag.name,
            'color': emotion_tag.color,
            'trade_count': trade_count,
            'closed_count': closed_count,
            'win_rate': round(win_rate, 1),
            'avg_pnl': round(avg_pnl, 2),
            'total_pnl': round(total_pnl, 2),
        })
    
    # Sort by trade_count descending
    emotion_stats_list.sort(key=lambda x: x['trade_count'], reverse=True)
    
    # ─── Step 3: Build trades timeline ───
    import pytz
    user_timezone = pytz.timezone('Asia/Manila')  # Philippines timezone
    
    if emotion_id_filter:
        # Filter to trades with this emotion
        trades_timeline = []
        for trade in trades:
            has_emotion = any(
                te.emotion_tag_id == int(emotion_id_filter)
                for te in trade.emotions.all()
            )
            if has_emotion:
                trades_timeline.append(trade)
    else:
        trades_timeline = list(trades)
    
    trades_data = []
    for trade in trades_timeline:
        # Get first emotion tag (primary)
        emotion_tag = None
        emotion_name = "Untagged"
        emotion_color = "#888888"
        emotion_id = None
        
        if trade.emotions.exists():
            emotion_tag = trade.emotions.first().emotion_tag
            emotion_name = emotion_tag.name
            emotion_color = emotion_tag.color
            emotion_id = emotion_tag.id
        
        # Calculate realized_pnl
        realized_pnl = None
        if trade.sell_price is not None and trade.buy_price is not None:
            realized_pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
        
        # Format date in user's timezone (cross-platform: remove leading zero from day)
        from datetime import datetime
        if isinstance(trade.trade_date, datetime):
            if trade.trade_date.tzinfo is not None:
                local_dt = trade.trade_date.astimezone(user_timezone)
            else:
                utc_dt = pytz.UTC.localize(trade.trade_date)
                local_dt = utc_dt.astimezone(user_timezone)
            date_str = local_dt.strftime("%b %d").lstrip("0")
        else:
            date_str = str(trade.trade_date)
        
        trades_data.append({
            'id': trade.id,
            'date': date_str,
            'trade_date': trade.trade_date.isoformat(),
            'trade_type': trade.trade_type,
            'coin_symbol': trade.coin.symbol,
            'coin_name': trade.coin.name,
            'emotion_name': emotion_name,
            'emotion_color': emotion_color,
            'emotion_id': emotion_id,
            'realized_pnl': round(realized_pnl, 2) if realized_pnl is not None else None,
            'is_open': trade.sell_price is None,
            'notes': trade.notes or "",
        })
    
    # ─── Step 4: Build pattern insights ───
    insights_data = []
    
    if emotion_stats_list:
        # GOOD insight — best performing emotion
        good_candidates = [
            e for e in emotion_stats_list
            if e['avg_pnl'] > 0 and e['trade_count'] >= 3
        ]
        if good_candidates:
            best = max(good_candidates, key=lambda x: x['win_rate'])
            insights_data.append({
                'type': 'good',
                'title': f"{best['name']} trades are your best trades",
                'body': f"{best['win_rate']}% win rate with an average of +${best['avg_pnl']} per trade. Keep doing this.",
            })
        
        # BAD insight — worst performing emotion
        bad_candidates = [
            e for e in emotion_stats_list
            if e['avg_pnl'] < 0 and e['trade_count'] >= 2
        ]
        if bad_candidates:
            worst = min(bad_candidates, key=lambda x: x['avg_pnl'])
            insights_data.append({
                'type': 'bad',
                'title': f"{worst['name']} is destroying value",
                'body': f"Every {worst['name']} trade averaged ${worst['avg_pnl']}. That is ${worst['total_pnl']} in total losses.",
            })
        
        # WARN insight — most frequent losing emotion
        warn_candidates = [
            e for e in emotion_stats_list
            if e['win_rate'] < 40
        ]
        if warn_candidates:
            most_frequent = max(warn_candidates, key=lambda x: x['trade_count'])
            insights_data.append({
                'type': 'warn',
                'title': f"{most_frequent['name']} entries have a {most_frequent['win_rate']}% win rate",
                'body': f"{most_frequent['trade_count']} trades tagged {most_frequent['name']} with only {most_frequent['win_rate']}% profitable. Review your entry rules for these trades.",
            })
    
    # ─── Step 5: Build heatmap (full year 2026: Jan 1 - Dec 31) ───
    from datetime import date, datetime
    from django.utils import timezone as django_tz
    import pytz
    
    # Use Asia/Manila timezone for Philippines (UTC+8)
    # In production, this should come from user profile
    user_timezone = pytz.timezone('Asia/Manila')
    
    # Full year 2026
    start_date = date(2026, 1, 1)
    end_date = date(2026, 12, 31)
    
    # Build a map of dates to trade counts for efficiency
    date_trade_map = {}
    for trade in trades:
        # Convert to user's timezone before extracting date
        if isinstance(trade.trade_date, datetime):
            if trade.trade_date.tzinfo is not None:
                # Already timezone-aware, convert to user timezone
                local_dt = trade.trade_date.astimezone(user_timezone)
            else:
                # Naive datetime, assume UTC
                utc_dt = pytz.UTC.localize(trade.trade_date)
                local_dt = utc_dt.astimezone(user_timezone)
            trade_date = local_dt.date()
        else:
            trade_date = trade.trade_date
        
        date_key = trade_date.isoformat()
        date_trade_map[date_key] = date_trade_map.get(date_key, 0) + 1
    
    heatmap_data = []
    current_date = start_date
    
    while current_date <= end_date:
        date_key = current_date.isoformat()
        trade_count = date_trade_map.get(date_key, 0)
        
        # Assign intensity
        if trade_count == 0:
            intensity = 0
        elif trade_count == 1:
            intensity = 1
        elif trade_count <= 3:
            intensity = 2
        elif trade_count <= 5:
            intensity = 3
        else:
            intensity = 4
        
        heatmap_data.append({
            'date': date_key,
            'trade_count': trade_count,
            'intensity': intensity,
        })
        
        current_date += timedelta(days=1)
    
    # ─── Step 6: Return response ───
    response_data = {
        'emotion_stats': emotion_stats_list,
        'trades': trades_data,
        'insights': insights_data,
        'heatmap': heatmap_data,
    }
    
    serializer = EmotionJournalSerializer(response_data)
    return Response(serializer.data, status=status.HTTP_200_OK)



# ─── P&L Analysis View ────────────────────────────────────────────
from .serializers import (
    PnlSummarySerializer, CumulativePnlPointSerializer, MonthlyPnlSerializer,
    CoinPnlSerializer, WinLossRatioSerializer, FeeImpactSerializer,
    TopTradeSerializer, PnlAnalysisSerializer
)
from collections import defaultdict


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pnl_analysis(request):
    """
    GET /api/pnl-analysis/
    Get comprehensive P&L analysis with optional filtering.
    
    Query Parameters:
    - date_from: Filter trades from this date (YYYY-MM-DD)
    - date_to: Filter trades until this date (YYYY-MM-DD)
    - coin_id: Filter trades for a specific coin
    
    Response: Complete P&L analysis with summary, charts, and insights
    """
    user = request.user
    
    # ─── Step 1: Load trades ───
    queryset = Trade.objects.filter(user=user).select_related('coin').order_by('trade_date')
    
    # Apply filters
    date_from = request.query_params.get('date_from')
    if date_from:
        queryset = queryset.filter(trade_date__date__gte=date_from)
    
    date_to = request.query_params.get('date_to')
    if date_to:
        queryset = queryset.filter(trade_date__date__lte=date_to)
    
    coin_id = request.query_params.get('coin_id')
    if coin_id:
        queryset = queryset.filter(coin_id=coin_id)
    
    trades = list(queryset)
    
    # ─── Step 2: Separate closed vs open ───
    closed_trades = []
    open_trades = []
    
    for trade in trades:
        if trade.sell_price is not None and trade.buy_price is not None:
            closed_trades.append(trade)
        else:
            open_trades.append(trade)
    
    # ─── Step 3: Calculate realized_pnl for each closed trade ───
    trade_pnls = []  # List of (trade, pnl) tuples
    
    for trade in closed_trades:
        pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
        pnl = round(pnl, 2)
        trade_pnls.append((trade, pnl))
    
    # ─── Step 4: Build summary ───
    total_trades = len(trades)
    closed_count = len(closed_trades)
    
    winning_trades = [(t, pnl) for t, pnl in trade_pnls if pnl > 0]
    losing_trades = [(t, pnl) for t, pnl in trade_pnls if pnl < 0]
    breakeven_trades = [(t, pnl) for t, pnl in trade_pnls if pnl == 0]
    
    winning_count = len(winning_trades)
    losing_count = len(losing_trades)
    breakeven_count = len(breakeven_trades)
    
    # Calculate metrics
    realized_pnl = sum(pnl for _, pnl in trade_pnls)
    win_rate = (winning_count / closed_count * 100) if closed_count > 0 else 0.0
    
    winning_pnls = [pnl for _, pnl in winning_trades]
    losing_pnls = [pnl for _, pnl in losing_trades]
    
    avg_win = (sum(winning_pnls) / len(winning_pnls)) if winning_pnls else 0.0
    avg_loss = (sum(losing_pnls) / len(losing_pnls)) if losing_pnls else 0.0
    
    gross_profits = sum(winning_pnls) if winning_pnls else 0.0
    gross_losses = abs(sum(losing_pnls)) if losing_pnls else 0.0
    
    if gross_losses > 0 and gross_profits > 0:
        profit_factor = gross_profits / gross_losses
    else:
        profit_factor = 0.0
    
    summary_data = {
        'realized_pnl': round(realized_pnl, 2),
        'win_rate': round(win_rate, 1),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'profit_factor': round(profit_factor, 2),
        'total_trades': total_trades,
        'closed_trades': closed_count,
        'winning_trades': winning_count,
        'losing_trades': losing_count,
        'breakeven_trades': breakeven_count,
    }
    
    # ─── Step 5: Build cumulative_pnl series ───
    cumulative_pnl_data = []
    running_total = 0.0
    
    for trade, pnl in trade_pnls:
        running_total += pnl
        cumulative_pnl_data.append({
            'date': trade.trade_date.strftime('%Y-%m-%d'),
            'realized_pnl': round(pnl, 2),
            'cumulative_pnl': round(running_total, 2),
            'trade_id': trade.id,
            'coin_symbol': trade.coin.symbol,
            'trade_type': trade.trade_type,
        })
    
    # ─── Step 6: Build monthly_pnl ───
    MONTH_ABBREV = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    monthly_map = defaultdict(float)
    years_set = set()
    
    for trade, pnl in trade_pnls:
        year = trade.trade_date.year
        month = trade.trade_date.month
        years_set.add(year)
        monthly_map[(year, month)] += pnl
    
    # Determine if we need to show year in labels
    multi_year = len(years_set) > 1
    
    monthly_pnl_data = []
    for (year, month), pnl in sorted(monthly_map.items()):
        if multi_year:
            label = f"{MONTH_ABBREV[month-1]} {str(year)[-2:]}"
        else:
            label = MONTH_ABBREV[month-1]
        
        monthly_pnl_data.append({
            'label': label,
            'year': year,
            'month': month,
            'realized_pnl': round(pnl, 2),
            'is_profit': pnl > 0,
        })
    
    # ─── Step 7: Build pnl_by_coin ───
    coin_map = defaultdict(lambda: {'pnl': 0.0, 'count': 0, 'coin': None})
    
    for trade, pnl in trade_pnls:
        coin_id = trade.coin.id
        coin_map[coin_id]['pnl'] += pnl
        coin_map[coin_id]['count'] += 1
        coin_map[coin_id]['coin'] = trade.coin
    
    pnl_by_coin_data = []
    for coin_id, data in coin_map.items():
        pnl_by_coin_data.append({
            'coin_id': coin_id,
            'symbol': data['coin'].symbol,
            'name': data['coin'].name,
            'realized_pnl': round(data['pnl'], 2),
            'trade_count': data['count'],
            'is_profit': data['pnl'] > 0,
        })
    
    # Sort by absolute value of realized_pnl descending
    pnl_by_coin_data.sort(key=lambda x: abs(x['realized_pnl']), reverse=True)
    
    # ─── Step 8: Build win_loss_ratio ───
    total_closed = closed_count
    
    if total_closed > 0:
        winning_pct = (winning_count / total_closed * 100)
        losing_pct = (losing_count / total_closed * 100)
        breakeven_pct = (breakeven_count / total_closed * 100)
    else:
        winning_pct = 0.0
        losing_pct = 0.0
        breakeven_pct = 0.0
    
    win_loss_ratio_data = {
        'winning_count': winning_count,
        'losing_count': losing_count,
        'breakeven_count': breakeven_count,
        'winning_pct': round(winning_pct, 1),
        'losing_pct': round(losing_pct, 1),
        'breakeven_pct': round(breakeven_pct, 1),
    }
    
    # ─── Step 9: Build fee_impact ───
    total_fees = sum(trade.fee for trade in closed_trades)
    
    if gross_profits > 0:
        fee_impact_pct = (total_fees / gross_profits * 100)
    else:
        fee_impact_pct = 0.0
    
    fee_impact_data = {
        'total_fees': round(total_fees, 2),
        'gross_profits': round(gross_profits, 2),
        'fee_impact_pct': round(fee_impact_pct, 1),
    }
    
    # ─── Step 10: Build top_wins and top_losses ───
    # Sort by pnl descending for wins
    top_wins_list = sorted(winning_trades, key=lambda x: x[1], reverse=True)[:3]
    
    # Sort by pnl ascending for losses (most negative first)
    top_losses_list = sorted(losing_trades, key=lambda x: x[1])[:3]
    
    top_wins_data = []
    for trade, pnl in top_wins_list:
        # Cross-platform date format (remove leading zero from day)
        date_str = trade.trade_date.strftime("%b %d").lstrip("0")
        
        top_wins_data.append({
            'trade_id': trade.id,
            'trade_type': trade.trade_type,
            'coin_symbol': trade.coin.symbol,
            'coin_name': trade.coin.name,
            'date': date_str,
            'realized_pnl': round(pnl, 2),
            'quantity': trade.quantity,
            'buy_price': trade.buy_price,
            'sell_price': trade.sell_price,
        })
    
    top_losses_data = []
    for trade, pnl in top_losses_list:
        # Cross-platform date format (remove leading zero from day)
        date_str = trade.trade_date.strftime("%b %d").lstrip("0")
        
        top_losses_data.append({
            'trade_id': trade.id,
            'trade_type': trade.trade_type,
            'coin_symbol': trade.coin.symbol,
            'coin_name': trade.coin.name,
            'date': date_str,
            'realized_pnl': round(pnl, 2),
            'quantity': trade.quantity,
            'buy_price': trade.buy_price,
            'sell_price': trade.sell_price,
        })
    
    # ─── Step 11: Return response ───
    response_data = {
        'summary': summary_data,
        'cumulative_pnl': cumulative_pnl_data,
        'monthly_pnl': monthly_pnl_data,
        'pnl_by_coin': pnl_by_coin_data,
        'win_loss_ratio': win_loss_ratio_data,
        'fee_impact': fee_impact_data,
        'top_wins': top_wins_data,
        'top_losses': top_losses_data,
    }
    
    serializer = PnlAnalysisSerializer(response_data)
    return Response(serializer.data, status=status.HTTP_200_OK)



# ─── Monthly Report Views ─────────────────────────────────────────
from .serializers import (
    MonthlyReportMetricsSerializer, MonthTradeSerializer, BestWorstTradeSerializer,
    MonthCoinPnlSerializer, MonthlyBarSerializer, CumulativeMonthlyPnlSerializer,
    MonthlyReportResponseSerializer
)
from .models import MonthlyReport
import calendar


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monthly_report_list(request):
    """
    GET /api/monthly-reports/
    Returns the list of all months that have trade data for the current user.
    Used to populate the month selector tabs and the report history table.
    """
    user = request.user
    
    # Step 1: Find all months with trades
    trades = Trade.objects.filter(user=user).select_related('coin').order_by('trade_date')
    
    if not trades.exists():
        return Response({
            'available_months': [],
            'total_months': 0
        }, status=status.HTTP_200_OK)
    
    # Extract distinct (year, month) pairs
    month_set = set()
    for trade in trades:
        year = trade.trade_date.year
        month = trade.trade_date.month
        month_set.add((year, month))
    
    # Sort ascending for cumulative calculation
    months_sorted = sorted(list(month_set))
    
    # Step 2: For each month calculate summary
    MONTH_ABBREV = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    # Determine if we need to show year in labels
    years_set = set(y for y, m in months_sorted)
    multi_year = len(years_set) > 1
    
    month_summaries = []
    
    for year, month in months_sorted:
        # Filter trades to this month
        month_trades = [
            t for t in trades
            if t.trade_date.year == year and t.trade_date.month == month
        ]
        
        # Calculate metrics
        total_trades = len(month_trades)
        
        closed_trades = [
            t for t in month_trades
            if t.sell_price is not None and t.buy_price is not None
        ]
        
        closed_count = len(closed_trades)
        
        # Calculate realized_pnl and winning_trades
        realized_pnl = 0.0
        winning_trades = 0
        
        for trade in closed_trades:
            pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
            realized_pnl += pnl
            if pnl > 0:
                winning_trades += 1
        
        # Calculate win_rate
        win_rate = (winning_trades / closed_count * 100) if closed_count > 0 else 0.0
        
        # Month label
        if multi_year:
            month_label = f"{MONTH_ABBREV[month-1]} {str(year)[-2:]}"
        else:
            month_label = MONTH_ABBREV[month-1]
        
        month_summaries.append({
            'year': year,
            'month': month,
            'month_label': month_label,
            'realized_pnl': round(realized_pnl, 2),
            'win_rate': round(win_rate, 1),
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'is_profit': realized_pnl > 0,
        })
    
    # Step 3: Build cumulative P&L series
    cumulative_total = 0.0
    for summary in month_summaries:
        cumulative_total += summary['realized_pnl']
        summary['cumulative_pnl'] = round(cumulative_total, 2)
    
    # Step 4: Return response (descending order - newest first)
    month_summaries.reverse()
    
    return Response({
        'available_months': month_summaries,
        'total_months': len(month_summaries)
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def monthly_report_detail(request, year, month):
    """
    GET /api/monthly-reports/<year>/<month>/
    Returns all data needed to render the full monthly report page for one selected month.
    """
    user = request.user
    
    # Step 1: Validate year and month
    if month < 1 or month > 12:
        return Response(
            {'error': 'Invalid month value. Must be 1-12.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Step 2: Load trades for this month
    trades = Trade.objects.filter(
        user=user,
        trade_date__year=year,
        trade_date__month=month
    ).select_related('coin').prefetch_related('emotions__emotion_tag').order_by('trade_date')
    
    if not trades.exists():
        return Response(
            {'error': 'No trades found for this month'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    # Step 3: Calculate metrics
    total_trades = trades.count()
    
    closed_trades = []
    open_trades = []
    
    for trade in trades:
        if trade.sell_price is not None and trade.buy_price is not None:
            closed_trades.append(trade)
        else:
            open_trades.append(trade)
    
    closed_count = len(closed_trades)
    
    # Calculate P&L metrics
    realized_pnl = 0.0
    winning_trades = 0
    losing_trades = 0
    total_fees = 0.0
    
    trade_pnls = []  # List of (trade, pnl) tuples
    
    for trade in trades:
        total_fees += trade.fee
        
        if trade.sell_price is not None and trade.buy_price is not None:
            pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
            pnl = round(pnl, 2)
            realized_pnl += pnl
            trade_pnls.append((trade, pnl))
            
            if pnl > 0:
                winning_trades += 1
            elif pnl < 0:
                losing_trades += 1
    
    # Calculate win_rate
    win_rate = (winning_trades / closed_count * 100) if closed_count > 0 else 0.0
    
    # Calculate fees_pct_of_pnl
    if realized_pnl != 0:
        fees_pct_of_pnl = (total_fees / abs(realized_pnl)) * 100
    else:
        fees_pct_of_pnl = 0.0
    
    # Calculate avg_pnl_per_trade
    avg_pnl_per_trade = (realized_pnl / closed_count) if closed_count > 0 else 0.0
    
    # Month label (full name)
    month_label = f"{calendar.month_name[month]} {year}"
    
    metrics_data = {
        'year': year,
        'month': month,
        'month_label': month_label,
        'realized_pnl': round(realized_pnl, 2),
        'win_rate': round(win_rate, 1),
        'total_trades': total_trades,
        'closed_trades': closed_count,
        'winning_trades': winning_trades,
        'losing_trades': losing_trades,
        'total_fees': round(total_fees, 2),
        'fees_pct_of_pnl': round(fees_pct_of_pnl, 1),
        'avg_pnl_per_trade': round(avg_pnl_per_trade, 2),
    }
    
    # Step 4: Build trades list
    trades_data = []
    
    for trade in trades:
        # Get emotions
        emotions_list = []
        for te in trade.emotions.all():
            emotions_list.append({
                'id': te.emotion_tag.id,
                'name': te.emotion_tag.name,
                'color': te.emotion_tag.color,
            })
        
        # Calculate realized_pnl
        realized_pnl_value = None
        if trade.sell_price is not None and trade.buy_price is not None:
            realized_pnl_value = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
            realized_pnl_value = round(realized_pnl_value, 2)
        
        # Format date (cross-platform: remove leading zero from day)
        date_str = trade.trade_date.strftime("%b %d").lstrip("0")
        
        trades_data.append({
            'id': trade.id,
            'date': date_str,
            'trade_type': trade.trade_type,
            'coin_symbol': trade.coin.symbol,
            'coin_name': trade.coin.name,
            'quantity': trade.quantity,
            'buy_price': trade.buy_price,
            'sell_price': trade.sell_price,
            'fee': trade.fee,
            'realized_pnl': realized_pnl_value,
            'is_open': trade.sell_price is None,
            'emotions': emotions_list,
            'notes': trade.notes or "",
        })
    
    # Step 5: Find best and worst trades
    best_trade_data = None
    worst_trade_data = None
    
    if trade_pnls:
        # Best trade (highest P&L)
        best_trade, best_pnl = max(trade_pnls, key=lambda x: x[1])
        
        best_emotions = []
        for te in best_trade.emotions.all():
            best_emotions.append({
                'id': te.emotion_tag.id,
                'name': te.emotion_tag.name,
                'color': te.emotion_tag.color,
            })
        
        best_date_str = best_trade.trade_date.strftime("%b %d").lstrip("0")
        
        best_trade_data = {
            'id': best_trade.id,
            'date': best_date_str,
            'trade_type': best_trade.trade_type,
            'coin_symbol': best_trade.coin.symbol,
            'coin_name': best_trade.coin.name,
            'quantity': best_trade.quantity,
            'buy_price': best_trade.buy_price,
            'sell_price': best_trade.sell_price,
            'fee': best_trade.fee,
            'realized_pnl': best_pnl,
            'is_open': False,
            'emotions': best_emotions,
            'notes': best_trade.notes or "",
        }
        
        # Worst trade (lowest P&L)
        worst_trade, worst_pnl = min(trade_pnls, key=lambda x: x[1])
        
        worst_emotions = []
        for te in worst_trade.emotions.all():
            worst_emotions.append({
                'id': te.emotion_tag.id,
                'name': te.emotion_tag.name,
                'color': te.emotion_tag.color,
            })
        
        worst_date_str = worst_trade.trade_date.strftime("%b %d").lstrip("0")
        
        worst_trade_data = {
            'id': worst_trade.id,
            'date': worst_date_str,
            'trade_type': worst_trade.trade_type,
            'coin_symbol': worst_trade.coin.symbol,
            'coin_name': worst_trade.coin.name,
            'quantity': worst_trade.quantity,
            'buy_price': worst_trade.buy_price,
            'sell_price': worst_trade.sell_price,
            'fee': worst_trade.fee,
            'realized_pnl': worst_pnl,
            'is_open': False,
            'emotions': worst_emotions,
            'notes': worst_trade.notes or "",
        }
    
    best_worst_data = {
        'best_trade': best_trade_data,
        'worst_trade': worst_trade_data,
    }
    
    # Step 6: Build pnl_by_coin
    coin_map = defaultdict(lambda: {'pnl': 0.0, 'count': 0, 'coin': None})
    
    for trade, pnl in trade_pnls:
        coin_id = trade.coin.id
        coin_map[coin_id]['pnl'] += pnl
        coin_map[coin_id]['count'] += 1
        coin_map[coin_id]['coin'] = trade.coin
    
    pnl_by_coin_data = []
    for coin_id, data in coin_map.items():
        pnl_by_coin_data.append({
            'coin_id': coin_id,
            'symbol': data['coin'].symbol,
            'name': data['coin'].name,
            'realized_pnl': round(data['pnl'], 2),
            'trade_count': data['count'],
            'is_profit': data['pnl'] > 0,
        })
    
    # Sort by absolute value of realized_pnl descending
    pnl_by_coin_data.sort(key=lambda x: abs(x['realized_pnl']), reverse=True)
    
    # Step 7: Build monthly_bars (all months, not just this one)
    all_trades = Trade.objects.filter(user=user).select_related('coin').order_by('trade_date')
    
    # Extract distinct (year, month) pairs
    month_set = set()
    for trade in all_trades:
        y = trade.trade_date.year
        m = trade.trade_date.month
        month_set.add((y, m))
    
    # Sort ascending
    months_sorted = sorted(list(month_set))
    
    MONTH_ABBREV = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    
    # Determine if we need to show year in labels
    years_set = set(y for y, m in months_sorted)
    multi_year = len(years_set) > 1
    
    monthly_bars_data = []
    
    for y, m in months_sorted:
        # Filter trades to this month
        month_trades = [
            t for t in all_trades
            if t.trade_date.year == y and t.trade_date.month == m
        ]
        
        # Calculate metrics
        total_trades_month = len(month_trades)
        
        closed_trades_month = [
            t for t in month_trades
            if t.sell_price is not None and t.buy_price is not None
        ]
        
        closed_count_month = len(closed_trades_month)
        
        # Calculate realized_pnl and winning_trades
        realized_pnl_month = 0.0
        winning_trades_month = 0
        
        for trade in closed_trades_month:
            pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
            realized_pnl_month += pnl
            if pnl > 0:
                winning_trades_month += 1
        
        # Calculate win_rate
        win_rate_month = (winning_trades_month / closed_count_month * 100) if closed_count_month > 0 else 0.0
        
        # Month label
        if multi_year:
            month_label_bar = f"{MONTH_ABBREV[m-1]} {str(y)[-2:]}"
        else:
            month_label_bar = MONTH_ABBREV[m-1]
        
        monthly_bars_data.append({
            'year': y,
            'month': m,
            'month_label': month_label_bar,
            'realized_pnl': round(realized_pnl_month, 2),
            'win_rate': round(win_rate_month, 1),
            'total_trades': total_trades_month,
            'winning_trades': winning_trades_month,
            'is_profit': realized_pnl_month > 0,
        })
    
    # Step 8: Build cumulative_pnl series
    cumulative_pnl_data = []
    cumulative_total = 0.0
    
    for bar in monthly_bars_data:
        cumulative_total += bar['realized_pnl']
        cumulative_pnl_data.append({
            'year': bar['year'],
            'month': bar['month'],
            'month_label': bar['month_label'],
            'monthly_pnl': bar['realized_pnl'],
            'cumulative_pnl': round(cumulative_total, 2),
        })
    
    # Step 9: Save or update MonthlyReport record
    try:
        MonthlyReport.objects.update_or_create(
            user=user,
            year=year,
            month=month,
            defaults={
                'total_realized_pnl': metrics_data['realized_pnl'],
                'win_rate': metrics_data['win_rate'],
                'total_trades': metrics_data['total_trades'],
                'winning_trades': metrics_data['winning_trades'],
            }
        )
    except Exception as e:
        # Save failure must NOT prevent the response from being returned
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to save MonthlyReport: {e}")
    
    # Step 10: Build available_months (same as monthly_report_list)
    available_months_data = []
    cumulative_total_avail = 0.0
    
    for bar in monthly_bars_data:
        cumulative_total_avail += bar['realized_pnl']
        available_months_data.append({
            'year': bar['year'],
            'month': bar['month'],
            'month_label': bar['month_label'],
            'realized_pnl': bar['realized_pnl'],
            'win_rate': bar['win_rate'],
            'total_trades': bar['total_trades'],
            'winning_trades': bar['winning_trades'],
            'is_profit': bar['is_profit'],
            'cumulative_pnl': round(cumulative_total_avail, 2),
        })
    
    # Reverse for descending order (newest first)
    available_months_data.reverse()
    
    # Step 11: Return full response
    response_data = {
        'metrics': metrics_data,
        'trades': trades_data,
        'best_worst': best_worst_data,
        'pnl_by_coin': pnl_by_coin_data,
        'monthly_bars': monthly_bars_data,
        'cumulative_pnl': cumulative_pnl_data,
        'available_months': available_months_data,
    }
    
    serializer = MonthlyReportResponseSerializer(response_data)
    return Response(serializer.data, status=status.HTTP_200_OK)


# ─── AI Feedback Views ────────────────────────────────────────────
from .models import AIFeedback
from .serializers import AIFeedbackSerializer, AIFeedbackPreviewSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ai_feedback_preview(request):
    """
    GET /api/ai-feedback/preview/
    Returns preview stats for AI feedback generation.
    """
    user = request.user
    year = request.query_params.get('year')
    month = request.query_params.get('month')
    
    # Filter trades
    trades_query = Trade.objects.filter(user=user)
    if year:
        trades_query = trades_query.filter(trade_date__year=int(year))
    if month:
        trades_query = trades_query.filter(trade_date__month=int(month))
    
    trades = list(trades_query)
    
    # Calculate stats
    total_trades = len(trades)
    closed_trades = [t for t in trades if t.sell_price is not None and t.buy_price is not None]
    closed_count = len(closed_trades)
    
    # Calculate P&L
    realized_pnl = 0.0
    winning_trades = 0
    for trade in closed_trades:
        pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
        realized_pnl += pnl
        if pnl > 0:
            winning_trades += 1
    
    win_rate = (winning_trades / closed_count * 100) if closed_count > 0 else 0.0
    
    # Count emotions tagged
    emotions_tagged = TradeEmotion.objects.filter(trade__user=user).count()
    
    # Check if enough data
    has_enough_data = total_trades >= 3 and emotions_tagged >= 2
    
    data = {
        'total_trades': total_trades,
        'closed_trades': closed_count,
        'winning_trades': winning_trades,
        'win_rate': round(win_rate, 2),
        'realized_pnl': round(realized_pnl, 2),
        'emotions_tagged': emotions_tagged,
        'has_enough_data': has_enough_data,
    }
    
    serializer = AIFeedbackPreviewSerializer(data)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ai_feedback_generate(request):
    """
    POST /api/ai-feedback/generate/
    Generates AI feedback using built-in rule-based analyzer.
    """
    from .ai_analyzer import TradingAnalyzer
    from django.utils import timezone
    import calendar
    
    user = request.user
    year = request.data.get('year')
    month = request.data.get('month')
    
    # Get trades for analysis
    trades_query = Trade.objects.filter(user=user).select_related('coin').prefetch_related('emotions__emotion_tag')
    if year:
        trades_query = trades_query.filter(trade_date__year=int(year))
    if month:
        trades_query = trades_query.filter(trade_date__month=int(month))
    
    trades = list(trades_query.order_by('trade_date'))
    
    if not trades:
        return Response(
            {'error': 'No trades found for the specified period.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Analyze trades using built-in analyzer
    analyzer = TradingAnalyzer(trades)
    feedback_text = analyzer.generate_feedback()
    
    # Determine month label
    if year and month:
        month_label = f"{calendar.month_name[int(month)]} {year}"
    elif year:
        month_label = f"{year}"
    else:
        month_label = f"{timezone.now().strftime('%B %Y')}"
    
    # Create prompt summary
    closed_count = len([t for t in trades if t.sell_price and t.buy_price])
    prompt_summary = f"Analyzed {len(trades)} trades ({closed_count} closed) for {month_label}"
    
    # Save feedback
    feedback = AIFeedback.objects.create(
        user=user,
        prompt_summary=prompt_summary,
        feedback_text=feedback_text,
        month_label=month_label
    )
    
    serializer = AIFeedbackSerializer(feedback)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ai_feedback_list(request):
    """
    GET /api/ai-feedback/
    Returns all AI feedback for the current user.
    """
    feedbacks = AIFeedback.objects.filter(user=request.user).order_by('-created_at')
    serializer = AIFeedbackSerializer(feedbacks, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def ai_feedback_delete(request, pk):
    """
    DELETE /api/ai-feedback/<id>/
    Deletes an AI feedback record.
    """
    try:
        feedback = AIFeedback.objects.get(pk=pk, user=request.user)
        feedback.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    except AIFeedback.DoesNotExist:
        return Response(
            {'error': 'Feedback not found'},
            status=status.HTTP_404_NOT_FOUND
        )


# ─── Dashboard View ───────────────────────────────────────────────
from .serializers import (
    DashboardMetricsSerializer, DashboardHoldingSerializer, DashboardEmotionSerializer,
    DashboardRecentTradeSerializer, DashboardAISnippetSerializer, DashboardResponseSerializer
)
import json


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_overview(request):
    """
    GET /api/dashboard/
    Aggregates all dashboard data into one response.
    """
    user = request.user
    
    # ─── Step 1: Load all user trades ───
    trades = list(
        Trade.objects.filter(user=user)
        .select_related('coin')
        .prefetch_related('emotions__emotion_tag')
        .order_by('-trade_date')
    )
    
    # ─── Step 4: Calculate holdings from BUY trades only (same as Portfolio) ───
    # Only look at BUY trades to get current holdings
    buy_trades = Trade.objects.filter(user=user, trade_type='buy').select_related('coin')
    
    holdings_dict = {}
    for trade in buy_trades:
        coin_id = trade.coin.id
        if coin_id not in holdings_dict:
            holdings_dict[coin_id] = {
                'coin': trade.coin,
                'total_quantity': 0.0,
                'total_cost': 0.0,
            }
        
        holdings_dict[coin_id]['total_quantity'] += trade.quantity
        if trade.buy_price:
            holdings_dict[coin_id]['total_cost'] += trade.quantity * trade.buy_price
    
    # Calculate holdings (only positive quantities)
    holdings = []
    for coin_id, data in holdings_dict.items():
        total_quantity = data['total_quantity']
        
        # Use epsilon comparison for floats
        if total_quantity > 0.000001:
            avg_buy_price = data['total_cost'] / total_quantity if total_quantity > 0 else 0.0
            cost_basis = data['total_cost']
            
            holdings.append({
                'coin': data['coin'],
                'held_qty': total_quantity,
                'avg_buy': avg_buy_price,
                'cost_basis': cost_basis,
            })
    
    # ─── Step 5: Fetch live prices from CoinGecko ───
    prices_live = True
    warning = None
    prices = {}
    
    if holdings:
        coingecko_ids = [h['coin'].coingecko_id for h in holdings]
        ids_param = ','.join(coingecko_ids)
        
        try:
            from django.conf import settings
            
            # Try to get CoinGecko API key (note: APIKey model was removed, so we skip this)
            # In production, you might want to store this in settings or environment
            api_key = getattr(settings, 'COINGECKO_API_KEY', '')
            
            headers = {}
            if api_key:
                headers['x-cg-demo-api-key'] = api_key
            
            response = requests.get(
                'https://api.coingecko.com/api/v3/simple/price',
                params={
                    'ids': ids_param,
                    'vs_currencies': 'usd',
                    'include_24hr_change': 'true'
                },
                headers=headers,
                timeout=8
            )
            response.raise_for_status()
            prices = response.json()
            
        except requests.RequestException:
            prices_live = False
            warning = "Could not fetch live prices from CoinGecko. Showing last known values."
            prices = {}
    
    # ─── Step 6: Enrich holdings with live prices ───
    for holding in holdings:
        coingecko_id = holding['coin'].coingecko_id
        coin_price_data = prices.get(coingecko_id, {})
        
        live_price = coin_price_data.get('usd', 0.0)
        held_qty = holding['held_qty']
        avg_buy = holding['avg_buy']
        
        current_value = live_price * held_qty
        unrealized_pnl = (live_price - avg_buy) * held_qty
        unrealized_pnl_pct = ((live_price - avg_buy) / avg_buy * 100) if avg_buy > 0 else 0.0
        
        holding['live_price'] = live_price
        holding['current_value'] = current_value
        holding['unrealized_pnl'] = unrealized_pnl
        holding['unrealized_pnl_pct'] = unrealized_pnl_pct
    
    # ─── Step 7: Calculate portfolio totals ───
    portfolio_value = sum(h['current_value'] for h in holdings)
    total_unrealized = sum(h['unrealized_pnl'] for h in holdings)
    total_cost = sum(h['avg_buy'] * h['held_qty'] for h in holdings)
    unrealized_pct = (total_unrealized / total_cost * 100) if total_cost > 0 else 0.0
    
    if unrealized_pct >= 0:
        unrealized_label = f"+{unrealized_pct:.1f}% unrealized"
    else:
        unrealized_label = f"{unrealized_pct:.1f}% unrealized"
    
    # ─── Step 8: Build emotion breakdown ───
    # Get all TradeEmotion records for user's trades
    trade_ids = [t.id for t in trades]
    trade_emotions = TradeEmotion.objects.filter(
        trade_id__in=trade_ids
    ).select_related('emotion_tag')
    
    # Count trades with at least one emotion
    trades_with_emotions = set(te.trade_id for te in trade_emotions)
    total_tagged = len(trades_with_emotions)
    
    # Group by emotion tag
    emotion_map = defaultdict(int)
    for te in trade_emotions:
        emotion_map[te.emotion_tag.id] += 1
    
    emotions_data = []
    for emotion_id, trade_count in emotion_map.items():
        emotion_tag = EmotionTag.objects.get(id=emotion_id)
        percentage = (trade_count / total_tagged * 100) if total_tagged > 0 else 0.0
        
        emotions_data.append({
            'id': emotion_tag.id,
            'name': emotion_tag.name,
            'color': emotion_tag.color,
            'trade_count': trade_count,
            'percentage': round(percentage, 1),
        })
    
    # Sort by trade_count descending
    emotions_data.sort(key=lambda x: x['trade_count'], reverse=True)
    
    # ─── Step 9: Build recent trades ───
    recent_trades_data = []
    for trade in trades[:5]:  # First 5 (already ordered by trade_date desc)
        # Get price based on trade type
        price = trade.buy_price if trade.trade_type == 'buy' else trade.sell_price
        if price is None:
            price = 0.0
        
        # Get first emotion tag
        emotion_name = None
        emotion_color = None
        if trade.emotions.exists():
            first_emotion = trade.emotions.first().emotion_tag
            emotion_name = first_emotion.name
            emotion_color = first_emotion.color
        
        recent_trades_data.append({
            'id': trade.id,
            'trade_type': trade.trade_type,
            'coin_symbol': trade.coin.symbol,
            'coin_name': trade.coin.name,
            'quantity': round(trade.quantity, 8),
            'price': round(price, 2),
            'trade_date': trade.trade_date.strftime('%Y-%m-%d'),
            'emotion_name': emotion_name,
            'emotion_color': emotion_color,
        })
    
    # ─── Step 10: Get AI feedback snippet ───
    latest_feedback = AIFeedback.objects.filter(user=user).order_by('-created_at').first()
    
    if latest_feedback:
        # Try to parse feedback_text as JSON
        try:
            parsed = json.loads(latest_feedback.feedback_text)
            overall = parsed.get('overall', '')
        except (json.JSONDecodeError, ValueError):
            # If JSON parse fails, use raw text truncated to 300 chars
            overall = latest_feedback.feedback_text[:300]
        
        # Format month_label
        month_label = latest_feedback.created_at.strftime('%B %Y')
        
        ai_snippet_data = {
            'id': latest_feedback.id,
            'overall': overall,
            'month_label': month_label,
            'created_at': latest_feedback.created_at.isoformat(),
        }
    else:
        ai_snippet_data = {
            'id': None,
            'overall': None,
            'month_label': None,
            'created_at': None,
        }
    
    # ─── Step 10.5: Calculate realized P&L and win rate from trades ───
    closed_count = 0
    winning_count = 0
    realized_pnl = 0.0
    
    for trade in trades:
        if trade.sell_price and trade.buy_price:
            closed_count += 1
            trade_pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
            realized_pnl += trade_pnl
            if trade_pnl > 0:
                winning_count += 1
    
    win_rate = (winning_count / closed_count * 100) if closed_count > 0 else 0.0
    
    # Format labels
    winning_label = f"{winning_count} of {closed_count} profitable"
    realized_label = f"{closed_count} closed trades"
    
    # ─── Step 11: Build metrics ───
    metrics_data = {
        'portfolio_value': round(portfolio_value, 2),
        'realized_pnl': round(realized_pnl, 2),
        'unrealized_pnl': round(total_unrealized, 2),
        'unrealized_pct': round(unrealized_pct, 1),
        'win_rate': round(win_rate, 1),
        'winning_trades': winning_count,
        'closed_trades': closed_count,
        'winning_label': winning_label,
        'unrealized_label': unrealized_label,
        'realized_label': realized_label,
    }
    
    # ─── Step 12: Build holdings data ───
    # Sort by current_value descending
    holdings.sort(key=lambda x: x['current_value'], reverse=True)
    
    holdings_data = []
    for h in holdings:
        holdings_data.append({
            'coin_id': h['coin'].id,
            'symbol': h['coin'].symbol,
            'name': h['coin'].name,
            'coingecko_id': h['coin'].coingecko_id,
            'total_quantity': round(h['held_qty'], 8),
            'avg_buy_price': round(h['avg_buy'], 2),
            'live_price': round(h['live_price'], 2),
            'current_value': round(h['current_value'], 2),
            'unrealized_pnl': round(h['unrealized_pnl'], 2),
            'unrealized_pnl_pct': round(h['unrealized_pnl_pct'], 1),
        })
    
    # ─── Step 13: Return response ───
    response_data = {
        'metrics': metrics_data,
        'holdings': holdings_data,
        'emotions': emotions_data,
        'recent_trades': recent_trades_data,
        'ai_snippet': ai_snippet_data,
        'prices_live': prices_live,
        'warning': warning,
        'last_updated': datetime.now().isoformat(),
    }
    
    serializer = DashboardResponseSerializer(response_data)
    return Response(serializer.data, status=status.HTTP_200_OK)


# ─── Danger Zone Views ────────────────────────────────────────────
from .models import PortfolioSnapshot, MonthlyReport
from .serializers import DangerZoneStatusSerializer, ConfirmDeleteSerializer, AccountDeleteSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def danger_zone_status(request):
    """
    GET /api/danger-zone/status/
    Returns counts of all user data for display in the frontend before any destructive action.
    
    Response:
    {
        "trade_count": 39,
        "snapshot_count": 5,
        "report_count": 4,
        "ai_feedback_count": 3,
        "trade_emotion_count": 27
    }
    """
    try:
        counts = {
            'trade_count': Trade.objects.filter(user=request.user).count(),
            'snapshot_count': PortfolioSnapshot.objects.filter(user=request.user).count(),
            'report_count': MonthlyReport.objects.filter(user=request.user).count(),
            'ai_feedback_count': AIFeedback.objects.filter(user=request.user).count(),
            'trade_emotion_count': TradeEmotion.objects.filter(trade__user=request.user).count(),
        }
        serializer = DangerZoneStatusSerializer(counts)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {'error': f'Failed to retrieve danger zone status: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def reset_portfolio_snapshots(request):
    """
    DELETE /api/danger-zone/reset-snapshots/
    Delete all PortfolioSnapshot records for this user.
    They will be recalculated on next portfolio visit.
    
    Response:
    {
        "message": "Portfolio snapshots cleared. They will recalculate on your next Portfolio visit.",
        "deleted_count": 5
    }
    """
    try:
        deleted_count, _ = PortfolioSnapshot.objects.filter(user=request.user).delete()
        return Response(
            {
                'message': 'Portfolio snapshots cleared. They will recalculate on your next Portfolio visit.',
                'deleted_count': deleted_count
            },
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {'error': f'Failed to reset portfolio snapshots: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def clear_report_cache(request):
    """
    DELETE /api/danger-zone/clear-reports/
    Delete all MonthlyReport records for this user.
    They will be recalculated from raw Trade data on demand.
    
    Response:
    {
        "message": "Monthly report cache cleared. Reports will recalculate from your trade data on demand.",
        "deleted_count": 4
    }
    """
    try:
        deleted_count, _ = MonthlyReport.objects.filter(user=request.user).delete()
        return Response(
            {
                'message': 'Monthly report cache cleared. Reports will recalculate from your trade data on demand.',
                'deleted_count': deleted_count
            },
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {'error': f'Failed to clear report cache: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_ai_feedback_all(request):
    """
    DELETE /api/danger-zone/delete-ai-feedback/
    Delete all AIFeedback records for this user.
    
    Request body:
    { "confirmation": "DELETE" }
    
    Response:
    {
        "message": "All AI feedback deleted. You can regenerate it at any time.",
        "deleted_count": 3
    }
    
    Response 400:
    { "error": "Type DELETE to confirm." }
    """
    try:
        # Validate confirmation
        confirmation = request.data.get('confirmation', '').strip()
        if confirmation != 'DELETE':
            return Response(
                {'error': 'Type DELETE to confirm.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Delete AI feedback
        deleted_count, _ = AIFeedback.objects.filter(user=request.user).delete()
        
        return Response(
            {
                'message': 'All AI feedback deleted. You can regenerate it at any time.',
                'deleted_count': deleted_count
            },
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {'error': f'Failed to delete AI feedback: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_all_trades(request):
    """
    DELETE /api/danger-zone/delete-trades/
    Delete all Trade records for this user.
    This CASCADE deletes all TradeEmotion records too.
    Also deletes all PortfolioSnapshot records for this user.
    
    Request body:
    { "confirmation": "DELETE ALL" }
    
    Response:
    {
        "message": "All trades and portfolio snapshots deleted. Your journal has been reset.",
        "trades_deleted": 39,
        "snapshots_deleted": 5
    }
    
    Response 400:
    { "error": "Type DELETE ALL to confirm." }
    """
    try:
        # Validate confirmation
        confirmation = request.data.get('confirmation', '').strip()
        if confirmation != 'DELETE ALL':
            return Response(
                {'error': 'Type DELETE ALL to confirm.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Delete trades (CASCADE deletes TradeEmotions)
        trade_deleted, _ = Trade.objects.filter(user=request.user).delete()
        
        # Also delete snapshots (derived from trades)
        snapshot_deleted, _ = PortfolioSnapshot.objects.filter(user=request.user).delete()
        
        return Response(
            {
                'message': 'All trades and portfolio snapshots deleted. Your journal has been reset.',
                'trades_deleted': trade_deleted,
                'snapshots_deleted': snapshot_deleted
            },
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {'error': f'Failed to delete trades: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_account(request):
    """
    DELETE /api/danger-zone/delete-account/
    Permanently delete the entire account and all associated data.
    
    Request body:
    { "username": "juandelacruz" }
    
    Response:
    {
        "message": "Account 'juandelacruz' and all associated data have been permanently deleted."
    }
    
    Response 400:
    { "error": "Username does not match your account. Type your exact username to confirm." }
    """
    try:
        # Validate username matches current user
        username = request.data.get('username', '').strip()
        if username != request.user.username:
            return Response(
                {'error': 'Username does not match your account. Type your exact username to confirm.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Try to blacklist current JWT token if token_blacklist is installed
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            tokens = OutstandingToken.objects.filter(user=request.user)
            for token in tokens:
                BlacklistedToken.objects.get_or_create(token=token)
        except Exception:
            # Token blacklist may not be installed, that is OK
            pass
        
        # Store username for response before deletion
        username_for_response = request.user.username
        
        # Delete the user (CASCADE deletes everything linked to the user)
        request.user.delete()
        
        return Response(
            {'message': f"Account '{username_for_response}' and all associated data have been permanently deleted."},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {'error': f'Failed to delete account: {str(e)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
