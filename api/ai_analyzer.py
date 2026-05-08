"""
AI Feedback Analyzer - Advanced rule-based trading pattern analysis
Analyzes user trades and generates intelligent, actionable feedback
Includes per-trade analysis and market trend recommendations
"""
import json
from datetime import datetime, timedelta
from collections import defaultdict
import statistics


class PerTradeAnalyzer:
    """Analyzes individual trades with market context"""
    
    def __init__(self, trade):
        self.trade = trade
        self.pnl = self._calculate_pnl()
        self.trade_type_label = self._get_trade_type_label()
        self.position_type_label = self._get_position_type_label()
    
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
    
    def _get_trade_type_label(self):
        """Get human-readable trade type"""
        if self.trade.position_type == 'spot':
            return 'BUY' if self.trade.trade_type == 'buy' else 'SELL'
        else:
            return self.trade.position_type.upper()
    
    def _get_position_type_label(self):
        """Get human-readable position type"""
        return self.trade.position_type.upper()
    
    def get_analysis(self):
        """Get per-trade analysis"""
        emotions = [te.emotion_tag.name for te in self.trade.emotions.all()]
        
        # Determine if trade was good or bad
        is_winning = self.pnl > 0
        
        # Generate trade-specific feedback
        feedback = self._generate_trade_feedback(is_winning, emotions)
        
        return {
            'trade_id': self.trade.id,
            'coin': self.trade.coin.symbol,
            'position_type': self.position_type_label,
            'trade_type': self.trade_type_label,
            'entry_price': self.trade.entry_price or self.trade.buy_price,
            'exit_price': self.trade.exit_price or self.trade.sell_price,
            'quantity': self.trade.quantity,
            'pnl': round(self.pnl, 2),
            'pnl_percent': self._calculate_pnl_percent(),
            'emotions': emotions,
            'trade_date': self.trade.trade_date.isoformat(),
            'feedback': feedback,
            'recommendation': self._get_hold_sell_recommendation()
        }
    
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
    
    def _generate_trade_feedback(self, is_winning, emotions):
        """Generate specific feedback for this trade"""
        if is_winning:
            feedback = f"✓ Winning trade. "
            if self.pnl > 100:
                feedback += "Excellent execution. "
            if emotions:
                feedback += f"You were {emotions[0].lower()}—remember this state for future trades."
        else:
            feedback = f"✕ Losing trade. "
            if self.pnl < -100:
                feedback += "This was a significant loss. "
            if emotions:
                feedback += f"You were {emotions[0].lower()}—avoid trading in this state."
        
        return feedback
    
    def _get_hold_sell_recommendation(self):
        """Get hold/sell recommendation based on trade status"""
        if self.trade.position_type == 'spot':
            if self.trade.sell_price:
                return "CLOSED"
            else:
                # Open position - recommend based on recent performance
                if self.pnl > 0:
                    return "HOLD - Position is profitable"
                else:
                    return "CONSIDER SELLING - Position is underwater"
        else:
            if self.trade.is_open:
                if self.pnl > 0:
                    return "HOLD - Position is profitable"
                else:
                    return "CONSIDER CLOSING - Position is losing"
            else:
                return "CLOSED"


