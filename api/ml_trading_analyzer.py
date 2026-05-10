"""
ML-Enhanced Trading Analyzer
Uses scikit-learn to predict trade outcomes and provide data-driven insights
Drop-in replacement for ai_analyzer.py with machine learning capabilities
"""
import json
import warnings
from datetime import datetime
from collections import defaultdict
import statistics

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.cluster import KMeans
from sklearn.model_selection import cross_val_score

warnings.filterwarnings("ignore")

MIN_TRADES_FOR_ML = 10


class TradeFeatureBuilder:
    """Converts trade objects into numeric feature matrix for sklearn"""
    
    def __init__(self):
        self.coin_encoder = LabelEncoder()
        self.position_encoder = LabelEncoder()
        self.emotion_encoder = LabelEncoder()
        self.feature_cols_ = None
    
    def fit_transform(self, trades):
        """Convert trades to DataFrame with features and targets"""
        if not trades:
            return pd.DataFrame()
        
        rows = []
        for i, trade in enumerate(trades):
            # Calculate P&L
            if trade.position_type == 'spot':
                if trade.sell_price and trade.buy_price:
                    pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
                    is_win = pnl > 0
                else:
                    continue  # Skip open trades
            else:  # long or short
                if trade.exit_price and trade.entry_price:
                    if trade.position_type == 'long':
                        pnl = (trade.exit_price - trade.entry_price) * trade.quantity - trade.funding_fees
                    else:  # short
                        pnl = (trade.entry_price - trade.exit_price) * trade.quantity - trade.funding_fees
                    is_win = pnl > 0
                else:
                    continue  # Skip open trades
            
            # Extract features
            trade_date = trade.trade_date
            entry_price = trade.entry_price if trade.position_type != 'spot' else trade.buy_price
            
            # Get primary emotion
            emotions = list(trade.emotions.all())
            primary_emotion = emotions[0].emotion_tag.name if emotions else "None"
            
            # Calculate rolling metrics (no lookahead)
            past_trades = trades[:i]
            rolling_win_rate_5 = self._calculate_rolling_win_rate(past_trades, 5)
            rolling_pnl_5 = self._calculate_rolling_pnl(past_trades, 5)
            consecutive_losses = self._calculate_consecutive_losses(past_trades)
            
            # Trade size
            trade_size = entry_price * trade.quantity if entry_price else 0
            
            # Fee ratio
            total_fee = trade.fee if trade.position_type == 'spot' else trade.funding_fees
            fee_to_size_ratio = total_fee / trade_size if trade_size > 0 else 0
            
            row = {
                'hour_of_day': trade_date.hour,
                'day_of_week': trade_date.weekday(),
                'position_type': trade.position_type,
                'coin': trade.coin.symbol,
                'emotion': primary_emotion,
                'trade_size': trade_size,
                'leverage_flag': 1 if trade.position_type in ['long', 'short'] else 0,
                'rolling_win_rate_5': rolling_win_rate_5,
                'rolling_pnl_5': rolling_pnl_5,
                'consecutive_losses': consecutive_losses,
                'fee_to_size_ratio': fee_to_size_ratio,
                '_pnl': pnl,
                '_is_win': int(is_win),
                '_trade_obj': trade  # Keep reference for later
            }
            rows.append(row)
        
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        
        # Encode categorical features
        df['position_type_enc'] = self.position_encoder.fit_transform(df['position_type'])
        df['coin_enc'] = self.coin_encoder.fit_transform(df['coin'])
        df['emotion_enc'] = self.emotion_encoder.fit_transform(df['emotion'])
        
        # Define feature columns
        self.feature_cols_ = [
            'hour_of_day', 'day_of_week', 'position_type_enc', 'coin_enc', 
            'emotion_enc', 'trade_size', 'leverage_flag', 'rolling_win_rate_5',
            'rolling_pnl_5', 'consecutive_losses', 'fee_to_size_ratio'
        ]
        
        return df
    
    def transform_single(self, trade, pnl_history, loss_streak):
        """Transform a single trade for prediction"""
        trade_date = trade.trade_date
        entry_price = trade.entry_price if trade.position_type != 'spot' else trade.buy_price
        
        # Get primary emotion
        emotions = list(trade.emotions.all())
        primary_emotion = emotions[0].emotion_tag.name if emotions else "None"
        
        # Trade size
        trade_size = entry_price * trade.quantity if entry_price else 0
        
        # Fee ratio
        total_fee = trade.fee if trade.position_type == 'spot' else trade.funding_fees
        fee_to_size_ratio = total_fee / trade_size if trade_size > 0 else 0
        
        # Rolling metrics from history
        if len(pnl_history) >= 5:
            recent_5 = pnl_history[-5:]
            rolling_win_rate_5 = sum(1 for p in recent_5 if p > 0) / len(recent_5)
            rolling_pnl_5 = sum(recent_5)
        else:
            rolling_win_rate_5 = 0.5
            rolling_pnl_5 = 0
        
        row = {
            'hour_of_day': trade_date.hour,
            'day_of_week': trade_date.weekday(),
            'trade_size': trade_size,
            'leverage_flag': 1 if trade.position_type in ['long', 'short'] else 0,
            'rolling_win_rate_5': rolling_win_rate_5,
            'rolling_pnl_5': rolling_pnl_5,
            'consecutive_losses': loss_streak,
            'fee_to_size_ratio': fee_to_size_ratio,
        }
        
        # Encode with fallback for unseen labels
        try:
            row['position_type_enc'] = self.position_encoder.transform([trade.position_type])[0]
        except:
            row['position_type_enc'] = 0
        
        try:
            row['coin_enc'] = self.coin_encoder.transform([trade.coin.symbol])[0]
        except:
            row['coin_enc'] = 0
        
        try:
            row['emotion_enc'] = self.emotion_encoder.transform([primary_emotion])[0]
        except:
            row['emotion_enc'] = 0
        
        return pd.DataFrame([row])[self.feature_cols_]
    
    @property
    def feature_cols(self):
        return self.feature_cols_
    
    def _calculate_rolling_win_rate(self, past_trades, window):
        """Calculate win rate of last N trades"""
        if len(past_trades) < window:
            return 0.5  # Default
        
        recent = past_trades[-window:]
        wins = 0
        for t in recent:
            if t.position_type == 'spot':
                if t.sell_price and t.buy_price:
                    pnl = (t.sell_price - t.buy_price) * t.quantity - t.fee
                    if pnl > 0:
                        wins += 1
            else:
                if t.exit_price and t.entry_price:
                    if t.position_type == 'long':
                        pnl = (t.exit_price - t.entry_price) * t.quantity - t.funding_fees
                    else:
                        pnl = (t.entry_price - t.exit_price) * t.quantity - t.funding_fees
                    if pnl > 0:
                        wins += 1
        
        return wins / window
    
    def _calculate_rolling_pnl(self, past_trades, window):
        """Calculate total P&L of last N trades"""
        if len(past_trades) < window:
            return 0
        
        recent = past_trades[-window:]
        total_pnl = 0
        for t in recent:
            if t.position_type == 'spot':
                if t.sell_price and t.buy_price:
                    total_pnl += (t.sell_price - t.buy_price) * t.quantity - t.fee
            else:
                if t.exit_price and t.entry_price:
                    if t.position_type == 'long':
                        total_pnl += (t.exit_price - t.entry_price) * t.quantity - t.funding_fees
                    else:
                        total_pnl += (t.entry_price - t.exit_price) * t.quantity - t.funding_fees
        
        return total_pnl
    
    def _calculate_consecutive_losses(self, past_trades):
        """Count consecutive losses before this trade"""
        count = 0
        for t in reversed(past_trades):
            if t.position_type == 'spot':
                if t.sell_price and t.buy_price:
                    pnl = (t.sell_price - t.buy_price) * t.quantity - t.fee
                    if pnl < 0:
                        count += 1
                    else:
                        break
            else:
                if t.exit_price and t.entry_price:
                    if t.position_type == 'long':
                        pnl = (t.exit_price - t.entry_price) * t.quantity - t.funding_fees
                    else:
                        pnl = (t.entry_price - t.exit_price) * t.quantity - t.funding_fees
                    if pnl < 0:
                        count += 1
                    else:
                        break
        return count



