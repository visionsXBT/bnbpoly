import { useState, useEffect, useRef } from 'react';
import type { PriceUpdate } from '../types';
import './LiveTradesRibbon.css';

interface LiveTradesRibbonProps {
  apiBaseUrl?: string;
}

const LiveTradesRibbon: React.FC<LiveTradesRibbonProps> = ({ apiBaseUrl = '' }) => {
  const [priceUpdates, setPriceUpdates] = useState<PriceUpdate[]>([]);
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
          console.log('Price updates WebSocket connected');
          setIsConnected(true);
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            
            if (message.type === 'connected') {
              console.log('Price updates connected:', message.message);
            } else if (message.type === 'price_update' && message.data) {
              const priceUpdate = message.data as PriceUpdate;
              console.log('Received price update:', priceUpdate);
              setPriceUpdates(prev => {
                // Avoid duplicates (same market, same price direction within 2 seconds)
                const now = Date.now();
                const exists = prev.some(p => 
                  p.market_id === priceUpdate.market_id && 
                  p.price_direction === priceUpdate.price_direction &&
                  p.timestamp && 
                  (now - new Date(p.timestamp).getTime()) < 2000
                );
                if (exists) return prev;
                const updated = [priceUpdate, ...prev].slice(0, 50); // Keep last 50 updates
                return updated;
              });
            } else if (message.type === 'error') {
              console.error('Price updates error:', message.message);
            } else {
              console.log('Received unknown message type:', message.type, message);
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

  const formatPrice = (price: number | undefined): string => {
    if (price === undefined || price === null) return 'N/A';
    return `$${price.toFixed(4)}`;
  };

  const formatMarket = (question?: string, marketId?: string): string => {
    if (question) {
      return question.length > 40 ? question.substring(0, 40) + '...' : question;
    }
    if (marketId) {
      return marketId.substring(0, 20) + '...';
    }
    return 'Unknown Market';
  };

  const formatPriceChange = (change: number | undefined): string => {
    if (change === undefined || change === null) return '';
    const sign = change > 0 ? '+' : '';
    return `${sign}${(change * 100).toFixed(2)}%`;
  };

  return (
    <div className="live-trades-ribbon">
      <div className="ribbon-status">
        <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}></span>
        <span className="status-text">{isConnected ? 'LIVE' : 'Connecting...'}</span>
      </div>
      <div className="ribbon-trades-scroll">
        {priceUpdates.length === 0 ? (
          <div className="ribbon-no-trades">
            {isConnected ? 'Monitoring price changes...' : 'Connecting...'}
          </div>
        ) : (
          <>
            <div className="ribbon-trades-scroll-wrapper">
              {/* Duplicate items for seamless loop */}
              {[...priceUpdates, ...priceUpdates].map((update, index) => (
                <div key={`${update.market_id}-${update.timestamp}-${index}`} className={`ribbon-price-item price-${update.price_direction || 'neutral'}`}>
                  <span className="price-market">{formatMarket(update.question, update.market_id)}</span>
                  <span className="price-arrow"> &gt; </span>
                  <span className="price-label">PRICE</span>
                  <span className="price-value">{formatPrice(update.current_price || update.lastTradePrice)}</span>
                  {update.price_direction && update.price_direction !== 'neutral' && (
                    <>
                      <span className={`price-direction price-${update.price_direction}`}>
                        {update.price_direction === 'up' ? '↑' : '↓'}
                      </span>
                      {update.price_change !== undefined && update.previous_price && update.previous_price > 0 && (
                        <span className={`price-change price-${update.price_direction}`}>
                          {formatPriceChange(update.price_change / update.previous_price)}
                        </span>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default LiveTradesRibbon;

