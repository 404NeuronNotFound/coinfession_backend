from django.contrib.auth.models import User
from rest_framework import serializers
from .models import (
    UserProfile, UserSession, RefreshToken, Coin, EmotionTag, 
    TradeEmotion, Trade, AIFeedback, FundingFeeLog
)
from .trade_utils import (
    calculate_pnl, calculate_liquidation_price, 
    calculate_quantity_from_collateral
)


class CoinSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coin
        fields = ['id', 'symbol', 'name', 'coingecko_id']


class EmotionTagSerializer(serializers.ModelSerializer):
    trade_count = serializers.SerializerMethodField()
    win_rate = serializers.SerializerMethodField()
    avg_pnl = serializers.SerializerMethodField()

    class Meta:
        model = EmotionTag
        fields = ['id', 'name', 'color', 'trade_count', 'win_rate', 'avg_pnl']

    def get_trade_count(self, obj):
        """Return the number of TradeEmotion records linked to this tag"""
        return obj.trade_emotions.count()

    def get_win_rate(self, obj):
        """Calculate win rate for closed trades with this emotion tag"""
        trade_emotions = obj.trade_emotions.select_related('trade').all()
        
        closed_trades = []
        for te in trade_emotions:
            trade = te.trade
            pnl_result = calculate_pnl(trade)
            if pnl_result is not None:
                closed_trades.append(pnl_result['realized_pnl'])
        
        if not closed_trades:
            return 0.0
        
        winning_count = sum(1 for pnl in closed_trades if pnl > 0)
        win_rate = (winning_count / len(closed_trades)) * 100
        return round(win_rate, 1)

    def get_avg_pnl(self, obj):
        """Calculate average P&L for closed trades with this emotion tag"""
        trade_emotions = obj.trade_emotions.select_related('trade').all()
        
        closed_pnls = []
        for te in trade_emotions:
            trade = te.trade
            pnl_result = calculate_pnl(trade)
            if pnl_result is not None:
                closed_pnls.append(pnl_result['realized_pnl'])
        
        if not closed_pnls:
            return 0.0
        
        avg = sum(closed_pnls) / len(closed_pnls)
        return round(avg, 2)


class EmotionTagWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmotionTag
        fields = ['id', 'name', 'color']

    def validate_name(self, value):
        """Validate name is not empty and is unique per user (case-insensitive)"""
        value = value.strip()
        
        if not value:
            raise serializers.ValidationError("Name cannot be empty")
        
        # Check for duplicate name within current user only (case-insensitive)
        # Handle case where context might not have request (e.g., in tests)
        if 'request' in self.context:
            user = self.context['request'].user
            queryset = EmotionTag.objects.filter(name__iexact=value, user=user)
            
            # Exclude current instance when updating
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise serializers.ValidationError("An emotion tag with this name already exists")
        
        return value

    def validate_color(self, value):
        """Validate color is not empty"""
        value = value.strip()
        
        if not value:
            raise serializers.ValidationError("Color cannot be empty")
        
        return value


class TradeEmotionSerializer(serializers.ModelSerializer):
    emotion_tag = EmotionTagSerializer(read_only=True)
    emotion_tag_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = TradeEmotion
        fields = ['id', 'emotion_tag', 'emotion_tag_id']


