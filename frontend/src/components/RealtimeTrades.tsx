import { useState, useEffect, useRef } from 'react';
import type { Trade, TradeStreamMessage } from '../types';
import './RealtimeTrades.css';

interface RealtimeTradesProps {
  marketId: string;
  marketTitle?: string;
  onClose?: () => void;
  apiBaseUrl?: string;
}

const RealtimeTrades: React.FC<RealtimeTradesProps> = ({ 
  marketId, 
  marketTitle,
  onClose,
  apiBaseUrl = '' 
}) => {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const connectWebSocket = () => {
      try {
        // Construct WebSocket URL
        let wsUrl: string;
        if (apiBaseUrl) {
          // If API base URL is provided, use it
          const baseUrl = apiBaseUrl.replace(/^https?:\/\//, '').replace(/\/$/, '');
          const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
          wsUrl = `${wsProtocol}//${baseUrl}/api/markets/${marketId}/trades/stream`;
        } else {
          // Use relative URL (for development)
          const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
          const host = window.location.host;
          wsUrl = `${wsProtocol}//${host}/api/markets/${marketId}/trades/stream`;
        }
        
        console.log('Connecting to WebSocket:', wsUrl);
        
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('WebSocket connected');
          setIsConnected(true);
          setError(null);
        };

        ws.onmessage = (event) => {
          try {
            const message: TradeStreamMessage = JSON.parse(event.data);
            
            if (message.type === 'recent_trades' && Array.isArray(message.data)) {
              // Initial batch of recent trades
              setTrades(message.data as Trade[]);
            } else if (message.type === 'new_trade' && message.data) {
              // New trade - add to the beginning of the list
              const newTrade = message.data as Trade;
              setTrades(prev => [newTrade, ...prev].slice(0, 100)); // Keep last 100 trades
            } else if (message.type === 'error') {
              setError(message.message || 'Unknown error');
            }
          } catch (e) {
            console.error('Error parsing WebSocket message:', e);
          }
        };

        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          setError('Connection error. Attempting to reconnect...');
          setIsConnected(false);
        };

        ws.onclose = () => {
          console.log('WebSocket closed');
          setIsConnected(false);
          
          // Attempt to reconnect after 3 seconds
          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
          }
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('Attempting to reconnect...');
            connectWebSocket();
          }, 3000);
        };
      } catch (e) {
        console.error('Error creating WebSocket:', e);
        setError('Failed to connect. Please check your connection.');
        setIsConnected(false);
      }
    };

    connectWebSocket();

    // Cleanup on unmount
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [marketId, apiBaseUrl]);

  const formatPrice = (price: number | undefined): string => {
    if (price === undefined || price === null) return 'N/A';
    return `$${price.toFixed(4)}`;
  };

  const formatSize = (size: number | undefined): string => {
    if (size === undefined || size === null) return 'N/A';
    if (size >= 1000) {
      return `$${(size / 1000).toFixed(2)}k`;
    }
    return `$${size.toFixed(2)}`;
  };

  const formatTime = (timestamp: string | undefined): string => {
    if (!timestamp) return 'Just now';
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffSecs = Math.floor(diffMs / 1000);
      
      if (diffSecs < 60) return `${diffSecs}s ago`;
      if (diffSecs < 3600) return `${Math.floor(diffSecs / 60)}m ago`;
      return date.toLocaleTimeString();
    } catch {
      return 'Just now';
    }
  };

  return (
    <div className="realtime-trades-container">
      <div className="realtime-trades-header">
        <div className="realtime-trades-title">
          <h3>Real-Time Trades</h3>
          {marketTitle && <p className="market-title">{marketTitle}</p>}
        </div>
        <div className="realtime-trades-controls">
          <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
            <span className="status-dot"></span>
            {isConnected ? 'Live' : 'Connecting...'}
          </div>
          {onClose && (
            <button className="close-button" onClick={onClose} aria-label="Close">
              ×
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="realtime-trades-error">
          {error}
        </div>
      )}

      <div className="realtime-trades-list">
        {trades.length === 0 ? (
          <div className="no-trades">
            {isConnected ? 'Waiting for trades...' : 'Connecting...'}
          </div>
        ) : (
          <table className="trades-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Side</th>
                <th>Price</th>
                <th>Size</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade, index) => (
                <tr key={trade.id || index} className={`trade-row trade-${trade.side || 'unknown'}`}>
                  <td className="trade-time">{formatTime(trade.timestamp)}</td>
                  <td className={`trade-side trade-side-${trade.side || 'unknown'}`}>
                    {trade.side?.toUpperCase() || 'N/A'}
                  </td>
                  <td className="trade-price">{formatPrice(trade.price)}</td>
                  <td className="trade-size">{formatSize(trade.size)}</td>
                  <td className="trade-outcome">{trade.outcome || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default RealtimeTrades;

