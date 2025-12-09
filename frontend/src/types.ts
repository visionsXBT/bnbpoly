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
}

export interface TradeStreamMessage {
  type: 'recent_trades' | 'new_trade' | 'error';
  data?: Trade[] | Trade;
  message?: string;
}

