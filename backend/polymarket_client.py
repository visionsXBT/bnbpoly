"""
Polymarket API client for fetching market data and bet information.
"""
import httpx
from typing import List, Dict, Optional, Callable, AsyncIterator
import os
import json
import asyncio
import websockets
from datetime import datetime


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
            
            # Handle 404 gracefully - some markets don't have trades endpoint
            if response.status_code == 404:
                return []
            
            response.raise_for_status()
            return response.json()
        except Exception as e:
            # Log but don't fail - trades are optional
            if "404" not in str(e):
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
            # When using 'q' parameter, don't order by volume - let search relevance determine order
            params = {
                "limit": limit * 2,  # Request more to filter if needed
                "q": query,  # Full user query - Polymarket handles the matching
                "active": "true",
                "closed": "false",
                "end_date_min": min_end_date,  # Only future markets
                # Don't use "order": "volumeNum" when searching - it overrides search relevance!
            }
            
            try:
                print(f"Searching Polymarket API with query: '{query}'")
                print(f"API URL: {url}")
                print(f"Params: {params}")
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                markets = response.json()
                
                if markets and len(markets) > 0:
                    print(f"Polymarket API search returned {len(markets)} markets for query: '{query}'")
                    # Log first few market titles to debug
                    for i, market in enumerate(markets[:3], 1):
                        title = market.get('question') or market.get('title') or market.get('name', 'N/A')
                        print(f"  Result {i}: {title[:100]}")
                    
                    # Filter results to ensure they actually match the query
                    # Polymarket's q parameter might not be working correctly
                    filtered = self._filter_markets_by_query_relevance(markets, query)
                    print(f"After filtering for query relevance: {len(filtered)} markets match")
                    if filtered:
                        return filtered[:limit]
                    # If filtering removed all results, the API search didn't work - return empty
                    print("Warning: All search results were filtered out - API search may not be working correctly")
                    return []
            except Exception as e:
                print(f"API search with 'q' parameter failed: {e}")
                import traceback
                traceback.print_exc()
            
            # Fallback: Try without date filter (some markets might not have end dates)
            params = {
                "limit": limit,
                "q": query,
                "active": "true",
                "closed": "false",
                # Don't use "order": "volumeNum" when searching - it overrides search relevance!
            }
            
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                markets = response.json()
                
                if markets and len(markets) > 0:
                    print(f"Polymarket API search (no date filter) returned {len(markets)} markets for query: '{query}'")
                    # Filter results to ensure they actually match the query
                    filtered = self._filter_markets_by_query_relevance(markets, query)
                    if filtered:
                        return filtered[:limit]
                    return []
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
    
    def _filter_markets_by_query_relevance(self, markets: List[Dict], query: str) -> List[Dict]:
        """Filter markets to only include those that actually match the query terms."""
        import re
        
        # Extract meaningful terms from query (remove stop words)
        query_lower = query.lower()
        query_words = set(re.findall(r'\b\w+\b', query_lower))
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 
                     'will', 'be', 'is', 'are', 'was', 'were', 'have', 'has', 'had', 'do', 'does', 'did', 
                     'can', 'could', 'should', 'would', 'may', 'might', 'must', 'what', 'when', 'where', 
                     'who', 'why', 'how'}
        # Don't remove 'networth', 'net', 'worth' - they might be important
        query_words = {w for w in query_words if w not in stop_words and len(w) > 1}
        
        # Separate subject terms from date terms
        subject_terms = []
        date_terms = []
        for word in query_words:
            if word.isdigit() or (word.replace('.', '').replace('-', '').isdigit()):
                date_terms.append(word)
            else:
                subject_terms.append(word.lower())
        
        print(f"Filtering markets - Subject terms: {subject_terms}, Date terms: {date_terms}")
        
        # Require at least one subject term to match (not just dates)
        if not subject_terms:
            # If no subject terms, just check for any term match
            subject_terms = [w.lower() for w in query_words if len(w) > 1]
        
        filtered_markets = []
        skipped_count = 0
        
        for market in markets:
            if market.get('closed', False):
                continue
            
            question = str(market.get('question', '') or '').lower()
            title = str(market.get('title', '') or market.get('name', '') or '').lower()
            slug = str(market.get('slug', '') or '').lower()
            market_text = f"{question} {title} {slug}"
            
            # Check if any subject term appears in the market
            matched_subject_terms = [term for term in subject_terms if term in market_text]
            matched_count = len(matched_subject_terms)
            
            # Require at least 1 subject term match (unless query has no subject terms)
            if len(subject_terms) > 0 and matched_count == 0:
                skipped_count += 1
                if skipped_count <= 3:  # Log first 3 skipped markets
                    print(f"  Skipping: '{question[:60]}...' - no subject term matches")
                continue  # Skip markets that don't match any subject terms
            
            # If we have subject terms, require at least one match
            if len(subject_terms) > 0 and matched_count > 0:
                print(f"  Keeping: '{question[:60]}...' - matched terms: {matched_subject_terms}")
                filtered_markets.append(market)
            elif len(subject_terms) == 0:
                # If no subject terms, check for any query word match
                if any(word in market_text for word in query_words):
                    filtered_markets.append(market)
        
        print(f"Filtered {len(markets)} markets down to {len(filtered_markets)} matching markets")
        return filtered_markets
    
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
    
    async def stream_trades(
        self, 
        market_id: str, 
        callback: Optional[Callable[[Dict], None]] = None
    ) -> AsyncIterator[Dict]:
        """
        Stream real-time trades for a specific market using Polymarket RTDS.
        
        Args:
            market_id: The market ID to stream trades for
            callback: Optional callback function to handle each trade
            
        Yields:
            Dict containing trade data
        """
        ws_url = "wss://ws-live-data.polymarket.com"
        reconnect_delay = 5
        max_reconnect_delay = 60
        
        while True:
            try:
                async with websockets.connect(ws_url) as websocket:
                    print(f"Connected to Polymarket RTDS for market {market_id}")
                    
                    # Subscribe to trades for this market
                    # Polymarket RTDS uses topic-based subscriptions
                    # Try different subscription formats based on RTDS documentation
                    subscribe_formats = [
                        {
                            "topic": f"trades:{market_id}",
                            "type": "subscribe"
                        },
                        {
                            "topic": "trades",
                            "type": "subscribe",
                            "market": market_id
                        },
                        {
                            "type": "subscribe",
                            "channel": "trades",
                            "market": market_id
                        }
                    ]
                    
                    # Try to subscribe (send first format, others as fallback if needed)
                    subscribed = False
                    for i, sub_msg in enumerate(subscribe_formats):
                        try:
                            await websocket.send(json.dumps(sub_msg))
                            print(f"Sent subscription message {i+1} for market {market_id}: {sub_msg}")
                            subscribed = True
                            break
                        except Exception as e:
                            print(f"Error sending subscription format {i+1}: {e}")
                            if i < len(subscribe_formats) - 1:
                                await asyncio.sleep(0.5)  # Brief delay before trying next format
                    
                    if not subscribed:
                        print(f"Warning: Could not send subscription for market {market_id}")
                    
                    # Listen for messages
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            
                            # Handle RTDS message structure: {topic, type, timestamp, payload}
                            msg_type = data.get("type") or data.get("event") or ""
                            topic = data.get("topic", "")
                            payload = data.get("payload") or data.get("data") or data
                            
                            # Check if this is a trade-related message
                            if (msg_type == "trade" or 
                                "trade" in str(topic).lower() or 
                                "trade" in str(data).lower() or
                                topic.startswith("trades:")):
                                trade_data = payload if payload != data else data
                                
                                # Format trade data consistently
                                formatted_trade = {
                                    "id": trade_data.get("id") or trade_data.get("tradeId") or trade_data.get("trade_id"),
                                    "market_id": market_id,
                                    "timestamp": trade_data.get("timestamp") or trade_data.get("time") or trade_data.get("created_at") or datetime.now().isoformat(),
                                    "price": trade_data.get("price") or trade_data.get("priceNum"),
                                    "size": trade_data.get("size") or trade_data.get("amount") or trade_data.get("amountNum"),
                                    "side": trade_data.get("side") or trade_data.get("type") or trade_data.get("direction"),  # "buy" or "sell"
                                    "outcome": trade_data.get("outcome") or trade_data.get("outcomeIndex"),
                                    "user": trade_data.get("user") or trade_data.get("trader") or trade_data.get("userAddress"),
                                }
                                
                                # Call callback if provided
                                if callback:
                                    try:
                                        callback(formatted_trade)
                                    except Exception as e:
                                        print(f"Error in callback: {e}")
                                
                                # Yield the trade
                                yield formatted_trade
                                
                            elif msg_type == "error" or "error" in str(data).lower():
                                error_msg = data.get("message") or data.get("error") or "Unknown error"
                                print(f"RTDS error: {error_msg}")
                                
                            elif msg_type in ["subscribed", "subscription_succeeded"]:
                                print(f"Successfully subscribed to trades for market {market_id}")
                                
                            # Log other message types for debugging (uncomment for debugging)
                            # else:
                            #     print(f"Received message type: {msg_type}, data: {data}")
                                
                        except json.JSONDecodeError as e:
                            print(f"Error parsing WebSocket message: {e}, raw: {message[:200]}")
                            continue
                        except Exception as e:
                            print(f"Error processing trade message: {e}")
                            import traceback
                            traceback.print_exc()
                            continue
                            
            except websockets.exceptions.ConnectionClosed:
                print(f"WebSocket connection closed for market {market_id}, reconnecting in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                
            except Exception as e:
                print(f"Error in WebSocket stream for market {market_id}: {e}")
                print(f"Reconnecting in {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
    
    async def get_recent_trades_stream(
        self, 
        market_id: str, 
        limit: int = 10
    ) -> List[Dict]:
        """
        Get recent trades and then continue streaming new ones.
        This combines the initial fetch with real-time updates.
        """
        # First, get recent trades via HTTP
        recent_trades = await self.get_market_trades(market_id, limit=limit)
        
        # Return recent trades first, then stream will continue with new ones
        return recent_trades
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

