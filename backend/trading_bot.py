"""
Autonomous trading bot for Polymarket that runs continuously.
Uses realistic strategies: arbitrage, momentum, volume analysis, and risk management.
"""
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import random
import math


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
        
    def start(self, polymarket_client):
        """Start the trading bot in the background."""
        if self._task is None or self._task.done():
            self.is_running = True
            self.polymarket_client = polymarket_client  # Store client reference for price fetching
            self._task = asyncio.create_task(self._trading_loop(polymarket_client))
            # Start separate position update loop for real-time price updates
            self._position_update_task = asyncio.create_task(self._position_update_loop(polymarket_client))
            # Start separate scalping loop for high-frequency volume trades
            self._scalping_task = asyncio.create_task(self._scalping_loop(polymarket_client))
    
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
        """Check if market resolves in 1-2 weeks (7-14 days)."""
        try:
            # Try different possible field names for end date
            end_date_str = (
                market.get('endDate') or 
                market.get('end_date') or 
                market.get('resolutionDate') or
                market.get('resolution_date') or
                market.get('endsAt') or
                market.get('ends_at')
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
            
            # Only include markets resolving in 7-14 days (1-2 weeks)
            return 7 <= days_until_resolution <= 14
            
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
        """Extract Yes and No prices from market data."""
        # Try different possible field names for prices
        outcomes = market.get('outcomes', [])
        
        price_yes = None
        price_no = None
        
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
        market_id = market.get('id', '')
        volume = float(market.get('volumeNum', market.get('volume', 0)))
        liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
        volume_24h = float(market.get('volume24h', volume))
        
        # Get Yes/No prices
        price_yes, price_no = await self._get_outcome_prices(market, self.polymarket_client)
        
        # Skip if we couldn't get prices
        if price_yes is None or price_no is None:
            # Return default analysis with zero scores
            analysis.price_yes = 0.5
            analysis.price_no = 0.5
            analysis.score = 0
            return analysis
        
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
        
        volume_factor = min(1.0, volume_24h / 50000)  # Normalize: $50k = full factor
        sentiment = max(0.0, min(1.0, base_sentiment * (0.6 + volume_factor * 0.4)))
        
        # Calculate trading score
        # Arbitrage gets highest priority
        if arbitrage_opportunity:
            score = 80 + min(20, arbitrage_opportunity * 2)  # 80-100 for arbitrage
        else:
            # Volume strategy: Higher volume = more reliable
            volume_score = volume_factor * 30
            
            # Momentum strategy: Lower threshold for momentum
            momentum_score = abs(momentum) * 0.5 if abs(momentum) > 0.5 else 0  # Lowered from 2
            
            # Trend strategy: Lower threshold for trends
            trend_score = abs(trend) * 2 if abs(trend) > 0.05 else 0  # Lowered from 0.1
            
            # Liquidity strategy: Higher liquidity = better execution
            liquidity_score = min(20, liquidity / 1000) if liquidity > 0 else 0
            
            # Mean reversion: Expanded price ranges for more opportunities
            mean_reversion_score = 0
            if 0.25 < price_yes < 0.45 or 0.55 < price_yes < 0.75:
                mean_reversion_score = 8  # Mild reversion opportunity
            elif 0.2 < price_yes < 0.3 or 0.7 < price_yes < 0.8:
                mean_reversion_score = 12  # Moderate reversion opportunity
            elif price_yes < 0.2 or price_yes > 0.8:
                mean_reversion_score = 18  # Strong reversion opportunity
            
            score = volume_score + momentum_score + trend_score + liquidity_score + mean_reversion_score
            
            # Calculate separate volume and context scores
            # Volume score: purely based on trading volume and liquidity (for scalping)
            volume_score_value = (volume_factor * 50) + (liquidity_score * 1.5)
            
            # Context score: based on trend, momentum, sentiment (for swing trading)
            context_score_value = (momentum_score * 2) + (trend_score * 3) + ((sentiment - 0.5) * 40) + mean_reversion_score
            
            # Direction matters: positive score for bullish, negative for bearish
            if momentum < 0 or trend < 0:
                score = -score
                context_score_value = -context_score_value
        
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
    
    async def _fetch_markets_expanded(self, polymarket_client) -> List[dict]:
        """Fetch markets using multiple strategies, prioritizing trending and short-term markets."""
        all_markets = {}
        market_ids_seen = set()
        
        try:
            # Strategy 1: Trending markets (high volume, recent activity) - PRIORITY
            print("Fetching trending markets by volume (prioritized)...")
            volume_markets = await polymarket_client.get_markets(limit=300, offset=0)
            
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
            print("Fetching high liquidity short-term markets...")
            try:
                # Fetch with higher offset to get different markets
                liquidity_markets = await polymarket_client.get_markets(limit=150, offset=100)
                short_term_count = 0
                for market in liquidity_markets:
                    market_id = market.get('id')
                    if market_id and market_id not in market_ids_seen:
                        # Only include if it's in resolution window
                        if self._is_market_in_resolution_window(market):
                            liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
                            if liquidity > 2000:
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
                                # Include if it has reasonable volume or liquidity
                                if volume > 500 or liquidity > 800:
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
            
            return markets_list
            
        except Exception as e:
            print(f"Error in expanded market fetch: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to basic fetch
            return await polymarket_client.get_markets(limit=100, offset=0)
    
    async def _trading_loop(self, polymarket_client):
        """Main trading loop that runs continuously."""
        cycle_count = 0
        while self.is_running:
            try:
                cycle_count += 1
                
                # Fetch markets using expanded search (every cycle, but refresh full list every 10 cycles)
                if cycle_count == 1 or cycle_count % 10 == 0:
                    print(f"Performing expanded market search (cycle {cycle_count})...")
                    markets = await self._fetch_markets_expanded(polymarket_client)
                else:
                    # In between, just refresh top markets
                    markets = await polymarket_client.get_markets(limit=200, offset=0)
                
                if not markets:
                    print("WARNING: No markets fetched from Polymarket API")
                    await asyncio.sleep(10)
                    continue
                
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
                        if not self._is_market_in_resolution_window(market):
                            continue  # Skip long-term markets
                        
                        # Filter: only analyze markets with minimum volume/liquidity
                        volume = float(market.get('volumeNum', market.get('volume', 0)))
                        liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
                        
                        # Include if volume > 200 or liquidity > 500 (very relaxed thresholds)
                        if volume > 200 or liquidity > 500:
                            analysis = await self.analyze_market(market)
                            self.market_analyses[analysis.market_id] = analysis
                            analyzed_count += 1
                            short_term_analyzed += 1
                            
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
                price_diff = current_price - position.entry_price
                position.unrealized_pnl = price_diff * position.size
                
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
                # Fetch high-volume markets for scalping (top 100 by volume)
                markets = await polymarket_client.get_markets(limit=100, offset=0)
                
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
                        
                        # Scalping requires HIGH volume (minimum $10k) for liquidity
                        if volume < 10000 or liquidity < 5000:
                            continue
                        
                        # Quick analysis for scalping
                        analysis = await self.analyze_market(market)
                        
                        # Scalping criteria: High volume score and reasonable signal
                        if analysis.volume_score > 25 and abs(analysis.score) > 20:
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
                    
                    # Scalp position size: Flexible based on volume and balance (target ~$1, but can vary)
                    base_size = 1.0
                    volume_multiplier = 0.5 + (min(analysis.volume_score, 50) / 50) * 1.5
                    position_size = base_size * volume_multiplier
                    # Allow any size from $0.10 to balance (no artificial cap)
                    position_size = max(0.10, min(position_size, self.balance * 0.10))
                    
                    if position_size > self.balance:
                        continue
                    
                    price_yes, price_no = self._get_outcome_prices(market)
                    price = price_yes if outcome in ['Yes', 'YES', 'yes'] else price_no
                    
                    # Only filter out invalid prices (exactly 0 or 1, or outside 0-1 range)
                    if price <= 0 or price >= 1.0:
                        continue
                    
                    # Adjust position size based on remaining profit margin
                    # If buying at 0.98, max profit is 0.02 per share, so we need larger size
                    max_profit_per_share = 1.0 - price if outcome in ['Yes', 'YES', 'yes'] else price
                    if max_profit_per_share <= 0:
                        continue  # No profit potential
                    
                    # Scale position size inversely with profit margin to maintain target profit
                    # Example: At 0.98 price (0.02 margin), we need 5x size to get same $ profit as at 0.50
                    profit_margin_factor = max(0.02, max_profit_per_share)  # Minimum 2% margin
                    adjusted_position_size = position_size / profit_margin_factor
                    adjusted_position_size = max(0.10, min(adjusted_position_size, self.balance * 0.15))  # Cap at 15% for scalps
                    
                    if adjusted_position_size > self.balance:
                        continue
                    
                    # Execute scalp trade
                    reason = f"Volume Scalp: {outcome} @ {price:.3f} (Vol: {analysis.volume:.0f}, Margin: {max_profit_per_share:.3f})"
                    await self._open_position(market, analysis, outcome, market_title, price,
                                            adjusted_position_size, 'volume_scalp', reason, 'scalp')
                
                # Wait 2-5 seconds before next scalping cycle (randomized to avoid patterns)
                wait_time = 2 + random.random() * 3  # 2-5 seconds
                await asyncio.sleep(wait_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in scalping loop: {e}")
                await asyncio.sleep(3)
    
    async def _execute_trades(self, markets: List[dict]):
        """Execute trades based on sophisticated strategies."""
        opportunities = []
        
        # Collect all trading opportunities from analyzed markets
        # Check all markets that have been analyzed, not just top 50
        analyzed_market_ids = set(self.market_analyses.keys())
        tradeable_markets = [m for m in markets if m.get('id') in analyzed_market_ids]
        
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
            outcomes = market.get('outcomes', ['Yes', 'No'])
            
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
            
            # Strategy 2: Momentum trades (relaxed thresholds)
            elif abs(analysis.score) > 25 and analysis.volume > 2000:  # Lowered from 50/10000
                direction = 'Yes' if analysis.score > 0 else 'No'
                opportunities.append({
                    'market': market,
                    'analysis': analysis,
                    'strategy': 'momentum',
            'priority': abs(analysis.score),
            'outcome': direction,
            'expected_profit_pct': min(10, abs(analysis.momentum) * 2),
            'trade_type': 'swing'  # Momentum trades are swing trades
                })
            
            # Strategy 3: Mean reversion (works at any price - looks for markets far from 0.5)
            # Can trade at high prices (0.98) if expecting reversion, or low prices (0.02)
            elif ((analysis.price_yes < 0.45 or analysis.price_yes > 0.55) and 
                  abs(analysis.trend) > 0.5):  # Price away from 0.5 and showing trend
                direction = 'Yes' if analysis.price_yes < 0.5 else 'No'
                # Higher priority if price is more extreme (bigger reversion opportunity)
                priority_bonus = abs(analysis.price_yes - 0.5) * 50  # Bonus for extreme prices
                opportunities.append({
                    'market': market,
                    'analysis': analysis,
                    'strategy': 'mean_reversion',
                    'priority': 30 + priority_bonus,  # Higher priority for extreme prices
                    'outcome': direction,
                    'expected_profit_pct': 5,
                    'trade_type': 'swing'  # Mean reversion are swing trades
                })
            
            # Strategy 4: Volume breakouts (relaxed)
            elif abs(analysis.score) > 20 and analysis.volume_24h > 10000 and abs(analysis.momentum) > 1.5:  # Lowered thresholds
                direction = 'Yes' if analysis.momentum > 0 else 'No'
                opportunities.append({
                    'market': market,
                    'analysis': analysis,
                    'strategy': 'volume_breakout',
            'priority': 25,  # Lowered from 35
            'outcome': direction,
            'expected_profit_pct': 7,
            'trade_type': 'swing'  # Volume breakouts can be swings
                })
            
            # Strategy 5: Volume Scalping (high volume, small positions ~$1)
            # This will be handled separately in the scalping loop for faster execution
            
            # Strategy 6: Context Swing Trading (strong context signals, larger positions)
            elif abs(analysis.context_score) > 25:  # Strong context signal
                direction = 'Yes' if analysis.context_score > 0 else 'No'
                opportunities.append({
                    'market': market,
                    'analysis': analysis,
                    'strategy': 'context_swing',
                    'priority': abs(analysis.context_score),
                    'outcome': direction,
                    'expected_profit_pct': 8,  # Higher profit target for swings
                    'trade_type': 'swing'
                })
            
            # Strategy 7: General opportunity catch-all (very relaxed)
            elif abs(analysis.score) > 15 and (analysis.volume > 1000 or analysis.liquidity > 500):
                direction = 'Yes' if analysis.score > 0 else 'No'
                opportunities.append({
                    'market': market,
                    'analysis': analysis,
                    'strategy': 'general',
                    'priority': abs(analysis.score),
                    'outcome': direction,
                    'expected_profit_pct': 4,
                    'trade_type': 'swing'  # Default to swing
                })
        
        # Sort by priority and execute top opportunities
        opportunities.sort(key=lambda x: x['priority'], reverse=True)
        
        print(f"Found {len(opportunities)} trading opportunities")
        
        # Filter out scalping opportunities (handled separately in scalping loop)
        swing_opportunities = [opp for opp in opportunities if opp.get('trade_type') == 'swing']
        
        print(f"Executing {min(len(swing_opportunities), 6)} swing trades from {len(swing_opportunities)} opportunities")
        
        # Execute swing trades (larger, context-based positions)
        max_swings_per_cycle = 6  # Focus on swing trades in main loop
        trades_executed = 0
        
        for opp in swing_opportunities[:max_swings_per_cycle]:
            if trades_executed >= max_swings_per_cycle:
                break
            try:
                await self._execute_opportunity(opp)
                trades_executed += 1
                print(f"Executed trade: {opp['strategy']} on {opp['market'].get('question', 'Unknown')[:50]}")
            except Exception as e:
                print(f"Error executing opportunity: {e}")
                import traceback
                traceback.print_exc()
        
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
        
        # Arbitrage: Buy both outcomes
        if strategy == 'arbitrage' and outcome_str == 'both':
            # Allow arbitrage with any balance (removed $100 minimum)
            if self.balance < 1.0:  # Just need at least $1
                return
            
            price_yes = analysis.price_yes
            price_no = analysis.price_no
            total_cost = price_yes + price_no
            
            if total_cost >= 0.99:  # Not profitable after fees
                return
            
            # Flexible position sizing: 5-20% of balance for arbitrage
            max_investment = self.balance * 0.20
            min_investment = max(self.balance * 0.05, 1.0)  # At least $1 or 5% of balance, whichever is higher
            
            # Use amount between min and max
            investment = min(max_investment, max(min_investment, self.balance * 0.10))
            shares = investment / total_cost
            
            # Buy Yes
            cost_yes = shares * price_yes
            if cost_yes <= self.balance and cost_yes >= 0.10:  # Minimum $0.10 position
                position_key_yes = f"{analysis.market_id}-Yes"
                if position_key_yes not in self.positions:
                    await self._open_position(market, analysis, 'Yes', market_title, price_yes, 
                                            cost_yes, strategy, f"Arbitrage: Buy Yes at {price_yes:.3f}", 'swing')
            
            # Buy No
            cost_no = shares * price_no
            if cost_no <= self.balance and cost_no >= 0.10:  # Minimum $0.10 position
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
                return
            
            price = price_yes if outcome in ['Yes', 'YES', 'yes'] else price_no
            position_key = f"{analysis.market_id}-{outcome}"
            
            # Only filter out invalid prices (exactly 0 or 1, or outside 0-1 range)
            if price <= 0 or price >= 1.0:
                return
            
            # Don't open if position already exists
            if position_key in self.positions:
                return
            
            # Calculate remaining profit margin
            max_profit_per_share = 1.0 - price if outcome in ['Yes', 'YES', 'yes'] else price
            if max_profit_per_share <= 0:
                return  # No profit potential
            
            # Determine trade type from opportunity
            trade_type = opportunity.get('trade_type', 'swing')
            
            # Calculate position size based on strategy and trade type
            # Note: Scalping positions are calculated in _scalping_loop()
            if trade_type == 'scalp':
                # This shouldn't be called from here, but handle it anyway - flexible sizing
                base_scalp_size = 1.0
                volume_multiplier = 0.3 + (min(analysis.volume_score, 50) / 50) * 2.0  # Wider range: 0.3x to 2.3x
                position_size = base_scalp_size * volume_multiplier
                position_size = max(0.10, min(position_size, self.balance * 0.15))  # Min $0.10, max 15% of balance
            else:
                # Swing trading: Flexible positions based on context and balance
                if strategy == 'context_swing':
                    # Context-based swing: 2-10% of balance (flexible)
                    position_size = self.balance * (0.02 + (abs(analysis.context_score) / 100) * 0.08)
                elif strategy == 'momentum':
                    # 2-10% of balance for momentum trades
                    position_size = self.balance * (0.02 + (abs(analysis.score) / 100) * 0.08)
                elif strategy == 'mean_reversion':
                    # 1.5-6% for mean reversion
                    position_size = self.balance * (0.015 + (abs(analysis.score) / 100) * 0.045)
                elif strategy == 'volume_breakout':
                    # 3-8% for volume breakouts
                    position_size = self.balance * (0.03 + (abs(analysis.score) / 100) * 0.05)
                elif strategy == 'general':
                    # 1-5% for general opportunities
                    position_size = self.balance * (0.01 + (abs(analysis.score) / 100) * 0.04)
                else:
                    position_size = self.balance * 0.03
                
                # Flexible swing position sizing - no artificial minimum, max based on balance
                position_size = min(position_size, self.balance * 0.20)  # Max 20% of balance
                position_size = max(position_size, 1.0)  # Minimum $1 for swings (much lower than before)
            
            # Adjust position size based on profit margin for high-priced near-certain outcomes
            # Example: Buying Yes at 0.98 (2% margin) needs larger size to capture meaningful profit
            # Scale up position size inversely with profit margin, but cap it
            profit_margin_factor = max(0.02, max_profit_per_share)  # Minimum 2% margin for calculation
            adjusted_position_size = position_size / profit_margin_factor
            
            # Cap adjusted size to prevent excessive risk
            max_adjusted_size = self.balance * 0.25 if trade_type == 'swing' else self.balance * 0.15
            adjusted_position_size = min(adjusted_position_size, max_adjusted_size)
            # Don't reduce below 30% of base (was 50%, which could cause $0.50 positions)
            adjusted_position_size = max(adjusted_position_size, position_size * 0.3)
            
            if adjusted_position_size <= self.balance and adjusted_position_size >= 0.10:
                if trade_type == 'scalp':
                    reason = f"Volume Scalp: {outcome} @ {price:.3f} (Vol: {analysis.volume:.0f}, Margin: {max_profit_per_share:.3f})"
                else:
                    reason = f"{strategy.title()}: {outcome} @ {price:.3f} (Vol: {analysis.volume:.0f}, Margin: {max_profit_per_share:.3f})"
                await self._open_position(market, analysis, outcome, market_title, price,
                                        adjusted_position_size, strategy, reason, trade_type)
    
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
            trade_type=trade_type
        )
        
        self.trades.insert(0, trade)
    
    async def _close_position(self, position: TradingPosition, current_price: float, 
                             market_title: str, reason: str):
        """Close an existing trading position."""
        position_key = f"{position.market_id}-{position.outcome}"
        
        if position_key not in self.positions:
            return
        
        # Calculate profit/loss
        price_diff = current_price - position.entry_price
        profit = price_diff * position.size
        
        # Add balance back with profit/loss
        self.balance += position.size + profit
        
        # Update P&L history after closing position
        self._update_pnl_history()
        
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
            trade_type=position.trade_type
        )
        
        self.trades.insert(0, trade)
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
        
        total_profit = sum(t.profit for t in completed_trades if t.profit is not None)
        
        # Update P&L history when getting stats
        self._update_pnl_history()
        
        return {
            'balance': round(self.balance, 2),
            'initialBalance': self.initial_balance,
            'totalProfit': round(total_profit, 2),
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
        return [
            {
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
                'tradeType': getattr(t, 'trade_type', 'swing')
            }
            for t in self.trades[:limit]
        ]
    
    def get_market_analyses(self) -> List[dict]:
        """Get market analyses as dictionaries."""
        return [
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


# Global trading bot instance
_trading_bot: Optional[TradingBot] = None


def get_trading_bot() -> TradingBot:
    """Get or create the global trading bot instance."""
    global _trading_bot
    if _trading_bot is None:
        _trading_bot = TradingBot(initial_balance=2000.0)
    return _trading_bot
