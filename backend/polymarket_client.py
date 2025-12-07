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
        """Search for markets by query string. Uses full query for general-purpose search."""
        try:
            from datetime import datetime, timedelta
            
            url = f"{self.api_url}/markets"
            current_date = datetime.now()
            min_end_date = (current_date + timedelta(days=1)).isoformat() + 'Z'
            
            # Strategy 1: Use full query with Polymarket API search parameter
            # This lets Polymarket's search algorithm handle the matching
            params = {
                "limit": limit * 3,  # Fetch more to filter
                "q": query,  # Use full query - let API handle it
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
                    # Light filtering by relevance (less strict)
                    filtered = self._filter_markets_by_relevance(markets, query, strict=False)
                    if filtered:
                        return filtered[:limit]
            except Exception as e:
                print(f"API search with 'q' parameter failed: {e}")
            
            # Strategy 2: Try without date filter (some markets might not have end dates)
            params = {
                "limit": limit * 3,
                "q": query,
                "active": "true",
                "closed": "false",
                "order": "volumeNum",
                "ascending": "false"
            }
            
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                markets = response.json()
                
                if markets and len(markets) > 0:
                    filtered = self._filter_markets_by_relevance(markets, query, strict=False)
                    if filtered:
                        return filtered[:limit]
            except Exception as e:
                print(f"API search without date filter failed: {e}")
            
            # Strategy 3: Fetch many active markets and filter by full query text matching
            # This is a fallback if API search doesn't work
            params = {
                "limit": limit * 30,  # Fetch many markets
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
                    # Filter by relevance to full query
                    filtered = self._filter_markets_by_relevance(all_markets, query, strict=False)
                    if filtered:
                        return filtered[:limit]
            except Exception as e:
                print(f"Fetching all markets failed: {e}")
            
            return []
        except Exception as e:
            print(f"Error searching markets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _filter_markets_by_relevance(self, markets: List[Dict], query: str, strict: bool = True) -> List[Dict]:
        """Filter and score markets by relevance to query. Uses full query text matching."""
        import re
        
        # Normalize query
        query_lower = query.lower().strip()
        query_words = set(re.findall(r'\b\w+\b', query_lower))
        
        # Remove only very common stop words (keep more words for better matching)
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 
                     'will', 'be', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 'do', 'does', 'did', 
                     'can', 'could', 'should', 'would', 'may', 'might', 'must'}
        query_words = {w for w in query_words if w not in stop_words and len(w) > 1}  # Keep 2+ char words
        
        # Extract all meaningful terms from query (not just hardcoded keywords)
        important_terms = []
        for word in query_words:
            # Keep numbers (years, prices, etc.)
            if word.isdigit() or (word.replace('.', '').replace('-', '').isdigit()):
                important_terms.append(word)
            # Keep all words that are likely meaningful (proper nouns, technical terms, etc.)
            # Don't filter by hardcoded list - use all query words
            elif len(word) > 2:  # Keep words longer than 2 chars
                important_terms.append(word.lower())
        
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
            if query_lower in question or query_lower in title or query_lower in slug:
                score += 150
            
            # Check for partial phrase matches using all words from query
            # Create phrases of varying lengths from the query
            words_list = list(query_words)
            query_phrases = []
            
            # 2-word phrases
            for i in range(len(words_list) - 1):
                phrase = f"{words_list[i]} {words_list[i+1]}"
                query_phrases.append(phrase)
            
            # 3-word phrases
            for i in range(len(words_list) - 2):
                phrase = f"{words_list[i]} {words_list[i+1]} {words_list[i+2]}"
                query_phrases.append(phrase)
            
            # 4-word phrases (for longer queries like "jensen huang nvidia earnings")
            for i in range(len(words_list) - 3):
                phrase = f"{words_list[i]} {words_list[i+1]} {words_list[i+2]} {words_list[i+3]}"
                query_phrases.append(phrase)
            
            for phrase in query_phrases:
                if phrase in question or phrase in title or phrase in slug:
                    score += 60  # Higher weight for phrase matches
            
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
            
            # Score based on all query terms (not just hardcoded keywords)
            # This makes it work for any query, not just predefined terms
            for term in important_terms:
                term_lower = term.lower()
                # Count occurrences (some terms might appear multiple times)
                question_count = question.count(term_lower)
                title_count = title.count(term_lower)
                slug_count = slug.count(term_lower)
                
                # Weight by term length (longer terms are more specific and important)
                term_weight = min(len(term), 5)  # Cap at 5x weight for very long terms
                
                score += question_count * (15 * term_weight)
                score += title_count * (12 * term_weight)
                score += slug_count * (18 * term_weight)  # Slug matches are very relevant
            
            # Penalty for mismatched sports/events (e.g., NBA query but Super Bowl market)
            # Check if query mentions specific sports/events and market mentions different ones
            sports_keywords = {
                'nba': ['nba', 'basketball', 'basket', 'nba championship', 'nba finals'],
                'nfl': ['nfl', 'american football', 'super bowl', 'superbowl', 'nfl championship'],
                'mlb': ['mlb', 'baseball', 'world series', 'mlb championship'],
                'nhl': ['nhl', 'hockey', 'stanley cup', 'nhl championship'],
                'soccer': ['soccer', 'football', 'uefa', 'champions league', 'premier league', 'world cup', 
                          'bundesliga', 'la liga', 'serie a', 'arsenal', 'manchester', 'real madrid', 
                          'barcelona', 'bayern', 'psg', 'liverpool', 'chelsea', 'inter', 'juventus'],
                'election': ['election', 'president', 'mayor', 'senate', 'congress', 'vote', 'candidate'],
                'crypto': ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'cryptocurrency', 'price']
            }
            
            query_lower_words = set(re.findall(r'\b\w+\b', query_lower))
            market_text = f"{question} {title} {slug}".lower()
            
            # Check for sport/event mismatches
            query_sports = set()
            market_sports = set()
            
            for sport, keywords in sports_keywords.items():
                if any(kw in query_lower for kw in keywords):
                    query_sports.add(sport)
                if any(kw in market_text for kw in keywords):
                    market_sports.add(sport)
            
            # If query mentions a specific sport but market is about a different sport, heavy penalty
            if query_sports and market_sports:
                if not query_sports.intersection(market_sports):
                    # Completely different sports - heavy penalty
                    score -= 100
            elif query_sports and not market_sports:
                # Query mentions sport but market doesn't - significant penalty
                score -= 50
            elif not query_sports and market_sports:
                # Market mentions sport but query doesn't - smaller penalty (might be relevant)
                score -= 10
            
            # Special handling for soccer - many variations
            if 'soccer' in query_sports or 'soccer' in market_sports:
                # Check for specific soccer competitions
                soccer_competitions = {
                    'champions league': ['champions league', 'uefa champions', 'ucl'],
                    'premier league': ['premier league', 'epl', 'english premier'],
                    'world cup': ['world cup', 'fifa world cup'],
                    'bundesliga': ['bundesliga'],
                    'la liga': ['la liga', 'spanish league'],
                    'serie a': ['serie a', 'italian league']
                }
                
                query_competition = None
                market_competition = None
                
                for comp, keywords in soccer_competitions.items():
                    if any(kw in query_lower for kw in keywords):
                        query_competition = comp
                    if any(kw in market_text for kw in keywords):
                        market_competition = comp
                
                # If query asks about specific competition but market is different competition
                if query_competition and market_competition and query_competition != market_competition:
                    score -= 75  # Different soccer competitions - significant penalty
            
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

