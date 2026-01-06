"""
Autonomous trading bot for Polymarket that runs continuously.
Uses Anthropic Claude AI as the primary decision maker for trade execution.
"""
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import random
import math
import os
import json
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("Warning: anthropic package not installed. Trading bot will use algorithmic strategies as fallback.")


@dataclass
class TradingPosition:
    """Represents an open trading position."""
    market_id: str
    market_title: str
    outcome: str
    entry_price: float
    size: float
    entry_time: datetime
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    strategy: str = ""  # Track which strategy opened this position
    trade_type: str = "swing"  # "scalp" for small volume trades, "swing" for context trades


@dataclass
class SimulatedTrade:
    """Represents a completed trade."""
    id: str
    market_id: str
    market_title: str
    timestamp: datetime
    action: str  # 'BUY' or 'SELL'
    outcome: str
    price: float
    size: float
    reason: str
    profit: Optional[float] = None
    strategy: str = ""
    trade_type: str = "swing"  # "scalp" or "swing"
    market_image: Optional[str] = None  # Market icon/image URL


@dataclass
class MarketAnalysis:
    """Analysis of a market for trading decisions."""
    market_id: str
    volume: float
    liquidity: float
    trend: float  # -1 to 1 (down to up)
    momentum: float  # price change rate
    sentiment: float  # 0 to 1 (negative to positive)
    score: float  # overall trading score
    arbitrage_opportunity: Optional[float] = None  # Profit % if arbitrage exists
    spread: float = 0.0  # Bid-ask spread
    price_yes: float = 0.5
    price_no: float = 0.5
    volume_24h: float = 0.0
    liquidity_depth: float = 0.0
    volume_score: float = 0.0  # Volume-based trading signal strength
    context_score: float = 0.0  # Context-based trading signal strength (trend, momentum, sentiment)


