import './LandingPage.css'

interface LandingPageProps {
  onEnter: () => void
}

function LandingPage({ onEnter }: LandingPageProps) {
  return (
    <div className="landing-page">
      <div className="landing-content">
        <div className="landing-logo-container">
          <img src="/bnbpoly.png" alt="BNBPOLY Logo" className="landing-logo" />
          <h1 className="landing-title">WHISPER</h1>
        </div>
        <h2 className="landing-subtitle">Polymarket Insights Assistant</h2>
        <p className="landing-description">AI-powered prediction market analysis and betting insights. Get real-time data, expert analysis, and actionable insights to make informed decisions.</p>
        <button className="landing-button" onClick={onEnter}>
          Get Started
        </button>
      </div>
    </div>
  )
}

export default LandingPage

