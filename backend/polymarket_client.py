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
        """Search for markets by query string. Tries multiple search strategies."""
        try:
            from datetime import datetime, timedelta
            import re
            
            url = f"{self.api_url}/markets"
            current_date = datetime.now()
            min_end_date = (current_date + timedelta(days=1)).isoformat() + 'Z'
            
            # Extract key terms from query for multiple search strategies
            query_lower = query.lower()
            # Extract important keywords (remove stop words, keep meaningful terms)
            words = re.findall(r'\b\w+\b', query_lower)
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 
                         'will', 'be', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 'do', 'does', 'did', 
                         'can', 'could', 'should', 'would', 'may', 'might', 'must', 'what', 'when', 'where', 
                         'who', 'why', 'how', 'does', 'doesn', 'don', 'doesnt', 'dont'}
            key_terms = [w for w in words if w not in stop_words and len(w) > 2]
            
            # Strategy 1: Try API search parameter with full query
            params = {
                "limit": limit * 5,  # Fetch more to filter
                "q": query,
                "active": "true",
                "closed": "false",
                "end_date_min": min_end_date,
                "order": "volumeNum",
                "ascending": "false"
            }
            
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                markets = response.json()
                
                if markets and len(markets) > 0:
                    # Filter and sort by relevance
                    filtered = self._filter_markets_by_relevance(markets, query)
                    if filtered:
                        return filtered[:limit]
            except Exception as e:
                print(f"API search with 'q' parameter failed: {e}")
            
            # Strategy 2: Try with key terms only (if query is long)
            if len(key_terms) > 2:
                key_query = ' '.join(key_terms[:5])  # Use top 5 key terms
                params = {
                    "limit": limit * 5,
                    "q": key_query,
                    "active": "true",
                    "closed": "false",
                    "end_date_min": min_end_date,
                    "order": "volumeNum",
                    "ascending": "false"
                }
                
                try:
                    response = await self.client.get(url, params=params)
                    response.raise_for_status()
                    markets = response.json()
                    
                    if markets and len(markets) > 0:
                        filtered = self._filter_markets_by_relevance(markets, query)
                        if filtered:
                            return filtered[:limit]
                except Exception as e:
                    print(f"API search with key terms failed: {e}")
            
            # Strategy 3: Fetch many active markets and filter by keywords (no date filter first)
            # This ensures we don't miss markets due to date filtering
            params = {
                "limit": limit * 20,  # Fetch many markets
                "active": "true",
                "closed": "false",
                "order": "volumeNum",
                "ascending": "false"
            }
            
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                all_markets = response.json()
                
                if all_markets:
                    # Filter by relevance to query
                    filtered = self._filter_markets_by_relevance(all_markets, query)
                    if filtered:
                        return filtered[:limit]
            except Exception as e:
                print(f"Fetching all markets failed: {e}")
            
            # Strategy 4: Try with date filter but larger limit
            params = {
                "limit": limit * 20,
                "active": "true",
                "closed": "false",
                "end_date_min": min_end_date,
                "order": "volumeNum",
                "ascending": "false"
            }
            
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                all_markets = response.json()
                
                if all_markets:
                    filtered = self._filter_markets_by_relevance(all_markets, query)
                    if filtered:
                        return filtered[:limit]
            except Exception as e:
                print(f"Fetching markets with date filter failed: {e}")
            
            return []
        except Exception as e:
            print(f"Error searching markets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _filter_markets_by_relevance(self, markets: List[Dict], query: str) -> List[Dict]:
        """Filter and score markets by relevance to query."""
        import re
        
        # Normalize query - extract key terms
        query_lower = query.lower()
        query_words = set(re.findall(r'\b\w+\b', query_lower))
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 
                     'will', 'be', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 'do', 'does', 'did', 
                     'can', 'could', 'should', 'would', 'may', 'might', 'must', 'what', 'when', 'where', 
                     'who', 'why', 'how', 'does', 'doesn', 'don', 'doesnt', 'dont'}
        query_words = {w for w in query_words if w not in stop_words and len(w) > 2}
        
        # Extract important keywords (proper nouns, numbers, key terms)
        important_terms = []
        for word in query_words:
            # Keep numbers (years, prices, etc.)
            if word.isdigit() or (word.replace('.', '').isdigit()):
                important_terms.append(word)
            # Keep capitalized words (proper nouns)
            elif word[0].isupper() if word else False:
                important_terms.append(word.lower())
            # Keep common important terms
            elif word in ['bitcoin', 'btc', 'ethereum', 'eth', 'price', 'hit', 'reach', 'election', 'win', 'trump', 'biden']:
                important_terms.append(word)
        
        scored_markets = []
        
        for market in markets:
            if market.get('closed', False):
                continue
            
            score = 0
            question = str(market.get('question', '') or '').lower()
            title = str(market.get('title', '') or market.get('name', '') or '').lower()
            description = str(market.get('description', '') or '').lower()
            slug = str(market.get('slug', '') or '').lower()
            
            # Check for exact phrase matches (highest score)
            if query_lower in question or query_lower in title:
                score += 100
            
            # Check for partial phrase matches (e.g., "bitcoin 2025" matches "bitcoin hit in 2025")
            query_phrases = []
            words_list = list(query_words)
            # Create 2-3 word phrases from query
            for i in range(len(words_list) - 1):
                phrase = f"{words_list[i]} {words_list[i+1]}"
                query_phrases.append(phrase)
            for i in range(len(words_list) - 2):
                phrase = f"{words_list[i]} {words_list[i+1]} {words_list[i+2]}"
                query_phrases.append(phrase)
            
            for phrase in query_phrases:
                if phrase in question or phrase in title:
                    score += 50
            
            # Check for individual word matches
            question_words = set(re.findall(r'\b\w+\b', question))
            title_words = set(re.findall(r'\b\w+\b', title))
            slug_words = set(re.findall(r'\b\w+\b', slug))
            
            # Count matching words (higher weight for important terms)
            matches = query_words.intersection(question_words)
            score += len(matches) * 10
            
            matches = query_words.intersection(title_words)
            score += len(matches) * 8
            
            matches = query_words.intersection(slug_words)
            score += len(matches) * 12  # Slug matches are very relevant
            
            # Extra bonus for important terms (proper nouns, numbers, key words)
            for term in important_terms:
                term_lower = term.lower()
                if term_lower in question:
                    score += 20
                if term_lower in title:
                    score += 18
                if term_lower in slug:
                    score += 25  # Slug matches are highly relevant
            
            # Penalty for mismatched sports/events (e.g., NBA query but Super Bowl market)
            # Check if query mentions specific sports/events and market mentions different ones
            sports_keywords = {
                'nba': ['nba', 'basketball', 'basket'],
                'nfl': ['nfl', 'football', 'super bowl', 'superbowl'],
                'mlb': ['mlb', 'baseball'],
                'nhl': ['nhl', 'hockey', 'stanley cup'],
                'soccer': ['soccer', 'football', 'premier league', 'champions league', 'world cup'],
                'election': ['election', 'president', 'mayor', 'senate', 'congress'],
                'crypto': ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'cryptocurrency']
            }
            
            query_lower_words = set(re.findall(r'\b\w+\b', query_lower))
            market_text = f"{question} {title} {slug}".lower()
            
            # Check for sport/event mismatches
            for sport, keywords in sports_keywords.items():
                query_has_sport = any(kw in query_lower for kw in keywords)
                market_has_sport = any(kw in market_text for kw in keywords)
                
                if query_has_sport and not market_has_sport:
                    # Query mentions this sport but market doesn't - significant penalty
                    score -= 50
                elif not query_has_sport and market_has_sport:
                    # Market mentions sport but query doesn't - smaller penalty
                    score -= 20
            
            # Bonus for volume (more popular markets are more likely to be what user wants)
            volume = float(market.get('volumeNum', 0) or market.get('volume', 0) or 0)
            if volume > 0:
                # Higher volume = more relevant, but cap it
                score += min(volume / 500000, 10)  # Cap at 10 points, scales with volume
            
            if score > 0:
                market['_relevance_score'] = score
                scored_markets.append(market)
        
        # Sort by relevance score (descending)
        scored_markets.sort(key=lambda x: x.get('_relevance_score', 0), reverse=True)
        
        # Remove the temporary score field
        for market in scored_markets:
            market.pop('_relevance_score', None)
        
        return scored_markets
    
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