class TradingBot:
    """Autonomous trading bot that simulates trading on Polymarket."""
    
    def __init__(self, initial_balance: float = 2000.0):
        self.balance: float = initial_balance
        self.initial_balance: float = initial_balance
        self.positions: Dict[str, TradingPosition] = {}  # key: market_id-outcome
        self.trades: List[SimulatedTrade] = []
        self.market_analyses: Dict[str, MarketAnalysis] = {}
        self.price_history: Dict[str, List[Tuple[datetime, float]]] = {}  # Track price history
        self.pnl_history: List[Tuple[datetime, float]] = []  # Track P&L over time for charting
        self.is_running: bool = True
        self._task: Optional[asyncio.Task] = None
        self._position_update_task: Optional[asyncio.Task] = None
        self._scalping_task: Optional[asyncio.Task] = None
        
        # Initialize Anthropic Claude client for AI-powered trading decisions
        self.claude_client = None
        if ANTHROPIC_AVAILABLE:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                try:
                    self.claude_client = anthropic.Anthropic(api_key=api_key)
                    print("TradingBot: Anthropic Claude initialized - AI will make trading decisions")
                except Exception as e:
                    print(f"TradingBot: Failed to initialize Claude: {e}")
            else:
                print("TradingBot: ANTHROPIC_API_KEY not set - using algorithmic strategies")
        else:
            print("TradingBot: Anthropic package not available - using algorithmic strategies")
        
        # Initialize CLOB client for fetching markets (public methods only)
        self.clob_client = None
        self._clob_initialized = False
        
    async def _initialize_clob_client(self):
        """Initialize CLOB client for public data extraction (no private key needed)."""
        if self._clob_initialized:
            return
            
        try:
            from py_clob_client.client import ClobClient
            
            host = "https://clob.polymarket.com"
            chain_id = 137  # Polygon mainnet
            
            # Initialize client for public methods only (no private key needed)
            self.clob_client = ClobClient(
                host=host,
                chain_id=chain_id
            )
            
            self._clob_initialized = True
            print("TradingBot: CLOB client initialized successfully (public methods only)")
        except ImportError:
            print("TradingBot: py-clob-client not installed - install with: pip install py-clob-client")
        except Exception as e:
            print(f"TradingBot: Failed to initialize CLOB client: {e}")
            import traceback
            traceback.print_exc()
        
    def start(self, polymarket_client):
        """Start the trading bot in the background."""
        if self._task is None or self._task.done():
            print("TradingBot: Starting trading loops...")
            self.is_running = True
            self.polymarket_client = polymarket_client  # Store client reference for price fetching
            self._task = asyncio.create_task(self._trading_loop(polymarket_client))
            # Start separate position update loop for real-time price updates
            self._position_update_task = asyncio.create_task(self._position_update_loop(polymarket_client))
            # Start separate scalping loop for high-frequency volume trades
            self._scalping_task = asyncio.create_task(self._scalping_loop(polymarket_client))
            print("TradingBot: All trading loops started successfully")
    
    def stop(self):
        """Stop the trading bot."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
        if hasattr(self, '_position_update_task') and self._position_update_task and not self._position_update_task.done():
            self._position_update_task.cancel()
        if hasattr(self, '_scalping_task') and self._scalping_task and not self._scalping_task.done():
            self._scalping_task.cancel()
    
    def _is_market_in_resolution_window(self, market: dict) -> bool:
        """Check if market resolves in 1-4 weeks (7-28 days)."""
        try:
            # Try different possible field names for end date (including CLOB format)
            end_date_str = (
                market.get('end_date_iso') or  # CLOB format
                market.get('endDate') or 
                market.get('end_date') or 
                market.get('resolutionDate') or
                market.get('resolution_date') or
                market.get('endsAt') or
                market.get('ends_at') or
                market.get('endDateISO8601')
            )
            
            if not end_date_str:
                # If no end date, check if it's a short-term market based on question
                question = (market.get('question') or market.get('title') or '').lower()
                # Look for time indicators like "this week", "next week", dates, etc.
                short_term_indicators = ['this week', 'next week', 'today', 'tomorrow', 
                                        'in 7 days', 'in 14 days', 'january 2024', 'february 2024',
                                        'march 2024', 'april 2024', 'may 2024', 'june 2024']
                # If it mentions 2025+ or "2028", likely long-term - filter out
                if any(indicator in question for indicator in short_term_indicators):
                    return True
                # If question mentions years far in future (2025+), filter out
                import re
                years = re.findall(r'\b(20\d{2})\b', question)
                if years:
                    max_year = max([int(y) for y in years])
                    if max_year > 2024:
                        return False
                # Default: if no date info, allow it but prefer markets with explicit dates
                return True
            
            # Parse the end date
            if isinstance(end_date_str, str):
                # Try ISO format
                if 'T' in end_date_str or end_date_str.endswith('Z'):
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                else:
                    end_date = datetime.strptime(end_date_str.split('T')[0], '%Y-%m-%d')
            else:
                return True  # If we can't parse, allow it
            
            now = datetime.now(end_date.tzinfo) if end_date.tzinfo else datetime.now()
            days_until_resolution = (end_date - now).days
            
            # Only include markets resolving in 7-28 days (1-4 weeks) - expanded range
            # This is more flexible and allows more trading opportunities
            return 7 <= days_until_resolution <= 28
            
        except Exception as e:
            print(f"Error checking market resolution date: {e}")
            # On error, default to allowing the market
            return True
    
    def _is_realistic_market(self, market: dict) -> bool:
        """Filter out joke/unrealistic markets."""
        question = (market.get('question') or market.get('title') or market.get('name') or '').lower()
        
        # List of celebrity names and joke indicators
        unrealistic_patterns = [
            # Celebrity names that shouldn't be in serious political markets
            'mrbeast', 'mr beast', 'lebon james', 'lebron', 'kanye', 'kanye west',
            'elon musk', 'elon', 'trump', 'donald trump',  # Trump in unrealistic contexts
            'taylor swift', 'kardashian', 'justin bieber', 'cristiano ronaldo',
            'messi', 'tom brady', 'serena williams',
            
            # Joke indicators
            'meme', 'joke', 'troll', 'satire', 'parody',
            'will i', 'will you', 'will we',  # Personal questions
            'will my', 'will your', 'will our',
            
            # Unrealistic political combinations
            'celebrity.*president', 'celebrity.*nomination', 'youtuber.*president',
            'athlete.*president', 'musician.*president',
        ]
        
        # Check for unrealistic patterns
        import re
        for pattern in unrealistic_patterns:
            if re.search(pattern, question, re.IGNORECASE):
                # But allow if it's a "No" bet on something unrealistic (that's actually smart)
                # We'll filter these out entirely to avoid confusion
                print(f"Filtered out unrealistic market: {market.get('question', 'Unknown')[:80]}")
                return False
        
        # Additional checks for political markets with celebrities
        political_keywords = ['president', 'presidential', 'nomination', 'election', 'senate', 'congress', 'governor']
        has_political = any(keyword in question for keyword in political_keywords)
        
        if has_political:
            # Blocklist of celebrities that shouldn't be in political markets
            celebrity_blocklist = [
                'mrbeast', 'mr beast', 'lebron', 'kanye', 'elon musk', 
                'taylor swift', 'kardashian', 'justin bieber', 'cristiano',
                'messi', 'tom brady', 'serena', 'oprah', 'dwayne johnson',
                'the rock', 'mark cuban', 'bill gates', 'warren buffett'
            ]
            for celebrity in celebrity_blocklist:
                if celebrity in question:
                    print(f"Filtered out celebrity political market: {market.get('question', 'Unknown')[:80]}")
                    return False
        
        return True
    
    async def _get_outcome_prices(self, market: dict, polymarket_client=None) -> Tuple[Optional[float], Optional[float]]:
        """Extract Yes and No prices from market data, prioritizing CLOB API tokens."""
        market_id = market.get('id') or market.get('condition_id') or market.get('question_id')
        price_yes = None
        price_no = None
        
        # 1. Try CLOB API tokens array first (most accurate)
        if market.get('tokens') and isinstance(market.get('tokens'), list):
            for token in market['tokens']:
                if isinstance(token, dict):
                    outcome = str(token.get('outcome', '')).upper()
                    price = token.get('price')
                    if price is not None:
                        try:
                            price_float = float(price)
                            if 0 < price_float < 1:
                                if outcome in ['YES', 'YES ']:
                                    price_yes = price_float
                                elif outcome in ['NO', 'NO ']:
                                    price_no = price_float
                        except (ValueError, TypeError):
                            continue
        
        # 2. Try CLOB API via client if we have condition_id
        if (price_yes is None or price_no is None) and polymarket_client and hasattr(polymarket_client, 'clob_client') and polymarket_client.clob_client:
            condition_id = market.get('condition_id') or market.get('conditionId')
            if condition_id:
                try:
                    # Check if get_market is async or sync
                    import inspect
                    clob_client = polymarket_client.clob_client
                    get_market_method = getattr(clob_client, 'get_market', None)
                    if get_market_method:
                        if inspect.iscoroutinefunction(get_market_method):
                            clob_market = await get_market_method(condition_id)
                        else:
                            # Sync method - run in thread
                            clob_market = await asyncio.to_thread(get_market_method, condition_id)
                        
                        # Handle different response formats
                        if clob_market:
                            tokens = None
                            if isinstance(clob_market, dict):
                                tokens = clob_market.get('tokens') or clob_market.get('data', {}).get('tokens')
                            elif hasattr(clob_market, 'tokens'):
                                tokens = clob_market.tokens
                            
                            if tokens:
                                for token in tokens:
                                    if isinstance(token, dict):
                                        outcome = str(token.get('outcome', '')).strip().upper()
                                        price = token.get('price')
                                        if price is not None:
                                            try:
                                                price_float = float(price)
                                                if 0 < price_float < 1:
                                                    if outcome in ['YES', 'YES ']:
                                                        price_yes = price_float
                                                    elif outcome in ['NO', 'NO ']:
                                                        price_no = price_float
                                            except (ValueError, TypeError):
                                                continue
                except Exception as e:
                    print(f"Warning: CLOB API price fetch failed for market {market_id}: {e}")
                    import traceback
                    traceback.print_exc()
        
        # 3. Fallback to outcomes array (Gamma API format)
        outcomes = market.get('outcomes', [])
        
        if outcomes and len(outcomes) >= 2:
            # Try to get prices from outcomes array
            for outcome in outcomes:
                if not isinstance(outcome, dict):
                    continue
                
                outcome_name = str(outcome.get('outcome', outcome.get('title', outcome.get('name', '')))).upper()
                
                # Try multiple price field names
                price = None
                for price_field in ['price', 'newestPrice', 'lastPrice', 'currentPrice', 'yesPrice', 'noPrice']:
                    if price_field in outcome:
                        try:
                            price = float(outcome[price_field])
                            if 0 < price < 1:
                                break
                        except (ValueError, TypeError):
                            continue
                
                # If no price found in outcome, try market-level fields
                if price is None:
                    for price_field in ['newestPrice', 'price', 'lastPrice', 'currentPrice']:
                        if price_field in market:
                            try:
                                price = float(market[price_field])
                                if 0 < price < 1:
                                    break
                            except (ValueError, TypeError):
                                continue
                
                if price is not None and 0 < price < 1:
                    if 'YES' in outcome_name or outcome_name == 'YES':
                        price_yes = price
                    elif 'NO' in outcome_name or outcome_name == 'NO':
                        price_no = price
                    # If we can't determine which outcome, use order (first = Yes, second = No)
                    elif price_yes is None:
                        price_yes = price
                    elif price_no is None:
                        price_no = price
        
        # Fallback: use main market price fields
        if price_yes is None:
            for price_field in ['newestPrice', 'price', 'lastPrice', 'currentPrice', 'yesPrice']:
                if price_field in market:
                    try:
                        price_yes = float(market[price_field])
                        if 0 < price_yes < 1:
                            break
                    except (ValueError, TypeError):
                        continue
        
        # Calculate No price from Yes price if we have it
        if price_yes is not None and price_no is None:
            price_no = 1.0 - price_yes
        elif price_no is not None and price_yes is None:
            price_yes = 1.0 - price_no
        
        # Final fallback: if we still don't have prices, return None to skip this market
        if price_yes is None or price_no is None:
            # Log warning but don't use default 0.5 - skip this market instead
            print(f"Warning: Could not extract prices for market {market.get('id', 'unknown')}. Skipping.")
            return None, None
        
        return price_yes, price_no
    
    async def analyze_market(self, market: dict) -> MarketAnalysis:
        """Analyze a market with realistic trading strategies."""
        # Handle both CLOB (condition_id) and Gamma (id) formats
        market_id = market.get('id') or market.get('condition_id') or market.get('question_id') or ''
        volume = float(market.get('volumeNum', market.get('volume', 0)))
        liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
        volume_24h = float(market.get('volume24h', volume))
        
        # Debug: Log volume data to see if it's being preserved
        if volume > 0 or liquidity > 0:
            print(f"  Analyzing market {market_id[:20]}...: volume={volume:.0f}, liquidity={liquidity:.0f}, volume_24h={volume_24h:.0f}")
        
        # Get Yes/No prices
        price_yes, price_no = await self._get_outcome_prices(market, self.polymarket_client)
        
        # Skip if we couldn't get prices
        if price_yes is None or price_no is None:
            # Still return analysis but with default prices and a base score
            print(f"  WARNING: Could not extract prices for market {market_id[:20]}, using defaults")
            # Use default prices but still give a score based on volume/liquidity
            price_yes = 0.5
            price_no = 0.5
            # Calculate a minimal score based on volume/liquidity only
            volume_factor = min(1.0, volume_24h / 50000) if volume_24h > 0 else 0.3
            liquidity_score = min(20, liquidity / 1000) if liquidity > 0 else 10
            base_score = 5
            minimal_score = base_score + (volume_factor * 30) + liquidity_score
            
            return MarketAnalysis(
                market_id=market_id,
                volume=volume,
                liquidity=liquidity,
                trend=0.0,
                momentum=0.0,
                sentiment=0.5,
                score=minimal_score,  # Give at least some score
                arbitrage_opportunity=None,
                spread=0.0,
                price_yes=price_yes,
                price_no=price_no,
                volume_24h=volume_24h,
                liquidity_depth=liquidity,
                volume_score=(volume_factor * 50) + (liquidity_score * 1.5),
                context_score=minimal_score
            )
        
        # Track price history for momentum calculation
        if market_id not in self.price_history:
            self.price_history[market_id] = []
        
        current_time = datetime.now()
        self.price_history[market_id].append((current_time, price_yes))
        # Keep only last 20 price points
        self.price_history[market_id] = self.price_history[market_id][-20:]
        
        # Calculate momentum from price history
        momentum = 0.0
        if len(self.price_history[market_id]) >= 2:
            recent_prices = [p[1] for p in self.price_history[market_id][-5:]]
            if len(recent_prices) >= 2:
                price_change = recent_prices[-1] - recent_prices[0]
                momentum = price_change * 100  # Percentage points
        
        # Calculate trend (short-term vs medium-term)
        trend = 0.0
        if len(self.price_history[market_id]) >= 5:
            short_term = self.price_history[market_id][-3:]
            medium_term = self.price_history[market_id][-5:]
            avg_short = sum(p[1] for p in short_term) / len(short_term)
            avg_medium = sum(p[1] for p in medium_term) / len(medium_term)
            trend = (avg_short - avg_medium) * 10  # Amplify for signal
        
        # Arbitrage detection: Check if Yes + No != 1.0 (with tolerance for fees)
        arbitrage_opportunity = None
        price_sum = price_yes + price_no
        if price_sum < 0.98:  # Arbitrage exists if sum < 0.98 (2% fee buffer)
            # We can buy both outcomes for less than $1, guaranteed profit
            arbitrage_profit = (1.0 - price_sum) * 100  # Percentage profit
            if arbitrage_profit > 0.5:  # Only if profit > 0.5%
                arbitrage_opportunity = arbitrage_profit
        
        # Calculate spread (bid-ask difference)
        # Use liquidity depth as proxy for spread
        spread = 0.0
        if liquidity > 0:
            # Lower liquidity = higher spread
            spread = max(0.001, min(0.05, 1000 / liquidity))  # 0.1% to 5%
        
        # Sentiment calculation (volume-weighted)
        base_sentiment = 0.5
        if momentum != 0:
            base_sentiment = 0.5 + (momentum / 200)  # Convert momentum to sentiment
        
        # Handle zero volume (CLOB API doesn't provide volume data)
        # When volume is 0, use a default volume_factor to still allow trading
        if volume_24h > 0:
            volume_factor = min(1.0, volume_24h / 50000)  # Normalize: $50k = full factor
        else:
            # CLOB API: no volume data, but still allow trading based on price signals
            volume_factor = 0.3  # Default to 30% to allow some volume-based scoring
        
        sentiment = max(0.0, min(1.0, base_sentiment * (0.6 + volume_factor * 0.4)))
        
        # Calculate trading score
        # Arbitrage gets highest priority
        if arbitrage_opportunity:
            score = 80 + min(20, arbitrage_opportunity * 2)  # 80-100 for arbitrage
        else:
            # Volume strategy: Higher volume = more reliable
            # When volume is 0, still give some score based on other factors
            volume_score = volume_factor * 30
            
            # Momentum strategy: Give score even with small momentum, or base score if no history
            if len(self.price_history.get(market_id, [])) >= 2:
                momentum_score = abs(momentum) * 0.5 if abs(momentum) > 0.5 else 0
            else:
                # No price history yet - give base momentum score based on price position
                # Prices away from 0.5 have more potential
                momentum_score = abs(price_yes - 0.5) * 20  # Up to 10 points
            
            # Trend strategy: Give score even with small trends, or base score if no history
            if len(self.price_history.get(market_id, [])) >= 5:
                trend_score = abs(trend) * 2 if abs(trend) > 0.05 else 0
            else:
                # No price history yet - give base trend score
                trend_score = abs(price_yes - 0.5) * 15  # Up to 7.5 points
            
            # Liquidity strategy: Higher liquidity = better execution
            # Always give at least some liquidity score
            if liquidity > 0:
                liquidity_score = min(20, liquidity / 1000)
            else:
                liquidity_score = 10  # Higher default liquidity score
            
            # Mean reversion: Give score based on price position (always give some score)
            mean_reversion_score = 0
            if 0.25 < price_yes < 0.45 or 0.55 < price_yes < 0.75:
                mean_reversion_score = 12  # Mild reversion opportunity
            elif 0.2 < price_yes < 0.3 or 0.7 < price_yes < 0.8:
                mean_reversion_score = 18  # Moderate reversion opportunity
            elif price_yes < 0.2 or price_yes > 0.8:
                mean_reversion_score = 25  # Strong reversion opportunity
            else:
                # Price is around 0.5 - still give some score based on distance from 0.5
                mean_reversion_score = abs(price_yes - 0.5) * 30  # Up to 15 points
            
            # Base score: Always give at least 5 points just for having a valid market
            base_score = 5
            
            # Calculate raw score (always positive)
            raw_score = base_score + volume_score + momentum_score + trend_score + liquidity_score + mean_reversion_score
            
            # Calculate separate volume and context scores
            # Volume score: purely based on trading volume and liquidity (for scalping)
            volume_score_value = (volume_factor * 50) + (liquidity_score * 1.5)
            
            # Context score: based on trend, momentum, sentiment (for swing trading)
            context_score_value = (momentum_score * 2) + (trend_score * 3) + ((sentiment - 0.5) * 40) + mean_reversion_score + base_score
            
            # Direction: positive for bullish, negative for bearish
            # But ALWAYS keep score positive - direction is just for trading decisions
            score_direction = 1  # 1 for bullish, -1 for bearish
            
            price_history_len = len(self.price_history.get(market_id, []))
            if price_history_len >= 2:
                if momentum < 0 or trend < 0:
                    score_direction = -1
            else:
                # No history yet - use price position for direction
                # If price < 0.5, bearish, if > 0.5, bullish
                if price_yes < 0.5:
                    score_direction = -1
            
            # IMPORTANT: Keep score always positive for display
            # The direction is stored separately and used for trading decisions
            score = raw_score  # Always positive (raw_score is always positive)
            
            # Debug: Log score calculation for first few markets
            if volume > 1000:  # Only log for high-volume markets to avoid spam
                print(f"    Score calc for {market_id[:20]}: base={base_score}, vol={volume_score:.1f}, mom={momentum_score:.1f}, trend={trend_score:.1f}, liq={liquidity_score:.1f}, mean={mean_reversion_score:.1f}, total={score:.1f}, price_yes={price_yes:.3f}")
            
            # For context_score, keep it positive
            context_score_value = abs(context_score_value)
        
        return MarketAnalysis(
            market_id=market_id,
            volume=volume,
            liquidity=liquidity,
            trend=trend,
            momentum=momentum,
            sentiment=sentiment,
            score=score,
            arbitrage_opportunity=arbitrage_opportunity,
            spread=spread,
            price_yes=price_yes,
            price_no=price_no,
            volume_24h=volume_24h,
            liquidity_depth=liquidity,
            volume_score=volume_score_value,
            context_score=context_score_value
        )
    
    async def _enrich_markets_with_clob_prices(self, markets: List[dict], polymarket_client) -> List[dict]:
        """Enrich Gamma API markets with accurate prices from CLOB API.
        Keeps Gamma volume/liquidity data but uses CLOB for accurate prices."""
        if not polymarket_client or not hasattr(polymarket_client, 'clob_client') or not polymarket_client.clob_client:
            # No CLOB client available, return markets as-is
            return markets
        
        enriched_markets = []
        enriched_count = 0
        
        # Process markets in batches to avoid overwhelming the API
        batch_size = 20
        for i in range(0, len(markets), batch_size):
            batch = markets[i:i + batch_size]
            
            # Process batch concurrently
            tasks = []
            for market in batch:
                tasks.append(self._enrich_single_market(market, polymarket_client))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for market, result in zip(batch, results):
                if isinstance(result, Exception):
                    # If enrichment failed, keep original market with Gamma prices
                    print(f"Warning: Could not enrich market {market.get('id')} with CLOB prices: {result}")
                    enriched_markets.append(market)
                else:
                    enriched_markets.append(result)
                    if result.get('_clob_enriched'):
                        enriched_count += 1
            
            # Small delay between batches to avoid rate limiting
            if i + batch_size < len(markets):
                await asyncio.sleep(0.5)
        
        print(f"Enriched {enriched_count}/{len(markets)} markets with CLOB prices")
        return enriched_markets
    
    async def _enrich_single_market(self, market: dict, polymarket_client) -> dict:
        """Enrich a single market with CLOB API prices."""
        condition_id = market.get('condition_id') or market.get('conditionId')
        market_id = market.get('id')
        
        # Try to get condition_id from market ID if not present
        if not condition_id and market_id:
            # Some Gamma API markets use market_id as condition_id
            condition_id = market_id
        
        # If we have condition_id, fetch prices from CLOB
        if condition_id and polymarket_client.clob_client:
            try:
                clob_market = await polymarket_client.clob_client.get_market(condition_id)
                if clob_market:
                    # Handle different CLOB response formats
                    tokens = None
                    if isinstance(clob_market, dict):
                        tokens = clob_market.get('tokens') or clob_market.get('data', {}).get('tokens')
                    elif hasattr(clob_market, 'tokens'):
                        tokens = clob_market.tokens
                    
                    if tokens:
                        # Update market with CLOB prices while EXPLICITLY preserving Gamma volume data
                        market = market.copy()  # Don't modify original
                        
                        # EXPLICITLY preserve volume/liquidity fields from Gamma API
                        preserved_volume = market.get('volumeNum', market.get('volume', 0))
                        preserved_liquidity = market.get('liquidityNum', market.get('liquidity', 0))
                        preserved_volume_24h = market.get('volume24h', preserved_volume)
                        
                        # Update tokens array (don't overwrite, append if needed)
                        if 'tokens' not in market:
                            market['tokens'] = []
                        else:
                            # Keep existing tokens if any, but we'll add CLOB tokens
                            market['tokens'] = market.get('tokens', [])
                        
                        for token in tokens:
                            if isinstance(token, dict):
                                outcome = token.get('outcome', '')
                                price = token.get('price')
                                
                                if price is not None:
                                    try:
                                        price_float = float(price)
                                        if 0 < price_float < 1:
                                            # Check if token already exists
                                            existing_token = next((t for t in market['tokens'] if isinstance(t, dict) and t.get('outcome', '').upper() == outcome.upper()), None)
                                            if not existing_token:
                                                market['tokens'].append({
                                                    'outcome': outcome,
                                                    'price': price_float
                                                })
                                            
                                            # Update direct price fields for compatibility
                                            if outcome.upper() in ['YES', 'YES ']:
                                                market['newestPrice'] = price_float
                                                market['price'] = price_float
                                                market['yesPrice'] = price_float
                                            elif outcome.upper() in ['NO', 'NO ']:
                                                market['noPrice'] = price_float
                                    except (ValueError, TypeError):
                                        continue
                        
                        # RESTORE volume/liquidity fields to ensure they're preserved
                        market['volumeNum'] = preserved_volume
                        market['volume'] = preserved_volume
                        market['liquidityNum'] = preserved_liquidity
                        market['liquidity'] = preserved_liquidity
                        market['volume24h'] = preserved_volume_24h
                        
                        market['_clob_enriched'] = True
                        return market
            except Exception as e:
                # If CLOB fetch fails, keep Gamma prices
                pass
        
        # If enrichment failed, return original market (with volume data intact)
        market['_clob_enriched'] = False
        return market
    
    async def _fetch_markets_expanded(self, polymarket_client) -> List[dict]:
        """Fetch markets using multiple strategies, prioritizing trending and short-term markets.
        Uses Gamma API for volume data, then enriches with CLOB API for accurate prices."""
        all_markets = {}
        market_ids_seen = set()
        
        try:
            # Strategy 1: Trending markets (high volume, recent activity) - PRIORITY
            # Use Gamma API - it has BOTH volume AND prices
            print("Fetching trending markets from Gamma API...")
            volume_markets = await polymarket_client.get_markets(limit=300, offset=0, use_clob=False)
            
            # Separate markets by resolution window
            short_term_markets = []
            other_markets = []
            
            for market in volume_markets:
                market_id = market.get('id')
                if market_id and market_id not in market_ids_seen:
                    if self._is_market_in_resolution_window(market):
                        short_term_markets.append(market)
                    else:
                        other_markets.append(market)
                    market_ids_seen.add(market_id)
            
            # Prioritize short-term markets - add them first
            for market in short_term_markets:
                all_markets[market.get('id')] = market
            
            print(f"Found {len(short_term_markets)} short-term markets (1-2 weeks), {len(other_markets)} long-term markets")
            
            # Strategy 2: High liquidity markets - ONLY short-term
            print("Fetching high liquidity short-term markets from Gamma API...")
            try:
                # Fetch with higher offset to get different markets
                liquidity_markets = await polymarket_client.get_markets(limit=150, offset=100, use_clob=False)
                short_term_count = 0
                for market in liquidity_markets:
                    market_id = market.get('id')
                    if market_id and market_id not in market_ids_seen:
                        # Only include if it's in resolution window
                        if self._is_market_in_resolution_window(market):
                            liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
                            # Allow CLOB markets (liquidity == 0) or high liquidity markets
                            if liquidity > 2000 or liquidity == 0:
                                all_markets[market_id] = market
                                market_ids_seen.add(market_id)
                                short_term_count += 1
                print(f"Found {short_term_count} additional short-term liquidity markets")
            except Exception as e:
                print(f"Error fetching liquidity markets: {e}")
            
            # Strategy 3: Search for trending keywords to find active markets
            trending_searches = [
                "2024", "2025", "election", "president", "crypto", "bitcoin", "ethereum",
                "sports", "nfl", "nba", "soccer", "football", "basketball",
                "politics", "economy", "stock", "market", "tech", "AI"
            ]
            
            print(f"Searching for short-term markets by trending keywords...")
            for keyword in trending_searches[:8]:  # Limit to avoid too many requests
                try:
                    searched_markets = await polymarket_client.search_markets(keyword, limit=30)
                    short_term_count = 0
                    for market in searched_markets:
                        market_id = market.get('id')
                        if market_id and market_id not in market_ids_seen:
                            # Only include short-term markets
                            if self._is_market_in_resolution_window(market):
                                volume = float(market.get('volumeNum', market.get('volume', 0)))
                                liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
                                # Include if it has reasonable volume or liquidity OR if volume/liquidity is 0 (CLOB API)
                                if volume > 500 or liquidity > 800 or (volume == 0 and liquidity == 0):
                                    all_markets[market_id] = market
                                    market_ids_seen.add(market_id)
                                    short_term_count += 1
                    if short_term_count > 0:
                        print(f"Found {short_term_count} short-term markets for '{keyword}'")
                    await asyncio.sleep(0.5)  # Rate limiting between searches
                except Exception as e:
                    print(f"Error searching for '{keyword}': {e}")
                    continue
            
            print(f"Total unique markets found: {len(all_markets)}")
            
            # Convert to list and sort by combined score (volume + liquidity)
            # Prioritize trending markets (high volume/activity)
            markets_list = list(all_markets.values())
            markets_list.sort(
                key=lambda x: (
                    # Prioritize by volume (trending indicator)
                    float(x.get('volumeNum', 0) or x.get('volume', 0) or 0) * 1.5 +  # Volume weighted more
                    float(x.get('liquidityNum', 0) or x.get('liquidity', 0) or 0) * 0.5 +
                    # Bonus for markets resolving soon (within 10 days)
                    (10 if self._is_market_in_resolution_window(x) else 0) * 1000
                ),
                reverse=True
            )
            
            # Log summary
            short_term_count = sum(1 for m in markets_list if self._is_market_in_resolution_window(m))
            print(f"Total markets after filtering: {len(markets_list)} ({short_term_count} short-term 1-2 weeks)")
            
            # Gamma API already has both volume and prices - no need to enrich
            if markets_list:
                sample_market = markets_list[0]
                sample_volume = float(sample_market.get('volumeNum', sample_market.get('volume', 0)))
                sample_liquidity = float(sample_market.get('liquidityNum', sample_market.get('liquidity', 0)))
                print(f"  Sample market: volume={sample_volume:.0f}, liquidity={sample_liquidity:.0f}")
            
            return markets_list
            
        except Exception as e:
            print(f"Error in expanded market fetch: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to basic fetch (Gamma API has everything)
            return await polymarket_client.get_markets(limit=100, offset=0, use_clob=False)
    
    async def _trading_loop(self, polymarket_client):
        """Main trading loop that runs continuously."""
        debug_mode = os.getenv("DEBUG", "false").lower() == "true"
        if debug_mode:
            print("=" * 60)
            print("TRADING LOOP STARTED")
            print("=" * 60)
        cycle_count = 0
        while self.is_running:
            try:
                cycle_count += 1
                
                # Initialize CLOB client if not already done
                if not self._clob_initialized:
                    await self._initialize_clob_client()
                
                # Fetch markets from CLOB API
                markets = []
                debug_mode = os.getenv("DEBUG", "false").lower() == "true"
                if self.clob_client:
                    try:
                        if debug_mode:
                            print(f"Fetching markets from CLOB API (cycle {cycle_count})...")
                        clob_response = await self.clob_client.get_markets()
                        
                        if hasattr(clob_response, 'data') and isinstance(clob_response.data, list):
                            markets = clob_response.data
                        elif isinstance(clob_response, dict) and 'data' in clob_response:
                            markets = clob_response['data']
                        elif isinstance(clob_response, list):
                            markets = clob_response
                        else:
                            if debug_mode:
                                print(f"Unexpected CLOB response format: {type(clob_response)}, falling back to Gamma API")
                            markets = await polymarket_client.get_markets(limit=200, offset=0, use_clob=False)
                    except Exception as e:
                        if debug_mode:
                            print(f"Error fetching from CLOB API: {e}, falling back to Gamma API")
                            import traceback
                            traceback.print_exc()
                        markets = await polymarket_client.get_markets(limit=200, offset=0, use_clob=False)
                else:
                    markets = await polymarket_client.get_markets(limit=200, offset=0, use_clob=False)
                
                if not markets:
                    if debug_mode:
                        print("WARNING: No markets fetched from Polymarket API")
                    await asyncio.sleep(10)
                    continue
                
                if debug_mode:
                    print(f"Fetched {len(markets)} markets from Polymarket")
                    print(f"Analyzing {len(markets)} markets for trading opportunities...")
                
                # Analyze all fetched markets, prioritizing short-term trending markets
                analyzed_count = 0
                short_term_analyzed = 0
                
                for market in markets:
                    try:
                        # Filter out unrealistic/joke markets
                        if not self._is_realistic_market(market):
                            continue
                        
                        # CRITICAL: Only analyze markets that resolve in 1-2 weeks
                        # TEMPORARILY RELAXED: Allow markets up to 4 weeks for testing
                        resolution_ok = self._is_market_in_resolution_window(market)
                        # Also allow markets resolving in 2-4 weeks for more opportunities
                        if not resolution_ok:
                            # Check if market resolves in 2-4 weeks as fallback
                            try:
                                end_date_str = market.get('end_date_iso') or market.get('endDate') or market.get('end_date') or market.get('endDateISO8601')
                                if end_date_str:
                                    # Reject markets clearly in 2026+ (over a year away)
                                    end_date_str_lower = str(end_date_str).lower()
                                    if '2026' in end_date_str_lower or '2027' in end_date_str_lower or '2028' in end_date_str_lower:
                                        resolution_ok = False
                                    else:
                                        if 'T' in str(end_date_str) or str(end_date_str).endswith('Z'):
                                            end_date = datetime.fromisoformat(str(end_date_str).replace('Z', '+00:00'))
                                        else:
                                            end_date = datetime.strptime(str(end_date_str).split('T')[0], '%Y-%m-%d')
                                        now = datetime.now(end_date.tzinfo) if end_date.tzinfo else datetime.now()
                                        days_until_resolution = (end_date - now).days
                                        if 7 <= days_until_resolution <= 28:  # 1-4 weeks
                                            resolution_ok = True
                                        elif days_until_resolution > 365:  # Over a year
                                            resolution_ok = False
                            except Exception as e:
                                # On error, be conservative and skip
                                resolution_ok = False
                        
                        if not resolution_ok:
                            continue  # Skip long-term markets
                        
                        # Filter: only analyze markets with minimum volume/liquidity (very relaxed)
                        # NOTE: After enrichment, markets should have Gamma volume data + CLOB prices
                        volume = float(market.get('volumeNum', market.get('volume', 0)))
                        liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
                        
                        # Debug: Log first few markets being analyzed
                        if analyzed_count < 3:
                            print(f"  Market {market.get('id', 'unknown')[:30]}: volume={volume:.0f}, liquidity={liquidity:.0f}")
                        
                        # Include if volume > 100 or liquidity > 200 OR if volume is 0 (fallback for markets without volume)
                        # After enrichment, most markets should have volume from Gamma API
                        if volume > 100 or liquidity > 200 or (volume == 0 and liquidity == 0):
                            analysis = await self.analyze_market(market)
                            # Use market_id from analysis or fallback to market's ID
                            analysis_market_id = analysis.market_id or market_id
                            self.market_analyses[analysis_market_id] = analysis
                            analyzed_count += 1
                            short_term_analyzed += 1
                            
                            # Debug: Log analysis results for first few
                            if analyzed_count <= 3:
                                print(f"    Analysis result: score={analysis.score:.2f}, volume_score={analysis.volume_score:.2f}, context_score={analysis.context_score:.2f}")
                            
                            # Limit analysis to prevent memory issues, prioritize trending (already sorted)
                            if analyzed_count >= 150:  # Analyze up to 150 markets
                                break
                    except Exception as e:
                        print(f"Error analyzing market {market.get('id')}: {e}")
                        continue
                
                print(f"Analyzed {short_term_analyzed} short-term markets (1-2 week resolution)")
                print(f"Total analyzed: {analyzed_count} markets")
                print(f"Current balance: ${self.balance:.2f}, Active positions: {len(self.positions)}")
                
                # Update existing positions (check all markets for position updates)
                await self._update_positions(markets, polymarket_client)
                
                # Find trading opportunities from analyzed markets
                print(f"Executing trades on {len(self.market_analyses)} analyzed markets...")
                if len(self.market_analyses) == 0:
                    print("WARNING: No markets have been analyzed! Cannot execute trades.")
                else:
                    print(f"Market analyses available: {list(self.market_analyses.keys())[:5]}...")  # Show first 5
                await self._execute_trades(markets)
                
                # Cleanup: Remove old analyses for markets we're no longer tracking
                if len(self.market_analyses) > 200:
                    # Keep only the most recent 200 analyses
                    market_ids_in_list = {m.get('id') for m in markets if m.get('id')}
                    analyses_to_keep = {
                        k: v for k, v in self.market_analyses.items()
                        if k in market_ids_in_list
                    }
                    self.market_analyses = analyses_to_keep
                
                # Periodic cleanup every 20 cycles
                if cycle_count % 20 == 0:
                    self._cleanup_old_data()
                
                # Keep only last 500 trades to prevent memory issues
                if len(self.trades) > 500:
                    self.trades = self.trades[-500:]
                
                # Wait before next iteration
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in trading loop: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(10)
    
    async def _update_positions(self, markets: List[dict] = None, polymarket_client = None):
        """Update current prices and P&L for open positions."""
        if not self.positions:
            return
        
        # If markets not provided, fetch them
        if markets is None and polymarket_client:
            try:
                # Get markets for all open positions
                market_ids = [p.market_id for p in self.positions.values()]
                markets = []
                for market_id in market_ids:
                    market_data = await polymarket_client.get_market_by_id(market_id)
                    if market_data:
                        markets.append(market_data)
            except Exception as e:
                print(f"Error fetching markets for position update: {e}")
                return
        
        if not markets:
            return
        
        for position_key, position in list(self.positions.items()):
            market = next((m for m in markets if m.get('id') == position.market_id), None)
            if market:
                price_yes, price_no = await self._get_outcome_prices(market, self.polymarket_client)
                
                # Skip if we couldn't get prices
                if price_yes is None or price_no is None:
                    continue
                
                # Determine current price based on outcome
                if position.outcome in ['Yes', 'YES', 'yes']:
                    current_price = price_yes
                else:
                    current_price = price_no
                
                position.current_price = current_price
                
                # Calculate unrealized P&L
                # Current value of position: position.size * (current_price / entry_price)
                # Unrealized P&L = current value - original investment
                current_value = position.size * (current_price / position.entry_price)
                position.unrealized_pnl = current_value - position.size
                
                self.positions[position_key] = position
    
    async def _position_update_loop(self, polymarket_client):
        """Separate loop that updates position prices every 2 seconds for real-time updates."""
        while self.is_running:
            try:
                if self.positions:
                    await self._update_positions(polymarket_client=polymarket_client)
                    # Update P&L history after position updates
                    self._update_pnl_history()
                await asyncio.sleep(2)  # Update every 2 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in position update loop: {e}")
                await asyncio.sleep(5)
    
    async def _scalping_loop(self, polymarket_client):
        """Separate high-frequency loop for volume scalping trades (every 2-5 seconds)."""
        import random
        
        while self.is_running:
            try:
                # Fetch high-volume markets for scalping (Gamma API has everything)
                markets = await polymarket_client.get_markets(limit=100, offset=0, use_clob=False)
                
                if not markets:
                    await asyncio.sleep(3)
                    continue
                
                # Filter for high-volume, realistic, short-term markets
                scalp_opportunities = []
                
                for market in markets[:50]:  # Check top 50 high-volume markets
                    try:
                        # Quick filters
                        if not self._is_realistic_market(market):
                            continue
                        
                        if not self._is_market_in_resolution_window(market):
                            continue
                        
                        volume = float(market.get('volumeNum', market.get('volume', 0)))
                        liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
                        
                        # Scalping requires reasonable volume (relaxed)
                        # Allow CLOB markets (volume == 0) since they have accurate prices
                        if (volume > 0 and volume < 500) or (liquidity > 0 and liquidity < 300):
                            continue
                        # If volume is 0, it's from CLOB API - allow it for scalping
                        
                        # Quick analysis for scalping
                        analysis = await self.analyze_market(market)
                        
                        # Scalping criteria: Much more relaxed thresholds
                        if analysis.volume_score > 10 and abs(analysis.score) > 5:
                            market_title = market.get('question') or market.get('title') or market.get('name') or 'Unknown'
                            
                            # Check if we already have a position
                            direction = 'Yes' if analysis.score > 0 else 'No'
                            position_key = f"{analysis.market_id}-{direction}"
                            
                            if position_key not in self.positions:
                                scalp_opportunities.append({
                                    'market': market,
                                    'analysis': analysis,
                                    'outcome': direction,
                                    'priority': analysis.volume_score
                                })
                    except Exception as e:
                        continue
                
                # Sort by volume score (highest first)
                scalp_opportunities.sort(key=lambda x: x['priority'], reverse=True)
                
                # Execute up to 3-5 scalping trades per cycle (small positions)
                max_scalps = min(5, len(scalp_opportunities))
                
                for opp in scalp_opportunities[:max_scalps]:
                    if self.balance < 0.5:  # Need minimum balance
                        break
                    
                    market = opp['market']
                    analysis = opp['analysis']
                    outcome = opp['outcome']
                    market_title = market.get('question') or market.get('title') or market.get('name') or 'Unknown'
                    
                    # Scalp position size: 1-2% of portfolio
                    position_pct = 0.015  # 1.5% base for scalps
                    if abs(analysis.score) > 20:
                        position_pct = 0.02  # 2% for high confidence
                    elif abs(analysis.score) > 10:
                        position_pct = 0.015  # 1.5% for medium confidence
                    else:
                        position_pct = 0.01  # 1% for low confidence
                    
                    position_size = self.balance * position_pct
                    position_size = max(0.10, min(position_size, self.balance * 0.02))  # 1-2% of portfolio
                    
                    if position_size > self.balance:
                        continue
                    
                    price_yes, price_no = await self._get_outcome_prices(market, self.polymarket_client)
                    if price_yes is None or price_no is None:
                        continue
                    
                    price = price_yes if outcome in ['Yes', 'YES', 'yes'] else price_no
                    
                    # Only allow prices between $0.10 and $0.99
                    if price < 0.10 or price > 0.99:
                        continue
                    
                    # Calculate remaining profit margin
                    max_profit_per_share = 1.0 - price if outcome in ['Yes', 'YES', 'yes'] else price
                    if max_profit_per_share <= 0:
                        continue  # No profit potential
                    
                    # Execute scalp trade
                    reason = f"Volume Scalp: {outcome} @ {price:.3f} (Vol: {analysis.volume:.0f}, Margin: {max_profit_per_share:.3f})"
                    await self._open_position(market, analysis, outcome, market_title, price,
                                            position_size, 'volume_scalp', reason, 'scalp')
                
                # Wait 2-5 seconds before next scalping cycle (randomized to avoid patterns)
                wait_time = 2 + random.random() * 3  # 2-5 seconds
                await asyncio.sleep(wait_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in scalping loop: {e}")
                await asyncio.sleep(3)
    
    async def _get_claude_trading_decision(self, market: dict, analysis: MarketAnalysis) -> Optional[Dict]:
        """Use Claude AI to analyze market and make trading decision."""
        if not self.claude_client:
            return None
        
        try:
            # Prepare market data for Claude - handle both CLOB and Gamma API formats
            market_title = market.get('question') or market.get('title') or market.get('name', 'Unknown')
            description = market.get('description', '')
            
            # Extract prices from CLOB tokens if available
            price_yes = analysis.price_yes
            price_no = analysis.price_no
            
            # Try to get prices from CLOB tokens directly
            if market.get('tokens') and isinstance(market.get('tokens'), list):
                for token in market['tokens']:
                    if isinstance(token, dict):
                        outcome = str(token.get('outcome', '')).strip().upper()
                        price = token.get('price')
                        if price is not None:
                            try:
                                price_float = float(price)
                                if 0 < price_float < 1:
                                    if outcome in ['YES', 'YES ']:
                                        price_yes = price_float
                                    elif outcome in ['NO', 'NO ']:
                                        price_no = price_float
                            except (ValueError, TypeError):
                                continue
            
            volume = analysis.volume
            liquidity = analysis.liquidity
            momentum = analysis.momentum
            trend = analysis.trend
            sentiment = analysis.sentiment
            score = analysis.score
            
            # Get market metadata from CLOB format
            end_date = market.get('end_date_iso') or market.get('endDate') or market.get('endDateISO8601', 'Unknown')
            active = market.get('active', True)
            closed = market.get('closed', False)
            accepting_orders = market.get('accepting_orders', True)
            
            # Get price history for context
            price_history_str = "No price history yet"
            if market.get('id') in self.price_history:
                history = self.price_history[market.get('id')]
                if len(history) > 0:
                    recent_prices = [f"{p[1]:.3f}" for p in history[-5:]]
                    price_history_str = ", ".join(recent_prices)
            
            # Check if we already have a position
            has_position_yes = f"{analysis.market_id}-Yes" in self.positions
            has_position_no = f"{analysis.market_id}-No" in self.positions
            
            prompt = f"""You are an expert Polymarket trading bot. Analyze this market and decide whether to trade.

