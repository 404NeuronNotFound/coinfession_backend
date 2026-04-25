from django.contrib.auth.models import User
from rest_framework import serializers
from .models import (
    UserProfile, UserSession, RefreshToken, Coin, EmotionTag, 
    TradeEmotion, Trade
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
            if trade.sell_price is not None and trade.buy_price is not None:
                realized_pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
                closed_trades.append(realized_pnl)
        
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
            if trade.sell_price is not None and trade.buy_price is not None:
                realized_pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
                closed_pnls.append(realized_pnl)
        
        if not closed_pnls:
            return 0.0
        
        avg = sum(closed_pnls) / len(closed_pnls)
        return round(avg, 2)


class EmotionTagWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmotionTag
        fields = ['id', 'name', 'color']

    def validate_name(self, value):
        """Validate name is not empty and is unique (case-insensitive)"""
        value = value.strip()
        
        if not value:
            raise serializers.ValidationError("Name cannot be empty")
        
        # Check for duplicate name (case-insensitive)
        queryset = EmotionTag.objects.filter(name__iexact=value)
        
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
        required=False
    )
    realized_pnl = serializers.SerializerMethodField()
    is_open = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = [
            'id', 'coin', 'coin_id', 'trade_type', 'quantity',
            'buy_price', 'sell_price', 'fee', 'trade_date', 'notes',
            'emotions', 'emotion_tag_ids', 'realized_pnl', 'is_open',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_realized_pnl(self, obj):
        if obj.sell_price is None or obj.buy_price is None:
            return None
        return (obj.sell_price - obj.buy_price) * obj.quantity - obj.fee

    def get_is_open(self, obj):
        return obj.sell_price is None

    def create(self, validated_data):
        emotion_tag_ids = validated_data.pop('emotion_tag_ids', [])
        trade = Trade.objects.create(**validated_data)
        
        for emotion_tag_id in emotion_tag_ids:
            TradeEmotion.objects.create(
                trade=trade,
                emotion_tag_id=emotion_tag_id
            )
        
        return trade

    def update(self, instance, validated_data):
        emotion_tag_ids = validated_data.pop('emotion_tag_ids', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if emotion_tag_ids is not None:
            instance.emotions.all().delete()
            for emotion_tag_id in emotion_tag_ids:
                TradeEmotion.objects.create(
                    trade=instance,
                    emotion_tag_id=emotion_tag_id
                )
        
        return instance


class TradeSummarySerializer(serializers.Serializer):
    total_trades = serializers.IntegerField()
    closed_trades = serializers.IntegerField()
    open_trades = serializers.IntegerField()
    winning_trades = serializers.IntegerField()
    win_rate = serializers.FloatField()
    total_realized_pnl = serializers.FloatField()
    total_fees = serializers.FloatField()


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