class TradingAnalyzer:
    """Advanced trading pattern analyzer with professional insights"""
    
    def __init__(self, trades):
        self.trades = trades
        self.closed_trades = [t for t in trades if t.sell_price and t.buy_price]
        self.stats = self._calculate_comprehensive_stats()
    
    def _calculate_comprehensive_stats(self):
        """Calculate comprehensive trading statistics"""
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
            'consecutive_wins': 0,
            'consecutive_losses': 0,
            'max_win_streak': 0,
            'max_loss_streak': 0,
            'current_streak': 0,
            'trades_by_day': defaultdict(int),
            'trades_by_hour': defaultdict(int),
            'hold_times': [],
        }
        
        # Track streaks
        current_streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        
        for i, trade in enumerate(self.closed_trades):
            pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
            trade_size = trade.quantity * trade.buy_price
            
            stats['pnls'].append(pnl)
            stats['trade_sizes'].append(trade_size)
            stats['fees_total'] += trade.fee
            
            # Track wins/losses
            if pnl > 0:
                stats['wins'].append(pnl)
                if current_streak >= 0:
                    current_streak += 1
                else:
                    current_streak = 1
                max_win_streak = max(max_win_streak, current_streak)
            elif pnl < 0:
                stats['losses'].append(pnl)
                if current_streak <= 0:
                    current_streak -= 1
                else:
                    current_streak = -1
                max_loss_streak = max(max_loss_streak, abs(current_streak))
            
            # Emotion analysis
            for te in trade.emotions.all():
                stats['emotions'][te.emotion_tag.name].append(pnl)
            
            # Coin analysis
            stats['coins'][trade.coin.symbol].append(pnl)
            
            # Time analysis
            trade_date = trade.trade_date
            stats['trades_by_day'][trade_date.strftime('%A').lower()] += 1
            stats['trades_by_hour'][trade_date.hour] += 1
        
        # Calculate derived metrics
        stats['win_rate'] = (len(stats['wins']) / len(self.closed_trades) * 100) if self.closed_trades else 0
        stats['total_pnl'] = sum(stats['pnls'])
        stats['avg_win'] = sum(stats['wins']) / len(stats['wins']) if stats['wins'] else 0
        stats['avg_loss'] = sum(stats['losses']) / len(stats['losses']) if stats['losses'] else 0
        stats['profit_factor'] = abs(sum(stats['wins']) / sum(stats['losses'])) if stats['losses'] and sum(stats['losses']) != 0 else 0
        stats['max_win_streak'] = max_win_streak
        stats['max_loss_streak'] = max_loss_streak
        
        # Risk metrics
        if len(stats['pnls']) > 1:
            stats['pnl_std_dev'] = statistics.stdev(stats['pnls'])
            stats['sharpe_ratio'] = (statistics.mean(stats['pnls']) / stats['pnl_std_dev']) if stats['pnl_std_dev'] > 0 else 0
        else:
            stats['pnl_std_dev'] = 0
            stats['sharpe_ratio'] = 0
        
        # Position sizing analysis
        if stats['trade_sizes']:
            stats['avg_position_size'] = statistics.mean(stats['trade_sizes'])
            stats['position_size_std'] = statistics.stdev(stats['trade_sizes']) if len(stats['trade_sizes']) > 1 else 0
            stats['largest_position'] = max(stats['trade_sizes'])
            stats['smallest_position'] = min(stats['trade_sizes'])
        
        # Overtrading detection
        if len(self.closed_trades) > 0:
            date_range = (max(t.trade_date for t in self.closed_trades) - min(t.trade_date for t in self.closed_trades)).days
            stats['trades_per_day'] = len(self.closed_trades) / max(date_range, 1)
        
        return stats
    
    def generate_feedback(self):
        """Generate comprehensive feedback with action items"""
        if not self.closed_trades:
            return self._generate_no_data_feedback()
        
        feedback = {
            'overall': self._generate_overall_assessment(),
            'scores': self._calculate_scores(),
            'whats_working': self._identify_strengths(),
            'whats_hurting': self._identify_weaknesses(),
            'one_thing_to_fix': self._identify_top_priority(),
            'action_items': self._generate_action_items(),
            'per_trade_analysis': self._generate_per_trade_analysis(),
            'market_insights': self._generate_market_insights()
        }
        
        return json.dumps(feedback)
    
    def _generate_per_trade_analysis(self):
        """Generate analysis for each individual trade"""
        per_trade = []
        
        # Analyze last 10 trades for detailed feedback
        recent_trades = sorted(self.trades, key=lambda t: t.trade_date, reverse=True)[:10]
        
        for trade in recent_trades:
            analyzer = PerTradeAnalyzer(trade)
            per_trade.append(analyzer.get_analysis())
        
        return per_trade
    
    def _generate_market_insights(self):
        """Generate market trend insights and coin recommendations"""
        insights = {
            'coin_recommendations': self._generate_coin_recommendations(),
            'position_type_analysis': self._analyze_position_types(),
            'market_trend_summary': self._generate_market_trend_summary()
        }
        return insights
    
    def _generate_coin_recommendations(self):
        """Generate hold/sell recommendations for each coin"""
        recommendations = []
        
        for coin_symbol, pnls in self.stats['coins'].items():
            if len(pnls) < 2:
                continue
            
            total_pnl = sum(pnls)
            win_rate = len([p for p in pnls if p > 0]) / len(pnls) * 100
            avg_pnl = total_pnl / len(pnls)
            
            # Determine recommendation
            if total_pnl > 0 and win_rate > 60:
                recommendation = "STRONG BUY - Excellent track record"
                confidence = "HIGH"
            elif total_pnl > 0 and win_rate > 50:
                recommendation = "BUY - Positive performance"
                confidence = "MEDIUM"
            elif total_pnl > 0:
                recommendation = "HOLD - Slightly profitable but inconsistent"
                confidence = "LOW"
            elif win_rate > 50:
                recommendation = "HOLD - Good win rate but small losses"
                confidence = "MEDIUM"
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
        
        # Sort by total PnL descending
        return sorted(recommendations, key=lambda x: x['total_pnl'], reverse=True)
    
    def _analyze_position_types(self):
        """Analyze performance by position type (spot vs leverage)"""
        analysis = {}
        
        spot_trades = [t for t in self.closed_trades if t.position_type == 'spot']
        leverage_trades = [t for t in self.closed_trades if t.position_type in ['long', 'short']]
        
        # Analyze spot trades
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
        
        # Analyze leverage trades
        if leverage_trades:
            leverage_pnls = []
            for t in leverage_trades:
                if t.position_type == 'long':
                    pnl = (t.exit_price - t.entry_price) * t.quantity - t.funding_fees if t.exit_price else 0
                else:  # short
                    pnl = (t.entry_price - t.exit_price) * t.quantity - t.funding_fees if t.exit_price else 0
                leverage_pnls.append(pnl)
            
            analysis['leverage'] = {
                'total_trades': len(leverage_trades),
                'total_pnl': round(sum(leverage_pnls), 2),
                'win_rate': round(len([p for p in leverage_pnls if p > 0]) / len(leverage_pnls) * 100, 1) if leverage_pnls else 0,
                'avg_pnl': round(sum(leverage_pnls) / len(leverage_pnls), 2) if leverage_pnls else 0,
                'recommendation': 'FOCUS HERE' if sum(leverage_pnls) > 0 else 'NEEDS WORK'
            }
        
        return analysis
    
    def _generate_market_trend_summary(self):
        """Generate summary of market trends based on trading data"""
        summary = "Based on your trading history: "
        
        # Identify best performing period
        trades_by_day = defaultdict(list)
        for trade in self.closed_trades:
            day = trade.trade_date.strftime('%A')
            pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
            trades_by_day[day].append(pnl)
        
        best_day = max(trades_by_day.items(), key=lambda x: sum(x[1]), default=None)
        if best_day:
            summary += f"You trade best on {best_day[0]}s. "
        
        # Identify best performing hour
        trades_by_hour = defaultdict(list)
        for trade in self.closed_trades:
            hour = trade.trade_date.hour
            pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
            trades_by_hour[hour].append(pnl)
        
        best_hour = max(trades_by_hour.items(), key=lambda x: sum(x[1]), default=None)
        if best_hour:
            summary += f"Your best trading hour is {best_hour[0]}:00. "
        
        # Volatility insight
        if self.stats.get('pnl_std_dev', 0) > 0:
            if self.stats['pnl_std_dev'] > 200:
                summary += "Your P&L swings wildly—you're taking on too much risk per trade. "
            elif self.stats['pnl_std_dev'] < 50:
                summary += "Your P&L is consistent—you've found a stable strategy. "
        
        return summary
    
    def _generate_no_data_feedback(self):
        """Feedback when there's insufficient data"""
        return json.dumps({
            'overall': "You need at least 5 closed trades to get meaningful analysis. Start trading and tag your emotions to unlock personalized insights.",
            'scores': {'discipline': 5, 'risk_mgmt': 5, 'consistency': 5},
            'whats_working': [],
            'whats_hurting': [],
            'one_thing_to_fix': "Close at least 5 trades with emotion tags",
            'action_items': []
        })
    
    def _generate_overall_assessment(self):
        """Generate brutally honest overall assessment"""
        win_rate = self.stats['win_rate']
        total_pnl = self.stats['total_pnl']
        profit_factor = self.stats['profit_factor']
        sharpe = self.stats['sharpe_ratio']
        
        # Determine performance tier
        if total_pnl > 0 and win_rate > 55 and profit_factor > 2:
            tone = "You're crushing it. "
            performance = "Your numbers are solid across the board."
        elif total_pnl > 0 and win_rate > 50:
            tone = "You're profitable, but leaving money on the table. "
            performance = "You're winning, but your edge could be sharper."
        elif total_pnl > 0:
            tone = "You're barely profitable. "
            performance = "You're one bad streak away from being in the red."
        elif win_rate > 50:
            tone = "You're picking good entries but bleeding money. "
            performance = "Your win rate is decent, but you're cutting winners and holding losers."
        else:
            tone = "Your trading needs serious work. "
            performance = "You're losing money and losing often."
        
        # Add specific insights
        insights = []
        
        if profit_factor > 2:
            insights.append("Your winners are 2x bigger than your losers—that's textbook risk management.")
        elif profit_factor < 1:
            insights.append("Your losses are bigger than your wins. You're doing the opposite of what works.")
        
        if sharpe > 1:
            insights.append("Your returns are consistent relative to risk.")
        elif sharpe < 0.5:
            insights.append("Your P&L swings wildly—you're gambling, not trading.")
        
        if self.stats['max_loss_streak'] > 5:
            insights.append(f"You had a {self.stats['max_loss_streak']}-trade losing streak. That's when most traders blow up.")
        
        return tone + performance + " " + " ".join(insights)
    
    def _calculate_scores(self):
        """Calculate discipline, risk management, and consistency scores (1-10)"""
        return {
            'discipline': self._score_discipline(),
            'risk_mgmt': self._score_risk_management(),
            'consistency': self._score_consistency()
        }
    
    def _score_discipline(self):
        """Score based on emotional control and trading behavior"""
        score = 7
        
        # Emotional trading penalties
        if 'Revenge trading' in self.stats['emotions']:
            revenge_pnls = self.stats['emotions']['Revenge trading']
            if sum(revenge_pnls) < 0:
                score -= 3
        
        if 'Greedy' in self.stats['emotions']:
            greedy_pnls = self.stats['emotions']['Greedy']
            if sum(greedy_pnls) < 0:
                score -= 2
        
        if 'Fear of loss' in self.stats['emotions']:
            fear_pnls = self.stats['emotions']['Fear of loss']
            if sum(fear_pnls) < 0:
                score -= 2
        
        # Overtrading penalty
        if self.stats.get('trades_per_day', 0) > 3:
            score -= 2
        
        # Calm trading reward
        if 'Calm' in self.stats['emotions']:
            calm_pnls = self.stats['emotions']['Calm']
            if sum(calm_pnls) > 0:
                score += 2
        
        # Confident trading reward
        if 'Confident' in self.stats['emotions']:
            confident_pnls = self.stats['emotions']['Confident']
            if sum(confident_pnls) > 0:
                score += 1
        
        return max(1, min(10, score))
    
    def _score_risk_management(self):
        """Score based on risk management metrics"""
        score = 5
        
        # Profit factor scoring
        pf = self.stats['profit_factor']
        if pf > 2.5:
            score += 4
        elif pf > 2:
            score += 3
        elif pf > 1.5:
            score += 2
        elif pf > 1:
            score += 1
        elif pf < 0.5:
            score -= 4
        elif pf < 0.8:
            score -= 2
        
        # Position sizing consistency
        if self.stats.get('position_size_std', 0) > 0:
            cv = self.stats['position_size_std'] / self.stats['avg_position_size']
            if cv < 0.3:  # Consistent sizing
                score += 2
            elif cv > 1:  # Erratic sizing
                score -= 2
        
        # Risk-reward ratio
        avg_win = abs(self.stats['avg_win'])
        avg_loss = abs(self.stats['avg_loss'])
        if avg_loss > 0:
            rr_ratio = avg_win / avg_loss
            if rr_ratio > 2:
                score += 2
            elif rr_ratio < 1:
                score -= 2
        
        return max(1, min(10, score))
    
    def _score_consistency(self):
        """Score based on trading consistency"""
        score = 5
        
        # Win rate consistency
        wr = self.stats['win_rate']
        if 45 <= wr <= 65:
            score += 2
        elif wr < 30 or wr > 80:
            score -= 2
        
        # Sharpe ratio
        sharpe = self.stats['sharpe_ratio']
        if sharpe > 1.5:
            score += 3
        elif sharpe > 1:
            score += 2
        elif sharpe < 0.3:
            score -= 3
        
        # Streak analysis
        if self.stats['max_loss_streak'] > 5:
            score -= 2
        if self.stats['max_win_streak'] > 5:
            score += 1
        
        return max(1, min(10, score))
    
    def _identify_strengths(self):
        """Identify what's working well"""
        strengths = []
        
        # Strong win rate
        if self.stats['win_rate'] > 55:
            strengths.append({
                'title': 'Strong Win Rate',
                'body': f"You're winning {self.stats['win_rate']:.1f}% of trades. You're picking good entries more often than not. Keep doing whatever analysis you're doing."
            })
        
        # Excellent risk-reward
        if self.stats['profit_factor'] > 1.8:
            strengths.append({
                'title': 'Excellent Risk-Reward',
                'body': f"Your profit factor of {self.stats['profit_factor']:.2f} means your winners are much bigger than your losers. This is the #1 trait of profitable traders."
            })
        
        # Best performing emotion
        best_emotion = None
        best_emotion_pnl = float('-inf')
        for emotion, pnls in self.stats['emotions'].items():
            if len(pnls) >= 3 and sum(pnls) > best_emotion_pnl:
                best_emotion = emotion
                best_emotion_pnl = sum(pnls)
        
        if best_emotion and best_emotion_pnl > 0:
            avg_pnl = best_emotion_pnl / len(self.stats['emotions'][best_emotion])
            strengths.append({
                'title': f'Trading {best_emotion} Works',
                'body': f"When you trade feeling '{best_emotion}', you average ${avg_pnl:.2f} per trade. This emotional state keeps you sharp. Recognize it and trade more when you feel this way."
            })
        
        # Best performing coin
        best_coin = None
        best_coin_pnl = float('-inf')
        for coin, pnls in self.stats['coins'].items():
            if len(pnls) >= 3 and sum(pnls) > best_coin_pnl:
                best_coin = coin
                best_coin_pnl = sum(pnls)
        
        if best_coin and best_coin_pnl > 0:
            win_rate = len([p for p in self.stats['coins'][best_coin] if p > 0]) / len(self.stats['coins'][best_coin]) * 100
            strengths.append({
                'title': f'{best_coin} is Your Edge',
                'body': f"You've made ${best_coin_pnl:.2f} on {best_coin} with a {win_rate:.0f}% win rate. You clearly understand this coin. Consider making it 40-50% of your trades."
            })
        
        # Consistent position sizing
        if self.stats.get('position_size_std', 0) > 0:
            cv = self.stats['position_size_std'] / self.stats['avg_position_size']
            if cv < 0.3:
                strengths.append({
                    'title': 'Consistent Position Sizing',
                    'body': f"Your position sizes are consistent (${self.stats['avg_position_size']:.0f} average). This shows discipline and protects you from blowing up on one bad trade."
                })
        
        if not strengths:
            strengths.append({
                'title': 'Still Finding Your Edge',
                'body': "You haven't found a clear pattern that works yet. That's normal. Focus on one setup, one coin, and one timeframe until you master it."
            })
        
        return strengths[:3]
    
    def _identify_weaknesses(self):
        """Identify what's hurting performance"""
        weaknesses = []
        
        # Worst emotion
        worst_emotion = None
        worst_emotion_pnl = 0
        for emotion, pnls in self.stats['emotions'].items():
            if len(pnls) >= 2 and sum(pnls) < worst_emotion_pnl:
                worst_emotion = emotion
                worst_emotion_pnl = sum(pnls)
        
        if worst_emotion and worst_emotion_pnl < -50:
            weaknesses.append({
                'title': f'Stop Trading {worst_emotion}',
                'body': f"When you feel '{worst_emotion}', you lose ${abs(worst_emotion_pnl):.2f}. This emotion makes you irrational. Set a rule: if you feel this way, close your trading app and walk away."
            })
        
        # Worst coin
        worst_coin = None
        worst_coin_pnl = 0
        for coin, pnls in self.stats['coins'].items():
            if len(pnls) >= 2 and sum(pnls) < worst_coin_pnl:
                worst_coin = coin
                worst_coin_pnl = sum(pnls)
        
        if worst_coin and worst_coin_pnl < -50:
            loss_rate = len([p for p in self.stats['coins'][worst_coin] if p < 0]) / len(self.stats['coins'][worst_coin]) * 100
            weaknesses.append({
                'title': f'Avoid {worst_coin}',
                'body': f"You've lost ${abs(worst_coin_pnl):.2f} on {worst_coin} ({loss_rate:.0f}% loss rate). Either you don't understand this coin or it's too volatile for your strategy. Stop trading it."
            })
        
        # Overtrading
        if self.stats.get('trades_per_day', 0) > 3: 
            weaknesses.append({
                'title': "You're Overtrading",
                'body': f"You're averaging {self.stats['trades_per_day']:.1f} trades per day. That's too many. Quality over quantity. Wait for A+ setups only."
            })
        
        # Fees eating profits
        if self.stats['fees_total'] > abs(self.stats['total_pnl']) * 0.3:
            weaknesses.append({
                'title': 'Fees Are Killing You',
                'body': f"You've paid ${self.stats['fees_total']:.2f} in fees—that's {(self.stats['fees_total'] / abs(self.stats['total_pnl']) * 100):.0f}% of your P&L. Trade less frequently or switch to a lower-fee exchange."
            })
        
        # Poor win rate
        if self.stats['win_rate'] < 40:
            weaknesses.append({
                'title': 'Poor Entry Timing',
                'body': f"You're only winning {self.stats['win_rate']:.1f}% of trades. You're entering at the wrong time—probably chasing pumps or FOMOing in. Wait for pullbacks and confirmations."
            })
        
        # Cutting winners, holding losers
        if self.stats['profit_factor'] < 1:
            avg_win = abs(self.stats['avg_win'])
            avg_loss = abs(self.stats['avg_loss'])
            weaknesses.append({
                'title': 'Cutting Winners, Holding Losers',
                'body': f"Your average win (${avg_win:.2f}) is smaller than your average loss (${avg_loss:.2f}). You're taking profits too early and hoping losers recover. Flip this immediately."
            })
        
        # Loss streaks
        if self.stats['max_loss_streak'] > 5:
            weaknesses.append({
                'title': 'Dangerous Losing Streaks',
                'body': f"You had a {self.stats['max_loss_streak']}-trade losing streak. After 3 losses in a row, stop trading for 24 hours. Streaks destroy accounts."
            })
        
        # Inconsistent position sizing
        if self.stats.get('position_size_std', 0) > 0:
            cv = self.stats['position_size_std'] / self.stats['avg_position_size']
            if cv > 0.8:
                weaknesses.append({
                    'title': 'Erratic Position Sizing',
                    'body': f"Your position sizes swing from ${self.stats['smallest_position']:.0f} to ${self.stats['largest_position']:.0f}. This is gambling. Pick a fixed size and stick to it."
                })
        
        if not weaknesses:
            weaknesses.append({
                'title': 'Minor Improvements Needed',
                'body': "You're doing well overall. Focus on consistency and don't get cocky. The market humbles everyone eventually."
            })
        
        return weaknesses[:3]
    
    def _identify_top_priority(self):
        """Identify the single most important thing to fix"""
        # Priority 1: Emotional trading
        worst_emotion_pnl = 0
        for emotion, pnls in self.stats['emotions'].items():
            if emotion in ['Revenge trading', 'Greedy', 'Fear of loss', 'Rushed'] and sum(pnls) < worst_emotion_pnl:
                worst_emotion_pnl = sum(pnls)
        
        if worst_emotion_pnl < -100:
            return "Stop emotional trading. After any loss, wait 24 hours before your next trade. No exceptions."
        
        # Priority 2: Risk management
        if self.stats['profit_factor'] < 0.8:
            return "Cut your losses at 2% and let winners run to at least 4%. Your risk-reward is backwards."
        
        # Priority 3: Overtrading
        if self.stats.get('trades_per_day', 0) > 3:
            return "Trade less. Set a rule: maximum 2 trades per day. Wait for perfect setups only."
        
        # Priority 4: Win rate
        if self.stats['win_rate'] < 35:
            return "Stop chasing. Only trade when you have 3+ confirmations (trend, support/resistance, volume)."
        
        # Priority 5: Fees
        if self.stats['fees_total'] > abs(self.stats['total_pnl']) * 0.4:
            return "Reduce trading frequency by 50%. Fees are eating your profits."
        
        # Priority 6: Loss streaks
        if self.stats['max_loss_streak'] > 5:
            return "After 3 losses in a row, stop trading for 24 hours. Streaks compound mistakes."
        
        # Default
        return "Keep a trading journal. Review every trade weekly to spot patterns you're missing."
    
    def _generate_action_items(self):
        """Generate specific, actionable next steps"""
        actions = []
        
        # Position sizing action
        if self.stats.get('position_size_std', 0) > 0:
            cv = self.stats['position_size_std'] / self.stats['avg_position_size']
            if cv > 0.5:
                actions.append({
                    'title': 'Fix Position Sizing',
                    'description': f"Your position sizes are all over the place. Pick one size (${self.stats['avg_position_size']:.0f}) and use it for every trade for the next month.",
                    'priority': 'high'
                })
            else:
                actions.append({
                    'title': 'Position Sizing Help',
                    'description': f"Your average position is ${self.stats['avg_position_size']:.0f}. This should be 1-2% of your total capital. Adjust if needed.",
                    'priority': 'low'
                })
        
        # Stop loss strategy
        if self.stats['profit_factor'] < 1.5:
            actions.append({
                'title': 'Stop Loss Strategy',
                'description': "Set a hard stop-loss at 2-3% below entry. No hoping, no averaging down. Cut losses fast and let winners run.",
                'priority': 'high'
            })
        
        # Compare months
        if len(self.closed_trades) > 10:
            actions.append({
                'title': 'Compare Months',
                'description': "Go to Monthly Report and compare your best month vs worst month. What did you do differently? Repeat what worked.",
                'priority': 'medium'
            })
        
        # Emotion tracking
        untagged_count = len([t for t in self.closed_trades if not t.emotions.all()])
        if untagged_count > len(self.closed_trades) * 0.3:
            actions.append({
                'title': 'Tag Your Emotions',
                'description': f"{untagged_count} trades have no emotion tags. Tag every trade immediately after closing it. Patterns will emerge.",
                'priority': 'medium'
            })
        
        # Best coin focus
        best_coin = None
        best_coin_pnl = float('-inf')
        for coin, pnls in self.stats['coins'].items():
            if len(pnls) >= 3 and sum(pnls) > best_coin_pnl:
                best_coin = coin
                best_coin_pnl = sum(pnls)
        
        if best_coin and best_coin_pnl > 0:
            actions.append({
                'title': 'Focus on Your Edge',
                'description': f"You make money on {best_coin}. Make it 50% of your trades for the next 2 weeks. Master one coin before diversifying.",
                'priority': 'high'
            })
        
        return actions[:3]  # Return top 3 action items
