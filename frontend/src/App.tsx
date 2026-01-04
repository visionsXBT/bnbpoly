import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './components/LandingPage'
import ChatApp from './components/ChatApp'
import TradingDashboard from './components/TradingDashboard'

function App() {
  // Always show landing page on first visit
  const [showLanding, setShowLanding] = useState<boolean>(true)
  
  const handleEnterLanding = () => {
    setShowLanding(false)
  }

  // Show landing page if not entered yet
  if (showLanding) {
    return (
      <LandingPage 
        onEnter={handleEnterLanding}
      />
    )
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ChatApp />} />
        <Route path="/trading" element={<TradingDashboard />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App