class PerTradeAnalyzer:
    """ML-enhanced per-trade analyzer"""
    
    def __init__(self, trade, feature_builder, win_classifier, pnl_regressor, anomaly_detector, scaler):
        self.trade = trade
        self.feature_builder = feature_builder
        self.win_classifier = win_classifier
        self.pnl_regressor = pnl_regressor
        self.anomaly_detector = anomaly_detector
        self.scaler = scaler
        self.pnl = self._calculate_pnl()
    
    def _calculate_pnl(self):
        """Calculate P&L for the trade"""
        if self.trade.position_type == 'spot':
            if self.trade.sell_price and self.trade.buy_price:
                return (self.trade.sell_price - self.trade.buy_price) * self.trade.quantity - self.trade.fee
            return 0
        else:  # long or short
            if self.trade.exit_price and self.trade.entry_price:
                if self.trade.position_type == 'long':
                    return (self.trade.exit_price - self.trade.entry_price) * self.trade.quantity - self.trade.funding_fees
                else:  # short
                    return (self.trade.entry_price - self.trade.exit_price) * self.trade.quantity - self.trade.funding_fees
            return 0
    
    def get_analysis(self, pnl_history, loss_streak):
        """Get ML-enhanced analysis for this trade"""
        emotions = [te.emotion_tag.name for te in self.trade.emotions.all()]
        
        # Get ML predictions
        ml_insights = self._get_ml_predictions(pnl_history, loss_streak)
        
        # Generate feedback based on ML vs actual
        feedback = self._generate_ml_feedback(ml_insights)
        
        # Determine recommendation
        recommendation = self._get_recommendation()
        
        return {
            'trade_id': self.trade.id,
            'coin': self.trade.coin.symbol,
            'position_type': self.trade.position_type.upper(),
            'trade_type': self.trade.trade_type.upper() if self.trade.position_type == 'spot' else self.trade.position_type.upper(),
            'entry_price': self.trade.entry_price or self.trade.buy_price,
            'exit_price': self.trade.exit_price or self.trade.sell_price,
            'quantity': self.trade.quantity,
            'pnl': round(self.pnl, 2),
            'pnl_percent': self._calculate_pnl_percent(),
            'emotions': emotions,
            'trade_date': self.trade.trade_date.isoformat(),
            'feedback': feedback,
            'recommendation': recommendation,
            'ml_insights': ml_insights
        }
    
    def _get_ml_predictions(self, pnl_history, loss_streak):
        """Get ML model predictions for this trade"""
        try:
            # Transform trade to features
            X = self.feature_builder.transform_single(self.trade, pnl_history, loss_streak)
            X_scaled = self.scaler.transform(X)
            
            # Win probability
            win_prob = self.win_classifier.predict_proba(X_scaled)[0][1]
            
            # Predicted P&L
            pred_pnl = self.pnl_regressor.predict(X_scaled)[0]
            
            # Anomaly detection
            anomaly_score = self.anomaly_detector.predict(X_scaled)[0]
            is_anomalous = anomaly_score == -1
            
            # Feature importances
            importances = dict(zip(
                self.feature_builder.feature_cols,
                self.win_classifier.feature_importances_
            ))
            top_features = dict(sorted(importances.items(), key=lambda x: x[1], reverse=True)[:3])
            
            return {
                'win_probability_at_entry': round(float(win_prob), 3),
                'predicted_pnl': round(float(pred_pnl), 2),
                'was_anomalous_setup': bool(is_anomalous),
                'top_influencing_features': top_features
            }
        except Exception as e:
            # Fallback on error
            return {
                'win_probability_at_entry': 0.5,
                'predicted_pnl': 0.0,
                'was_anomalous_setup': False,
                'top_influencing_features': {}
            }
    
    def _generate_ml_feedback(self, ml_insights):
        """Generate feedback comparing ML prediction vs actual outcome"""
        win_prob = ml_insights['win_probability_at_entry']
        actually_won = self.pnl > 0
        
        # Compare prediction vs reality
        if win_prob >= 0.5 and actually_won:
            feedback = f"Model agreed ({win_prob*100:.0f}% win probability) — good execution of a high-quality setup."
        elif win_prob >= 0.5 and not actually_won:
            feedback = f"Model expected a win ({win_prob*100:.0f}%) but you lost. Review execution."
        elif win_prob < 0.5 and actually_won:
            feedback = f"You won despite the model rating this low-probability ({win_prob*100:.0f}%). Log your reasoning."
        else:
            feedback = f"Model flagged this as low-probability ({win_prob*100:.0f}%) and it lost. Avoid similar conditions."
        
        # Add anomaly warning
        if ml_insights['was_anomalous_setup']:
            feedback += " ⚠ Anomaly detected — unusual profile vs your history."
        
        return feedback
    
    def _calculate_pnl_percent(self):
        """Calculate P&L percentage"""
        if self.trade.position_type == 'spot':
            entry = self.trade.buy_price
        else:
            entry = self.trade.entry_price
        
        if entry and entry > 0:
            if self.trade.position_type == 'spot':
                exit_price = self.trade.sell_price
            else:
                exit_price = self.trade.exit_price
            
            if exit_price:
                return round(((exit_price - entry) / entry) * 100, 2)
        return 0
    
    def _get_recommendation(self):
        """Get hold/sell recommendation"""
        if self.trade.position_type == 'spot':
            if self.trade.sell_price:
                return "CLOSED"
            else:
                if self.pnl > 0:
                    return "HOLD — profitable"
                else:
                    return "CONSIDER SELLING — underwater"
        else:
            if self.trade.is_open:
                if self.pnl > 0:
                    return "HOLD — profitable"
                else:
                    return "CONSIDER CLOSING — losing"
            else:
                return "CLOSED"



