import React from 'react'
import type { Message } from '../types'

interface ChatMessageProps {
  message: Message
}

// Parse markdown: **bold** and bullet points
function parseMarkdown(text: string): React.ReactNode {
  const lines = text.split('\n')
  const elements: React.ReactNode[] = []
  let currentList: React.ReactNode[] = []
  let keyCounter = 0
  
  const renderBold = (line: string): React.ReactNode[] => {
    const parts: React.ReactNode[] = []
    const regex = /\*\*(.+?)\*\*/g
    let lastIndex = 0
    let match
    
    while ((match = regex.exec(line)) !== null) {
      // Add text before the match
      if (match.index > lastIndex) {
        parts.push(line.substring(lastIndex, match.index))
      }
      // Add bold text
      parts.push(<strong key={`bold-${keyCounter++}`}>{match[1]}</strong>)
      lastIndex = regex.lastIndex
    }
    
    // Add remaining text
    if (lastIndex < line.length) {
      parts.push(line.substring(lastIndex))
    }
    
    return parts.length > 0 ? parts : [line]
  }
  
  lines.forEach((line) => {
    const trimmed = line.trim()
    
    // Handle bullet points
    if (trimmed.startsWith('- ')) {
      const content = trimmed.substring(2)
      currentList.push(
        <li key={`li-${keyCounter++}`}>{renderBold(content)}</li>
      )
      return
    }
    
    // Close current list if exists
    if (currentList.length > 0) {
      elements.push(<ul key={`ul-${keyCounter++}`}>{currentList}</ul>)
      currentList = []
    }
    
    // Handle section headers (lines that are entirely bold, no colon)
    if (trimmed.startsWith('**') && trimmed.endsWith('**') && !trimmed.includes(':')) {
      const headerText = trimmed.replace(/\*\*/g, '')
      elements.push(
        <div key={`header-${keyCounter++}`} className="section-header">
          <strong>{headerText}</strong>
        </div>
      )
      return
    }
    
    // Regular paragraph
    if (trimmed) {
      elements.push(
        <div key={`p-${keyCounter++}`}>{renderBold(trimmed)}</div>
      )
    } else {
      elements.push(<br key={`br-${keyCounter++}`} />)
    }
  })
  
  // Close any remaining list
  if (currentList.length > 0) {
    elements.push(<ul key={`ul-final-${keyCounter++}`}>{currentList}</ul>)
  }
  
  return elements.length > 0 ? elements : text
}

function ChatMessage({ message }: ChatMessageProps) {
  return (
    <div className={`message ${message.role}`}>
      <div className="message-content">
        {parseMarkdown(message.content)}
      </div>
    </div>
  )
}

export default ChatMessage

