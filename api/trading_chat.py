"""
Trading Chat Assistant - Conversational AI layer using Ollama
Provides natural language interface to user's trading data and ML analysis
"""
import json
import requests
from datetime import datetime
from typing import Optional, Dict, List


class TradingChatAssistant:
    """
    Conversational AI assistant for trading analysis using local Ollama LLM.
    Provides context-aware chat about user's trades, positions, and ML insights.
    """
    
    def __init__(self, user, trades_queryset, ollama_model="llama3", ollama_host="http://localhost:11434"):
        """
        Initialize trading chat assistant.
        
        Args:
            user: Django user object
            trades_queryset: User's Trade queryset (same as MLTradingAnalyzer uses)
            ollama_model: Ollama model name (default: "llama3")
            ollama_host: Ollama server URL (default: "http://localhost:11434")
        """
        self.user = user
        self.trades = list(trades_queryset.select_related('coin').prefetch_related('emotions__emotion_tag').order_by('trade_date'))
        self.ollama_model = ollama_model
        self.ollama_host = ollama_host
        self._user_context = None
        self._system_prompt = None
    
    def __str__(self):
        return f"TradingChatAssistant(user={self.user.username}, model={self.ollama_model})"
    
    def _fetch_coingecko_data(self, coin_symbols: List[str]) -> Dict[str, Dict]:
        """
        Fetch live market data from CoinGecko for user's coins.
        
        Args:
            coin_symbols: List of coin symbols (e.g., ['BTC', 'ETH', 'SOL'])
            
        Returns:
            Dict mapping coin symbols to their market data
        """
        if not coin_symbols:
            return {}
        
        # Map common symbols to CoinGecko IDs
        symbol_to_id = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'BNB': 'binancecoin',
            'SOL': 'solana',
            'XRP': 'ripple',
            'ADA': 'cardano',
            'DOGE': 'dogecoin',
            'MATIC': 'matic-network',
            'DOT': 'polkadot',
            'AVAX': 'avalanche-2',
            'LINK': 'chainlink',
            'UNI': 'uniswap',
            'ATOM': 'cosmos',
            'LTC': 'litecoin',
            'BCH': 'bitcoin-cash',
            'NEAR': 'near',
            'APT': 'aptos',
            'ARB': 'arbitrum',
            'OP': 'optimism',
            'SUI': 'sui',
        }
        
        # Get CoinGecko IDs for user's coins
        coin_ids = []
        symbol_map = {}
        for symbol in coin_symbols:
            symbol_upper = symbol.upper()
            if symbol_upper in symbol_to_id:
                coin_id = symbol_to_id[symbol_upper]
                coin_ids.append(coin_id)
                symbol_map[coin_id] = symbol_upper
        
        if not coin_ids:
            return {}
        
        try:
            # Fetch market data from CoinGecko
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                'ids': ','.join(coin_ids),
                'vs_currencies': 'usd',
                'include_24hr_change': 'true',
                'include_24hr_vol': 'true',
                'include_market_cap': 'true'
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Transform to symbol-keyed dict
            result = {}
            for coin_id, market_data in data.items():
                symbol = symbol_map.get(coin_id)
                if symbol:
                    result[symbol] = {
                        'current_price': market_data.get('usd', 0),
                        'price_change_24h_percent': market_data.get('usd_24h_change', 0),
                        'volume_24h': market_data.get('usd_24h_vol', 0),
                        'market_cap': market_data.get('usd_market_cap', 0)
                    }
            
            return result
            
        except Exception as e:
            # Log error without exposing sensitive API details
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("CoinGecko API request failed")
            return {}
    
    def build_user_context(self) -> str:
        """
        Build structured text summary of user's trading data for AI context.
        Includes ML analysis, open positions, coin performance, recent trades, and live market data.
        
        Returns:
            Formatted context string (under 2000 tokens)
        """
        from .ml_trading_analyzer import MLTradingAnalyzer
        
        context_parts = []
        
        # Get unique coins user has traded
        user_coins = list(set([trade.coin.symbol for trade in self.trades]))
        
        # Fetch live market data from CoinGecko
        live_market_data = self._fetch_coingecko_data(user_coins)
        
        # Section 1: Trading Performance Summary (from ML analyzer)
        context_parts.append("=== TRADING PERFORMANCE SUMMARY ===")
        
        if len(self.trades) >= 10:
            try:
                analyzer = MLTradingAnalyzer(self.trades)
                feedback_json = json.loads(analyzer.generate_feedback())
                
                context_parts.append(f"Overall: {feedback_json.get('overall', 'N/A')}")
                
                scores = feedback_json.get('scores', {})
                context_parts.append(f"Scores - Discipline: {scores.get('discipline', 0)}/10, Risk Mgmt: {scores.get('risk_mgmt', 0)}/10, Consistency: {scores.get('consistency', 0)}/10")
                
                strengths = feedback_json.get('whats_working', [])[:3]
                if strengths:
                    context_parts.append("Top Strengths:")
                    for s in strengths:
                        context_parts.append(f"  • {s.get('title', '')}: {s.get('body', '')}")
                
                weaknesses = feedback_json.get('whats_hurting', [])[:3]
                if weaknesses:
                    context_parts.append("Top Weaknesses:")
                    for w in weaknesses:
                        context_parts.append(f"  • {w.get('title', '')}: {w.get('body', '')}")
                
                context_parts.append(f"Priority Fix: {feedback_json.get('one_thing_to_fix', 'N/A')}")
                
                model_info = feedback_json.get('model_info', {})
                if model_info.get('status') == 'Trained':
                    context_parts.append(f"ML (Machine Learning) Model: Trained on {model_info.get('trades_used', 0)} trades")
                    
            except Exception as e:
                context_parts.append(f"ML (Machine Learning) analysis unavailable: {str(e)}")
        else:
            context_parts.append(f"ML (Machine Learning) analysis requires 10+ closed trades. Current: {len(self.trades)} total trades.")
        
        # Section 2: Live Market Data (from CoinGecko)
        if live_market_data:
            context_parts.append("\n=== LIVE MARKET DATA (CoinGecko) ===")
            for symbol, data in sorted(live_market_data.items()):
                price = data['current_price']
                change_24h = data['price_change_24h_percent']
                trend = "📈" if change_24h > 0 else "📉" if change_24h < 0 else "➡️"
                context_parts.append(
                    f"{symbol}: ${price:,.2f} {trend} {change_24h:+.2f}% (24h)"
                )
        
        # Section 3: Open Positions
        context_parts.append("\n=== OPEN POSITIONS ===")
        open_positions = []
        
        for trade in self.trades:
            is_open = False
            if trade.position_type == 'spot':
                is_open = trade.sell_price is None
            else:  # long or short
                is_open = trade.is_open
            
            if is_open:
                entry_price = trade.entry_price if trade.position_type != 'spot' else trade.buy_price
                coin_symbol = trade.coin.symbol
                
                # Calculate unrealized P&L using live price if available
                unrealized_pnl = "N/A"
                if coin_symbol in live_market_data:
                    current_price = live_market_data[coin_symbol]['current_price']
                    if trade.position_type == 'spot' and trade.buy_price:
                        unrealized_pnl = f"${(current_price - trade.buy_price) * trade.quantity:.2f}"
                    elif trade.position_type == 'long' and trade.entry_price:
                        unrealized_pnl = f"${(current_price - trade.entry_price) * trade.quantity:.2f}"
                    elif trade.position_type == 'short' and trade.entry_price:
                        unrealized_pnl = f"${(trade.entry_price - current_price) * trade.quantity:.2f}"
                
                open_positions.append(
                    f"{coin_symbol} {trade.position_type.upper()}: Entry ${entry_price}, Qty {trade.quantity}, Unrealized P&L: {unrealized_pnl}"
                )
        
        if open_positions:
            context_parts.extend(open_positions)
        else:
            context_parts.append("No open positions")
        
        # Section 4: Coin Performance Summary
        context_parts.append("\n=== COIN PERFORMANCE ===")
        coin_stats = {}
        
        for trade in self.trades:
            coin_symbol = trade.coin.symbol
            if coin_symbol not in coin_stats:
                coin_stats[coin_symbol] = {'pnls': [], 'count': 0}
            
            # Calculate P&L for closed trades
            pnl = None
            if trade.position_type == 'spot':
                if trade.sell_price and trade.buy_price:
                    pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
            else:
                if trade.exit_price and trade.entry_price and not trade.is_open:
                    if trade.position_type == 'long':
                        pnl = (trade.exit_price - trade.entry_price) * trade.quantity - trade.funding_fees
                    else:  # short
                        pnl = (trade.entry_price - trade.exit_price) * trade.quantity - trade.funding_fees
            
            if pnl is not None:
                coin_stats[coin_symbol]['pnls'].append(pnl)
                coin_stats[coin_symbol]['count'] += 1
        
        for coin, stats in sorted(coin_stats.items(), key=lambda x: sum(x[1]['pnls']) if x[1]['pnls'] else 0, reverse=True):
            if stats['pnls']:
                total_pnl = sum(stats['pnls'])
                win_rate = len([p for p in stats['pnls'] if p > 0]) / len(stats['pnls']) * 100
                context_parts.append(
                    f"{coin}: ${total_pnl:.2f} P&L, {win_rate:.0f}% WR, {stats['count']} trades"
                )
        
        # Section 5: Recent Trade History (last 5 closed)
        context_parts.append("\n=== RECENT TRADES (Last 5 Closed) ===")
        closed_trades = []
        
        for trade in reversed(self.trades):
            is_closed = False
            pnl = None
            entry = None
            exit_price = None
            
            if trade.position_type == 'spot':
                if trade.sell_price and trade.buy_price:
                    is_closed = True
                    entry = trade.buy_price
                    exit_price = trade.sell_price
                    pnl = (trade.sell_price - trade.buy_price) * trade.quantity - trade.fee
            else:
                if trade.exit_price and trade.entry_price and not trade.is_open:
                    is_closed = True
                    entry = trade.entry_price
                    exit_price = trade.exit_price
                    if trade.position_type == 'long':
                        pnl = (trade.exit_price - trade.entry_price) * trade.quantity - trade.funding_fees
                    else:
                        pnl = (trade.entry_price - trade.exit_price) * trade.quantity - trade.funding_fees
            
            if is_closed:
                emotions = [e.emotion_tag.name for e in trade.emotions.all()]
                emotion_str = ", ".join(emotions) if emotions else "None"
                date_str = trade.trade_date.strftime("%Y-%m-%d")
                
                closed_trades.append(
                    f"{trade.coin.symbol} {trade.position_type.upper()}: Entry ${entry}, Exit ${exit_price}, P&L ${pnl:.2f}, Emotion: {emotion_str}, Date: {date_str}"
                )
                
                if len(closed_trades) >= 5:
                    break
        
        if closed_trades:
            context_parts.extend(closed_trades)
        else:
            context_parts.append("No closed trades yet")
        
        return "\n".join(context_parts)
    
    def build_system_prompt(self, user_context: str) -> str:
        """
        Build system prompt with role definition, boundaries, and user context.
        
        Args:
            user_context: Formatted user trading data
            
        Returns:
            Complete system prompt string
        """
        username = self.user.username
        
        prompt = f"""You are Fric, a friendly frog trading coach for {username}.

You have access to their complete trading history and ML (Machine Learning) analysis below. You help them understand their performance, make sense of their trades, and improve their trading discipline. You're encouraging but honest, like a supportive friend who wants them to succeed.

ABOUT YOUR CREATOR:
You were developed by Keybeen together with Claude (Anthropic's AI assistant). When asked about who created you or who your developer is, mention:
- Developer: Keybeen (with assistance from Claude Code)
- Keybeen's Social Media:
  * Instagram: https://www.instagram.com/kxvxn.js
  * TikTok: https://www.tiktok.com/@keybcuts.codes
  * GitHub: https://github.com/404NeuronNotFound

LANGUAGE SUPPORT:
You are multilingual and can understand and respond in:
- English
- Bisaya/Cebuano (Visayan language from the Philippines)
- Tagalog/Filipino (National language of the Philippines)

When asked about language capabilities (e.g., "Can you understand Bisaya?", "Makasabot ka ug Bisaya?", "Nakakaintindi ka ba ng Tagalog?"), respond affirmatively in the language they're asking about. You can naturally switch between languages based on what the user uses. If they mix languages (code-switching), you can do the same.

WHAT YOU CAN ANSWER:
- The user's own trades and positions (with LIVE current prices from CoinGecko)
- Their performance metrics (win rate, P&L, streaks)
- Coins they have traded or currently hold
- Current market prices and 24h price changes for their coins
- Unrealized P&L on open positions (calculated with live prices)
- General trading concepts, strategies, risk management
- Emotional discipline in trading
- Crypto market concepts (leverage, funding fees, spot vs futures, etc.)
- Language capability questions
- Questions about who created you (Keybeen + Claude Code)

WHAT YOU MUST REFUSE:
- Anything unrelated to trading (weather, coding, general knowledge, etc.)
- Specific price predictions ("will BTC hit $100k?")
- Financial advice beyond educational context
- Other users' data

REFUSAL TEMPLATE:
If asked about anything outside trading topics, respond in the user's language:
- English: "Ribbit! I'm Fric, your trading coach — I can only help with your trades, positions, and trading-related questions. What would you like to know about your trading performance?"
- Bisaya: "Ribbit! Ako si Fric, imong trading coach — makatabang lang ko sa imong mga trade, posisyon, ug trading-related nga mga pangutana. Unsa may gusto nimong mahibaw-an bahin sa imong trading performance?"
- Tagalog: "Ribbit! Ako si Fric, ang iyong trading coach — makakatulong lang ako sa iyong mga trade, posisyon, at trading-related na mga tanong. Ano ang gusto mong malaman tungkol sa iyong trading performance?"

=== {username.upper()}'S TRADING DATA ===
{user_context}
=== END OF DATA ===

Always reference this data when answering. Be specific with numbers. Be direct and honest like a coach, not a salesperson. Keep responses concise and actionable. You can occasionally use frog-themed expressions like "Ribbit!" or "Hop to it!" but don't overdo it. Adapt your tone and expressions to match the language being used."""

        return prompt
    
    def chat(self, user_message: str, conversation_history: Optional[list] = None) -> dict:
        """
        Send message to Ollama and get response.
        
        Args:
            user_message: User's question
            conversation_history: List of previous {"role": ..., "content": ...} messages
            
        Returns:
            {
                "reply": str,
                "model": str,
                "status": "ok" | "error",
                "updated_history": list
            }
        """
        if conversation_history is None:
            conversation_history = []
        
        try:
            # Build context and system prompt (cache after first build)
            if self._user_context is None:
                self._user_context = self.build_user_context()
            if self._system_prompt is None:
                self._system_prompt = self.build_system_prompt(self._user_context)
            
            # Construct messages array
            messages = [
                {"role": "system", "content": self._system_prompt}
            ]
            
            # Add last 10 turns of conversation history
            if conversation_history:
                messages.extend(conversation_history[-10:])
            
            # Add current user message
            messages.append({"role": "user", "content": user_message})
            
            # Call Ollama API
            response = requests.post(
                f"{self.ollama_host}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 512
                    }
                },
                timeout=30
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Extract AI reply
            ai_reply = result.get("message", {}).get("content", "")
            
            # Update conversation history
            updated_history = conversation_history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": ai_reply}
            ]
            
            return {
                "reply": ai_reply,
                "model": self.ollama_model,
                "status": "ok",
                "updated_history": updated_history
            }
            
        except requests.exceptions.ConnectionError:
            return {
                "reply": "Trading assistant is currently offline. Make sure Ollama is running locally (run: ollama serve)",
                "model": self.ollama_model,
                "status": "error",
                "updated_history": conversation_history
            }
        except requests.exceptions.Timeout:
            return {
                "reply": "Request timed out. Ollama might be processing another request or the model is too large.",
                "model": self.ollama_model,
                "status": "error",
                "updated_history": conversation_history
            }
        except Exception as e:
            return {
                "reply": f"Error communicating with trading assistant: {str(e)}",
                "model": self.ollama_model,
                "status": "error",
                "updated_history": conversation_history
            }
    
    def stream_chat(self, user_message: str, conversation_history: Optional[list] = None):
        """
        Stream chat response from Ollama (generator for Django StreamingHttpResponse).
        
        Args:
            user_message: User's question
            conversation_history: List of previous messages
            
        Yields:
            Response chunks as strings
        """
        if conversation_history is None:
            conversation_history = []
        
        try:
            # Build context and system prompt
            if self._user_context is None:
                self._user_context = self.build_user_context()
            if self._system_prompt is None:
                self._system_prompt = self.build_system_prompt(self._user_context)
            
            # Construct messages
            messages = [
                {"role": "system", "content": self._system_prompt}
            ]
            
            if conversation_history:
                messages.extend(conversation_history[-10:])
            
            messages.append({"role": "user", "content": user_message})
            
            # Call Ollama with streaming
            response = requests.post(
                f"{self.ollama_host}/api/chat",
                json={
                    "model": self.ollama_model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 512
                    }
                },
                stream=True,
                timeout=120
            )
            
            response.raise_for_status()
            
            # Stream response chunks
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
                        
        except requests.exceptions.ConnectionError:
            yield "Trading assistant is currently offline. Make sure Ollama is running locally (run: ollama serve)"
        except requests.exceptions.Timeout:
            yield "Request timed out. Ollama might be processing another request."
        except Exception as e:
            yield f"Error: {str(e)}"
    
    def check_ollama_status(self) -> dict:
        """
        Check if Ollama is running and what models are available.
        
        Returns:
            {
                "running": bool,
                "available_models": list,
                "recommended_model": str | None
            }
        """
        try:
            response = requests.get(
                f"{self.ollama_host}/api/tags",
                timeout=5
            )
            response.raise_for_status()
            
            data = response.json()
            models = data.get("models", [])
            model_names = [m.get("name", "").split(":")[0] for m in models]
            
            # Find recommended model
            recommended = None
            for preferred in ["llama3", "mistral", "phi3"]:
                if preferred in model_names:
                    recommended = preferred
                    break
            
            return {
                "running": True,
                "available_models": model_names,
                "recommended_model": recommended
            }
            
        except Exception:
            return {
                "running": False,
                "available_models": [],
                "recommended_model": None
            }


