import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import './TradingDashboard.css'

// Use relative URLs in production (proxy handles routing), or explicit URL if set
// In production, always use relative URLs so the proxy can handle routing
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// API base URL is set (not logged for security)

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
  marketImage?: string
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
  realizedProfit?: number
  unrealizedProfit?: number
  netWorth?: number
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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pnlHistory, setPnlHistory] = useState<Array<{timestamp: string, pnl: number, balance: number, netWorth: number}>>([])
  const [backendConnected, setBackendConnected] = useState(false)
  const [errorCount, setErrorCount] = useState(0)

  // Debug: Log when component mounts
  useEffect(() => {
    // Component mounted
  }, [])

  // Fetch markets for analysis display
  useEffect(() => {
    const fetchMarkets = async () => {
      try {
        const url = `${API_BASE_URL}/api/markets?limit=50`
        const response = await axios.get<{markets: any[]}>(url)
        if (response.data.markets && Array.isArray(response.data.markets)) {
          setMarkets(response.data.markets)
        }
      } catch (error) {
        // Error fetching markets (logged server-side)
        // Don't set error state for markets, just log it
      }
    }
    fetchMarkets()
  }, [])

  // Fetch trading data from backend
  useEffect(() => {
    const fetchTradingData = async () => {
      try {
        // Only show error after multiple consecutive failures
        if (errorCount < 3) {
          setError(null)
        }
        
        // Fetch stats
        const statsUrl = `${API_BASE_URL}/api/trading/stats`
        const statsResponse = await axios.get(statsUrl, {
          timeout: 5000 // 5 second timeout
        })
        // Stats fetched
        if (statsResponse.data) {
          // Log debug info from backend
          if (statsResponse.data._debug) {
            console.log('TradingDashboard: Stats Debug Info:', statsResponse.data._debug)
            console.log(`  - Bot is running: ${statsResponse.data._debug.bot_is_running}`)
            console.log(`  - Internal trades count: ${statsResponse.data._debug.internal_trades_count}`)
            console.log(`  - Has Claude client: ${statsResponse.data._debug.has_claude_client}`)
            console.log(`  - Has CLOB client: ${statsResponse.data._debug.has_clob_client}`)
            console.log(`  - CLOB initialized: ${statsResponse.data._debug.clob_initialized}`)
            console.log(`  - Market analyses: ${statsResponse.data._debug.market_analyses_count}`)
            
            if (!statsResponse.data._debug.bot_is_running) {
              console.error('ERROR: Trading bot is not running! Check backend logs.')
            }
            if (!statsResponse.data._debug.has_claude_client) {
              console.warn('WARNING: Claude client not initialized. Set ANTHROPIC_API_KEY environment variable.')
            }
            if (!statsResponse.data._debug.clob_initialized && !statsResponse.data._debug.has_clob_client) {
              console.warn('WARNING: CLOB client not initialized. Install py-clob-client.')
            }
          }
          
          setStats({
            balance: statsResponse.data.balance ?? 2000,
            initialBalance: statsResponse.data.initialBalance ?? 2000,
            totalProfit: statsResponse.data.totalProfit ?? 0,
            realizedProfit: statsResponse.data.realizedProfit ?? 0,
            unrealizedProfit: statsResponse.data.unrealizedProfit ?? 0,
            netWorth: statsResponse.data.netWorth ?? (statsResponse.data.initialBalance ?? 2000),
            totalTrades: statsResponse.data.totalTrades ?? 0,
            winningTrades: statsResponse.data.winningTrades ?? 0,
            losingTrades: statsResponse.data.losingTrades ?? 0,
            activePositions: statsResponse.data.activePositions ?? 0,
            winRate: statsResponse.data.winRate ?? 0
          })
        }

        // Fetch positions
        const positionsResponse = await axios.get(`${API_BASE_URL}/api/trading/positions`)
        const positionsList = Array.isArray(positionsResponse.data?.positions) ? positionsResponse.data.positions : []
        setPositions(positionsList)

        // Fetch trades
        const tradesResponse = await axios.get(`${API_BASE_URL}/api/trading/trades?limit=100`)
        // Log debug info from backend
        if (tradesResponse.data?._debug) {
          console.log('TradingDashboard: Backend Debug Info:', tradesResponse.data._debug)
          console.log(`  - Bot is running: ${tradesResponse.data._debug.bot_is_running}`)
          console.log(`  - Internal trades count: ${tradesResponse.data._debug.internal_trades_count}`)
          console.log(`  - Returned trades count: ${tradesResponse.data._debug.returned_trades_count}`)
          console.log(`  - Has Claude client: ${tradesResponse.data._debug.has_claude_client}`)
          console.log(`  - Has CLOB client: ${tradesResponse.data._debug.has_clob_client}`)
          console.log(`  - Market analyses: ${tradesResponse.data._debug.market_analyses_count}`)
          console.log(`  - Positions: ${tradesResponse.data._debug.positions_count}`)
          console.log(`  - Balance: $${tradesResponse.data._debug.balance}`)
          
          if (tradesResponse.data._debug.internal_trades_count > 0 && tradesResponse.data._debug.returned_trades_count === 0) {
            console.error('ERROR: Backend has trades but get_recent_trades returned empty!')
          }
          if (!tradesResponse.data._debug.bot_is_running) {
            console.error('ERROR: Trading bot is not running!')
          }
          if (!tradesResponse.data._debug.has_claude_client) {
            console.warn('WARNING: Claude client not initialized - trading decisions will use algorithmic fallback')
          }
        }
        
        const tradesList = Array.isArray(tradesResponse.data?.trades) ? tradesResponse.data.trades : []
        // Trades data processed
        setTrades(tradesList)

        // Fetch analyses
        const analysesResponse = await axios.get(`${API_BASE_URL}/api/trading/analyses`)
        const analysesMap = new Map<string, MarketAnalysis>()
        if (Array.isArray(analysesResponse.data?.analyses)) {
          analysesResponse.data.analyses.forEach((a: MarketAnalysis) => {
            if (a && a.marketId) {
              analysesMap.set(a.marketId, a)
            }
          })
        }
        setAnalyses(analysesMap)
        
        // Fetch P&L history
        const pnlResponse = await axios.get(`${API_BASE_URL}/api/trading/pnl-history?limit=100`, {
          timeout: 5000
        })
        const pnlList = Array.isArray(pnlResponse.data?.history) ? pnlResponse.data.history : []
        setPnlHistory(pnlList)
        
        // Success - reset error count and mark as connected
        setBackendConnected(true)
        setErrorCount(0)
        setError(null)
        setLoading(false)
      } catch (error) {
        const newErrorCount = errorCount + 1
        setErrorCount(newErrorCount)
        setBackendConnected(false)
        
        // Only show error after 3 consecutive failures to avoid spam
        if (newErrorCount >= 3) {
          if (axios.isAxiosError(error)) {
            if (error.code === 'ECONNABORTED') {
              setError('Backend request timeout. Make sure the backend is running.')
            } else if (error.message === 'Network Error' || error.code === 'ERR_NETWORK') {
              setError('Cannot connect to backend. Make sure the backend server is running on port 8080.')
            } else {
              setError(`Error connecting to backend: ${error.message}`)
            }
          } else {
            setError('Error fetching trading data')
          }
        }
        
        setLoading(false)
        // Error fetching trading data (logged server-side)
      }
    }
    
    const fetchPnlHistory = async () => {
      // Skip if backend is not connected to avoid spam
      if (!backendConnected && errorCount >= 3) {
        return
      }
      
      try {
        const pnlResponse = await axios.get(`${API_BASE_URL}/api/trading/pnl-history?limit=100`, {
          timeout: 5000
        })
        if (Array.isArray(pnlResponse.data?.history)) {
          setPnlHistory(pnlResponse.data.history)
        }
        setBackendConnected(true)
        setErrorCount(0)
      } catch (error) {
        // Silently fail for P&L history to avoid error spam
        // Error fetching P&L history (logged server-side)
      }
    }

    // Fetch immediately
    fetchTradingData()

    // Then fetch every 2 seconds for real-time updates
    // Will automatically slow down if errors persist (handled in fetchTradingData)
    const interval = setInterval(() => {
      fetchTradingData()
    }, 2000)
    
    // Fetch P&L history every 5 seconds (less frequent)
    const pnlInterval = setInterval(fetchPnlHistory, 5000)

    return () => {
      clearInterval(interval)
      clearInterval(pnlInterval)
    }
  }, []) // Empty deps - fetch functions use current state values via closure

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value)
  }

  const formatPercent = (value: number) => {
    if (typeof value !== 'number' || isNaN(value)) return '0%'
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
  }

  if (loading) {
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
        <div className="loading-state">
          <div className="loading-spinner"></div>
          <p>Loading trading data...</p>
        </div>
      </div>
    )
  }

  if (error) {
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
        <div className="error-state">
          <p>⚠️ {error}</p>
          <p style={{ fontSize: '14px', color: '#888', marginTop: '10px' }}>
            {API_BASE_URL 
              ? `Trying to connect to: ${API_BASE_URL}`
              : 'Using relative URLs (make sure backend is running on port 8080)'}
          </p>
          <p style={{ fontSize: '12px', color: '#666', marginTop: '5px' }}>
            Check that the backend server is running and accessible.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="trading-dashboard">
      <div className="dashboard-header">
        <div className="dashboard-header-left">
          <div className="logo-container">
            <img src="/whisper.png" alt="Logo" className="logo" />
            <span className="logo-text">POLYSCOUT</span>
          </div>
          <h1>Trading Dashboard</h1>
        </div>
        <div className="dashboard-header-nav">
          <button onClick={() => navigate('/')} className="nav-button">
            Chat
          </button>
          <button className="nav-button active">
            Trade Bot
          </button>
          <button onClick={() => navigate('/terminal')} className="nav-button">
            Terminal
          </button>
        </div>
      </div>

      <div className="dashboard-stats">
        <div className="stat-card">
          <div className="stat-label">Balance</div>
          <div className="stat-value">{formatCurrency(stats.balance)}</div>
        </div>
        {stats.netWorth !== undefined && (
          <div className="stat-card">
            <div className="stat-label">Net Worth</div>
            <div className={`stat-value ${(stats.netWorth - (stats.initialBalance || 2000)) >= 0 ? 'profit' : 'loss'}`}>
              {formatCurrency(stats.netWorth)}
            </div>
          </div>
        )}
        <div className="stat-card">
          <div className="stat-label">Total Trades</div>
          <div className="stat-value">{stats.totalTrades}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Win Rate</div>
          <div className="stat-value">
            {typeof stats.winRate === 'number' ? `${stats.winRate.toFixed(1)}%` : '0%'}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total P&L</div>
          <div className={`stat-value ${stats.totalProfit >= 0 ? 'profit' : 'loss'}`}>
            {formatCurrency(stats.totalProfit)}
          </div>
          {stats.unrealizedProfit !== undefined && stats.unrealizedProfit !== 0 && (
            <div style={{ fontSize: '11px', color: '#888', marginTop: '4px' }}>
              ({formatCurrency(stats.realizedProfit ?? 0)} realized, {formatCurrency(stats.unrealizedProfit)} unrealized)
            </div>
          )}
        </div>
        <div className="stat-card">
          <div className="stat-label">Active Positions</div>
          <div className="stat-value">{stats.activePositions}</div>
        </div>
      </div>

      <div className="pnl-chart-section">
        <h2>Portfolio Net Worth</h2>
        <div className="pnl-chart-container">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={pnlHistory.length > 0 ? pnlHistory : [{timestamp: new Date().toISOString(), pnl: 0, balance: stats.initialBalance || 2000, netWorth: stats.initialBalance || 2000}]}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis 
                  dataKey="timestamp" 
                  stroke="#888"
                  tick={{ fill: '#888', fontSize: 12 }}
                  tickFormatter={(value) => {
                    const date = new Date(value)
                    return `${date.getHours()}:${date.getMinutes().toString().padStart(2, '0')}`
                  }}
                />
                <YAxis 
                  stroke="#888"
                  tick={{ fill: '#888', fontSize: 12 }}
                  tickFormatter={(value) => `$${value.toFixed(0)}`}
                  domain={['dataMin - 50', 'dataMax + 50']}  // Add padding for better visualization
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: '#1a1a1a', 
                    border: '1px solid #333',
                    borderRadius: '4px',
                    color: '#e0e0e0'
                  }}
                  labelFormatter={(value) => {
                    const date = new Date(value)
                    return date.toLocaleString()
                  }}
                  formatter={(value: any, name?: string) => {
                    if (name === 'netWorth') {
                      return [formatCurrency(value), 'Net Worth']
                    }
                    return [formatCurrency(value), name || 'Value']
                  }}
                />
                <Legend wrapperStyle={{ color: '#888' }} />
                <Line 
                  type="monotone" 
                  dataKey="netWorth" 
                  stroke="#00FF00" 
                  strokeWidth={2}
                  dot={false}
                  name="Net Worth"
                />
              </LineChart>
            </ResponsiveContainer>
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
                    {(position as any).strategy && (
                      <div className="position-detail">
                        <span className="detail-label">Strategy:</span>
                        <span className="detail-value" style={{textTransform: 'capitalize'}}>{(position as any).strategy.replace('_', ' ')}</span>
                      </div>
                    )}
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
                    <div className="trade-header-left">
                      {trade.marketImage && (
                        <img 
                          src={trade.marketImage} 
                          alt={trade.marketTitle}
                          className="trade-market-icon"
                          onError={(e) => {
                            // Hide image if it fails to load
                            (e.target as HTMLImageElement).style.display = 'none'
                          }}
                        />
                      )}
                      <div className="trade-action">{trade.action}</div>
                    </div>
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
                    {trade.profit !== undefined && trade.profit !== null && (
                      <div className="trade-detail">
                        <span className="detail-label">P&L:</span>
                        <span className={`detail-value ${trade.profit >= 0 ? 'profit' : 'loss'}`}>
                          {formatCurrency(trade.profit)}
                        </span>
                      </div>
                    )}
                    {(trade as any).strategy && (
                      <div className="trade-detail">
                        <span className="detail-label">Strategy:</span>
                        <span className="detail-value" style={{textTransform: 'capitalize'}}>{(trade as any).strategy.replace('_', ' ')}</span>
                      </div>
                    )}
                  </div>
                  <div className="trade-reason">{trade.reason}</div>
                </div>
              ))
            ) : (
              <div className="empty-state">
                No trades yet. Waiting for Claude AI to execute trades...
                <div style={{fontSize: '12px', marginTop: '8px', opacity: 0.7}}>
                  Trades will appear here once the bot starts trading.
                </div>
              </div>
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