class TradeSerializer(serializers.ModelSerializer):
    coin = CoinSerializer(read_only=True)
    coin_id = serializers.IntegerField(write_only=True)
    emotions = TradeEmotionSerializer(many=True, read_only=True)
    emotion_tag_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=True
    )
    realized_pnl = serializers.SerializerMethodField()
    roi = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = [
            'id', 'coin', 'coin_id', 'trade_type', 'quantity',
            'buy_price', 'sell_price', 'fee', 'trade_date', 'notes',
            'emotions', 'emotion_tag_ids', 'realized_pnl', 'roi',
            'created_at',
            # Long/Short fields
            'position_type', 'leverage', 'entry_price', 'exit_price',
            'collateral', 'liquidation_price', 'funding_fees',
            'is_open', 'close_date'
        ]
        read_only_fields = ['id', 'created_at', 'liquidation_price']

    def get_realized_pnl(self, obj):
        pnl_result = calculate_pnl(obj)
        return pnl_result['realized_pnl'] if pnl_result else None

    def get_roi(self, obj):
        pnl_result = calculate_pnl(obj)
        return pnl_result['roi'] if pnl_result else None

    def validate(self, data):
        """Validate trade data based on position type"""
        position_type = data.get('position_type', 'spot')
        
        # SPOT validation
        if position_type == 'spot':
            # Require buy_price OR entry_price
            buy_price = data.get('buy_price')
            entry_price = data.get('entry_price')
            if buy_price is None and entry_price is None:
                raise serializers.ValidationError({
                    'buy_price': 'Either buy_price or entry_price is required for spot trades'
                })
            
            # Force leverage to 1.0 for spot
            data['leverage'] = 1.0
            
            # Force is_open to False for spot
            data['is_open'] = False
        
        # LONG/SHORT validation
        elif position_type in ['long', 'short']:
            # Require entry_price
            entry_price = data.get('entry_price')
            if entry_price is None or entry_price <= 0:
                raise serializers.ValidationError({
                    'entry_price': 'Entry price is required and must be greater than 0 for long/short trades'
                })
            
            # Require collateral
            collateral = data.get('collateral')
            if collateral is None or collateral <= 0:
                raise serializers.ValidationError({
                    'collateral': 'Collateral is required and must be greater than 0 for long/short trades'
                })
            
            # Require leverage
            leverage = data.get('leverage')
            if leverage is None:
                raise serializers.ValidationError({
                    'leverage': 'Leverage is required for long/short trades'
                })
            
            # Validate leverage range
            if leverage < 1.0 or leverage > 125.0:
                raise serializers.ValidationError({
                    'leverage': 'Leverage must be between 1.0 and 125.0'
                })
            
            # Check if position is closed
            exit_price = data.get('exit_price')
            is_open = data.get('is_open', True)
            
            if not is_open and exit_price is None:
                raise serializers.ValidationError({
                    'exit_price': 'Exit price is required when is_open is False'
                })
            
            if is_open and exit_price is not None:
                raise serializers.ValidationError({
                    'exit_price': 'Exit price must be None when is_open is True'
                })
        
        return data

    def create(self, validated_data):
        """Create trade with proper long/short handling"""
        emotion_tag_ids = validated_data.pop('emotion_tag_ids', [])
        position_type = validated_data.get('position_type', 'spot')
        
        # Handle backward compatibility: if trade_type is provided but position_type is not
        if 'trade_type' in validated_data and position_type == 'spot':
            # Map old buy_price/sell_price to entry_price/exit_price if not provided
            if 'entry_price' not in validated_data and 'buy_price' in validated_data:
                validated_data['entry_price'] = validated_data['buy_price']
            if 'exit_price' not in validated_data and 'sell_price' in validated_data:
                validated_data['exit_price'] = validated_data['sell_price']
        
        # LONG/SHORT: Auto-calculate quantity from collateral
        if position_type in ['long', 'short']:
            collateral = validated_data.get('collateral')
            leverage = validated_data.get('leverage')
            entry_price = validated_data.get('entry_price')
            
            # Recalculate quantity server-side (ignore client value)
            validated_data['quantity'] = calculate_quantity_from_collateral(
                collateral, leverage, entry_price
            )
            
            # Calculate liquidation price
            validated_data['liquidation_price'] = calculate_liquidation_price(
                entry_price, leverage, position_type
            )
            
            # Set is_open based on exit_price
            if validated_data.get('exit_price') is not None:
                validated_data['is_open'] = False
                # Set close_date if not provided
                if 'close_date' not in validated_data or validated_data['close_date'] is None:
                    from django.utils import timezone
                    validated_data['close_date'] = timezone.now()
            else:
                validated_data['is_open'] = True
                validated_data['close_date'] = None
        
        # SPOT: Set defaults and copy prices for backward compatibility
        elif position_type == 'spot':
            validated_data['is_open'] = False
            validated_data['leverage'] = 1.0
            validated_data['liquidation_price'] = None
            
            # Copy entry_price to buy_price for backward compatibility
            if 'entry_price' in validated_data and validated_data['entry_price'] is not None:
                validated_data['buy_price'] = validated_data['entry_price']
            
            # Copy exit_price to sell_price for backward compatibility
            if 'exit_price' in validated_data and validated_data['exit_price'] is not None:
                validated_data['sell_price'] = validated_data['exit_price']
            
            # Calculate collateral if not provided
            if 'collateral' not in validated_data or validated_data['collateral'] is None:
                entry_price = validated_data.get('entry_price') or validated_data.get('buy_price')
                quantity = validated_data.get('quantity', 0)
                if entry_price and quantity:
                    validated_data['collateral'] = entry_price * quantity
        
        # Create trade
        trade = Trade.objects.create(**validated_data)
        
        # Create emotion links
        for emotion_tag_id in emotion_tag_ids:
            TradeEmotion.objects.create(
                trade=trade,
                emotion_tag_id=emotion_tag_id
            )
        
        return trade

    def update(self, instance, validated_data):
        """Update trade with proper long/short handling"""
        emotion_tag_ids = validated_data.pop('emotion_tag_ids', None)
        position_type = validated_data.get('position_type', instance.position_type)
        
        # LONG/SHORT: Auto-calculate quantity from collateral if relevant fields changed
        if position_type in ['long', 'short']:
            collateral = validated_data.get('collateral', instance.collateral)
            leverage = validated_data.get('leverage', instance.leverage)
            entry_price = validated_data.get('entry_price', instance.entry_price)
            
            # Recalculate quantity if any of these changed
            if ('collateral' in validated_data or 'leverage' in validated_data or 
                'entry_price' in validated_data):
                validated_data['quantity'] = calculate_quantity_from_collateral(
                    collateral, leverage, entry_price
                )
            
            # Recalculate liquidation price if entry_price or leverage changed
            if 'entry_price' in validated_data or 'leverage' in validated_data:
                validated_data['liquidation_price'] = calculate_liquidation_price(
                    entry_price, leverage, position_type
                )
            
            # Handle is_open and exit_price relationship
            # Priority: explicit is_open value from frontend
            if 'is_open' in validated_data:
                # Frontend explicitly set is_open
                if not validated_data['is_open']:
                    # Position is being closed
                    if instance.close_date is None and 'close_date' not in validated_data:
                        from django.utils import timezone
                        validated_data['close_date'] = timezone.now()
                else:
                    # Position is being opened/kept open
                    validated_data['close_date'] = None
            elif 'exit_price' in validated_data:
                # No explicit is_open, infer from exit_price
                if validated_data['exit_price'] is not None:
                    validated_data['is_open'] = False
                    if instance.close_date is None:
                        from django.utils import timezone
                        validated_data['close_date'] = timezone.now()
                else:
                    validated_data['is_open'] = True
                    validated_data['close_date'] = None
        
        # SPOT: Maintain backward compatibility
        elif position_type == 'spot':
            validated_data['is_open'] = False
            validated_data['leverage'] = 1.0
            validated_data['liquidation_price'] = None
            
            # Sync entry_price with buy_price
            if 'entry_price' in validated_data:
                validated_data['buy_price'] = validated_data['entry_price']
            if 'buy_price' in validated_data:
                validated_data['entry_price'] = validated_data['buy_price']
            
            # Sync exit_price with sell_price
            if 'exit_price' in validated_data:
                validated_data['sell_price'] = validated_data['exit_price']
            if 'sell_price' in validated_data:
                validated_data['exit_price'] = validated_data['sell_price']
        
        # Update trade fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update emotions if provided
        if emotion_tag_ids is not None:
            instance.emotions.all().delete()
            for emotion_tag_id in emotion_tag_ids:
                TradeEmotion.objects.create(
                    trade=instance,
                    emotion_tag_id=emotion_tag_id
                )
        
        return instance


