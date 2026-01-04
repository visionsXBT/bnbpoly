"""
Autonomous trading bot for Polymarket that runs continuously.
Uses realistic strategies: arbitrage, momentum, volume analysis, and risk management.
"""
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
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


class TradingBot:
    """Autonomous trading bot that simulates trading on Polymarket."""
    
    def __init__(self, initial_balance: float = 2000.0):
        self.balance: float = initial_balance
        self.initial_balance: float = initial_balance
        self.positions: Dict[str, TradingPosition] = {}  # key: market_id-outcome
        self.trades: List[SimulatedTrade] = []
        self.market_analyses: Dict[str, MarketAnalysis] = {}
        self.price_history: Dict[str, List[Tuple[datetime, float]]] = {}  # Track price history
        self.is_running: bool = True
        self._task: Optional[asyncio.Task] = None
        
    def start(self, polymarket_client):
        """Start the trading bot in the background."""
        if self._task is None or self._task.done():
            self.is_running = True
            self._task = asyncio.create_task(self._trading_loop(polymarket_client))
    
    def stop(self):
        """Stop the trading bot."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
    
    def _get_outcome_prices(self, market: dict) -> Tuple[float, float]:
        """Extract Yes and No prices from market data."""
        # Try different possible field names for prices
        outcomes = market.get('outcomes', [])
        
        price_yes = 0.5
        price_no = 0.5
        
        if outcomes and len(outcomes) >= 2:
            # Try to get prices from outcomes array
            outcome_yes = outcomes[0] if isinstance(outcomes[0], dict) else None
            outcome_no = outcomes[1] if len(outcomes) > 1 and isinstance(outcomes[1], dict) else None
            
            if outcome_yes:
                price_yes = float(outcome_yes.get('price', outcome_yes.get('newestPrice', 0.5)))
            if outcome_no:
                price_no = float(outcome_no.get('price', outcome_no.get('newestPrice', 0.5)))
        else:
            # Fallback: use main price for Yes, calculate No
            price_yes = float(market.get('newestPrice', market.get('price', 0.5)))
            price_no = 1.0 - price_yes
        
        return price_yes, price_no
    
    def analyze_market(self, market: dict) -> MarketAnalysis:
        """Analyze a market with realistic trading strategies."""
        market_id = market.get('id', '')
        volume = float(market.get('volumeNum', market.get('volume', 0)))
        liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
        volume_24h = float(market.get('volume24h', volume))
        
        # Get Yes/No prices
        price_yes, price_no = self._get_outcome_prices(market)
        
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
            
            # Direction matters: positive score for bullish, negative for bearish
            if momentum < 0 or trend < 0:
                score = -score
        
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
            liquidity_depth=liquidity
        )
    
    async def _fetch_markets_expanded(self, polymarket_client) -> List[dict]:
        """Fetch markets using multiple strategies to find all tradeable opportunities."""
        all_markets = {}
        market_ids_seen = set()
        
        try:
            # Strategy 1: Top markets by volume (primary source)
            print("Fetching top markets by volume...")
            volume_markets = await polymarket_client.get_markets(limit=200, offset=0)
            for market in volume_markets:
                market_id = market.get('id')
                if market_id and market_id not in market_ids_seen:
                    all_markets[market_id] = market
                    market_ids_seen.add(market_id)
            print(f"Found {len(volume_markets)} markets by volume")
            
            # Strategy 2: High liquidity markets (different ordering)
            print("Fetching high liquidity markets...")
            try:
                # Fetch with higher offset to get different markets
                liquidity_markets = await polymarket_client.get_markets(limit=150, offset=100)
                for market in liquidity_markets:
                    market_id = market.get('id')
                    if market_id and market_id not in market_ids_seen:
                        liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
                        if liquidity > 2000:  # Lowered liquidity threshold
                            all_markets[market_id] = market
                            market_ids_seen.add(market_id)
                print(f"Found {len([m for m in liquidity_markets if m.get('id') not in market_ids_seen])} additional liquidity markets")
            except Exception as e:
                print(f"Error fetching liquidity markets: {e}")
            
            # Strategy 3: Search for trending keywords to find active markets
            trending_searches = [
                "2024", "2025", "election", "president", "crypto", "bitcoin", "ethereum",
                "sports", "nfl", "nba", "soccer", "football", "basketball",
                "politics", "economy", "stock", "market", "tech", "AI"
            ]
            
            print(f"Searching for markets by trending keywords...")
            for keyword in trending_searches[:8]:  # Limit to avoid too many requests
                try:
                    searched_markets = await polymarket_client.search_markets(keyword, limit=30)
                    for market in searched_markets:
                        market_id = market.get('id')
                        if market_id and market_id not in market_ids_seen:
                            volume = float(market.get('volumeNum', market.get('volume', 0)))
                            liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
                            # Include if it has reasonable volume or liquidity
                            if volume > 500 or liquidity > 800:  # Relaxed thresholds
                                all_markets[market_id] = market
                                market_ids_seen.add(market_id)
                    await asyncio.sleep(0.5)  # Rate limiting between searches
                except Exception as e:
                    print(f"Error searching for '{keyword}': {e}")
                    continue
            
            print(f"Total unique markets found: {len(all_markets)}")
            
            # Convert to list and sort by combined score (volume + liquidity)
            markets_list = list(all_markets.values())
            markets_list.sort(
                key=lambda x: (
                    float(x.get('volumeNum', 0) or x.get('volume', 0) or 0) +
                    float(x.get('liquidityNum', 0) or x.get('liquidity', 0) or 0) * 0.5
                ),
                reverse=True
            )
            
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
                    await asyncio.sleep(10)
                    continue
                
                print(f"Analyzing {len(markets)} markets for trading opportunities...")
                
                # Analyze all fetched markets (not just top 50)
                analyzed_count = 0
                for market in markets:
                    try:
                        # Filter: only analyze markets with minimum volume/liquidity
                        volume = float(market.get('volumeNum', market.get('volume', 0)))
                        liquidity = float(market.get('liquidityNum', market.get('liquidity', 0)))
                        
                        # Include if volume > 200 or liquidity > 500 (very relaxed thresholds)
                        if volume > 200 or liquidity > 500:
                            analysis = self.analyze_market(market)
                            self.market_analyses[analysis.market_id] = analysis
                            analyzed_count += 1
                            
                            # Limit analysis to prevent memory issues, but analyze more than before
                            if analyzed_count >= 150:  # Analyze up to 150 markets
                                break
                    except Exception as e:
                        print(f"Error analyzing market {market.get('id')}: {e}")
                        continue
                
                print(f"Analyzed {analyzed_count} markets")
                
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
    
    async def _update_positions(self, markets: List[dict], polymarket_client):
        """Update current prices and P&L for open positions."""
        for position_key, position in list(self.positions.items()):
            market = next((m for m in markets if m.get('id') == position.market_id), None)
            if market:
                price_yes, price_no = self._get_outcome_prices(market)
                
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
                    'expected_profit_pct': min(10, abs(analysis.momentum) * 2)
                })
            
            # Strategy 3: Mean reversion (expanded price ranges)
            elif (0.20 < analysis.price_yes < 0.40 or 0.60 < analysis.price_yes < 0.80):  # Expanded from 0.15-0.25 and 0.75-0.85
                direction = 'Yes' if analysis.price_yes < 0.5 else 'No'
                opportunities.append({
                    'market': market,
                    'analysis': analysis,
                    'strategy': 'mean_reversion',
                    'priority': 30,  # Lowered from 40
                    'outcome': direction,
                    'expected_profit_pct': 5
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
                    'expected_profit_pct': 7
                })
            
            # Strategy 5: General opportunity catch-all (very relaxed)
            elif abs(analysis.score) > 15 and (analysis.volume > 1000 or analysis.liquidity > 500):
                direction = 'Yes' if analysis.score > 0 else 'No'
                opportunities.append({
                    'market': market,
                    'analysis': analysis,
                    'strategy': 'general',
                    'priority': abs(analysis.score),
                    'outcome': direction,
                    'expected_profit_pct': 4
                })
        
        # Sort by priority and execute top opportunities
        opportunities.sort(key=lambda x: x['priority'], reverse=True)
        
        # Execute trades (limit to prevent over-trading, but allow more opportunities)
        max_trades_per_cycle = 12  # Increased to allow more trades with relaxed thresholds
        trades_executed = 0
        
        for opp in opportunities[:max_trades_per_cycle]:
            if trades_executed >= max_trades_per_cycle:
                break
            
            await self._execute_opportunity(opp)
            trades_executed += 1
        
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
            if self.balance < 100:  # Need at least $100 for arbitrage
                return
            
            price_yes = analysis.price_yes
            price_no = analysis.price_no
            total_cost = price_yes + price_no
            
            if total_cost >= 0.99:  # Not profitable after fees
                return
            
            # Calculate position size (use up to 20% of balance)
            max_investment = self.balance * 0.20
            shares = max_investment / total_cost
            
            # Buy Yes
            cost_yes = shares * price_yes
            if cost_yes <= self.balance:
                position_key_yes = f"{analysis.market_id}-Yes"
                if position_key_yes not in self.positions:
                    await self._open_position(market, analysis, 'Yes', market_title, price_yes, 
                                            cost_yes, strategy, f"Arbitrage: Buy Yes at {price_yes:.3f}")
            
            # Buy No
            cost_no = shares * price_no
            if cost_no <= self.balance:
                position_key_no = f"{analysis.market_id}-No"
                if position_key_no not in self.positions:
                    await self._open_position(market, analysis, 'No', market_title, price_no,
                                            cost_no, strategy, f"Arbitrage: Buy No at {price_no:.3f}")
        
        else:
            # Regular directional trade
            outcome = outcome_str
            price = analysis.price_yes if outcome in ['Yes', 'YES', 'yes'] else analysis.price_no
            position_key = f"{analysis.market_id}-{outcome}"
            
            # Don't open if position already exists
            if position_key in self.positions:
                return
            
            # Calculate position size based on strategy and confidence
            if strategy == 'momentum':
                # 3-8% of balance for momentum trades
                position_size = self.balance * (0.03 + (abs(analysis.score) / 100) * 0.05)
            elif strategy == 'mean_reversion':
                # 2-5% for mean reversion
                position_size = self.balance * 0.04
            elif strategy == 'volume_breakout':
                # 4-7% for volume breakouts
                position_size = self.balance * 0.05
            elif strategy == 'general':
                # 1.5-3% for general opportunities
                position_size = self.balance * 0.025
            else:
                position_size = self.balance * 0.03
            
            # Cap position size
            position_size = min(position_size, self.balance * 0.10, 100.0)  # Max 10% or $100
            position_size = max(position_size, 10.0)  # Min $10
            
            if position_size <= self.balance:
                reason = f"{strategy.title()}: {outcome} signal (Vol: {analysis.volume:.0f}, Mom: {analysis.momentum:.2f}%)"
                await self._open_position(market, analysis, outcome, market_title, price,
                                        position_size, strategy, reason)
    
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
            price_yes, price_no = self._get_outcome_prices(market)
            current_price = price_yes if position.outcome in ['Yes', 'YES', 'yes'] else price_no
            
            # Calculate P&L
            profit_pct = (current_price - position.entry_price) / position.entry_price
            profit_abs = (current_price - position.entry_price) * position.size
            
            # Exit conditions based on strategy
            should_exit = False
            exit_reason = ""
            
            if position.strategy == 'arbitrage':
                # Exit arbitrage when sum approaches 1.0 (market corrects)
                if analysis.price_yes + analysis.price_no >= 0.99:
                    should_exit = True
                    exit_reason = "Arbitrage closed: Market corrected"
                # Or if we've made 3%+ profit
                elif profit_pct > 0.03:
                    should_exit = True
                    exit_reason = "Take profit: Arbitrage profit target met"
            
            elif position.strategy == 'momentum':
                # Take profit at 8%, stop loss at 4%
                if profit_pct > 0.08:
                    should_exit = True
                    exit_reason = "Take profit: Momentum target reached"
                elif profit_pct < -0.04:
                    should_exit = True
                    exit_reason = "Stop loss: Momentum reversed"
            
            elif position.strategy == 'mean_reversion':
                # Exit when price returns to mean (0.45-0.55)
                if 0.45 <= analysis.price_yes <= 0.55:
                    should_exit = True
                    exit_reason = "Mean reversion: Price returned to equilibrium"
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
                            market_title: str, price: float, size: float, strategy: str, reason: str):
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
            strategy=strategy
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
            strategy=strategy
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
            strategy=position.strategy
        )
        
        self.trades.insert(0, trade)
        del self.positions[position_key]
    
    def get_stats(self) -> dict:
        """Get trading statistics."""
        completed_trades = [t for t in self.trades if t.profit is not None]
        winning_trades = [t for t in completed_trades if t.profit and t.profit > 0]
        losing_trades = [t for t in completed_trades if t.profit and t.profit <= 0]
        
        total_profit = sum(t.profit for t in completed_trades if t.profit is not None)
        
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
                'strategy': p.strategy
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
                'strategy': t.strategy
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
