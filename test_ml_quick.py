"""Quick test to verify ML imports work"""
import sys
import os

# Add the project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("Testing ML imports...")
    import pandas as pd
    print("✓ pandas imported")
    
    import numpy as np
    print("✓ numpy imported")
    
    from sklearn.ensemble import RandomForestClassifier
    print("✓ sklearn imported")
    
    print("\nTesting ML analyzer import...")
    from api.ml_trading_analyzer import MLTradingAnalyzer, MIN_TRADES_FOR_ML
    print(f"✓ MLTradingAnalyzer imported (MIN_TRADES_FOR_ML = {MIN_TRADES_FOR_ML})")
    
    print("\n✅ All ML dependencies are working!")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