class FundingFeeLogSerializer(serializers.ModelSerializer):
    trade_id = serializers.IntegerField(write_only=True, source='trade.id')
    
    class Meta:
        model = FundingFeeLog
        fields = ['id', 'trade_id', 'fee_amount', 'fee_rate', 'timestamp']
        read_only_fields = ['id']


class TradeSummarySerializer(serializers.Serializer):
    total_trades = serializers.IntegerField()
    closed_trades = serializers.IntegerField()
    open_trades = serializers.IntegerField()
    winning_trades = serializers.IntegerField()
    win_rate = serializers.FloatField()
    total_realized_pnl = serializers.FloatField()
    total_fees = serializers.FloatField()
    avg_hold_time_days = serializers.FloatField()


class UserSerializers(serializers.ModelSerializer):
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'id', 
            'username', 
            'first_name', 
            'last_name', 
            'email',
            'password',
            'confirm_password'
        ]
        extra_kwargs = {
            'password': {'write_only': True}
        }

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = User.objects.create_user(**validated_data)
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            'username',
            'email',
            'first_name',
            'last_name',
            'display_name',
            'bio',
            'profile_photo_url',
            'currency',
            'timezone',
            'member_since',
        ]
        read_only_fields = [
            'username',
            'email',
            'first_name',
            'last_name',
            'member_since',
        ]


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            'display_name',
            'bio',
            'profile_photo_url',
            'currency',
            'timezone',
        ]


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        user = self.context['request'].user
        
        if not user.check_password(data['current_password']):
            raise serializers.ValidationError({
                'current_password': 'Current password is incorrect.'
            })
        
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': 'New passwords do not match.'
            })
        
        if user.check_password(data['new_password']):
            raise serializers.ValidationError({
                'new_password': 'New password must be different from current password.'
            })
        
        if len(data['new_password']) < 8:
            raise serializers.ValidationError({
                'new_password': 'Password must be at least 8 characters long.'
            })
        
        return data


