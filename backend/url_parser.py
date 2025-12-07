"""
Utility to parse Polymarket URLs and extract event/market identifiers.
"""
import re
from typing import Optional, Dict, List
from urllib.parse import urlparse, parse_qs


def parse_polymarket_url(url: str) -> Optional[Dict[str, str]]:
    """
    Parse a Polymarket URL and extract event/market information.
    
    Examples:
    - https://polymarket.com/event/time-2025-person-of-the-year?tid=1765088115846
    - https://polymarket.com/event/event-slug
    - https://polymarket.com/market/market-id
    
    Returns:
        Dict with 'type' (event/market), 'slug' or 'id', and 'tid' if present
    """
    if not url or not isinstance(url, str):
        return None
    
    # Check if it's a Polymarket URL
    if 'polymarket.com' not in url.lower():
        return None
    
    try:
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p]
        
        if len(path_parts) < 2:
            return None
        
        result = {}
        
        # Check for /event/ or /market/ in path
        if path_parts[0] == 'event' and len(path_parts) > 1:
            result['type'] = 'event'
            result['slug'] = path_parts[1]
        elif path_parts[0] == 'market' and len(path_parts) > 1:
            result['type'] = 'market'
            result['id'] = path_parts[1]
        else:
            # Try to match event pattern in path
            event_match = re.search(r'/event/([^/?]+)', parsed.path)
            if event_match:
                result['type'] = 'event'
                result['slug'] = event_match.group(1)
            else:
                market_match = re.search(r'/market/([^/?]+)', parsed.path)
                if market_match:
                    result['type'] = 'market'
                    result['id'] = market_match.group(1)
                else:
                    return None
        
        # Extract query parameters
        query_params = parse_qs(parsed.query)
        if 'tid' in query_params:
            result['tid'] = query_params['tid'][0]
        
        return result if result else None
        
    except Exception as e:
        print(f"Error parsing URL {url}: {e}")
        return None


def extract_urls_from_text(text: str) -> List[str]:
    """
    Extract all URLs from a text string.
    
    Returns:
        List of URL strings
    """
    url_pattern = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    )
    return url_pattern.findall(text)

