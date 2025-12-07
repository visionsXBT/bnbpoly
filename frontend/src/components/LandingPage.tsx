import './LandingPage.css'

interface LandingPageProps {
  onEnter: () => void
  language: 'en' | 'zh'
}

function LandingPage({ onEnter, language }: LandingPageProps) {
  const title = language === 'zh' ? 'BNBPOLY' : 'BNBPOLY'
  const subtitle = language === 'zh' 
    ? 'Polymarket 洞察助手' 
    : 'Polymarket Insights Assistant'
  const description = language === 'zh'
    ? 'AI 驱动的预测市场分析和投注洞察。获取实时数据、专家分析和可操作的见解，做出明智决策。'
    : 'AI-powered prediction market analysis and betting insights. Get real-time data, expert analysis, and actionable insights to make informed decisions.'
  const enterButton = language === 'zh' ? '开始使用' : 'Get Started'

  return (
    <div className="landing-page">
      <div className="landing-content">
        <div className="landing-logo-container">
          <img src="/bnbpoly.png" alt="BNBPOLY Logo" className="landing-logo" />
          <h1 className="landing-title">{title}</h1>
        </div>
        <h2 className="landing-subtitle">{subtitle}</h2>
        <p className="landing-description">{description}</p>
        <button className="landing-button" onClick={onEnter}>
          {enterButton}
        </button>
      </div>
    </div>
  )
}

export default LandingPage

