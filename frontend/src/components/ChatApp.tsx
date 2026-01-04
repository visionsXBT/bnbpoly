import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import ChatMessage from './ChatMessage'
import ChatInput from './ChatInput'
import RealtimeTrades from './RealtimeTrades'
import LiveTradesRibbon from './LiveTradesRibbon'
import '../App.css'
import axios from 'axios'
import type { Message, ChatResponse, Market } from '../types'

// Use environment variable for production, or relative URL for development
// In production, set VITE_API_BASE_URL in Railway environment variables
// NOTE: Vite env vars are baked at build time - rebuild frontend after setting this!
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// Log API URL for debugging (will show in browser console)
if (import.meta.env.DEV) {
  console.log('API_BASE_URL:', API_BASE_URL || '(empty - using relative URLs)')
}

function ChatApp() {
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: 'Welcome to POLYSCOUT. Your AI-powered Polymarket insights assistant. Ask me about markets, betting opportunities, or get analysis on specific predictions. How can I help you today?'
    }
  ])
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [trendingMarkets, setTrendingMarkets] = useState<Market[]>([])
  const [selectedMarketForTrades, setSelectedMarketForTrades] = useState<{id: string, title?: string} | null>(null)
  
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Fetch trending markets on component mount
  useEffect(() => {
    const fetchTrendingMarkets = async () => {
      try {
        const response = await axios.get<{markets: Market[]}>(`${API_BASE_URL}/api/markets?limit=30`)
        console.log('Markets response:', response.data)
        if (response.data.markets && Array.isArray(response.data.markets)) {
          setTrendingMarkets(response.data.markets)
        } else {
          console.warn('No markets in response or invalid format:', response.data)
        }
      } catch (error) {
        console.error('Error fetching trending markets:', error)
        if (axios.isAxiosError(error)) {
          console.error('Response:', error.response?.data)
        }
      }
    }
    fetchTrendingMarkets()
  }, [])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  const handleSendMessage = async (message: string): Promise<void> => {
    if (!message.trim() || isLoading) return

    // Add user message to UI immediately
    const userMessage: Message = { role: 'user', content: message }
    setMessages(prev => [...prev, userMessage])
    setIsLoading(true)

    try {
      // Send conversation history (last 10 messages BEFORE adding current message)
      // This excludes the current message since it's sent separately
      const conversationHistory = messages.slice(-10).map(msg => ({
        role: msg.role,
        content: msg.content
      }))
      
      // Ensure no double slashes in URL
      const baseUrl = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL
      const apiUrl = `${baseUrl}/api/chat`
      console.log('API_BASE_URL:', API_BASE_URL)
      console.log('Sending request to:', apiUrl)
      
      const response = await axios.post<ChatResponse>(apiUrl, {
        message: message,
        search_query: message.toLowerCase().includes('search') ? message : null,
        conversation_history: conversationHistory,
        language: 'en'
      }, {
        timeout: 60000 // 60 second timeout
      })

      const assistantMessage: Message = {
        role: 'assistant',
        content: response.data.response
      }

      setMessages(prev => [...prev, assistantMessage])
    } catch (error) {
      console.error('Error sending message:', error)
      let errorContent = 'Sorry, I encountered an error processing your request. Please try again.'
      
      // Show more detailed error
      if (axios.isAxiosError(error)) {
        if (error.code === 'ECONNABORTED') {
          errorContent = 'Error: Request timeout. Please try again.'
        } else if (error.response) {
          // Server responded with error
          const errorDetail = error.response.data?.detail || error.response.statusText || error.message
          errorContent = `Error: ${errorDetail}`
          console.error('Backend error details:', errorDetail, error.response.status)
        } else if (error.request) {
          // Request made but no response
          errorContent = 'Error: No response from server. Check if backend is running and VITE_API_BASE_URL is set correctly.'
          console.error('No response received:', error.request)
        } else {
          errorContent = `Error: ${error.message}`
        }
      } else if (error instanceof Error) {
        errorContent = `Error: ${error.message}`
      }
      
      const errorMessage: Message = {
        role: 'assistant',
        content: errorContent
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const getPolymarketUrl = (market: Market): string => {
    const marketData = market as any
    
    // Polymarket URLs use event slugs when markets are part of events
    // Check if market belongs to an event and use event slug if available
    let eventSlug = null
    
    // Check for events array (markets can belong to events)
    if (marketData.events && Array.isArray(marketData.events) && marketData.events.length > 0) {
      const event = marketData.events[0]
      if (event && event.slug) {
        eventSlug = event.slug
      }
    }
    
    // Also check for direct event relationship
    if (!eventSlug && marketData.event && typeof marketData.event === 'object' && marketData.event.slug) {
      eventSlug = marketData.event.slug
    }
    
    // Use event slug if available (this is the correct URL for markets that are part of events)
    if (eventSlug && typeof eventSlug === 'string' && eventSlug.trim()) {
      return `https://polymarket.com/event/${eventSlug.trim()}`
    }
    
    // Fallback to market slug if no event slug (for standalone markets)
    if (marketData.slug && typeof marketData.slug === 'string' && marketData.slug.trim()) {
      const slug = marketData.slug.trim()
      return `https://polymarket.com/event/${slug}`
    }
    
    // Fallback: try conditionId for individual market pages
    if (marketData.conditionId && typeof marketData.conditionId === 'string' && marketData.conditionId.trim()) {
      return `https://polymarket.com/market/${marketData.conditionId.trim()}`
    }
    
    // Last resort: try using ID field
    if (market.id) {
      const idStr = String(market.id).trim()
      if (idStr) {
        return `https://polymarket.com/market/${idStr}`
      }
    }
    
    // If nothing works, log and return base URL
    console.warn('Could not construct Polymarket URL:', {
      id: market.id,
      slug: marketData.slug,
      events: marketData.events,
      event: marketData.event,
      conditionId: marketData.conditionId,
      allFields: Object.keys(marketData)
    })
    return 'https://polymarket.com'
  }

  return (
    <>
      <div className="header">
        <div className="logo-container">
          <img src="/whisper.png" alt="Logo" className="logo" />
          <span className="logo-text">POLYSCOUT</span>
        </div>
        <div className="header-nav">
          <button onClick={() => navigate('/trading')} className="nav-button">
            Trading Dashboard
          </button>
        </div>
        <LiveTradesRibbon apiBaseUrl={API_BASE_URL} />
      </div>
      <div className="app-layout">
        <div className="app">
          <div className="chat-container">
            <div className="chat-messages">
              {messages.map((msg, index) => (
                <ChatMessage key={index} message={msg} />
              ))}
              {isLoading && (
                <div className="message assistant">
                  <div className="message-content">
                    <div className="typing-indicator">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                  </div>
                </div>
              )}
              {selectedMarketForTrades && (
                <div className="realtime-trades-wrapper">
                  <RealtimeTrades
                    marketId={selectedMarketForTrades.id}
                    marketTitle={selectedMarketForTrades.title}
                    onClose={() => setSelectedMarketForTrades(null)}
                    apiBaseUrl={API_BASE_URL}
                  />
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <ChatInput onSendMessage={handleSendMessage} disabled={isLoading} />
          </div>
        </div>
        
        <div className="trending-sidebar">
          <h3 className="trending-title">Trending Markets</h3>
          <div className="trending-markets">
            {trendingMarkets.length > 0 ? (
              trendingMarkets.map((market, index) => {
                const marketData = market as any
                const imageUrl = marketData.image || marketData.icon || null
                const marketTitle = market.question || marketData.title || marketData.name || `Market ${index + 1}`
                const marketUrl = getPolymarketUrl(market)
                
                return (
                  <a
                    key={market.id || index}
                    href={marketUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="trending-market-link"
                  >
                    {imageUrl && (
                      <img 
                        src={imageUrl} 
                        alt="" 
                        className="trending-market-image"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = 'none'
                        }}
                      />
                    )}
                    <span className="trending-market-text">{marketTitle}</span>
                  </a>
                )
              })
            ) : (
              <div className="trending-loading">Loading markets...</div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

export default ChatApp

