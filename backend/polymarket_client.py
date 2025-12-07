"""
Polymarket API client for fetching market data and bet information.
"""
import httpx
from typing import List, Dict, Optional
import os


class PolymarketClient:
    """Client for interacting with Polymarket API."""
    
    def __init__(self, api_url: Optional[str] = None):
        self.api_url = api_url or os.getenv("POLYMARKET_API_URL", "https://gamma-api.polymarket.com")
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def get_markets(self, limit: int = 20, offset: int = 0) -> List[Dict]:
        """Fetch current active markets from Polymarket, using API date filtering."""
        try:
            from datetime import datetime, timedelta
            
            url = f"{self.api_url}/markets"
            
            # Use API's end_date_min parameter to only get markets with end dates in the future
            # This is much more reliable than filtering in Python
            current_date = datetime.now()
            # Only get markets that end at least 1 day from now (to include markets ending soon)
            min_end_date = (current_date + timedelta(days=1)).isoformat() + 'Z'
            
            # Also filter by year in question as backup, but use API date filter as primary
            params = {
                "limit": limit * 3,  # Fetch more to sort through
                "offset": offset,
                "active": "true",
                "closed": "false",
                "end_date_min": min_end_date,  # Only markets ending in the future
                "order": "volumeNum",  # Order by volume
                "ascending": "false"  # Descending order (highest volume first)
            }
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            markets = response.json()
            
            if not markets or len(markets) == 0:
                # Fallback: try without end_date_min but still filter by year in question
                print("No markets with future end dates, trying with year filter...")
                params_fallback = {
                    "limit": limit * 5,
                    "offset": offset,
                    "active": "true",
                    "closed": "false",
                    "order": "volumeNum",
                    "ascending": "false"
                }
                response = await self.client.get(url, params=params_fallback)
                response.raise_for_status()
                markets = response.json()
                
                # Filter by year in question as backup
                if markets:
                    import re
                    filtered_markets = []
                    for market in markets:
                        is_closed = market.get('closed', False)
                        if is_closed:
                            continue
                        
                        question = str(market.get('question', '') or '')
                        if question:
                            year_matches = re.findall(r'\b(19\d{2}|20\d{2})\b', question)
                            if year_matches:
                                max_year = max([int(y) for y in year_matches])
                                if max_year < 2024:
                                    continue
                        
                        filtered_markets.append(market)
                    
                    markets = filtered_markets
            
            if not markets:
                print("No markets returned from API")
                return []
            
            print(f"Fetched {len(markets)} markets from API")
            
            # Simple filtering: only exclude explicitly closed
            filtered_markets = []
            for market in markets:
                is_closed = market.get('closed', False)
                if not is_closed:
                    filtered_markets.append(market)
            
            # Sort by volume (descending) - API should already sort, but ensure it
            filtered_markets.sort(
                key=lambda x: float(x.get('volumeNum', 0) or x.get('volume', 0) or x.get('liquidityNum', 0) or 0), 
                reverse=True
            )
            
            result = filtered_markets[:limit]
            print(f"Returning {len(result)} markets (sorted by volume)")
            return result
            
        except Exception as e:
            print(f"Error fetching markets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    async def get_market_by_id(self, market_id: str) -> Optional[Dict]:
        """Fetch a specific market by ID."""
        try:
            url = f"{self.api_url}/markets/{market_id}"
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching market {market_id}: {e}")
            return None
    
    async def get_market_trades(self, market_id: str, limit: int = 50) -> List[Dict]:
        """Fetch recent trades for a specific market."""
        try:
            url = f"{self.api_url}/markets/{market_id}/trades"
            params = {"limit": limit}
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching trades for market {market_id}: {e}")
            return []
    
    async def search_markets(self, query: str, limit: int = 20) -> List[Dict]:
        """Search for markets by query string."""
        try:
            url = f"{self.api_url}/markets"
            params = {
                "limit": limit,
                "q": query
            }
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error searching markets: {e}")
            return []
    
    async def get_event_by_slug(self, event_slug: str) -> Optional[Dict]:
        """Fetch event data by event slug from Polymarket URL."""
        try:
            # Try different API endpoints for event data
            # First, try searching for the event
            url = f"{self.api_url}/events"
            params = {"slug": event_slug}
            response = await self.client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                if data:
                    return data[0] if isinstance(data, list) else data
            
            # Try alternative endpoint structure
            url = f"{self.api_url}/event/{event_slug}"
            response = await self.client.get(url)
            if response.status_code == 200:
                return response.json()
            
            # Try searching markets with the slug
            markets = await self.search_markets(event_slug, limit=5)
            if markets:
                # Return the first matching market
                return markets[0]
            
            return None
        except Exception as e:
            print(f"Error fetching event by slug {event_slug}: {e}")
            # Try searching as fallback
            try:
                markets = await self.search_markets(event_slug, limit=5)
                return markets[0] if markets else None
            except:
                return None
    
    async def get_event_markets(self, event_slug: str) -> List[Dict]:
        """Get all markets for a specific event."""
        try:
            # Try to get markets associated with the event
            url = f"{self.api_url}/events/{event_slug}/markets"
            response = await self.client.get(url)
            if response.status_code == 200:
                return response.json()
            
            # Fallback: search for markets with event slug
            return await self.search_markets(event_slug, limit=20)
        except Exception as e:
            print(f"Error fetching markets for event {event_slug}: {e}")
            return []
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

