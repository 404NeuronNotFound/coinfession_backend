from django.contrib import admin
from .models import Coin, Trade, EmotionTag, TradeEmotion, PortfolioSnapshot, MonthlyReport, AIFeedback


# Register your models here.
admin.site.register(Coin)
admin.site.register(Trade)
admin.site.register(EmotionTag)
admin.site.register(TradeEmotion)
admin.site.register(PortfolioSnapshot)
admin.site.register(MonthlyReport)
admin.site.register(AIFeedback)