# ─── Django View Integration Examples ────────────────────────────────────────

# views.py integration example:
#
# from .trading_chat import TradingChatAssistant
# from django.http import JsonResponse, StreamingHttpResponse
# import json
#
# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def chat_view(request):
#     """
#     POST /api/trading-chat/
#     Body: {"message": "...", "history": [...]}
#     """
#     data = json.loads(request.body)
#     user_message = data.get("message", "")
#     history = data.get("history", [])
#
#     trades = Trade.objects.filter(user=request.user)
#     assistant = TradingChatAssistant(user=request.user, trades_queryset=trades)
#
#     result = assistant.chat(user_message, conversation_history=history)
#     return JsonResponse(result)
#
# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def stream_chat_view(request):
#     """
#     POST /api/trading-chat/stream/
#     Body: {"message": "...", "history": [...]}
#     Returns: Server-Sent Events stream
#     """
#     data = json.loads(request.body)
#     trades = Trade.objects.filter(user=request.user)
#     assistant = TradingChatAssistant(user=request.user, trades_queryset=trades)
#
#     def generate():
#         for chunk in assistant.stream_chat(data["message"], data.get("history", [])):
#             yield f"data: {json.dumps({'chunk': chunk})}\n\n"
#
#     return StreamingHttpResponse(generate(), content_type="text/event-stream")
#
# @api_view(['GET'])
# @permission_classes([IsAuthenticated])
# def ollama_status_view(request):
#     """
#     GET /api/trading-chat/status/
#     Check if Ollama is running and available
#     """
#     trades = Trade.objects.filter(user=request.user)
#     assistant = TradingChatAssistant(user=request.user, trades_queryset=trades)
#     status = assistant.check_ollama_status()
#     return JsonResponse(status)