class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = [
            'id',
            'device_id',
            'browser',
            'os',
            'ip_address',
            'location',
            'created_at',
            'last_active',
            'is_current',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'last_active',
        ]


class RefreshTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefreshToken
        fields = [
            'id',
            'token_suffix',
            'created_at',
            'expires_at',
            'revoked_at',
            'last_used',
        ]
        read_only_fields = [
            'id',
            'token_suffix',
            'created_at',
            'expires_at',
            'revoked_at',
            'last_used',
        ]


# ─── Portfolio Serializers ────────────────────────────────────────
class CoinHoldingSerializer(serializers.Serializer):
    """Represents one coin holding in the portfolio"""
    coin_id = serializers.IntegerField()
    symbol = serializers.CharField()
    name = serializers.CharField()
    coingecko_id = serializers.CharField()
    total_quantity = serializers.FloatField()
    avg_buy_price = serializers.FloatField()
    cost_basis = serializers.FloatField()
    live_price = serializers.FloatField()
    change_24h = serializers.FloatField()
    current_value = serializers.FloatField()
    unrealized_pnl = serializers.FloatField()
    unrealized_pnl_pct = serializers.FloatField()
    allocation_pct = serializers.FloatField()


class PortfolioSummarySerializer(serializers.Serializer):
    """Represents the top-level portfolio metrics"""
    total_value = serializers.FloatField()
    total_cost = serializers.FloatField()
    total_unrealized_pnl = serializers.FloatField()
    total_unrealized_pct = serializers.FloatField()
    active_positions = serializers.IntegerField()
    last_updated = serializers.CharField()


class PortfolioResponseSerializer(serializers.Serializer):
    """The full response shape for the portfolio endpoint"""
    summary = PortfolioSummarySerializer()
    holdings = CoinHoldingSerializer(many=True)
    prices_live = serializers.BooleanField()
    warning = serializers.CharField(allow_null=True)


