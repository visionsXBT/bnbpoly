"""
FastAPI backend server for Polymarket insights chatbot.
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os
import json
from dotenv import load_dotenv
from polymarket_client import PolymarketClient
from insight_generator import InsightGenerator
from url_parser import parse_polymarket_url, extract_urls_from_text

# Load environment variables
load_dotenv()

# Initialize clients (before lifespan)
polymarket_client = PolymarketClient()
insight_generator = InsightGenerator()

# Use lifespan context for cleanup (replaces deprecated on_event)
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    await polymarket_client.close()

app = FastAPI(title="Polymarket Insights Chatbot API", lifespan=lifespan)

# CORS middleware for React frontend
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
]
# Add production frontend URL from environment variable if set
production_frontend = os.getenv("FRONTEND_URL")
if production_frontend:
    # Handle both with and without protocol
    if not production_frontend.startswith(('http://', 'https://')):
        production_frontend = f"https://{production_frontend}"
    allowed_origins.append(production_frontend)
    # Also add without protocol in case
    if production_frontend.startswith('https://'):
        allowed_origins.append(production_frontend.replace('https://', 'http://'))

# Also allow requests from Railway's public domain (for custom domains that proxy through Railway)
railway_public_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN")
if railway_public_domain:
    allowed_origins.append(f"https://{railway_public_domain}")
    allowed_origins.append(f"http://{railway_public_domain}")

# For custom domains, also allow the custom domain itself
# You can add your custom domain here or via FRONTEND_URL env var
custom_domain = os.getenv("CUSTOM_DOMAIN")
if custom_domain:
    if not custom_domain.startswith(('http://', 'https://')):
        allowed_origins.append(f"https://{custom_domain}")
        allowed_origins.append(f"http://{custom_domain}")
    else:
        allowed_origins.append(custom_domain)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MessageHistory(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str

class ChatMessage(BaseModel):
    message: str
    market_id: Optional[str] = None
    search_query: Optional[str] = None
    conversation_history: Optional[List[MessageHistory]] = None
    language: Optional[str] = 'en'  # 'en' or 'zh'


class ChatResponse(BaseModel):
    response: str
    markets: Optional[List[dict]] = None


@app.get("/")
async def root():
    return {"message": "Polymarket Insights Chatbot API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(message: ChatMessage):
    """Main chat endpoint that generates insights based on user query."""
    try:
        market_data = None
        market_details = None
        trades = None
        
        # Check if message contains Polymarket URLs
        urls = extract_urls_from_text(message.message)
        polymarket_url_info = None
        
        for url in urls:
            url_info = parse_polymarket_url(url)
            if url_info:
                polymarket_url_info = url_info
                break
        
        # Fetch relevant market data based on query
        if polymarket_url_info:
            # Handle Polymarket URL
            if polymarket_url_info.get('type') == 'event' and polymarket_url_info.get('slug'):
                # Fetch event data by slug
                event_data = await polymarket_client.get_event_by_slug(polymarket_url_info['slug'])
                if event_data:
                    market_details = event_data
                    # Try to get markets for this event
                    event_markets = await polymarket_client.get_event_markets(polymarket_url_info['slug'])
                    if event_markets:
                        market_data = event_markets
                        # Get trades for the first market if available
                        if event_markets and event_markets[0].get('id'):
                            trades = await polymarket_client.get_market_trades(event_markets[0]['id'])
            elif polymarket_url_info.get('type') == 'market' and polymarket_url_info.get('id'):
                # Fetch market by ID
                market_details = await polymarket_client.get_market_by_id(polymarket_url_info['id'])
                if market_details:
                    trades = await polymarket_client.get_market_trades(polymarket_url_info['id'])
        elif message.market_id:
            # Get specific market details
            market_details = await polymarket_client.get_market_by_id(message.market_id)
            if market_details:
                trades = await polymarket_client.get_market_trades(message.market_id)
        elif message.search_query:
            # Search for markets using explicit search query
            market_data = await polymarket_client.search_markets(message.search_query)
            # If we found a single highly relevant market, treat it as market_details
            if market_data and len(market_data) == 1:
                market_details = market_data[0]
                if market_details.get('id'):
                    trades = await polymarket_client.get_market_trades(market_details['id'])
        else:
            # No URL provided - try to search for markets based on user's query
            # Extract keywords from the message to search
            search_results = await polymarket_client.search_markets(message.message, limit=5)
            print(f"Search results for '{message.message}': {len(search_results) if search_results else 0} markets found")
            if search_results and len(search_results) > 0:
                # Log what markets were found
                for i, market in enumerate(search_results[:3], 1):
                    market_title = market.get('question') or market.get('title') or market.get('name', 'N/A')
                    print(f"  Market {i}: {market_title[:80]}")
                
                # If we found a single highly relevant market, use it as market_details
                if len(search_results) == 1:
                    market_details = search_results[0]
                    if market_details.get('id'):
                        trades = await polymarket_client.get_market_trades(market_details['id'])
                else:
                    # Multiple results - use as market_data
                    market_data = search_results
                    # Get trades for the most relevant market
                    if search_results[0].get('id'):
                        trades = await polymarket_client.get_market_trades(search_results[0]['id'])
            else:
                # Only use fallback if search truly found nothing
                print(f"No markets found for query: '{message.message}' - NOT using fallback to avoid irrelevant markets")
                # Don't use fallback - it returns top volume markets which are often irrelevant
                # market_data = await polymarket_client.get_markets(limit=10)
        
        # Convert conversation history to dict format if provided
        conv_history = None
        if message.conversation_history:
            conv_history = [{"role": msg.role, "content": msg.content} for msg in message.conversation_history]
        
        # Generate insight using Claude
        insight = await insight_generator.generate_insight(
            user_query=message.message,
            market_data=market_data,
            market_details=market_details,
            trades=trades,
            conversation_history=conv_history,
            language=message.language or 'en'
        )
        
        return ChatResponse(
            response=insight,
            markets=market_data if market_data else None
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")


@app.get("/api/markets")
async def get_markets(limit: int = 20, offset: int = 0):
    """Get list of active markets."""
    try:
        markets = await polymarket_client.get_markets(limit=limit, offset=offset)
        return {"markets": markets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching markets: {str(e)}")


@app.get("/api/markets/{market_id}")
async def get_market(market_id: str):
    """Get specific market details."""
    try:
        market = await polymarket_client.get_market_by_id(market_id)
        if not market:
            raise HTTPException(status_code=404, detail="Market not found")
        return {"market": market}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching market: {str(e)}")


@app.get("/api/markets/{market_id}/trades")
async def get_market_trades(market_id: str, limit: int = 50):
    """Get trades for a specific market."""
    try:
        trades = await polymarket_client.get_market_trades(market_id, limit=limit)
        return {"trades": trades}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching trades: {str(e)}")


@app.websocket("/api/markets/{market_id}/trades/stream")
async def stream_market_trades(websocket: WebSocket, market_id: str):
    """
    WebSocket endpoint to stream real-time trades for a specific market.
    """
    await websocket.accept()
    print(f"Client connected to trades stream for market {market_id}")
    
    try:
        # First, send recent trades
        recent_trades = await polymarket_client.get_market_trades(market_id, limit=20)
        if recent_trades:
            await websocket.send_json({
                "type": "recent_trades",
                "data": recent_trades
            })
        
        # Then stream new trades in real-time
        async for trade in polymarket_client.stream_trades(market_id):
            try:
                await websocket.send_json({
                    "type": "new_trade",
                    "data": trade
                })
            except Exception as e:
                print(f"Error sending trade to client: {e}")
                break
                
    except WebSocketDisconnect:
        print(f"Client disconnected from trades stream for market {market_id}")
    except Exception as e:
        print(f"Error in trades stream for market {market_id}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass


@app.websocket("/api/trades/stream")
async def stream_price_updates(websocket: WebSocket):
    """
    WebSocket endpoint to stream price updates from all active markets.
    Shows price changes (up/down) instead of individual trades.
    """
    await websocket.accept()
    print("Client connected to price updates stream")
    
    try:
        # Get top markets to monitor
        top_markets = await polymarket_client.get_markets(limit=30)
        market_ids = [m.get('id') for m in top_markets if m.get('id')]
        
        if not market_ids:
            await websocket.send_json({
                "type": "error",
                "message": "No markets available"
            })
            return
        
        print(f"Monitoring {len(market_ids)} markets for price updates")
        
        # Send initial message
        await websocket.send_json({
            "type": "connected",
            "message": f"Monitoring {len(market_ids)} markets for price changes"
        })
        
        # Use polling-based price update stream
        async for price_update in polymarket_client.poll_price_updates_stream(market_ids, poll_interval=5):
            try:
                await websocket.send_json({
                    "type": "price_update",
                    "data": price_update
                })
            except Exception as e:
                print(f"Error sending price update to client: {e}")
                break
                
    except WebSocketDisconnect:
        print("Client disconnected from price updates stream")
    except Exception as e:
        print(f"Error in price updates stream: {e}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

