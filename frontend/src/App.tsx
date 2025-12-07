import { useState, useRef, useEffect } from 'react'
import ChatMessage from './components/ChatMessage'
import ChatInput from './components/ChatInput'
import './App.css'
import axios from 'axios'
import type { Message, ChatResponse, Market } from './types'

// Use environment variable for production, or relative URL for development
// In production, set VITE_API_BASE_URL in Railway environment variables
// NOTE: Vite env vars are baked at build time - rebuild frontend after setting this!
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// Log API URL for debugging (will show in browser console)
if (import.meta.env.DEV) {
  console.log('API_BASE_URL:', API_BASE_URL || '(empty - using relative URLs)')
}

function App() {
  const getInitialMessage = (lang: 'en' | 'zh'): string => {
    return lang === 'zh' 
      ? '你好！我是您的 Polymarket 洞察助手。询问我关于市场、投注机会或获取特定预测的分析。今天我能为您做些什么？'
      : 'Hello! I\'m your Polymarket insights assistant. Ask me about markets, betting opportunities, or get analysis on specific predictions. How can I help you today?'
  }
  
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: getInitialMessage('en')
    }
  ])
  const [isLoading, setIsLoading] = useState<boolean>(false)
  const [trendingMarkets, setTrendingMarkets] = useState<Market[]>([])
  const [language, setLanguage] = useState<'en' | 'zh'>('en')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  // Translation function
  const t = (key: string): string => {
    const translations: Record<string, { en: string; zh: string }> = {
      'trendingMarkets': { en: 'Trending Markets', zh: '热门市场' },
      'loadingMarkets': { en: 'Loading markets...', zh: '加载市场中...' },
      'placeholder': { en: 'Ask about Polymarket bets, markets, or get insights...', zh: '询问 Polymarket 投注、市场或获取见解...' },
      'error': { en: 'Sorry, I encountered an error processing your request. Please try again.', zh: '抱歉，处理您的请求时出错。请重试。' }
    }
    return translations[key]?.[language] || key
  }

  // Translate market title with multiple fallback options
  const translateMarketTitle = async (title: string): Promise<string> => {
    if (language === 'en' || !title) return title
    
    // Check localStorage cache first
    const cacheKey = `translation_${title}`
    const cached = localStorage.getItem(cacheKey)
    if (cached) {
      try {
        const cachedData = JSON.parse(cached)
        // Cache valid for 24 hours
        if (Date.now() - cachedData.timestamp < 24 * 60 * 60 * 1000) {
          return cachedData.translatedText
        }
      } catch (e) {
        // Invalid cache, continue to API
      }
    }
    
    try {
      // Try LibreTranslate (free, open-source alternative)
      const response = await fetch('https://libretranslate.de/translate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          q: title,
          source: 'en',
          target: 'zh',
          format: 'text'
        })
      })
      
      if (response.ok) {
        const data = await response.json()
        if (data.translatedText) {
          // Cache the translation
          localStorage.setItem(cacheKey, JSON.stringify({
            translatedText: data.translatedText,
            timestamp: Date.now()
          }))
          return data.translatedText
        }
      }
    } catch (error) {
      console.error('LibreTranslate error:', error)
    }
    
    // Fallback: return original title if translation fails
    return title
  }
  
  // State to store translated market titles
  const [translatedTitles, setTranslatedTitles] = useState<Record<string, string>>({})
  
  // Translate market titles when language changes
  useEffect(() => {
    if (language === 'zh' && trendingMarkets.length > 0) {
      const translateAll = async () => {
        const translations: Record<string, string> = {}
        for (const market of trendingMarkets) {
          const marketData = market as any
          const title = market.question || marketData.title || marketData.name || ''
          if (title && !translations[market.id]) {
            const translated = await translateMarketTitle(title)
            translations[market.id] = translated
          }
        }
        setTranslatedTitles(translations)
      }
      translateAll()
    } else if (language === 'en') {
      setTranslatedTitles({})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language, trendingMarkets])

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

  // Update initial message when language changes (only if it's still the initial message)
  useEffect(() => {
    if (messages.length === 1 && messages[0].role === 'assistant') {
      setMessages([{
        role: 'assistant',
        content: getInitialMessage(language)
      }])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language])

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
        language: language
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
      const errorPrefix = language === 'zh' ? '错误：' : 'Error: '
      let errorContent = t('error')
      
      // Show more detailed error
      if (axios.isAxiosError(error)) {
        if (error.code === 'ECONNABORTED') {
          errorContent = `${errorPrefix}Request timeout. Please try again.`
        } else if (error.response) {
          // Server responded with error
          const errorDetail = error.response.data?.detail || error.response.statusText || error.message
          errorContent = `${errorPrefix}${errorDetail}`
          console.error('Backend error details:', errorDetail, error.response.status)
        } else if (error.request) {
          // Request made but no response
          errorContent = `${errorPrefix}No response from server. Check if backend is running and VITE_API_BASE_URL is set correctly.`
          console.error('No response received:', error.request)
        } else {
          errorContent = `${errorPrefix}${error.message}`
        }
      } else if (error instanceof Error) {
        errorContent = `${errorPrefix}${error.message}`
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
          <img src="/bnbpoly.png" alt="Logo" className="logo" />
          <span className="logo-text">BNBPOLY</span>
        </div>
        <div className="language-selector">
          <button 
            className={`lang-btn ${language === 'en' ? 'active' : ''}`}
            onClick={() => setLanguage('en')}
          >
            EN
          </button>
          <button 
            className={`lang-btn ${language === 'zh' ? 'active' : ''}`}
            onClick={() => setLanguage('zh')}
          >
            中文
          </button>
        </div>
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
              <div ref={messagesEndRef} />
            </div>

                  <ChatInput onSendMessage={handleSendMessage} disabled={isLoading} language={language} />
          </div>
        </div>
        
        <div className="trending-sidebar">
          <h3 className="trending-title">{t('trendingMarkets')}</h3>
          <div className="trending-markets">
            {trendingMarkets.length > 0 ? (
              trendingMarkets.map((market, index) => {
                const marketData = market as any
                const imageUrl = marketData.image || marketData.icon || null
                const originalTitle = market.question || marketData.title || marketData.name || `Market ${index + 1}`
                const marketTitle = language === 'zh' && translatedTitles[market.id] 
                  ? translatedTitles[market.id] 
                  : originalTitle
                const marketUrl = getPolymarketUrl(market)
                
                // Debug: log first market to see structure
                if (index === 0 && import.meta.env.DEV) {
                  console.log('Sample market data:', {
                    id: market.id,
                    slug: marketData.slug,
                    conditionId: marketData.conditionId,
                    questionID: marketData.questionID,
                    constructedUrl: marketUrl,
                    allKeys: Object.keys(marketData)
                  })
                }
                
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
                          // Hide image if it fails to load
                          (e.target as HTMLImageElement).style.display = 'none'
                        }}
                      />
                    )}
                    <span className="trending-market-text">{marketTitle}</span>
                  </a>
                )
              })
            ) : (
              <div className="trending-loading">{t('loadingMarkets')}</div>
            )}
          </div>
        </div>
      </div>
    </>
  )
}

export default App