# ─── Emotion Journal Serializers ──────────────────────────────────
class EmotionStatSerializer(serializers.Serializer):
    """Represents one emotion tag with aggregated stats"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    color = serializers.CharField()
    trade_count = serializers.IntegerField()
    closed_count = serializers.IntegerField()
    win_rate = serializers.FloatField()
    avg_pnl = serializers.FloatField()
    total_pnl = serializers.FloatField()


class EmotionTradeSerializer(serializers.Serializer):
    """Represents one trade in the emotion journal timeline"""
    id = serializers.IntegerField()
    date = serializers.CharField()
    trade_date = serializers.CharField()
    trade_type = serializers.CharField()
    coin_symbol = serializers.CharField()
    coin_name = serializers.CharField()
    emotion_name = serializers.CharField()
    emotion_color = serializers.CharField()
    emotion_id = serializers.IntegerField(allow_null=True)
    realized_pnl = serializers.FloatField(allow_null=True)
    is_open = serializers.BooleanField()
    notes = serializers.CharField()


class PatternInsightSerializer(serializers.Serializer):
    """Represents one auto-generated insight"""
    type = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()


class HeatmapDaySerializer(serializers.Serializer):
    """Represents one day cell in the activity heatmap"""
    date = serializers.CharField()
    trade_count = serializers.IntegerField()
    intensity = serializers.IntegerField()


class EmotionJournalSerializer(serializers.Serializer):
    """The full response envelope for emotion journal"""
    emotion_stats = EmotionStatSerializer(many=True)
    trades = EmotionTradeSerializer(many=True)
    insights = PatternInsightSerializer(many=True)
    heatmap = HeatmapDaySerializer(many=True)
    available_years = serializers.ListField(child=serializers.IntegerField())
    selected_year = serializers.IntegerField()


# ─── P&L Analysis Serializers ─────────────────────────────────────
class PnlSummarySerializer(serializers.Serializer):
    """The top metrics strip"""
    realized_pnl = serializers.FloatField()
    win_rate = serializers.FloatField()
    avg_win = serializers.FloatField()
    avg_loss = serializers.FloatField()
    profit_factor = serializers.FloatField()
    total_trades = serializers.IntegerField()
    closed_trades = serializers.IntegerField()
    winning_trades = serializers.IntegerField()
    losing_trades = serializers.IntegerField()
    breakeven_trades = serializers.IntegerField()


class CumulativePnlPointSerializer(serializers.Serializer):
    """One point on the cumulative P&L line chart"""
    date = serializers.CharField()
    realized_pnl = serializers.FloatField()
    cumulative_pnl = serializers.FloatField()
    trade_id = serializers.IntegerField()
    coin_symbol = serializers.CharField()
    trade_type = serializers.CharField()


class MonthlyPnlSerializer(serializers.Serializer):
    """One bar in the monthly P&L bar chart"""
    label = serializers.CharField()
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    realized_pnl = serializers.FloatField()
    is_profit = serializers.BooleanField()


class CoinPnlSerializer(serializers.Serializer):
    """One row in the P&L by coin section"""
    coin_id = serializers.IntegerField()
    symbol = serializers.CharField()
    name = serializers.CharField()
    realized_pnl = serializers.FloatField()
    trade_count = serializers.IntegerField()
    is_profit = serializers.BooleanField()


class WinLossRatioSerializer(serializers.Serializer):
    """The donut chart data"""
    winning_count = serializers.IntegerField()
    losing_count = serializers.IntegerField()
    breakeven_count = serializers.IntegerField()
    winning_pct = serializers.FloatField()
    losing_pct = serializers.FloatField()
    breakeven_pct = serializers.FloatField()


class FeeImpactSerializer(serializers.Serializer):
    """The fee impact section"""
    total_fees = serializers.FloatField()
    gross_profits = serializers.FloatField()
    fee_impact_pct = serializers.FloatField()


class TopTradeSerializer(serializers.Serializer):
    """One row in top wins or top losses"""
    trade_id = serializers.IntegerField()
    trade_type = serializers.CharField()
    coin_symbol = serializers.CharField()
    coin_name = serializers.CharField()
    date = serializers.CharField()
    realized_pnl = serializers.FloatField()
    quantity = serializers.FloatField()
    buy_price = serializers.FloatField()
    sell_price = serializers.FloatField()


class PnlAnalysisSerializer(serializers.Serializer):
    """The full response envelope"""
    summary = PnlSummarySerializer()
    cumulative_pnl = CumulativePnlPointSerializer(many=True)
    monthly_pnl = MonthlyPnlSerializer(many=True)
    pnl_by_coin = CoinPnlSerializer(many=True)
    win_loss_ratio = WinLossRatioSerializer()
    fee_impact = FeeImpactSerializer()
    top_wins = TopTradeSerializer(many=True)
    top_losses = TopTradeSerializer(many=True)


# ─── Monthly Report Serializers ───────────────────────────────────
class MonthlyReportMetricsSerializer(serializers.Serializer):
    """The five metric cards for the selected month"""
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    month_label = serializers.CharField()
    realized_pnl = serializers.FloatField()
    win_rate = serializers.FloatField()
    total_trades = serializers.IntegerField()
    spot_trades = serializers.IntegerField()
    leverage_trades = serializers.IntegerField()
    closed_trades = serializers.IntegerField()
    winning_trades = serializers.IntegerField()
    losing_trades = serializers.IntegerField()
    total_fees = serializers.FloatField()
    fees_pct_of_pnl = serializers.FloatField()
    avg_pnl_per_trade = serializers.FloatField()
    avg_hold_time_days = serializers.FloatField()
    largest_win = serializers.FloatField()
    largest_loss = serializers.FloatField()
    profit_factor = serializers.FloatField()


class MonthTradeSerializer(serializers.Serializer):
    """One row in the 'this month's trades' list"""
    id = serializers.IntegerField()
    date = serializers.CharField()
    trade_type = serializers.CharField()
    coin_symbol = serializers.CharField()
    coin_name = serializers.CharField()
    quantity = serializers.FloatField()
    buy_price = serializers.FloatField(allow_null=True)
    sell_price = serializers.FloatField(allow_null=True)
    fee = serializers.FloatField()
    realized_pnl = serializers.FloatField(allow_null=True)
    is_open = serializers.BooleanField()
    emotions = serializers.ListField(child=serializers.DictField())
    notes = serializers.CharField()


