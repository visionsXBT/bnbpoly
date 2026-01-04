"""
Autonomous trading bot for Polymarket that runs continuously.
Simulates trades based on volume, trend, momentum, and sentiment.
"""
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field
import random


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


@dataclass
class MarketAnalysis:
    """Analysis of a market for trading decisions."""
    market_id: str
    volume: float
    trend: float  # -1 to 1 (down to up)
    momentum: float  # price change rate
    sentiment: float  # 0 to 1 (negative to positive)
    score: float  # overall trading score


class TradingBot:
    """Autonomous trading bot that simulates trading on Polymarket."""
    
    def __init__(self, initial_balance: float = 2000.0):
        self.balance: float = initial_balance
        self.initial_balance: float = initial_balance
        self.positions: Dict[str, TradingPosition] = {}  # key: market_id-outcome
        self.trades: List[SimulatedTrade] = []
        self.market_analyses: Dict[str, MarketAnalysis] = {}
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
    
    def analyze_market(self, market: dict) -> MarketAnalysis:
        """Analyze a market and generate a trading score."""
        volume = float(market.get('volumeNum', market.get('volume', 0)))
        price = float(market.get('newestPrice', market.get('price', 0.5)))
        previous_price = float(market.get('previousPrice', price * (0.95 + random.random() * 0.1)))
        price_change = price - previous_price
        price_change_percent = (price_change / previous_price) if previous_price > 0 else 0
        
        # Trend calculation (based on price movement)
        trend = max(-1, min(1, price_change_percent * 10))
        
        # Momentum (rate of change)
        momentum = price_change_percent * 100
        
        # Sentiment (based on volume and price movement)
        base_sentiment = 0.5 + (price_change_percent * 2)
        volume_factor = min(1, volume / 100000)  # Normalize volume
        sentiment = max(0, min(1, base_sentiment * (0.7 + volume_factor * 0.3)))
        
        # Trading score (combination of factors)
        score = (trend * 0.3 + sentiment * 0.4 + momentum * 0.2 + volume_factor * 0.1) * 100
        
        return MarketAnalysis(
            market_id=market.get('id', ''),
            volume=volume,
            trend=trend,
            momentum=momentum,
            sentiment=sentiment,
            score=score
        )
    
    async def _trading_loop(self, polymarket_client):
        """Main trading loop that runs continuously."""
        while self.is_running:
            try:
                # Fetch markets
                markets = await polymarket_client.get_markets(limit=50)
                if not markets:
                    await asyncio.sleep(10)
                    continue
                
                # Analyze markets
                for market in markets[:30]:  # Analyze top 30 markets
                    analysis = self.analyze_market(market)
                    self.market_analyses[analysis.market_id] = analysis
                
                # Update existing positions
                await self._update_positions(markets, polymarket_client)
                
                # Find trading opportunities
                await self._execute_trades(markets)
                
                # Keep only last 500 trades to prevent memory issues
                if len(self.trades) > 500:
                    self.trades = self.trades[-500:]
                
                # Wait before next iteration
                await asyncio.sleep(3)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in trading loop: {e}")
                await asyncio.sleep(5)
    
    async def _update_positions(self, markets: List[dict], polymarket_client):
        """Update current prices and P&L for open positions."""
        for position_key, position in list(self.positions.items()):
            market = next((m for m in markets if m.get('id') == position.market_id), None)
            if market:
                current_price = float(market.get('newestPrice', market.get('price', 0.5)))
                position.current_price = current_price
                
                # Calculate unrealized P&L
                price_diff = current_price - position.entry_price
                position.unrealized_pnl = price_diff * position.size
                
                self.positions[position_key] = position
    
    async def _execute_trades(self, markets: List[dict]):
        """Execute trades based on market analysis."""
        for market in markets[:20]:  # Trade on top 20 markets
            market_id = market.get('id')
            if not market_id:
                continue
            
            analysis = self.market_analyses.get(market_id)
            if not analysis or abs(analysis.score) < 30:
                continue
            
            market_title = market.get('question') or market.get('title') or market.get('name') or 'Unknown Market'
            current_price = float(market.get('newestPrice', market.get('price', 0.5)))
            outcomes = market.get('outcomes', ['Yes', 'No'])
            outcome = outcomes[0] if analysis.score > 0 else outcomes[1]
            position_key = f"{market_id}-{outcome}"
            
            existing_position = self.positions.get(position_key)
            
            if existing_position:
                # Check if we should close the position
                profit_percent = (current_price - existing_position.entry_price) / existing_position.entry_price
                if existing_position.outcome == outcomes[0]:
                    if profit_percent > 0.1 or profit_percent < -0.05:  # Take profit at 10% or stop loss at 5%
                        await self._close_position(existing_position, current_price, market_title)
                else:
                    # For "No" outcome, profit is inverse
                    profit_percent = -profit_percent
                    if profit_percent > 0.1 or profit_percent < -0.05:
                        await self._close_position(existing_position, current_price, market_title)
            else:
                # Open new position if score is strong enough
                if abs(analysis.score) > 40 and self.balance > 10:
                    await self._open_position(market, analysis, outcome, market_title, current_price)
    
    async def _open_position(self, market: dict, analysis: MarketAnalysis, outcome: str, market_title: str, price: float):
        """Open a new trading position."""
        # Calculate trade size (use 2-5% of balance, max $50)
        max_trade_size = min(self.balance * 0.05, 50.0)
        trade_size = max(10.0, min(max_trade_size, 10 + random.random() * 40))
        
        if trade_size > self.balance:
            return  # Not enough balance
        
        position_key = f"{analysis.market_id}-{outcome}"
        
        position = TradingPosition(
            market_id=analysis.market_id,
            market_title=market_title,
            outcome=outcome,
            entry_price=price,
            size=trade_size,
            entry_time=datetime.now(),
            current_price=price,
            unrealized_pnl=0.0
        )
        
        self.positions[position_key] = position
        self.balance -= trade_size
        
        trade = SimulatedTrade(
            id=f"trade-{datetime.now().timestamp()}-{random.random()}",
            market_id=analysis.market_id,
            market_title=market_title,
            timestamp=datetime.now(),
            action='BUY',
            outcome=outcome,
            price=price,
            size=trade_size,
            reason=f"Strong {'bullish' if analysis.score > 0 else 'bearish'} signal (Volume: {analysis.volume:.0f}, Trend: {analysis.trend*100:.1f}%)"
        )
        
        self.trades.insert(0, trade)
    
    async def _close_position(self, position: TradingPosition, current_price: float, market_title: str):
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
            reason='Take Profit' if profit > 0 else 'Stop Loss',
            profit=profit
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
            'balance': self.balance,
            'initial_balance': self.initial_balance,
            'total_profit': total_profit,
            'total_trades': len(completed_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'active_positions': len(self.positions),
            'win_rate': (len(winning_trades) / len(completed_trades) * 100) if completed_trades else 0
        }
    
    def get_positions(self) -> List[dict]:
        """Get all open positions as dictionaries."""
        return [
            {
                'marketId': p.market_id,
                'marketTitle': p.market_title,
                'outcome': p.outcome,
                'entryPrice': p.entry_price,
                'currentPrice': p.current_price,
                'size': p.size,
                'unrealizedPnl': p.unrealized_pnl,
                'entryTime': p.entry_time.isoformat()
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
                'price': t.price,
                'size': t.size,
                'reason': t.reason,
                'profit': t.profit
            }
            for t in self.trades[:limit]
        ]
    
    def get_market_analyses(self) -> List[dict]:
        """Get market analyses as dictionaries."""
        return [
            {
                'marketId': a.market_id,
                'volume': a.volume,
                'trend': a.trend,
                'momentum': a.momentum,
                'sentiment': a.sentiment,
                'score': a.score
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

