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
    List all emotion tags.
    """
    serializer_class = EmotionTagSerializer
    permission_classes = [IsAuthenticated]
    queryset = EmotionTag.objects.all().order_by('name')



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
    List all emotion tags with statistics.
    
    POST /api/emotion-tags/
    Create a new emotion tag.
    """
    permission_classes = [IsAuthenticated]
    queryset = EmotionTag.objects.all().order_by('name')
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return EmotionTagWriteSerializer
        return EmotionTagSerializer
    
    def create(self, request, *args, **kwargs):
        """Create emotion tag and return with stats"""
        serializer = EmotionTagWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        emotion_tag = serializer.save()
        
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
    queryset = EmotionTag.objects.all()
    
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
    Return hardcoded list of suggested emotion tags that don't already exist.
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
    
    # Get existing tag names (case-insensitive)
    existing_names = set(
        EmotionTag.objects.values_list('name', flat=True)
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