MARKET INFORMATION:
- Title: {market_title}
- Description: {description[:200] if description else 'N/A'}
- Market ID: {analysis.market_id}
- Condition ID: {market.get('condition_id', 'N/A')}
- Current Yes Price: ${price_yes:.4f}
- Current No Price: ${price_no:.4f}
- End Date: {end_date}
- Active: {active}
- Closed: {closed}
- Accepting Orders: {accepting_orders}
- Volume (24h): ${volume:,.2f}
- Liquidity: ${liquidity:,.2f}
- Momentum: {momentum:.2f}%
- Trend: {trend:.3f}
- Sentiment Score: {sentiment:.3f}
- Technical Score: {score:.2f}
- Recent Price History: {price_history_str}

CURRENT PORTFOLIO:
- Balance: ${self.balance:.2f}
- Active Positions: {len(self.positions)}
- Already have Yes position: {has_position_yes}
- Already have No position: {has_position_no}

TRADING CONSTRAINTS:
- Position size must be 1-2% of portfolio (${self.balance * 0.01:.2f} - ${self.balance * 0.02:.2f})
- Entry price must be between $0.10 and $0.99
- Only trade markets resolving in 1-2 weeks
- Don't open duplicate positions
- Only trade if market is active and accepting orders

Analyze this market and provide a trading decision in JSON format:
{{
  "should_trade": true/false,
  "direction": "Yes" or "No" or null,
  "confidence": 0.0-1.0,
  "position_size_pct": 0.01-0.02,
  "reasoning": "Brief explanation of your decision"
}}

