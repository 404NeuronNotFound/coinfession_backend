"""
Quick test script for ML Trading Analyzer
Run this to verify the ML analyzer works before integrating
"""
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from api.models import Trade
from api.ml_trading_analyzer import MLTradingAnalyzer
from django.contrib.auth import get_user_model

User = get_user_model()

# Get a user with trades
user = User.objects.first()
if not user:
    print("No users found. Create a user first.")
    exit()

print(f"Testing ML analyzer for user: {user.username}")

# Get user's trades
trades = Trade.objects.filter(user=user).order_by('trade_date')
print(f"Found {trades.count()} trades")

if trades.count() < 10:
    print(f"Warning: Only {trades.count()} trades. ML requires at least 10 closed trades.")
    print("The analyzer will return a 'not enough data' message.")

# Create analyzer
print("\nInitializing ML Trading Analyzer...")
analyzer = MLTradingAnalyzer(trades)

# Generate feedback
print("Generating ML-enhanced feedback...")
feedback_json = analyzer.generate_feedback()

# Parse and display
import json
feedback = json.loads(feedback_json)

print("\n" + "="*60)
print("ML TRADING ANALYZER RESULTS")
print("="*60)

print(f"\nModel Status: {feedback.get('model_info', {}).get('status', 'N/A')}")
print(f"Trades Used: {feedback.get('model_info', {}).get('trades_used', 0)}")

if feedback.get('model_info', {}).get('cross_validation'):
    cv_auc = feedback['model_info']['cross_validation'].get('win_clf_auc', 0)
    print(f"Model Accuracy (AUC): {cv_auc:.1%}")

print(f"\nOverall Assessment:")
print(feedback.get('overall', 'N/A'))

print(f"\nScores:")
scores = feedback.get('scores', {})
print(f"  Discipline: {scores.get('discipline', 0)}/10")
print(f"  Risk Management: {scores.get('risk_mgmt', 0)}/10")
print(f"  Consistency: {scores.get('consistency', 0)}/10")

if feedback.get('model_info', {}).get('feature_importances'):
    print(f"\nTop 3 Feature Importances:")
    for i, (feature, importance) in enumerate(list(feedback['model_info']['feature_importances'].items())[:3], 1):
        print(f"  {i}. {feature}: {importance:.3f}")

if feedback.get('model_info', {}).get('emotion_clusters'):
    print(f"\nEmotion Clusters:")
    for emotion, cluster in feedback['model_info']['emotion_clusters'].items():
        print(f"  {emotion}: {cluster}")

print(f"\nTop Priority Fix:")
print(f"  {feedback.get('one_thing_to_fix', 'N/A')}")

print("\n" + "="*60)
print("Test completed successfully!")
print("="*60)
