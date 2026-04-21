from django.db import models
from django.contrib.auth.models import User


class Coin(models.Model):
    symbol = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    coingecko_id = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return f"{self.name} ({self.symbol})"

    class Meta:
        db_table = 'coin'


class Trade(models.Model):
    TRADE_TYPE_CHOICES = [
        ('buy', 'Buy'),
        ('sell', 'Sell'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trades')
    coin = models.ForeignKey(Coin, on_delete=models.CASCADE, related_name='trades')
    trade_type = models.CharField(max_length=10, choices=TRADE_TYPE_CHOICES)
    quantity = models.FloatField()
    buy_price = models.FloatField(null=True, blank=True)
    sell_price = models.FloatField(null=True, blank=True)
    fee = models.FloatField(default=0.0)
    trade_date = models.DateTimeField()
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.trade_type.upper()} {self.quantity} {self.coin.symbol} by {self.user.username}"

    class Meta:
        db_table = 'trade'


class EmotionTag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=20)

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'emotion_tag'


class TradeEmotion(models.Model):
    trade = models.ForeignKey(Trade, on_delete=models.CASCADE, related_name='emotions')
    emotion_tag = models.ForeignKey(EmotionTag, on_delete=models.CASCADE, related_name='trade_emotions')

    def __str__(self):
        return f"{self.trade} — {self.emotion_tag}"

    class Meta:
        db_table = 'trade_emotion'
        unique_together = ('trade', 'emotion_tag')


class PortfolioSnapshot(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='portfolio_snapshots')
    coin = models.ForeignKey(Coin, on_delete=models.CASCADE, related_name='portfolio_snapshots')
    total_quantity = models.FloatField()
    avg_buy_price = models.FloatField()
    unrealized_pnl = models.FloatField()
    snapshot_date = models.DateTimeField()

    def __str__(self):
        return f"Snapshot: {self.user.username} — {self.coin.symbol} @ {self.snapshot_date}"

    class Meta:
        db_table = 'portfolio_snapshot'


class MonthlyReport(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='monthly_reports')
    year = models.IntegerField()
    month = models.IntegerField()
    total_realized_pnl = models.FloatField()
    win_rate = models.FloatField()
    total_trades = models.IntegerField()
    winning_trades = models.IntegerField()
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report: {self.user.username} — {self.year}/{self.month:02d}"

    class Meta:
        db_table = 'monthly_report'
        unique_together = ('user', 'year', 'month')


class AIFeedback(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_feedbacks')
    prompt_summary = models.TextField()
    feedback_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AI Feedback for {self.user.username} @ {self.created_at}"

    class Meta:
        db_table = 'ai_feedback'


class APIKey(models.Model):
    user      = models.ForeignKey(User, on_delete=models.CASCADE)
    provider  = models.CharField(max_length=50)  # 'anthropic', 'coingecko'
    key_encrypted = models.TextField()            # AES-256 encrypted
    key_suffix    = models.CharField(max_length=4) # last 4 chars, stored plain
    plan      = models.CharField(max_length=20, default='unknown')
    last_used = models.DateTimeField(null=True)
    created_at= models.DateTimeField(auto_now_add=True)


class UserPreference(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    require_emotion_tag   = models.BooleanField(default=True)
    require_notes         = models.BooleanField(default=False)
    default_trade_type    = models.CharField(max_length=4, default='BUY')
    default_fee_rate      = models.DecimalField(max_digits=5, decimal_places=2, default=0.10)
    confirm_before_save   = models.BooleanField(default=False)
    default_date          = models.CharField(max_length=20, default='today')
    ai_tone               = models.CharField(max_length=20, default='direct_kind')
    auto_generate_ai      = models.BooleanField(default=False)
    ai_include_notes      = models.BooleanField(default=True)
    ai_context_months     = models.IntegerField(default=3)
    pnl_format            = models.CharField(max_length=10, default='dollar')
    decimal_places        = models.IntegerField(default=4)
    dashboard_period      = models.CharField(max_length=5, default='1m')
    show_unrealized       = models.BooleanField(default=True)
    notify_monthly        = models.BooleanField(default=True)
    notify_untagged       = models.BooleanField(default=True)
    notify_weekly         = models.BooleanField(default=False)
    notification_email    = models.EmailField(blank=True, null=True)


class DataTransferLog(models.Model):
    EXPORT = 'export'
    IMPORT = 'import'
    TYPE_CHOICES = [(EXPORT,'Export'),(IMPORT,'Import')]

    user        = models.ForeignKey(User, on_delete=models.CASCADE)
    type        = models.CharField(max_length=10, choices=TYPE_CHOICES)
    filename    = models.CharField(max_length=255)
    result      = models.TextField()
    status      = models.CharField(max_length=10)  # 'ok', 'error'
    created_at  = models.DateTimeField(auto_now_add=True)