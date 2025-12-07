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
        """Search for markets by query string. Uses Polymarket API search directly."""
        try:
            from datetime import datetime, timedelta
            
            url = f"{self.api_url}/markets"
            current_date = datetime.now()
            min_end_date = (current_date + timedelta(days=1)).isoformat() + 'Z'
            
            # Use Polymarket's built-in search - trust their algorithm
            # The 'q' parameter searches across question, slug, and other fields
            params = {
                "limit": limit,  # Request exactly what we need
                "q": query,  # Full user query - Polymarket handles the matching
                "active": "true",
                "closed": "false",
                "end_date_min": min_end_date,  # Only future markets
                "order": "volumeNum",  # Order by volume (most relevant first)
                "ascending": "false"
            }
            
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                markets = response.json()
                
                if markets and len(markets) > 0:
                    print(f"Polymarket API search returned {len(markets)} markets for query: '{query}'")
                    # Return results directly - Polymarket's search should be accurate
                    return markets
            except Exception as e:
                print(f"API search with 'q' parameter failed: {e}")
            
            # Fallback: Try without date filter (some markets might not have end dates)
            params = {
                "limit": limit,
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
                    print(f"Polymarket API search (no date filter) returned {len(markets)} markets for query: '{query}'")
                    return markets
            except Exception as e:
                print(f"API search without date filter failed: {e}")
            
            # If no results, return empty list
            print(f"No markets found for query: '{query}'")
            return []
        except Exception as e:
            print(f"Error searching markets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _filter_markets_by_relevance(self, markets: List[Dict], query: str, strict: bool = True) -> List[Dict]:
        """Filter and score markets by relevance to query. Strict mode only returns strong matches."""
        import re
        
        # Normalize query
        query_lower = query.lower().strip()
        query_words = set(re.findall(r'\b\w+\b', query_lower))
        
        # Remove only very common stop words (keep more words for better matching)
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 
                     'will', 'be', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 'do', 'does', 'did', 
                     'can', 'could', 'should', 'would', 'may', 'might', 'must', 'what', 'when', 'where', 'who', 'why', 'how'}
        query_words = {w for w in query_words if w not in stop_words and len(w) > 1}  # Keep 2+ char words
        
        # Extract all meaningful terms from query
        # Separate dates/years from subject terms
        date_terms = []  # Years, dates - less important for matching
        subject_terms = []  # Main subject terms - must match
        
        for word in query_words:
            # Keep numbers (years, prices, etc.) but treat them as less important
            if word.isdigit() or (word.replace('.', '').replace('-', '').isdigit()):
                date_terms.append(word)
            # Keep all meaningful words (not filtered by hardcoded list)
            elif len(word) > 2:
                subject_terms.append(word.lower())
        
        # Combine all terms for scoring, but require subject terms to match
        important_terms = subject_terms + date_terms
        
        # Calculate minimum match threshold
        # For strict mode, require at least 1 subject term to match (not just dates)
        min_subject_terms_to_match = 1 if strict and len(subject_terms) > 0 else 0
        min_terms_to_match = max(1, int(len(important_terms) * 0.3)) if strict else 1
        
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
            
            # Score based on all query terms matching
            matched_terms = 0
            matched_subject_terms = 0  # Track subject term matches separately
            
            for term in important_terms:
                term_lower = term.lower()
                is_subject_term = term_lower in subject_terms
                
                # Check if term appears in market text
                if term_lower in question or term_lower in title or term_lower in slug:
                    matched_terms += 1
                    if is_subject_term:
                        matched_subject_terms += 1
                    
                    # Count occurrences (some terms might appear multiple times)
                    question_count = question.count(term_lower)
                    title_count = title.count(term_lower)
                    slug_count = slug.count(term_lower)
                    
                    # Weight by term length (longer terms are more specific and important)
                    term_weight = min(len(term), 5)  # Cap at 5x weight for very long terms
                    
                    # Subject terms get higher weight than date terms
                    base_weight = 30 if is_subject_term else 10
                    
                    score += question_count * (base_weight * term_weight)
                    score += title_count * (base_weight * 0.8 * term_weight)
                    score += slug_count * (base_weight * 1.2 * term_weight)  # Slug matches are very relevant
            
            # In strict mode, require subject terms to match (not just dates)
            # This is CRITICAL - prevents NFL markets from appearing for non-sports queries
            if strict and len(subject_terms) > 0:
                if matched_subject_terms < min_subject_terms_to_match:
                    # Debug: log why market was skipped
                    print(f"Skipping market '{question[:50]}...' - matched {matched_subject_terms} subject terms, need {min_subject_terms_to_match}")
                    continue  # Skip this market - doesn't match subject terms
            
            # Also require minimum overall terms to match
            if strict and matched_terms < min_terms_to_match:
                print(f"Skipping market '{question[:50]}...' - matched {matched_terms} terms, need {min_terms_to_match}")
                continue  # Skip this market - doesn't match enough terms
            
            # Heavy penalty if NO terms match at all
            if matched_terms == 0:
                continue  # Skip markets with zero matches
            
            # Bonus for volume (more popular markets are more likely to be what user wants)
            volume = float(market.get('volumeNum', 0) or market.get('volume', 0) or 0)
            if volume > 0:
                # Higher volume = more relevant, but cap it
                score += min(volume / 1000000, 5)  # Cap at 5 points, scales with volume
            
            # Only include markets with positive score
            if score > 0:
                market['_relevance_score'] = score
                market['_matched_terms'] = matched_terms
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

