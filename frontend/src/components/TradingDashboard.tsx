import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import './TradingDashboard.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

interface SimulatedTrade {
  id: string
  marketId: string
  marketTitle: string
  timestamp: string
  action: 'BUY' | 'SELL'
  outcome: string
  price: number
  size: number
  reason: string
  profit?: number
}

interface TradingPosition {
  marketId: string
  marketTitle: string
  outcome: string
  entryPrice: number
  size: number
  currentPrice: number
  unrealizedPnl: number
  entryTime: string
}

interface MarketAnalysis {
  marketId: string
  volume: number
  trend: number
  momentum: number
  sentiment: number
  score: number
}

interface TradingStats {
  balance: number
  initialBalance: number
  totalProfit: number
  totalTrades: number
  winningTrades: number
  losingTrades: number
  activePositions: number
  winRate: number
}

function TradingDashboard() {
  const navigate = useNavigate()
  const [trades, setTrades] = useState<SimulatedTrade[]>([])
  const [positions, setPositions] = useState<TradingPosition[]>([])
  const [analyses, setAnalyses] = useState<Map<string, MarketAnalysis>>(new Map())
  const [stats, setStats] = useState<TradingStats>({
    balance: 2000,
    initialBalance: 2000,
    totalProfit: 0,
    totalTrades: 0,
    winningTrades: 0,
    losingTrades: 0,
    activePositions: 0,
    winRate: 0
  })
  const [markets, setMarkets] = useState<any[]>([])

  // Fetch markets for analysis display
  useEffect(() => {
    const fetchMarkets = async () => {
      try {
        const response = await axios.get<{markets: any[]}>(`${API_BASE_URL}/api/markets?limit=50`)
        if (response.data.markets && Array.isArray(response.data.markets)) {
          setMarkets(response.data.markets)
        }
      } catch (error) {
        console.error('Error fetching markets:', error)
      }
    }
    fetchMarkets()
  }, [])

  // Fetch trading data from backend
  useEffect(() => {
    const fetchTradingData = async () => {
      try {
        // Fetch stats
        const statsResponse = await axios.get(`${API_BASE_URL}/api/trading/stats`)
        setStats(statsResponse.data)

        // Fetch positions
        const positionsResponse = await axios.get(`${API_BASE_URL}/api/trading/positions`)
        setPositions(positionsResponse.data.positions || [])

        // Fetch trades
        const tradesResponse = await axios.get(`${API_BASE_URL}/api/trading/trades?limit=100`)
        setTrades(tradesResponse.data.trades || [])

        // Fetch analyses
        const analysesResponse = await axios.get(`${API_BASE_URL}/api/trading/analyses`)
        const analysesMap = new Map<string, MarketAnalysis>()
        if (analysesResponse.data.analyses) {
          analysesResponse.data.analyses.forEach((a: MarketAnalysis) => {
            analysesMap.set(a.marketId, a)
          })
        }
        setAnalyses(analysesMap)
      } catch (error) {
        console.error('Error fetching trading data:', error)
      }
    }

    // Fetch immediately
    fetchTradingData()

    // Then fetch every 2 seconds for real-time updates
    const interval = setInterval(fetchTradingData, 2000)

    return () => clearInterval(interval)
  }, [])

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value)
  }

  const formatPercent = (value: number) => {
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  }

  return (
    <div className="trading-dashboard">
      <div className="dashboard-header">
        <div className="dashboard-header-left">
          <button onClick={() => navigate('/')} className="back-button">
            ← Back to Chat
          </button>
          <h1>POLYSCOUT Trading Dashboard</h1>
        </div>
      </div>

      <div className="dashboard-stats">
        <div className="stat-card">
          <div className="stat-label">Balance</div>
          <div className="stat-value">{formatCurrency(stats.balance)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Trades</div>
          <div className="stat-value">{stats.totalTrades}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Win Rate</div>
          <div className="stat-value">{stats.winRate.toFixed(1)}%</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total P&L</div>
          <div className={`stat-value ${stats.totalProfit >= 0 ? 'profit' : 'loss'}`}>
            {formatCurrency(stats.totalProfit)}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Active Positions</div>
          <div className="stat-value">{stats.activePositions}</div>
        </div>
      </div>

      <div className="dashboard-content">
        <div className="dashboard-section">
          <h2>Active Positions</h2>
          <div className="positions-list">
            {positions.length > 0 ? (
              positions.map((position) => (
                <div key={`${position.marketId}-${position.outcome}`} className="position-card">
                  <div className="position-header">
                    <div className="position-title">{position.marketTitle}</div>
                    <div className={`position-pnl ${position.unrealizedPnl >= 0 ? 'profit' : 'loss'}`}>
                      {formatCurrency(position.unrealizedPnl)}
                    </div>
                  </div>
                  <div className="position-details">
                    <div className="position-detail">
                      <span className="detail-label">Outcome:</span>
                      <span className="detail-value">{position.outcome}</span>
                    </div>
                    <div className="position-detail">
                      <span className="detail-label">Entry Price:</span>
                      <span className="detail-value">{position.entryPrice.toFixed(3)}</span>
                    </div>
                    <div className="position-detail">
                      <span className="detail-label">Current Price:</span>
                      <span className="detail-value">{position.currentPrice.toFixed(3)}</span>
                    </div>
                    <div className="position-detail">
                      <span className="detail-label">Size:</span>
                      <span className="detail-value">{formatCurrency(position.size)}</span>
                    </div>
                    <div className="position-detail">
                      <span className="detail-label">Entry Time:</span>
                      <span className="detail-value">{new Date(position.entryTime).toLocaleTimeString()}</span>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="empty-state">No active positions</div>
            )}
          </div>
        </div>

        <div className="dashboard-section">
          <h2>Recent Trades</h2>
          <div className="trades-list">
            {trades.length > 0 ? (
              trades.slice(0, 20).map((trade) => (
                <div key={trade.id} className={`trade-card ${trade.action.toLowerCase()}`}>
                  <div className="trade-header">
                    <div className="trade-action">{trade.action}</div>
                    <div className="trade-time">{new Date(trade.timestamp).toLocaleTimeString()}</div>
                  </div>
                  <div className="trade-title">{trade.marketTitle}</div>
                  <div className="trade-details">
                    <div className="trade-detail">
                      <span className="detail-label">Outcome:</span>
                      <span className="detail-value">{trade.outcome}</span>
                    </div>
                    <div className="trade-detail">
                      <span className="detail-label">Price:</span>
                      <span className="detail-value">{trade.price.toFixed(3)}</span>
                    </div>
                    <div className="trade-detail">
                      <span className="detail-label">Size:</span>
                      <span className="detail-value">{formatCurrency(trade.size)}</span>
                    </div>
                    {trade.profit !== undefined && (
                      <div className="trade-detail">
                        <span className="detail-label">P&L:</span>
                        <span className={`detail-value ${trade.profit >= 0 ? 'profit' : 'loss'}`}>
                          {formatCurrency(trade.profit)}
                        </span>
                      </div>
                    )}
                  </div>
                  <div className="trade-reason">{trade.reason}</div>
                </div>
              ))
            ) : (
              <div className="empty-state">No trades yet</div>
            )}
          </div>
        </div>
      </div>

      <div className="dashboard-section market-analysis-section">
        <h2>Market Analysis</h2>
        <div className="markets-grid">
          {markets.slice(0, 12).map((market) => {
            const analysis = analyses.get(market.id)
            const marketTitle = market.question || market.title || market.name || 'Unknown Market'
            
            if (!analysis) return null
            
            return (
              <div key={market.id} className="market-analysis-card">
                <div className="market-analysis-title">{marketTitle}</div>
                <div className="market-analysis-score">
                  <span className="score-label">Score:</span>
                  <span className={`score-value ${analysis.score > 0 ? 'bullish' : 'bearish'}`}>
                    {analysis.score.toFixed(1)}
                  </span>
                </div>
                <div className="market-analysis-metrics">
                  <div className="metric">
                    <span className="metric-label">Volume:</span>
                    <span className="metric-value">{analysis.volume.toLocaleString()}</span>
                  </div>
                  <div className="metric">
                    <span className="metric-label">Trend:</span>
                    <span className={`metric-value ${analysis.trend > 0 ? 'up' : 'down'}`}>
                      {formatPercent(analysis.trend * 100)}
                    </span>
                  </div>
                  <div className="metric">
                    <span className="metric-label">Momentum:</span>
                    <span className={`metric-value ${analysis.momentum > 0 ? 'up' : 'down'}`}>
                      {formatPercent(analysis.momentum)}
                    </span>
                  </div>
                  <div className="metric">
                    <span className="metric-label">Sentiment:</span>
                    <span className="metric-value">{formatPercent(analysis.sentiment * 100 - 50)}</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default TradingDashboard
