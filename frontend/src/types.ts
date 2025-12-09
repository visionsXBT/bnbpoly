export interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatResponse {
  response: string;
  markets?: Market[];
}

export interface Market {
  id: string;
  question?: string;
  [key: string]: unknown;
}

export interface Trade {
  id?: string;
  market_id: string;
  timestamp?: string;
  price?: number;
  size?: number;
  side?: 'buy' | 'sell';
  outcome?: string;
  user?: string;
  question?: string; // Market question/title
}

export interface PriceUpdate {
  market_id: string;
  question?: string;
  current_price?: number;
  previous_price?: number;
  price_change?: number;
  price_direction?: 'up' | 'down' | 'neutral';
  lastTradePrice?: number;
  bestBid?: number;
  bestAsk?: number;
  oneHourPriceChange?: number;
  oneDayPriceChange?: number;
  volume24hr?: number;
  timestamp?: string;
}

export interface TradeStreamMessage {
  type: 'recent_trades' | 'new_trade' | 'error';
  data?: Trade[] | Trade;
  message?: string;
}

