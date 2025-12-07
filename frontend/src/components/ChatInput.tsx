import React, { useState, FormEvent, KeyboardEvent } from 'react'
import './ChatInput.css'

interface ChatInputProps {
  onSendMessage: (message: string) => void
  disabled: boolean
  language?: 'en' | 'zh'
}

function ChatInput({ onSendMessage, disabled, language = 'en' }: ChatInputProps) {
  const [input, setInput] = useState<string>('')
  
  const placeholder = language === 'zh' 
    ? '询问 Polymarket 投注、市场或获取见解...' 
    : 'Ask about Polymarket bets, markets, or get insights...'

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (input.trim() && !disabled) {
      onSendMessage(input)
      setInput('')
    }
  }

  const handleKeyPress = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e as unknown as FormEvent<HTMLFormElement>)
    }
  }

  return (
    <div className="chat-input-container">
      <form onSubmit={handleSubmit} className="chat-input-form">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder={placeholder}
          disabled={disabled}
          className="chat-input"
        />
        <button
          type="submit"
          disabled={disabled || !input.trim()}
          className="send-button"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
        </button>
      </form>
    </div>
  )
}

export default ChatInput

