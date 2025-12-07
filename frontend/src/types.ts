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