class MLTradingAnalyzer:
    """ML-enhanced trading analyzer - drop-in replacement for TradingAnalyzer"""
    
    def __init__(self, trades):
        self.trades = list(trades)
        self.closed_trades = self._get_closed_trades()
        self.feature_builder = TradeFeatureBuilder()
        
        # ML models (will be trained if enough data)
        self.win_classifier = None
        self.pnl_regressor = None
        self.anomaly_detector = None
        self.scaler = None
        self.emotion_clusters = {}
        self.feature_importances = {}
        self.cross_val_score = None
        
        # Train models if we have enough data
        self.model_trained = False
        if len(self.closed_trades) >= MIN_TRADES_FOR_ML:
            self._train_models()
        
        # Calculate stats (same as original)
        self.stats = self._calculate_comprehensive_stats()
    
    def _get_closed_trades(self):
        """Get only closed trades"""
        closed = []
        for t in self.trades:
            if t.position_type == 'spot':
                if t.sell_price and t.buy_price:
                    closed.append(t)
            else:
                if t.exit_price and t.entry_price and not t.is_open:
                    closed.append(t)
        return closed
    
    def _train_models(self):
        """Train all ML models on user's trade history"""
        try:
            # Build feature matrix
            df = self.feature_builder.fit_transform(self.closed_trades)
            
            if df.empty or len(df) < MIN_TRADES_FOR_ML:
                return
            
            X = df[self.feature_builder.feature_cols]
            y_win = df['_is_win']
            y_pnl = df['_pnl']
            
            # Scale features
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)
            
            # Train win/loss classifier
            self.win_classifier = RandomForestClassifier(
                n_estimators=200,
                max_depth=6,
                min_samples_leaf=2,
                class_weight='balanced',
                random_state=42
            )
            self.win_classifier.fit(X_scaled, y_win)
            
            # Store feature importances
            self.feature_importances = dict(sorted(
                zip(self.feature_builder.feature_cols, self.win_classifier.feature_importances_),
                key=lambda x: x[1],
                reverse=True
            ))
            
            # Cross-validation if enough data
            if len(df) >= 20:
                cv_folds = min(5, len(df) // 4)
                try:
                    cv_scores = cross_val_score(
                        self.win_classifier, X_scaled, y_win,
                        cv=cv_folds, scoring='roc_auc'
                    )
                    self.cross_val_score = float(np.mean(cv_scores))
                except:
                    self.cross_val_score = None
            
            # Train P&L regressor
            self.pnl_regressor = LinearRegression()
            self.pnl_regressor.fit(X_scaled, y_pnl)
            
            # Train anomaly detector
            self.anomaly_detector = IsolationForest(
                contamination=0.1,
                random_state=42
            )
            self.anomaly_detector.fit(X_scaled)
            
            # Cluster emotions by performance
            self._cluster_emotions(df)
            
            self.model_trained = True
            
        except Exception as e:
            print(f"Model training failed: {e}")
            self.model_trained = False
    
    def _cluster_emotions(self, df):
        """Cluster emotions by avg P&L and count"""
        emotion_stats = {}
        
        for emotion in df['emotion'].unique():
            emotion_df = df[df['emotion'] == emotion]
            emotion_stats[emotion] = {
                'avg_pnl': emotion_df['_pnl'].mean(),
                'count': len(emotion_df)
            }
        
        if len(emotion_stats) < 2:
            # Not enough emotions to cluster
            for emotion in emotion_stats:
                self.emotion_clusters[emotion] = "Neutral"
            return
        
        # Prepare data for clustering
        emotions_list = list(emotion_stats.keys())
        features = np.array([[stats['avg_pnl'], stats['count']] for stats in emotion_stats.values()])
        
        # Cluster
        n_clusters = min(3, len(emotions_list))
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        labels = kmeans.fit_predict(features)
        
        # Assign cluster names based on avg P&L
        cluster_pnls = {}
        for i in range(n_clusters):
            cluster_emotions = [emotions_list[j] for j in range(len(emotions_list)) if labels[j] == i]
            cluster_pnls[i] = np.mean([emotion_stats[e]['avg_pnl'] for e in cluster_emotions])
        
        sorted_clusters = sorted(cluster_pnls.items(), key=lambda x: x[1])
        cluster_names = {sorted_clusters[0][0]: "Destructive"}
        if n_clusters >= 2:
            cluster_names[sorted_clusters[-1][0]] = "Profitable"
        if n_clusters == 3:
            cluster_names[sorted_clusters[1][0]] = "Neutral"
        
        # Map emotions to cluster names
        for i, emotion in enumerate(emotions_list):
            self.emotion_clusters[emotion] = cluster_names.get(labels[i], "Neutral")
    
    def _calculate_comprehensive_stats(self):
        """Calculate comprehensive trading statistics (same as original)"""
        if not self.closed_trades:
            return {}
        
        stats = {
            'total_trades': len(self.trades),
            'closed_trades': len(self.closed_trades),
            'open_trades': len(self.trades) - len(self.closed_trades),
            'pnls': [],
            'wins': [],
            'losses': [],
            'emotions': defaultdict(list),
            'coins': defaultdict(list),
            'trade_sizes': [],
            'fees_total': 0,
        }
        
        for trade in self.closed_trades:
            # Calculate P&L
            if trade.position_type == 'spot':
                pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
                trade_size = trade.quantity * trade.buy_price
                stats['fees_total'] += trade.fee
            else:
                if trade.position_type == 'long':
                    pnl = (trade.exit_price - trade.entry_price) * trade.quantity - trade.funding_fees
                else:
                    pnl = (trade.entry_price - trade.exit_price) * trade.quantity - trade.funding_fees
                trade_size = trade.quantity * trade.entry_price
                stats['fees_total'] += trade.funding_fees
            
            stats['pnls'].append(pnl)
            stats['trade_sizes'].append(trade_size)
            
            if pnl > 0:
                stats['wins'].append(pnl)
            elif pnl < 0:
                stats['losses'].append(pnl)
            
            # Emotion analysis
            for te in trade.emotions.all():
                stats['emotions'][te.emotion_tag.name].append(pnl)
            
            # Coin analysis
            stats['coins'][trade.coin.symbol].append(pnl)
        
        # Calculate derived metrics
        stats['win_rate'] = (len(stats['wins']) / len(self.closed_trades) * 100) if self.closed_trades else 0
        stats['total_pnl'] = sum(stats['pnls'])
        stats['avg_win'] = sum(stats['wins']) / len(stats['wins']) if stats['wins'] else 0
        stats['avg_loss'] = sum(stats['losses']) / len(stats['losses']) if stats['losses'] else 0
        stats['profit_factor'] = abs(sum(stats['wins']) / sum(stats['losses'])) if stats['losses'] and sum(stats['losses']) != 0 else 0
        
        if len(stats['pnls']) > 1:
            stats['pnl_std_dev'] = statistics.stdev(stats['pnls'])
            stats['sharpe_ratio'] = (statistics.mean(stats['pnls']) / stats['pnl_std_dev']) if stats['pnl_std_dev'] > 0 else 0
        else:
            stats['pnl_std_dev'] = 0
            stats['sharpe_ratio'] = 0
        
        if stats['trade_sizes']:
            stats['avg_position_size'] = statistics.mean(stats['trade_sizes'])
            stats['position_size_std'] = statistics.stdev(stats['trade_sizes']) if len(stats['trade_sizes']) > 1 else 0
        
        return stats
    
    def generate_feedback(self):
        """Generate comprehensive ML-enhanced feedback"""
        if not self.closed_trades:
            return self._generate_no_data_feedback()
        
        if len(self.closed_trades) < MIN_TRADES_FOR_ML:
            return self._generate_insufficient_data_feedback()
        
        feedback = {
            'overall': self._generate_overall_assessment(),
            'scores': self._calculate_scores(),
            'model_info': self._generate_model_info(),
            'whats_working': self._identify_strengths(),
            'whats_hurting': self._identify_weaknesses(),
            'one_thing_to_fix': self._identify_top_priority(),
            'action_items': self._generate_action_items(),
            'per_trade_analysis': self._generate_per_trade_analysis(),
            'market_insights': self._generate_market_insights()
        }
        
        return json.dumps(feedback)
    
    def _generate_model_info(self):
        """Generate model training information"""
        info = {
            'status': 'Trained' if self.model_trained else 'Not enough data',
            'trades_used': len(self.closed_trades),
            'feature_importances': self.feature_importances,
            'emotion_clusters': self.emotion_clusters
        }
        
        if self.cross_val_score is not None:
            info['cross_validation'] = {
                'win_clf_auc': round(self.cross_val_score, 3)
            }
        
        return info
    
    def _generate_no_data_feedback(self):
        """Feedback when there's no data"""
        return json.dumps({
            'overall': "You need at least 5 closed trades to get meaningful analysis. Start trading and tag your emotions to unlock personalized insights.",
            'scores': {'discipline': 5, 'risk_mgmt': 5, 'consistency': 5},
            'model_info': {'status': 'Not enough data', 'trades_used': 0},
            'whats_working': [],
            'whats_hurting': [],
            'one_thing_to_fix': "Close at least 5 trades with emotion tags",
            'action_items': [],
            'per_trade_analysis': [],
            'market_insights': {}
        })
    
    def _generate_insufficient_data_feedback(self):
        """Feedback when there's some data but not enough for ML"""
        return json.dumps({
            'overall': f"You have {len(self.closed_trades)} closed trades. ML (Machine Learning) models require at least {MIN_TRADES_FOR_ML} trades for reliable predictions. Keep trading to unlock ML-powered insights.",
            'scores': self._calculate_scores(),
            'model_info': {'status': 'Not enough data', 'trades_used': len(self.closed_trades)},
            'whats_working': self._identify_strengths(),
            'whats_hurting': self._identify_weaknesses(),
            'one_thing_to_fix': f"Close {MIN_TRADES_FOR_ML - len(self.closed_trades)} more trades to enable ML (Machine Learning) analysis",
            'action_items': self._generate_action_items(),
            'per_trade_analysis': [],
            'market_insights': {}
        })
    
    def _generate_overall_assessment(self):
        """Generate overall assessment (enhanced with ML insights)"""
        win_rate = self.stats['win_rate']
        total_pnl = self.stats['total_pnl']
        profit_factor = self.stats['profit_factor']
        
        # Base assessment
        if total_pnl > 0 and win_rate > 55 and profit_factor > 2:
            tone = "You're crushing it. "
        elif total_pnl > 0 and win_rate > 50:
            tone = "You're profitable, but leaving money on the table. "
        elif total_pnl > 0:
            tone = "You're barely profitable. "
        else:
            tone = "Your trading needs serious work. "
        
        # Add ML insight if available
        if self.model_trained and self.cross_val_score:
            tone += f"ML (Machine Learning) model trained on {len(self.closed_trades)} trades with {self.cross_val_score:.1%} prediction accuracy. "
        
        return tone
    
    def _calculate_scores(self):
        """Calculate discipline, risk management, and consistency scores"""
        return {
            'discipline': self._score_discipline(),
            'risk_mgmt': self._score_risk_management(),
            'consistency': self._score_consistency()
        }
    
    def _score_discipline(self):
        """Score based on emotional control (ML-enhanced)"""
        score = 7
        
        # Use emotion clusters if available
        if self.emotion_clusters:
            for emotion, pnls in self.stats['emotions'].items():
                cluster = self.emotion_clusters.get(emotion, "Neutral")
                if cluster == "Destructive" and sum(pnls) < 0:
                    score -= 3
                elif cluster == "Profitable" and sum(pnls) > 0:
                    score += 2
        else:
            # Fallback to hardcoded
            if 'Revenge trading' in self.stats['emotions']:
                if sum(self.stats['emotions']['Revenge trading']) < 0:
                    score -= 3
        
        return max(1, min(10, score))
    
    def _score_risk_management(self):
        """Score based on risk management metrics"""
        score = 5
        
        pf = self.stats['profit_factor']
        if pf > 2.5:
            score += 4
        elif pf > 2:
            score += 3
        elif pf > 1.5:
            score += 2
        elif pf < 0.5:
            score -= 4
        
        return max(1, min(10, score))
    
    def _score_consistency(self):
        """Score based on trading consistency"""
        score = 5
        
        wr = self.stats['win_rate']
        if 45 <= wr <= 65:
            score += 2
        elif wr < 30:
            score -= 2
        
        sharpe = self.stats['sharpe_ratio']
        if sharpe > 1.5:
            score += 3
        elif sharpe < 0.3:
            score -= 3
        
        return max(1, min(10, score))
    
    def _identify_strengths(self):
        """Identify what's working (ML-enhanced)"""
        strengths = []
        
        # ML-predicted best coin
        if self.model_trained and self.stats['coins']:
            best_coin_ml = self._get_ml_best_coin()
            if best_coin_ml:
                strengths.append({
                    'title': f'{best_coin_ml} - ML (Machine Learning) Recommended',
                    'body': f"ML (Machine Learning) model predicts highest win probability for {best_coin_ml}. Consider focusing more trades here."
                })
        
        # Best profitable emotion cluster
        if self.emotion_clusters:
            profitable_emotions = [e for e, c in self.emotion_clusters.items() if c == "Profitable"]
            if profitable_emotions:
                best_emotion = max(profitable_emotions, key=lambda e: sum(self.stats['emotions'].get(e, [0])))
                strengths.append({
                    'title': f'Trading {best_emotion} Works',
                    'body': f"ML (Machine Learning) clustered '{best_emotion}' as Profitable. Trade more when you feel this way."
                })
        
        # Strong win rate
        if self.stats['win_rate'] > 55:
            strengths.append({
                'title': 'Strong Win Rate',
                'body': f"You're winning {self.stats['win_rate']:.1f}% of trades. Keep doing your analysis."
            })
        
        return strengths[:3]
    
    def _get_ml_best_coin(self):
        """Use ML to find best coin by scanning all coins"""
        if not self.model_trained:
            return None
        
        try:
            coin_probs = {}
            for coin in self.stats['coins'].keys():
                # Create a mean feature row and change coin
                mean_features = pd.DataFrame([{
                    'hour_of_day': 12,
                    'day_of_week': 2,
                    'trade_size': self.stats['avg_position_size'],
                    'leverage_flag': 0,
                    'rolling_win_rate_5': 0.5,
                    'rolling_pnl_5': 0,
                    'consecutive_losses': 0,
                    'fee_to_size_ratio': 0.01,
                    'position_type_enc': 0,
                    'emotion_enc': 0
                }])
                
                try:
                    mean_features['coin_enc'] = self.feature_builder.coin_encoder.transform([coin])[0]
                except:
                    continue
                
                X_scaled = self.scaler.transform(mean_features[self.feature_builder.feature_cols])
                prob = self.win_classifier.predict_proba(X_scaled)[0][1]
                coin_probs[coin] = prob
            
            if coin_probs:
                return max(coin_probs.items(), key=lambda x: x[1])[0]
        except:
            pass
        
        return None
    
    def _identify_weaknesses(self):
        """Identify what's hurting performance (ML-enhanced)"""
        weaknesses = []
        
        # Destructive emotion cluster
        if self.emotion_clusters:
            destructive_emotions = [e for e, c in self.emotion_clusters.items() if c == "Destructive"]
            if destructive_emotions:
                worst_emotion = min(destructive_emotions, key=lambda e: sum(self.stats['emotions'].get(e, [0])))
                total_loss = sum(self.stats['emotions'].get(worst_emotion, [0]))
                weaknesses.append({
                    'title': f'Stop Trading {worst_emotion}',
                    'body': f"ML (Machine Learning) clustered '{worst_emotion}' as Destructive (${abs(total_loss):.2f} lost). Avoid trading in this state."
                })
        
        # Anomalous trades
        if self.model_trained:
            try:
                df = self.feature_builder.fit_transform(self.closed_trades)
                X_scaled = self.scaler.transform(df[self.feature_builder.feature_cols])
                anomalies = self.anomaly_detector.predict(X_scaled)
                anomaly_rate = (anomalies == -1).sum() / len(anomalies)
                
                if anomaly_rate > 0.2:
                    weaknesses.append({
                        'title': 'Too Many Anomalous Trades',
                        'body': f"{anomaly_rate*100:.0f}% of your trades are statistical outliers. You're not following a consistent strategy."
                    })
            except:
                pass
        
        # Poor win rate
        if self.stats['win_rate'] < 40:
            weaknesses.append({
                'title': 'Poor Entry Timing',
                'body': f"Only {self.stats['win_rate']:.1f}% win rate. Wait for better setups."
            })
        
        return weaknesses[:3]
    
    def _identify_top_priority(self):
        """Identify the single most important thing to fix (ML-enhanced)"""
        # Use ML feature importances if available
        if self.model_trained and self.feature_importances:
            top_feature = list(self.feature_importances.keys())[0]
            
            feature_advice = {
                'emotion_enc': "Emotion is the #1 driver of your outcomes (model confirmed). Tag every trade and stop trading in negative emotional states.",
                'consecutive_losses': "After 3 losses, stop trading for 24 hours.",
                'hour_of_day': "Only trade during your model's top-3 optimal hours.",
                'rolling_win_rate_5': "When on a cold streak, reduce size by 50%.",
                'fee_to_size_ratio': "Fees are eating your edge. Increase position size or trade less."
            }
            
            if top_feature in feature_advice:
                return feature_advice[top_feature]
        
        # Fallback to stat-based priorities
        if self.stats['profit_factor'] < 0.8:
            return "Cut your losses at 2% and let winners run to at least 4%. Your risk-reward is backwards."
        
        if self.stats['win_rate'] < 35:
            return "Stop chasing. Only trade when you have 3+ confirmations."
        
        return "Keep a trading journal. Review every trade weekly to spot patterns."
    
    def _generate_action_items(self):
        """Generate specific action items"""
        actions = []
        
        if self.stats.get('position_size_std', 0) > 0:
            cv = self.stats['position_size_std'] / self.stats['avg_position_size']
            if cv > 0.5:
                actions.append({
                    'title': 'Fix Position Sizing',
                    'description': f"Pick one size (${self.stats['avg_position_size']:.0f}) and use it for every trade.",
                    'priority': 'high'
                })
        
        if self.stats['profit_factor'] < 1.5:
            actions.append({
                'title': 'Stop Loss Strategy',
                'description': "Set a hard stop-loss at 2-3% below entry. Cut losses fast.",
                'priority': 'high'
            })
        
        if len(self.closed_trades) > 10:
            actions.append({
                'title': 'Compare Months',
                'description': "Go to Monthly Report and compare your best vs worst month.",
                'priority': 'medium'
            })
        
        return actions[:3]
    
    def _generate_per_trade_analysis(self):
        """Generate ML-enhanced per-trade analysis"""
        if not self.model_trained:
            return []
        
        per_trade = []
        recent_trades = sorted(self.trades, key=lambda t: t.trade_date, reverse=True)[:10]
        
        # Build P&L history for rolling metrics
        pnl_history = []
        loss_streak = 0
        
        for trade in recent_trades:
            analyzer = PerTradeAnalyzer(
                trade,
                self.feature_builder,
                self.win_classifier,
                self.pnl_regressor,
                self.anomaly_detector,
                self.scaler
            )
            
            analysis = analyzer.get_analysis(pnl_history, loss_streak)
            per_trade.append(analysis)
            
            # Update history
            pnl = analysis['pnl']
            pnl_history.append(pnl)
            if pnl < 0:
                loss_streak += 1
            else:
                loss_streak = 0
        
        return per_trade
    
    def _generate_market_insights(self):
        """Generate market insights with ML-powered optimal trading windows"""
        insights = {
            'coin_recommendations': self._generate_coin_recommendations(),
            'position_type_analysis': self._analyze_position_types(),
            'market_trend_summary': self._generate_market_trend_summary()
        }
        
        # Add ML-powered optimal trading windows
        if self.model_trained:
            insights['optimal_trading_windows'] = self._find_optimal_windows()
        
        return insights
    
    def _find_optimal_windows(self):
        """Use ML to find optimal hours and days to trade"""
        try:
            # Scan all 24 hours
            hour_probs = {}
            for hour in range(24):
                mean_features = pd.DataFrame([{
                    'hour_of_day': hour,
                    'day_of_week': 2,
                    'trade_size': self.stats['avg_position_size'],
                    'leverage_flag': 0,
                    'rolling_win_rate_5': 0.5,
                    'rolling_pnl_5': 0,
                    'consecutive_losses': 0,
                    'fee_to_size_ratio': 0.01,
                    'position_type_enc': 0,
                    'coin_enc': 0,
                    'emotion_enc': 0
                }])
                
                X_scaled = self.scaler.transform(mean_features[self.feature_builder.feature_cols])
                prob = self.win_classifier.predict_proba(X_scaled)[0][1]
                hour_probs[hour] = prob
            
            # Scan all 7 days
            day_probs = {}
            for day in range(7):
                mean_features = pd.DataFrame([{
                    'hour_of_day': 12,
                    'day_of_week': day,
                    'trade_size': self.stats['avg_position_size'],
                    'leverage_flag': 0,
                    'rolling_win_rate_5': 0.5,
                    'rolling_pnl_5': 0,
                    'consecutive_losses': 0,
                    'fee_to_size_ratio': 0.01,
                    'position_type_enc': 0,
                    'coin_enc': 0,
                    'emotion_enc': 0
                }])
                
                X_scaled = self.scaler.transform(mean_features[self.feature_builder.feature_cols])
                prob = self.win_classifier.predict_proba(X_scaled)[0][1]
                day_probs[day] = prob
            
            # Get top 3 hours and top 2 days
            top_hours = sorted(hour_probs.items(), key=lambda x: x[1], reverse=True)[:3]
            top_days = sorted(day_probs.items(), key=lambda x: x[1], reverse=True)[:2]
            
            day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            
            return {
                'best_hours': [{'hour': f"{h}:00", 'win_probability': round(p, 3)} for h, p in top_hours],
                'best_days': [{'day': day_names[d], 'win_probability': round(p, 3)} for d, p in top_days]
            }
        except:
            return {}
    
    def _generate_coin_recommendations(self):
        """Generate coin recommendations"""
        recommendations = []
        
        for coin_symbol, pnls in self.stats['coins'].items():
            if len(pnls) < 2:
                continue
            
            total_pnl = sum(pnls)
            win_rate = len([p for p in pnls if p > 0]) / len(pnls) * 100
            avg_pnl = total_pnl / len(pnls)
            
            if total_pnl > 0 and win_rate > 60:
                recommendation = "STRONG BUY - Excellent track record"
                confidence = "HIGH"
            elif total_pnl > 0 and win_rate > 50:
                recommendation = "BUY - Positive performance"
                confidence = "MEDIUM"
            elif total_pnl > 0:
                recommendation = "HOLD - Slightly profitable"
                confidence = "LOW"
            else:
                recommendation = "AVOID - Losing record"
                confidence = "HIGH"
            
            recommendations.append({
                'coin': coin_symbol,
                'total_pnl': round(total_pnl, 2),
                'trades': len(pnls),
                'win_rate': round(win_rate, 1),
                'avg_pnl_per_trade': round(avg_pnl, 2),
                'recommendation': recommendation,
                'confidence': confidence
            })
        
        return sorted(recommendations, key=lambda x: x['total_pnl'], reverse=True)
    
    def _analyze_position_types(self):
        """Analyze performance by position type"""
        analysis = {}
        
        spot_trades = [t for t in self.closed_trades if t.position_type == 'spot']
        leverage_trades = [t for t in self.closed_trades if t.position_type in ['long', 'short']]
        
        if spot_trades:
            spot_pnls = []
            for t in spot_trades:
                pnl = (t.sell_price - t.buy_price) * t.quantity - t.fee
                spot_pnls.append(pnl)
            
            analysis['spot'] = {
                'total_trades': len(spot_trades),
                'total_pnl': round(sum(spot_pnls), 2),
                'win_rate': round(len([p for p in spot_pnls if p > 0]) / len(spot_pnls) * 100, 1),
                'avg_pnl': round(sum(spot_pnls) / len(spot_pnls), 2),
                'recommendation': 'FOCUS HERE' if sum(spot_pnls) > 0 else 'NEEDS WORK'
            }
        
        if leverage_trades:
            leverage_pnls = []
            for t in leverage_trades:
                if t.position_type == 'long':
                    pnl = (t.exit_price - t.entry_price) * t.quantity - t.funding_fees
                else:
                    pnl = (t.entry_price - t.exit_price) * t.quantity - t.funding_fees
                leverage_pnls.append(pnl)
            
            analysis['leverage'] = {
                'total_trades': len(leverage_trades),
                'total_pnl': round(sum(leverage_pnls), 2),
                'win_rate': round(len([p for p in leverage_pnls if p > 0]) / len(leverage_pnls) * 100, 1),
                'avg_pnl': round(sum(leverage_pnls) / len(leverage_pnls), 2),
                'recommendation': 'FOCUS HERE' if sum(leverage_pnls) > 0 else 'NEEDS WORK'
            }
        
        return analysis
    
    def _generate_market_trend_summary(self):
        """Generate market trend summary"""
        return "ML (Machine Learning) enhanced analysis based on your trading history. Check optimal_trading_windows for best times to trade."