class BestWorstTradeSerializer(serializers.Serializer):
    """The best and worst single trade of the month"""
    best_trade = MonthTradeSerializer(allow_null=True)
    worst_trade = MonthTradeSerializer(allow_null=True)


class MonthCoinPnlSerializer(serializers.Serializer):
    """One row in the P&L by coin chart"""
    coin_id = serializers.IntegerField()
    symbol = serializers.CharField()
    name = serializers.CharField()
    realized_pnl = serializers.FloatField()
    trade_count = serializers.IntegerField()
    is_profit = serializers.BooleanField()


class MonthlyBarSerializer(serializers.Serializer):
    """One bar in the monthly P&L bar chart and one row in the report history table"""
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    month_label = serializers.CharField()
    realized_pnl = serializers.FloatField()
    win_rate = serializers.FloatField()
    total_trades = serializers.IntegerField()
    winning_trades = serializers.IntegerField()
    is_profit = serializers.BooleanField()


class CumulativeMonthlyPnlSerializer(serializers.Serializer):
    """One point on the cumulative P&L line chart"""
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    month_label = serializers.CharField()
    monthly_pnl = serializers.FloatField()
    cumulative_pnl = serializers.FloatField()


class MonthlyReportResponseSerializer(serializers.Serializer):
    """Full response envelope for one selected month"""
    metrics = MonthlyReportMetricsSerializer()
    trades = MonthTradeSerializer(many=True)
    best_worst = BestWorstTradeSerializer()
    pnl_by_coin = MonthCoinPnlSerializer(many=True)
    monthly_bars = MonthlyBarSerializer(many=True)
    cumulative_pnl = CumulativeMonthlyPnlSerializer(many=True)
    available_months = serializers.ListField(child=serializers.DictField())


# ─── AI Feedback Serializers ──────────────────────────────────────
class AIFeedbackScoresSerializer(serializers.Serializer):
    """Scores section of AI feedback"""
    discipline = serializers.IntegerField()
    risk_mgmt = serializers.IntegerField()
    consistency = serializers.IntegerField()


class AIFeedbackSectionSerializer(serializers.Serializer):
    """One section in whats_working or whats_hurting"""
    title = serializers.CharField()
    body = serializers.CharField()


class AIFeedbackParsedSerializer(serializers.Serializer):
    """The parsed feedback_text JSON"""
    overall = serializers.CharField()
    scores = AIFeedbackScoresSerializer()
    whats_working = AIFeedbackSectionSerializer(many=True)
    whats_hurting = AIFeedbackSectionSerializer(many=True)
    one_thing_to_fix = serializers.CharField()