Consider:
1. Is this a good trading opportunity based on price, volume, and market dynamics?
2. What direction (Yes/No) has better risk/reward?
3. What position size is appropriate given the confidence level?
4. Are there any risks or concerns?
5. Is the market active and accepting orders?

Respond ONLY with valid JSON, no other text."""

            # Claude API is synchronous, so we need to run it in a thread
            response = await asyncio.to_thread(
                self.claude_client.messages.create,
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            # Extract JSON from response
            response_text = response.content[0].text.strip()
            
            # Try to extract JSON if it's wrapped in markdown
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            decision = json.loads(response_text)
            
            if decision.get("should_trade") and decision.get("direction"):
                print(f"  Claude Decision: {decision.get('direction')} @ {price_yes if decision.get('direction') == 'Yes' else price_no:.3f}, confidence: {decision.get('confidence', 0):.2f}, size: {decision.get('position_size_pct', 0.01)*100:.1f}%")
                print(f"  Reasoning: {decision.get('reasoning', 'N/A')}")
                return decision
            else:
                print(f"  Claude Decision: No trade - {decision.get('reasoning', 'N/A')}")
                return None
                
        except json.JSONDecodeError as e:
            print(f"  Claude response JSON parse error: {e}")
            print(f"  Response was: {response_text[:200]}")
            return None
        except Exception as e:
            print(f"  Claude decision error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _execute_trades(self, markets: List[dict]):
        """Execute trades based on Claude AI decisions."""
        opportunities = []
        
        # Collect all trading opportunities from analyzed markets
        # Handle both CLOB (condition_id) and Gamma (id) formats
        analyzed_market_ids = set(self.market_analyses.keys())
        print(f"_execute_trades: Analyzed market IDs: {list(analyzed_market_ids)[:5]}...")
        
        tradeable_markets = []
        for m in markets:
            market_id = m.get('id') or m.get('condition_id') or m.get('question_id')
            if market_id and market_id in analyzed_market_ids:
                tradeable_markets.append(m)
            elif market_id:
                # Debug: Check why market is not in analyzed set
                if len(tradeable_markets) < 3:
                    print(f"  Market {market_id[:20]}... not in analyzed set (has {market_id})")
        
        print(f"_execute_trades: {len(analyzed_market_ids)} analyzed markets, {len(tradeable_markets)} tradeable markets")
        if len(tradeable_markets) == 0 and len(markets) > 0:
            print(f"  WARNING: No tradeable markets found! Sample market IDs from fetched markets:")
            for m in markets[:3]:
                print(f"    - id: {m.get('id')}, condition_id: {m.get('condition_id')}, question_id: {m.get('question_id')}")
        
        # If Claude is available, use AI for decisions
        if self.claude_client:
            print(f"Using Claude AI for trading decisions... ({len(tradeable_markets)} tradeable markets)")
            claude_opportunities = 0
            for market in tradeable_markets[:15]:  # Limit to 15 markets per cycle to avoid rate limits
                market_id = market.get('id') or market.get('condition_id') or market.get('question_id')
                if not market_id:
                    continue
                
                # Filter checks
                if not self._is_realistic_market(market):
                    continue
                
                if not self._is_market_in_resolution_window(market):
                    continue
                
                # Check if market is active and accepting orders (CLOB format)
                if not market.get('active', True):
                    continue
                if market.get('closed', False):
                    continue
                if not market.get('accepting_orders', True):
                    continue
                
                analysis = self.market_analyses.get(market_id)
                if not analysis:
                    continue
                
                # Get Claude's trading decision
                claude_decision = await self._get_claude_trading_decision(market, analysis)
                
                if claude_decision and claude_decision.get("should_trade"):
                    claude_opportunities += 1
                    opportunities.append({
                        'market': market,
                        'analysis': analysis,
                        'strategy': 'claude_ai',
                        'priority': int(claude_decision.get('confidence', 0.5) * 100),
                        'outcome': claude_decision.get('direction'),
                        'position_size_pct': claude_decision.get('position_size_pct', 0.015),
                        'reasoning': claude_decision.get('reasoning', 'AI decision'),
                        'trade_type': 'swing',
                        'claude_decision': claude_decision  # Store full decision
                    })
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.3)
            
            print(f"Claude AI found {claude_opportunities} trading opportunities out of {len(tradeable_markets[:15])} markets analyzed")
        else:
            # Fallback to algorithmic strategies if Claude not available
            print("Claude not available - using algorithmic strategies as fallback")
            for market in tradeable_markets:
                market_id = market.get('id')
                if not market_id:
                    continue
                
                # Double-check: Don't trade on unrealistic markets
                if not self._is_realistic_market(market):
                    continue
                
                # CRITICAL: Only trade markets resolving in 1-2 weeks
                if not self._is_market_in_resolution_window(market):
                    continue  # Skip long-term markets
                
                analysis = self.market_analyses.get(market_id)
                if not analysis:
                    continue
                
                market_title = market.get('question') or market.get('title') or market.get('name') or 'Unknown Market'
                
                # Strategy 1: Arbitrage (highest priority)
                if analysis.arbitrage_opportunity:
                    opportunities.append({
                        'market': market,
                        'analysis': analysis,
                        'strategy': 'arbitrage',
                        'priority': 100,
                        'outcome': 'both',
                        'expected_profit_pct': analysis.arbitrage_opportunity
                    })
                
                # Strategy 2: Catch-all for algorithmic fallback
                elif analysis.score > 5:
                    direction = 'Yes' if analysis.price_yes > 0.5 else 'No'
                    opportunities.append({
                        'market': market,
                        'analysis': analysis,
                        'strategy': 'algorithmic_fallback',
                        'priority': int(analysis.score),
                        'outcome': direction,
                        'expected_profit_pct': 2,
                        'trade_type': 'swing'
                    })
        
        # Sort by priority and execute top opportunities
        opportunities.sort(key=lambda x: x['priority'], reverse=True)
        
        print(f"Found {len(opportunities)} trading opportunities")
        if opportunities:
            print(f"Top opportunity: {opportunities[0]['strategy']} on {opportunities[0]['market'].get('question', 'Unknown')[:60]}")
            # Debug: Show top 5 opportunities
            for i, opp in enumerate(opportunities[:5], 1):
                print(f"  Opp {i}: {opp['strategy']} - score={opp['analysis'].score:.2f}, priority={opp['priority']:.1f}, outcome={opp['outcome']}")
        else:
            print("WARNING: No trading opportunities found! Checking why...")
            if len(self.market_analyses) > 0:
                # Show some analysis scores to debug
                sample_analyses = list(self.market_analyses.values())[:5]
                for analysis in sample_analyses:
                    print(f"  Sample analysis: score={analysis.score:.2f}, volume={analysis.volume:.0f}, context_score={analysis.context_score:.2f}, price_yes={analysis.price_yes:.3f}")
        
        # Filter out scalping opportunities (handled separately in scalping loop)
        swing_opportunities = [opp for opp in opportunities if opp.get('trade_type') == 'swing']
        
        print(f"Executing {min(len(swing_opportunities), 6)} swing trades from {len(swing_opportunities)} opportunities")
        print(f"Current balance: ${self.balance:.2f}, Active positions: {len(self.positions)}, Total trades in history: {len(self.trades)}")
        
        # Execute swing trades (larger, context-based positions)
        max_swings_per_cycle = 6  # Focus on swing trades in main loop
        trades_executed = 0
        
        if len(swing_opportunities) == 0:
            print("ERROR: No swing opportunities to execute! This should not happen if opportunities were found.")
        
        for i, opp in enumerate(swing_opportunities[:max_swings_per_cycle]):
            if trades_executed >= max_swings_per_cycle:
                break
            try:
                print(f"  Attempting to execute opportunity {i+1}/{min(len(swing_opportunities), max_swings_per_cycle)}: {opp['strategy']}")
                await self._execute_opportunity(opp)
                trades_executed += 1
                print(f"  ✓ SUCCESS: Executed trade {trades_executed}: {opp['strategy']} on {opp['market'].get('question', 'Unknown')[:50]}")
            except Exception as e:
                print(f"  ✗ ERROR executing opportunity {i+1}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"Total trades executed this cycle: {trades_executed}")
        
        # Note: Scalping trades are handled separately in _scalping_loop()
        
        # Check existing positions for exit conditions
        await self._check_exit_conditions(markets)
    
    async def _execute_opportunity(self, opportunity: dict):
        """Execute a specific trading opportunity."""
        market = opportunity['market']
        analysis = opportunity['analysis']
        strategy = opportunity['strategy']
        outcome_str = opportunity['outcome']
        market_title = market.get('question') or market.get('title') or market.get('name') or 'Unknown Market'
        
        print(f"  [_execute_opportunity] Strategy: {strategy}, Outcome: {outcome_str}, Market: {market_title[:50]}")
        print(f"  [_execute_opportunity] Balance: ${self.balance:.2f}, Analysis score: {analysis.score:.2f}, Price Yes: {analysis.price_yes:.3f}, Price No: {analysis.price_no:.3f}")
        
        # Arbitrage: Buy both outcomes
        if strategy == 'arbitrage' and outcome_str == 'both':
            # Allow arbitrage with any balance (removed $100 minimum)
            if self.balance < 1.0:  # Just need at least $1
                return
            
            price_yes = analysis.price_yes
            price_no = analysis.price_no
            
            # Only allow prices between $0.10 and $0.99
            if price_yes < 0.10 or price_yes > 0.99 or price_no < 0.10 or price_no > 0.99:
                print(f"  -> Skipping arbitrage: Prices outside allowed range (Yes: {price_yes:.3f}, No: {price_no:.3f})")
                return
            
            total_cost = price_yes + price_no
            
            if total_cost >= 0.99:  # Not profitable after fees
                return
            
            # Position sizing: 1-2% of portfolio for arbitrage (split between Yes and No)
            position_pct = 0.015  # 1.5% base
            if analysis.arbitrage_opportunity and analysis.arbitrage_opportunity > 2:
                position_pct = 0.02  # 2% for high arbitrage opportunity
            else:
                position_pct = 0.01  # 1% for lower opportunity
            
            investment = self.balance * position_pct
            investment = max(0.10, min(investment, self.balance * 0.02))  # 1-2% of portfolio
            shares = investment / total_cost
            
            # Buy Yes (half of investment)
            cost_yes = shares * price_yes
            if cost_yes <= self.balance and cost_yes >= 0.10:
                position_key_yes = f"{analysis.market_id}-Yes"
                if position_key_yes not in self.positions:
                    await self._open_position(market, analysis, 'Yes', market_title, price_yes, 
                                            cost_yes, strategy, f"Arbitrage: Buy Yes at {price_yes:.3f}", 'swing')
            
            # Buy No (half of investment)
            cost_no = shares * price_no
            if cost_no <= self.balance and cost_no >= 0.10:
                position_key_no = f"{analysis.market_id}-No"
                if position_key_no not in self.positions:
                    await self._open_position(market, analysis, 'No', market_title, price_no,
                                            cost_no, strategy, f"Arbitrage: Buy No at {price_no:.3f}", 'swing')
        
        else:
            # Regular directional trade
            outcome = outcome_str
            
            # Get fresh prices from market data (don't rely on analysis which might have stale 0.5 defaults)
            price_yes, price_no = await self._get_outcome_prices(market, self.polymarket_client)
            
            # Skip if we couldn't extract prices
            if price_yes is None or price_no is None:
                print(f"  -> ✗ SKIPPING: Could not extract prices (Yes: {price_yes}, No: {price_no})")
                print(f"     Market data keys: {list(market.keys())[:10]}")
                print(f"     Using analysis prices as fallback: Yes={analysis.price_yes:.3f}, No={analysis.price_no:.3f}")
                # FALLBACK: Use analysis prices
                price_yes = analysis.price_yes
                price_no = analysis.price_no
                if price_yes is None or price_no is None:
                    print(f"  -> ✗ SKIPPING: Analysis prices also None")
                    return
                print(f"  -> Using analysis prices: Yes={price_yes:.3f}, No={price_no:.3f}")
            
            price = price_yes if outcome in ['Yes', 'YES', 'yes'] else price_no
            position_key = f"{analysis.market_id}-{outcome}"
            
            # For catch_all strategy, be VERY lenient with price range (0.01-0.99)
            # For other strategies, enforce 0.10-0.99
            if strategy == 'catch_all':
                min_price = 0.01
                max_price = 0.99
            else:
                min_price = 0.10
                max_price = 0.99
            
            # Only allow prices in allowed range
            if price < min_price or price > max_price:
                print(f"  -> Price {price:.3f} outside allowed range ({min_price}-{max_price})")
                print(f"     Using analysis prices instead: Yes={analysis.price_yes:.3f}, No={analysis.price_no:.3f}")
                # FALLBACK: Use analysis prices if fresh prices are out of range
                if outcome in ['Yes', 'YES', 'yes']:
                    price = analysis.price_yes
                else:
                    price = analysis.price_no
                
                # For catch_all, be even more lenient - allow any price between 0.01 and 0.99
                if strategy == 'catch_all':
                    if 0.01 <= price <= 0.99:
                        print(f"  -> Using analysis price {price:.3f} for catch_all (lenient range)")
                    else:
                        print(f"  -> Still skipping: Analysis price {price:.3f} outside even lenient range")
                        return
                else:
                    # Check again with analysis prices for other strategies
                    if price < min_price or price > max_price:
                        print(f"  -> Still skipping: Analysis price {price:.3f} also outside range")
                        return
                    else:
                        print(f"  -> Using analysis price {price:.3f} (was outside range, now using fallback)")
            
            # Don't open if position already exists
            if position_key in self.positions:
                print(f"  -> Skipping: Position already exists")
                return
            
            # Calculate remaining profit margin
            max_profit_per_share = 1.0 - price if outcome in ['Yes', 'YES', 'yes'] else price
            if max_profit_per_share <= 0:
                print(f"  -> Skipping: No profit potential (margin: {max_profit_per_share})")
                return  # No profit potential
            
            # Determine trade type from opportunity
            trade_type = opportunity.get('trade_type', 'swing')
            
            # Position size: Use Claude's decision if available, otherwise use default logic
            if opportunity.get('strategy') == 'claude_ai' and opportunity.get('position_size_pct'):
                # Claude decided the position size
                position_pct = opportunity.get('position_size_pct')
                position_pct = max(0.01, min(position_pct, 0.02))  # Ensure 1-2% range
                position_size = self.balance * position_pct
                print(f"  -> Using Claude's position size: {position_pct*100:.1f}% = ${position_size:.2f}")
            else:
                # Default algorithmic position sizing
                base_position_pct = 0.015  # 1.5% base
                if abs(analysis.score) > 20:
                    position_pct = 0.02  # 2% for high confidence
                elif abs(analysis.score) > 10:
                    position_pct = 0.015  # 1.5% for medium confidence
                else:
                    position_pct = 0.01  # 1% for low confidence
                position_size = self.balance * position_pct
            
            # Ensure minimum of $0.10 and maximum of 2% of balance
            position_size = max(0.10, min(position_size, self.balance * 0.02))
            
            if position_size <= self.balance and position_size >= 0.10:
                # Use Claude's reasoning if available, otherwise generate default reason
                if strategy == 'claude_ai' and opportunity.get('reasoning'):
                    reason = f"Claude AI: {outcome} @ {price:.3f} - {opportunity.get('reasoning')}"
                elif trade_type == 'scalp':
                    reason = f"Volume Scalp: {outcome} @ {price:.3f} (Vol: {analysis.volume:.0f}, Margin: {max_profit_per_share:.3f})"
                elif strategy == 'catch_all':
                    reason = f"Catch-All: {outcome} @ {price:.3f} (Score: {analysis.score:.1f}, Vol: {analysis.volume:.0f})"
                else:
                    reason = f"{strategy.title()}: {outcome} @ {price:.3f} (Vol: {analysis.volume:.0f}, Margin: {max_profit_per_share:.3f})"
                print(f"  -> Opening position: {outcome} @ ${price:.3f}, size: ${position_size:.2f} ({position_pct*100:.1f}% of portfolio), balance: ${self.balance:.2f}")
                await self._open_position(market, analysis, outcome, market_title, price,
                                        position_size, strategy, reason, trade_type)
                print(f"  -> SUCCESS: Position opened!")
            else:
                print(f"  -> Skipping: Position size ${position_size:.2f} invalid (balance: ${self.balance:.2f}, min: 0.10, max: {self.balance * 0.02:.2f})")
                # DEBUG: Try with minimum size if balance allows
                if self.balance >= 0.10:
                    min_size = 0.10
                    print(f"  -> DEBUG: Trying with minimum size ${min_size:.2f}...")
                    await self._open_position(market, analysis, outcome, market_title, price,
                                            min_size, strategy, reason + " (min size)", trade_type)
                    print(f"  -> SUCCESS: Position opened with minimum size!")
    
    async def _check_exit_conditions(self, markets: List[dict]):
        """Check all open positions for exit conditions."""
        for position_key, position in list(self.positions.items()):
            market = next((m for m in markets if m.get('id') == position.market_id), None)
            if not market:
                continue
            
            analysis = self.market_analyses.get(position.market_id)
            if not analysis:
                continue
            
            # Get current price
            price_yes, price_no = await self._get_outcome_prices(market, self.polymarket_client)
            
            # Skip if we couldn't get prices
            if price_yes is None or price_no is None:
                continue
            
            current_price = price_yes if position.outcome in ['Yes', 'YES', 'yes'] else price_no
            
            # Calculate P&L
            profit_pct = (current_price - position.entry_price) / position.entry_price
            profit_abs = (current_price - position.entry_price) * position.size
            
            # Exit conditions based on strategy and trade type
            should_exit = False
            exit_reason = ""
            
            # Scalping trades: Quick in/out with small profit targets
            if position.trade_type == 'scalp':
                # Scalps: Take profit at 1-3%, stop loss at 0.5-1%
                if profit_pct > 0.02:  # Take profit at 2%
                    should_exit = True
                    exit_reason = "Scalp profit target: +2%"
                elif profit_pct < -0.008:  # Stop loss at 0.8%
                    should_exit = True
                    exit_reason = "Scalp stop loss: -0.8%"
                # Also exit if held too long (>2 hours for scalps)
                elif (datetime.now() - position.entry_time).total_seconds() > 7200:
                    should_exit = True
                    exit_reason = "Scalp timeout: 2 hours"
            
            elif position.strategy == 'arbitrage':
                # Exit arbitrage when sum approaches 1.0 (market corrects)
                if analysis.price_yes + analysis.price_no >= 0.99:
                    should_exit = True
                    exit_reason = "Arbitrage closed: Market corrected"
                # Or if we've made 3%+ profit
                elif profit_pct > 0.03:
                    should_exit = True
                    exit_reason = "Take profit: Arbitrage profit target met"
            
            elif position.strategy == 'context_swing':
                # Context swing trades: Higher profit targets, wider stops
                if profit_pct > 0.10:  # Take profit at 10%
                    should_exit = True
                    exit_reason = "Context swing profit: +10%"
                elif profit_pct < -0.06:  # Stop loss at 6%
                    should_exit = True
                    exit_reason = "Context swing stop: -6%"
            
            elif position.strategy == 'momentum':
                # Take profit at 8%, stop loss at 4%
                if profit_pct > 0.08:
                    should_exit = True
                    exit_reason = "Take profit: Momentum target reached"
                elif profit_pct < -0.04:
                    should_exit = True
                    exit_reason = "Stop loss: Momentum reversed"
            
            elif position.strategy == 'mean_reversion':
                # Exit when price moves significantly toward equilibrium (works at any price)
                price_from_equilibrium = abs(analysis.price_yes - 0.5)
                entry_from_equilibrium = abs(position.entry_price - 0.5)
                
                # Exit if price moved significantly toward 0.5 (reversion occurred)
                if price_from_equilibrium < entry_from_equilibrium * 0.7:  # Price moved 30%+ toward 0.5
                    should_exit = True
                    exit_reason = f"Mean reversion: Price moved toward equilibrium ({analysis.price_yes:.3f})"
                # Or take profit at 10%
                elif profit_pct > 0.10:
                    should_exit = True
                    exit_reason = "Take profit: Mean reversion target met"
                # Stop loss at 5%
                elif profit_pct < -0.05:
                    should_exit = True
                    exit_reason = "Stop loss: Mean reversion failed"
            
            elif position.strategy == 'volume_breakout':
                # Take profit at 7%, stop loss at 3%
                if profit_pct > 0.07:
                    should_exit = True
                    exit_reason = "Take profit: Breakout target reached"
                elif profit_pct < -0.03:
                    should_exit = True
                    exit_reason = "Stop loss: Breakout failed"
            
            # Default exit conditions for any strategy
            if not should_exit:
                if profit_pct > 0.12:  # Take profit at 12%
                    should_exit = True
                    exit_reason = "Take profit: Strong profit target"
                elif profit_pct < -0.06:  # Stop loss at 6%
                    should_exit = True
                    exit_reason = "Stop loss: Risk limit reached"
            
            if should_exit:
                await self._close_position(position, current_price, market.get('question') or market.get('title') or 'Unknown', exit_reason)
    
    async def _open_position(self, market: dict, analysis: MarketAnalysis, outcome: str, 
                            market_title: str, price: float, size: float, strategy: str, reason: str, trade_type: str = 'swing'):
        """Open a new trading position."""
        if size > self.balance:
            return  # Not enough balance
        
        position_key = f"{analysis.market_id}-{outcome}"
        
        position = TradingPosition(
            market_id=analysis.market_id,
            market_title=market_title,
            outcome=outcome,
            entry_price=price,
            size=size,
            entry_time=datetime.now(),
            current_price=price,
            unrealized_pnl=0.0,
            strategy=strategy,
            trade_type=trade_type
        )
        
        self.positions[position_key] = position
        self.balance -= size
        
        # Extract market image/icon from market data
        market_image = market.get('image') or market.get('icon') or market.get('imageUrl') or None
        
        trade = SimulatedTrade(
            id=f"trade-{datetime.now().timestamp()}-{random.random()}",
            market_id=analysis.market_id,
            market_title=market_title,
            timestamp=datetime.now(),
            action='BUY',
            outcome=outcome,
            price=price,
            size=size,
            reason=reason,
            strategy=strategy,
            trade_type=trade_type,
            market_image=market_image
        )
        
        self.trades.insert(0, trade)
        print(f"  -> ✓✓✓ TRADE CREATED (BUY): {trade.action} {trade.outcome} @ ${trade.price:.3f}, size: ${trade.size:.2f}")
        print(f"  -> Trade ID: {trade.id}, Market: {trade.market_title[:50]}")
        print(f"  -> Total trades in list: {len(self.trades)}")
        print(f"  -> Trade object type: {type(trade)}")
        print(f"  -> Trade has id: {hasattr(trade, 'id')}, has market_id: {hasattr(trade, 'market_id')}")
    
    async def _close_position(self, position: TradingPosition, current_price: float, 
                             market_title: str, reason: str):
        """Close an existing trading position."""
        position_key = f"{position.market_id}-{position.outcome}"
        
        if position_key not in self.positions:
            return
        
        # Calculate the current value of the position
        # When we bought, we spent position.size dollars at entry_price
        # Now the position is worth: position.size * (current_price / entry_price)
        current_value = position.size * (current_price / position.entry_price)
        
        # Calculate profit/loss: current value minus original investment
        profit = current_value - position.size
        
        # Add back the current value (which includes the original investment + profit/loss)
        self.balance += current_value
        
        # Update P&L history after closing position
        self._update_pnl_history()
        
        # Try to get market image from market data if available
        # We don't have market data here, so we'll leave it None (can be enhanced later)
        market_image = None
        
        trade = SimulatedTrade(
            id=f"trade-{datetime.now().timestamp()}-{random.random()}",
            market_id=position.market_id,
            market_title=market_title,
            timestamp=datetime.now(),
            action='SELL',
            outcome=position.outcome,
            price=current_price,
            size=position.size,
            reason=reason,
            profit=profit,
            strategy=position.strategy,
            trade_type=position.trade_type,
            market_image=market_image
        )
        
        self.trades.insert(0, trade)
        print(f"  -> ✓✓✓ TRADE CREATED (SELL): {trade.action} {trade.outcome} @ ${trade.price:.3f}, size: ${trade.size:.2f}, profit: ${profit:.2f}")
        print(f"  -> Trade ID: {trade.id}, Market: {trade.market_title[:50]}")
        print(f"  -> Total trades in list: {len(self.trades)}")
        print(f"  -> Trade object type: {type(trade)}")
        del self.positions[position_key]
    
    def _update_pnl_history(self):
        """Update P&L history for charting."""
        current_time = datetime.now()
        
        # Calculate total P&L (realized + unrealized)
        completed_trades = [t for t in self.trades if t.profit is not None]
        realized_pnl = sum(t.profit for t in completed_trades if t.profit is not None)
        
        # Calculate unrealized P&L from open positions
        unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        
        total_pnl = realized_pnl + unrealized_pnl
        
        # Add to history (only if it changed significantly or enough time passed)
        if not self.pnl_history:
            # Initialize with starting point
            self.pnl_history.append((current_time, 0.0))
        else:
            # Only add if P&L changed by >$0.10 or 30+ seconds passed
            last_time, last_pnl = self.pnl_history[-1]
            time_diff = (current_time - last_time).total_seconds()
            pnl_diff = abs(total_pnl - last_pnl)
            
            if pnl_diff > 0.10 or time_diff > 30:
                self.pnl_history.append((current_time, total_pnl))
        
        # Keep only last 200 data points (to prevent memory issues)
        if len(self.pnl_history) > 200:
            self.pnl_history = self.pnl_history[-200:]
    
    def _cleanup_old_data(self):
        """Clean up old data to prevent memory growth."""
        # Limit trades to last 1000
        if len(self.trades) > 1000:
            self.trades = self.trades[:1000]
        
        # Limit market analyses to last 500
        if len(self.market_analyses) > 500:
            # Keep most recent analyses
            sorted_analyses = sorted(
                self.market_analyses.items(),
                key=lambda x: getattr(x[1], 'timestamp', datetime.now()) if hasattr(x[1], 'timestamp') else datetime.now(),
                reverse=True
            )
            self.market_analyses = dict(sorted_analyses[:500])
        
        # Limit price history to last 100 entries per market
        for market_id in list(self.price_history.keys()):
            if len(self.price_history[market_id]) > 100:
                self.price_history[market_id] = self.price_history[market_id][-100:]
    
    def get_pnl_history(self, limit: int = 100) -> List[dict]:
        """Get P&L history for charting."""
        # Update P&L history before returning
        self._update_pnl_history()
        
        # Convert to list of dicts with timestamp, pnl, balance, and netWorth
        history = []
        for timestamp, pnl in self.pnl_history[-limit:]:
            balance = self.balance
            net_worth = self.initial_balance + pnl
            history.append({
                'timestamp': timestamp.isoformat(),
                'pnl': round(pnl, 2),
                'balance': round(balance, 2),
                'netWorth': round(net_worth, 2)
            })
        return history
    
    def get_stats(self) -> dict:
        """Get trading statistics."""
        completed_trades = [t for t in self.trades if t.profit is not None]
        winning_trades = [t for t in completed_trades if t.profit and t.profit > 0]
        losing_trades = [t for t in completed_trades if t.profit and t.profit <= 0]
        
        # Calculate realized P&L (from completed trades)
        realized_pnl = sum(t.profit for t in completed_trades if t.profit is not None)
        
        # Calculate unrealized P&L (from open positions)
        unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        
        # Total P&L = realized + unrealized
        total_pnl = realized_pnl + unrealized_pnl
        
        # Calculate net worth: initial balance + total P&L
        # OR: balance + current value of open positions
        # Both should equal the same thing
        net_worth = self.initial_balance + total_pnl
        
        # Update P&L history when getting stats
        self._update_pnl_history()
        
        return {
            'balance': round(self.balance, 2),
            'initialBalance': self.initial_balance,
            'totalProfit': round(total_pnl, 2),  # Now includes unrealized P&L
            'realizedProfit': round(realized_pnl, 2),  # Just completed trades
            'unrealizedProfit': round(unrealized_pnl, 2),  # Open positions
            'netWorth': round(net_worth, 2),  # Total portfolio value
            'totalTrades': len(completed_trades),
            'winningTrades': len(winning_trades),
            'losingTrades': len(losing_trades),
            'activePositions': len(self.positions),
            'winRate': round((len(winning_trades) / len(completed_trades) * 100) if completed_trades else 0, 1)
        }
    
    def get_positions(self) -> List[dict]:
        """Get all open positions as dictionaries."""
        return [
            {
                'marketId': p.market_id,
                'marketTitle': p.market_title,
                'outcome': p.outcome,
                'entryPrice': round(p.entry_price, 4),
                'currentPrice': round(p.current_price, 4),
                'size': round(p.size, 2),
                'unrealizedPnl': round(p.unrealized_pnl, 2),
                'entryTime': p.entry_time.isoformat(),
                'strategy': p.strategy,
                'tradeType': p.trade_type
            }
            for p in self.positions.values()
        ]
    
    def get_recent_trades(self, limit: int = 100) -> List[dict]:
        """Get recent trades as dictionaries."""
        print(f"get_recent_trades: Internal trades list has {len(self.trades)} trades")
        if len(self.trades) > 0:
            print(f"get_recent_trades: First trade type: {type(self.trades[0])}")
            print(f"get_recent_trades: First trade id: {self.trades[0].id if hasattr(self.trades[0], 'id') else 'NO ID'}")
        
        trades_list = []
        for t in self.trades[:limit]:
            try:
                trade_dict = {
                    'id': t.id,
                    'marketId': t.market_id,
                    'marketTitle': t.market_title,
                    'timestamp': t.timestamp.isoformat(),
                    'action': t.action,
                    'outcome': t.outcome,
                    'price': round(t.price, 4),
                    'size': round(t.size, 2),
                    'reason': t.reason,
                    'profit': round(t.profit, 2) if t.profit is not None else None,
                    'strategy': t.strategy,
                    'tradeType': getattr(t, 'trade_type', 'swing'),
                    'marketImage': getattr(t, 'market_image', None)  # Include market image/icon
                }
                trades_list.append(trade_dict)
            except Exception as e:
                print(f"Error converting trade to dict: {e}")
                print(f"Trade object: {t}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"get_recent_trades: Returning {len(trades_list)} formatted trades")
        return trades_list
    
    def get_market_analyses(self) -> List[dict]:
        """Get market analyses as dictionaries."""
        analyses_list = [
            {
                'marketId': a.market_id,
                'volume': round(a.volume, 2),
                'liquidity': round(a.liquidity, 2),
                'trend': round(a.trend, 3),
                'momentum': round(a.momentum, 2),
                'sentiment': round(a.sentiment, 3),
                'score': round(a.score, 1),
                'arbitrageOpportunity': round(a.arbitrage_opportunity, 2) if a.arbitrage_opportunity else None,
                'spread': round(a.spread, 4),
                'priceYes': round(a.price_yes, 4),
                'priceNo': round(a.price_no, 4),
                'volume24h': round(a.volume_24h, 2)
            }
            for a in self.market_analyses.values()
        ]
        print(f"get_market_analyses: Returning {len(analyses_list)} analyses")
        return analyses_list


# Global trading bot instance
_trading_bot: Optional[TradingBot] = None


def get_trading_bot() -> TradingBot:
    """Get or create the global trading bot instance."""
    global _trading_bot
    if _trading_bot is None:
        _trading_bot = TradingBot(initial_balance=2000.0)
    return _trading_bot
