import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import '../App.css'
import './Terminal.css'

function Terminal() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return

    setIsSubmitting(true)
    // TODO: Add API call to save email to waitlist
    // For now, just simulate submission
    setTimeout(() => {
      setIsSubmitting(false)
      setSubmitted(true)
      setEmail('')
    }, 1000)
  }

  return (
    <div className="terminal-page">
      <div className="terminal-gradient-overlay"></div>
      <div className="terminal-opacity-overlay"></div>
      <div className="terminal-content">
        <div className="terminal-header">
          <div className="logo-container">
            <img src="/whisper.png" alt="Logo" className="logo" />
            <span className="logo-text">POLYMAKER</span>
          </div>
          <div className="terminal-nav">
            <button onClick={() => navigate('/')} className="nav-button">
              Chat
            </button>
            <button onClick={() => navigate('/trading')} className="nav-button">
              Trade Bot
            </button>
            <button className="nav-button active">
              Terminal
            </button>
          </div>
        </div>

        <div className="terminal-main">
          <div className="terminal-card">
            <h1 className="terminal-title">POLYMAKER Terminal</h1>
            <p className="terminal-description">
              Deposit funds and execute autonomous trades directly on Polymarket. 
              Full trading capabilities coming soon - currently in beta development.
            </p>

            {!submitted ? (
              <form onSubmit={handleSubmit} className="waitlist-form">
                <div className="form-group">
                  <label htmlFor="email" className="form-label">
                    Join the Waitlist
                  </label>
                  <input
                    type="email"
                    id="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Enter your email"
                    className="form-input"
                    required
                    disabled={isSubmitting}
                  />
                </div>
                <button
                  type="submit"
                  className="submit-button"
                  disabled={isSubmitting || !email.trim()}
                >
                  {isSubmitting ? 'Submitting...' : 'Join Waitlist'}
                </button>
              </form>
            ) : (
              <div className="success-message">
                <div className="success-icon">✓</div>
                <p>Thank you! We'll notify you when Terminal is ready.</p>
                <button
                  onClick={() => setSubmitted(false)}
                  className="submit-button"
                >
                  Join Another Email
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default Terminal