class AIFeedbackSerializer(serializers.ModelSerializer):
    """Full AI feedback record with parsed JSON"""
    feedback_parsed = serializers.SerializerMethodField()
    
    class Meta:
        model = AIFeedback
        fields = ['id', 'prompt_summary', 'feedback_parsed', 'created_at', 'month_label']
        read_only_fields = ['id', 'created_at']
    
    def get_feedback_parsed(self, obj):
        """Parse the JSON feedback_text field"""
        import json
        try:
            parsed = json.loads(obj.feedback_text)
            return AIFeedbackParsedSerializer(parsed).data
        except (json.JSONDecodeError, ValueError):
            return None


class AIFeedbackPreviewSerializer(serializers.Serializer):
    """Preview of what will be analyzed"""
    total_trades = serializers.IntegerField()
    closed_trades = serializers.IntegerField()
    winning_trades = serializers.IntegerField()
    win_rate = serializers.FloatField()
    realized_pnl = serializers.FloatField()
    emotions_tagged = serializers.IntegerField()
    has_enough_data = serializers.BooleanField()


# ─── Dashboard Serializers ────────────────────────────────────────
class DashboardMetricsSerializer(serializers.Serializer):
    """The four metric cards at the top of the dashboard"""
    portfolio_value = serializers.FloatField()
    realized_pnl = serializers.FloatField()
    unrealized_pnl = serializers.FloatField()
    unrealized_pct = serializers.FloatField()
    win_rate = serializers.FloatField()
    winning_trades = serializers.IntegerField()
    closed_trades = serializers.IntegerField()
    winning_label = serializers.CharField()
    unrealized_label = serializers.CharField()
    realized_label = serializers.CharField()


class DashboardHoldingSerializer(serializers.Serializer):
    """One row in the current holdings table"""
    coin_id = serializers.IntegerField()
    symbol = serializers.CharField()
    name = serializers.CharField()
    coingecko_id = serializers.CharField()
    total_quantity = serializers.FloatField()
    avg_buy_price = serializers.FloatField()
    live_price = serializers.FloatField()
    current_value = serializers.FloatField()
    unrealized_pnl = serializers.FloatField()
    unrealized_pnl_pct = serializers.FloatField()


class DashboardEmotionSerializer(serializers.Serializer):
    """One row in the emotion breakdown"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    color = serializers.CharField()
    trade_count = serializers.IntegerField()
    percentage = serializers.FloatField()


class DashboardRecentTradeSerializer(serializers.Serializer):
    """One row in the recent trades list"""
    id = serializers.IntegerField()
    trade_type = serializers.CharField()
    coin_symbol = serializers.CharField()
    coin_name = serializers.CharField()
    quantity = serializers.FloatField()
    price = serializers.FloatField()
    trade_date = serializers.CharField()
    emotion_name = serializers.CharField(allow_null=True)
    emotion_color = serializers.CharField(allow_null=True)
    position_type = serializers.CharField()
    is_open = serializers.BooleanField()


class DashboardAISnippetSerializer(serializers.Serializer):
    """AI feedback snippet for the dashboard"""
    id = serializers.IntegerField(allow_null=True)
    overall = serializers.CharField(allow_null=True)
    month_label = serializers.CharField(allow_null=True)
    created_at = serializers.CharField(allow_null=True)


class DashboardResponseSerializer(serializers.Serializer):
    """The full dashboard response envelope"""
    metrics = DashboardMetricsSerializer()
    holdings = DashboardHoldingSerializer(many=True)
    emotions = DashboardEmotionSerializer(many=True)
    recent_trades = DashboardRecentTradeSerializer(many=True)
    ai_snippet = DashboardAISnippetSerializer()
    prices_live = serializers.BooleanField()
    warning = serializers.CharField(allow_null=True)
    last_updated = serializers.CharField()


# ─── Danger Zone Serializers ──────────────────────────────────────
class DangerZoneStatusSerializer(serializers.Serializer):
    """Returns counts of what will be deleted"""
    trade_count = serializers.IntegerField()
    snapshot_count = serializers.IntegerField()
    report_count = serializers.IntegerField()
    ai_feedback_count = serializers.IntegerField()
    trade_emotion_count = serializers.IntegerField()


class ConfirmDeleteSerializer(serializers.Serializer):
    """Validates typed confirmation from the frontend"""
    confirmation = serializers.CharField(required=True)


class AccountDeleteSerializer(serializers.Serializer):
    """Validates account deletion request"""
    username = serializers.CharField(required=True)
