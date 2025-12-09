import { useState, useEffect, useRef } from 'react';
import type { Trade } from '../types';
import './LiveTradesRibbon.css';

interface LiveTradesRibbonProps {
  apiBaseUrl?: string;
}

const LiveTradesRibbon: React.FC<LiveTradesRibbonProps> = ({ apiBaseUrl = '' }) => {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const connectWebSocket = () => {
      try {
        // Construct WebSocket URL for all trades stream
        let wsUrl: string;
        if (apiBaseUrl) {
          const baseUrl = apiBaseUrl.replace(/^https?:\/\//, '').replace(/\/$/, '');
          const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
          wsUrl = `${wsProtocol}//${baseUrl}/api/trades/stream`;
        } else {
          const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
          const host = window.location.host;
          wsUrl = `${wsProtocol}//${host}/api/trades/stream`;
        }
        
        console.log('Connecting to live trades WebSocket:', wsUrl);
        
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('Live trades WebSocket connected');
          setIsConnected(true);
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            
            if (message.type === 'connected') {
              console.log('Live trades connected:', message.message);
            } else if (message.type === 'new_trade' && message.data) {
              const newTrade = message.data as Trade;
              setTrades(prev => {
                // Avoid duplicates
                const exists = prev.some(t => t.id === newTrade.id);
                if (exists) return prev;
                const updated = [newTrade, ...prev].slice(0, 50); // Keep last 50 trades
                return updated;
              });
            } else if (message.type === 'error') {
              console.error('Live trades error:', message.message);
            }
          } catch (e) {
            console.error('Error parsing WebSocket message:', e);
          }
        };

        ws.onerror = (error) => {
          console.error('Live trades WebSocket error:', error);
          setIsConnected(false);
        };

        ws.onclose = () => {
          console.log('Live trades WebSocket closed');
          setIsConnected(false);
          
          if (reconnectTimeoutRef.current) {
            clearTimeout(reconnectTimeoutRef.current);
          }
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('Attempting to reconnect live trades...');
            connectWebSocket();
          }, 3000);
        };
      } catch (e) {
        console.error('Error creating live trades WebSocket:', e);
        setIsConnected(false);
      }
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [apiBaseUrl]);

  const formatAmount = (amount: number | undefined): string => {
    if (amount === undefined || amount === null) return '';
    if (amount >= 1000) {
      return `$${(amount / 1000).toFixed(1)}k`;
    }
    return `$${amount.toFixed(2)}`;
  };

  const formatUser = (user: string | undefined): string => {
    if (!user) return 'Anonymous';
    // Shorten wallet addresses
    if (user.length > 10) {
      return `${user.substring(0, 6)}...${user.substring(user.length - 4)}`;
    }
    return user;
  };

  const formatMarket = (marketId: string, question?: string): string => {
    if (question) {
      return question.length > 50 ? question.substring(0, 50) + '...' : question;
    }
    return marketId.substring(0, 20) + '...';
  };

  return (
    <div className="live-trades-ribbon">
      <div className="ribbon-status">
        <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}></span>
        <span className="status-text">{isConnected ? 'LIVE' : 'Connecting...'}</span>
      </div>
      <div className="ribbon-trades-scroll">
        {trades.length === 0 ? (
          <div className="ribbon-no-trades">
            {isConnected ? 'Waiting for trades...' : 'Connecting...'}
          </div>
        ) : (
          trades.map((trade, index) => (
            <div key={trade.id || index} className="ribbon-trade-item">
              <span className="trade-user">{formatUser(trade.user)}</span>
              <span className="trade-arrow"> &gt; </span>
              <span className={`trade-side trade-${trade.side || 'unknown'}`}>
                {trade.side?.toUpperCase() || 'TRADE'}
              </span>
              <span className="trade-market"> {formatMarket(trade.market_id, trade.question || trade.outcome)}</span>
              {trade.size && (
                <span className="trade-amount"> {formatAmount(trade.size)}</span>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default LiveTradesRibbon;

