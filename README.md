# Polymarket Insights Chatbot

An AI-powered chatbot that provides insights and analysis on Polymarket betting markets using Anthropic's Claude API and real-time Polymarket data.

## Features

- 🤖 **AI-Powered Insights**: Uses Anthropic Claude to analyze Polymarket markets and provide intelligent insights
- 📊 **Real-Time Market Data**: Fetches live data from Polymarket API
- 💬 **Interactive Chat Interface**: Modern React-based chat UI
- 🔍 **Market Search**: Search and analyze specific markets
- 📈 **Trade Analysis**: Get insights on recent trades and market activity

## Tech Stack

- **Backend**: Python with FastAPI
- **Frontend**: React with TypeScript (TSX) and Vite
- **LLM**: Anthropic Claude API (claude-sonnet-4-5-20250929)
- **Data Source**: Polymarket Gamma API (https://gamma-api.polymarket.com)

## Setup Instructions

### Prerequisites

- Python 3.8+
- Node.js 16+
- Anthropic API key

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
```

3. Activate the virtual environment:
   - On Windows:
   ```bash
   venv\Scripts\activate
   ```
   - On macOS/Linux:
   ```bash
   source venv/bin/activate
   ```

4. Upgrade pip first (important for Python 3.13):
```bash
python -m pip install --upgrade pip
```

5. Install dependencies:
```bash
pip install -r requirements.txt
```

**Note**: If you encounter Rust compilation errors with `pydantic-core` on Python 3.13, try:
```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt --only-binary :all:
```

If that doesn't work, you can install Rust from https://rustup.rs/ or use Python 3.11/3.12 instead.

6. Create a `.env` file in the `backend` directory:
   - Copy the `env.example` file and rename it to `.env`
   - Or create a new `.env` file with the following content:
   ```env
   ANTHROPIC_API_KEY=your_anthropic_api_key_here
   POLYMARKET_API_URL=https://gamma-api.polymarket.com
   ```
   
   **Required Variables:**
   - `ANTHROPIC_API_KEY`: Your Anthropic API key (get it from https://console.anthropic.com/)
   
   **Optional Variables:**
   - `POLYMARKET_API_URL`: Polymarket API endpoint (default: https://gamma-api.polymarket.com)
   
   **Note**: The `.env` file is required for the chatbot to work. Make sure to replace `your_anthropic_api_key_here` with your actual API key.

7. Start the backend server:
```bash
python main.py
```

The backend will run on `http://localhost:8000`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

The frontend will run on `http://localhost:3000`

## Usage

1. Make sure both backend and frontend servers are running
2. Open your browser and navigate to `http://localhost:3000`
3. Start chatting! Try asking questions like:
   - "What are the most active markets right now?"
   - "Analyze the market for [specific event]"
   - "What are the best betting opportunities?"
   - "Show me markets related to [topic]"

## API Endpoints

### POST `/api/chat`
Send a chat message and get AI-generated insights.

**Request Body:**
```json
{
  "message": "What are the best betting opportunities?",
  "market_id": "optional-market-id",
  "search_query": "optional-search-query"
}
```

**Response:**
```json
{
  "response": "AI-generated insight...",
  "markets": [...]
}
```

### GET `/api/markets`
Get list of active markets.

**Query Parameters:**
- `limit` (default: 20)
- `offset` (default: 0)

### GET `/api/markets/{market_id}`
Get specific market details.

### GET `/api/markets/{market_id}/trades`
Get recent trades for a market.

## Project Structure

```
.
├── backend/
│   ├── main.py                 # FastAPI server
│   ├── polymarket_client.py    # Polymarket API client
│   ├── insight_generator.py    # Claude API integration
│   ├── requirements.txt        # Python dependencies
│   └── .env                    # Environment variables (create this)
├── frontend/
│   ├── src/
│   │   ├── App.tsx            # Main React component (TypeScript)
│   │   ├── components/        # React components (TSX)
│   │   ├── types.ts           # TypeScript type definitions
│   │   └── main.tsx           # React entry point (TypeScript)
│   ├── package.json           # Node dependencies
│   ├── tsconfig.json          # TypeScript configuration
│   └── vite.config.ts         # Vite configuration (TypeScript)
└── README.md
```

## Notes

- The Anthropic API key is configured in the code. For production, use environment variables
- The Polymarket API uses the Gamma API endpoint: `https://gamma-api.polymarket.com`
- The chatbot uses Claude Sonnet 4.5 (claude-sonnet-4-5-20250929) for generating insights
- Frontend is built with TypeScript for type safety

## License

MIT

