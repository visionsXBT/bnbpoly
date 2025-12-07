"""
Insight generator using Anthropic Claude API to analyze Polymarket data.
"""
import anthropic
import os
from typing import Dict, List, Optional
import json
import asyncio
from datetime import datetime


class InsightGenerator:
    """Generates insights on Polymarket bets using Claude."""
    
    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self.client = anthropic.Anthropic(api_key=api_key)
    
    async def generate_insight(
        self, 
        user_query: str, 
        market_data: Optional[List[Dict]] = None,
        market_details: Optional[Dict] = None,
        trades: Optional[List[Dict]] = None,
        conversation_history: Optional[List[Dict]] = None,
        language: str = 'en'
    ) -> str:
        """Generate insights based on user query and Polymarket data."""
        
        # Build context from market data
        context_parts = []
        
        if market_data:
            context_parts.append(f"RELEVANT MARKETS FOUND ({len(market_data)}):")
            context_parts.append("IMPORTANT: These markets have been searched and found based on the user's query. You MUST analyze these markets and provide insights based on this data.")
            for i, market in enumerate(market_data[:10], 1):  # Limit to first 10 for context
                market_info = f"\nMarket {i}: {market.get('question', market.get('title', market.get('name', 'N/A')))}"
                if market.get('id'):
                    market_info += f" (ID: {market.get('id')})"
                
                # Add volume and liquidity if available
                volume = market.get('volumeNum') or market.get('volume')
                liquidity = market.get('liquidityNum') or market.get('liquidity')
                if volume:
                    market_info += f" | Volume: ${float(volume):,.0f}" if isinstance(volume, (int, float)) else f" | Volume: {volume}"
                if liquidity:
                    market_info += f" | Liquidity: ${float(liquidity):,.0f}" if isinstance(liquidity, (int, float)) else f" | Liquidity: {liquidity}"
                
                context_parts.append(market_info)
                
                # Extract outcomes/choices from market if available
                if 'outcomes' in market or 'tokens' in market:
                    outcomes = market.get('outcomes') or market.get('tokens')
                    if outcomes:
                        if isinstance(outcomes, list):
                            choice_list = []
                            for o in outcomes:
                                if isinstance(o, dict):
                                    choice_list.append(str(o.get('name', o.get('title', 'Unknown'))))
                                else:
                                    choice_list.append(str(o))
                            if choice_list:
                                context_parts.append(f"  Choices: {', '.join(choice_list)}")
                        elif isinstance(outcomes, dict):
                            choices = [str(k) for k in outcomes.keys()]
                            if choices:
                                context_parts.append(f"  Choices: {', '.join(choices)}")
        
        if market_details:
            formatted_details = {}
            context_parts.append(f"\n=== PRIMARY MARKET DATA (USE THIS DATA) ===")
            context_parts.append("This is the specific market that matches the user's query. You MUST analyze this market and provide insights based on this data.")
            
            # Extract key information
            question = market_details.get('question') or market_details.get('title') or market_details.get('name')
            if question:
                context_parts.append(f"Question: {question}")
            
            # Extract outcomes/choices from market_details
            outcomes_data = market_details.get('outcomes') or market_details.get('tokens') or market_details.get('conditions') or market_details.get('prices')
            if outcomes_data:
                context_parts.append(f"\nMarket Choices/Outcomes:")
                if isinstance(outcomes_data, list):
                    for i, outcome in enumerate(outcomes_data):
                        if isinstance(outcome, dict):
                            outcome_name = outcome.get('name') or outcome.get('title') or outcome.get('outcome') or f"Choice {i+1}"
                            outcome_price = outcome.get('price') or outcome.get('probability')
                            outcome_volume = outcome.get('volume')
                            
                            outcome_str = f"- {outcome_name}"
                            if outcome_price is not None:
                                outcome_str += f" | Price: {outcome_price}"
                            if outcome_volume is not None:
                                outcome_str += f" | Volume: ${outcome_volume:,.2f}" if isinstance(outcome_volume, (int, float)) else f" | Volume: {outcome_volume}"
                            context_parts.append(outcome_str)
                        elif isinstance(outcome, str):
                            context_parts.append(f"- {outcome}")
                        else:
                            context_parts.append(f"- Choice {i+1}: {outcome}")
                elif isinstance(outcomes_data, dict):
                    for key, value in outcomes_data.items():
                        if isinstance(value, dict):
                            outcome_name = value.get('name') or value.get('title') or key
                            outcome_price = value.get('price') or value.get('probability')
                            context_parts.append(f"- {outcome_name}" + (f" | Price: {outcome_price}" if outcome_price else ""))
                        else:
                            context_parts.append(f"- {key}: {value}")
            
            # Include prices if available separately
            if 'prices' in market_details and isinstance(market_details['prices'], (list, dict)):
                context_parts.append(f"\nCurrent Prices/Probabilities:")
                prices = market_details['prices']
                if isinstance(prices, list):
                    for i, price in enumerate(prices):
                        context_parts.append(f"  Choice {i+1}: {price}")
                elif isinstance(prices, dict):
                    for choice, price in prices.items():
                        context_parts.append(f"  {choice}: {price}")
            
            if not formatted_details:
                formatted_details = market_details
            context_parts.append(f"\nFull market data: {json.dumps(formatted_details, indent=2)}")
        
        if trades:
            context_parts.append(f"\nRecent trades ({len(trades)}):")
            for trade in trades[:10]:  # Limit to first 10
                context_parts.append(json.dumps(trade, indent=2))
        
        context = "\n".join(context_parts) if context_parts else "No specific market data provided."
        
        # Determine response language based on user query and language preference
        is_chinese_query = language == 'zh' or any('\u4e00' <= char <= '\u9fff' for char in user_query)
        response_language = 'Chinese (Simplified)' if is_chinese_query else 'English'
        
        system_prompt = f"""You are a professional prediction market analyst specializing in Polymarket. Provide structured, data-driven insights with intelligent predictions.

LANGUAGE REQUIREMENT: Respond in {response_language}. If the user writes in Chinese, respond in Chinese. If the user writes in English, respond in English. Always match the user's language preference.

CRITICAL RULES - READ CAREFULLY:
- **ALWAYS USE PROVIDED MARKET DATA**: If market data is provided in the "Market data context" section, you MUST analyze and use that data. NEVER say "I don't see a market" or "I can't find the market" when market data is provided. The market data has been searched and found for you - use it!
- **If market data is provided, it IS the relevant market** - analyze it directly, don't claim it doesn't exist or isn't available.
- Always use the current date and time provided in the user message to calculate accurate time differences. Do not estimate or guess the current date.
- Pay close attention to conversation history. If the user asks a follow-up question (e.g., "who do you think will win?", "based on the candidates"), they are likely referring to a market discussed in the previous conversation. Use the conversation context to understand what market or event they're asking about.
- If a market was discussed previously, maintain that context even if the user doesn't explicitly mention it again.
- MAKE INTELLIGENT PREDICTIONS: When asked "who do you think will win?" or similar questions, you MUST provide specific predictions based on:
  * The market data provided (if available)
  * Current events, news, and trends relevant to the market
  * Historical patterns and precedents
  * Market data available (volume, liquidity, timing)
  * General knowledge about likely candidates/outcomes
  * Analysis of what makes sense given the context
- Do NOT simply say "I can't see the probabilities" or "wait for more data" when market data is provided. Instead, use the provided data and your knowledge to make educated predictions.
- Be specific: Name actual candidates, outcomes, or scenarios you think are likely.
- Explain your reasoning based on current events, trends, and market dynamics.

Response Format (MUST FOLLOW):
Use this exact structure with markdown formatting. Use Chinese headers if responding in Chinese, English headers if responding in English:

**Key Metrics:** (or **关键指标:** in Chinese)
- List 3-5 key data points (volume, liquidity, probabilities, etc.) with specific numbers
- Use bullet points with bold labels: **Label:** value (or **标签:** 值 in Chinese)
- When showing time until resolution, calculate from the current date provided
- ALWAYS include specific candidate/choice probabilities if available in the market data (e.g., "Candidate A: 45%, Candidate B: 30%, Candidate C: 25%")

**Market Assessment:** (or **市场评估:** in Chinese)
- 2-3 sentences summarizing the market's current state
- Reference specific metrics from the data

**Trading Considerations:** (or **交易考虑:** in Chinese)
- Use numbered or bulleted list of key factors
- Focus on actionable insights, not generic advice
- Reference specific probabilities or patterns when available

**Recommendation:** (or **建议:** in Chinese)
- When asked "who will win?" or similar prediction questions, provide a specific prediction with reasoning
- Name actual candidates, outcomes, or scenarios you think are most likely
- Base predictions on current events, trends, historical patterns, and market dynamics
- If you cannot make a specific prediction, explain why and provide a range of likely outcomes
- Be specific about what to do or watch for

Formatting Rules:
- Use **bold** for all section headers (Key Metrics, Market Assessment, etc.)
- Use **bold** for labels within bullet points (e.g., **Volume:** $18.3M)
- Use bullet points (-) for lists
- Keep total response under 300 words
- Be concise and data-driven
- If specific candidate probabilities are available, include them in Key Metrics
- Always calculate time differences using the current date provided in the message"""

        # Build conversation context
        conversation_context = ""
        if conversation_history:
            conversation_context = "\n\nPrevious conversation:\n"
            for msg in conversation_history[-5:]:  # Last 5 messages for context
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                conversation_context += f"{role.capitalize()}: {content}\n"
        
        # Get current date and time
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        user_message = f"""Current date and time: {current_datetime}

{conversation_context}

User query: {user_query}

Market data context:
{context}

Please provide insights based on the above information."""
        
        try:
            message = await asyncio.to_thread(
                self.client.messages.create,
                model="claude-sonnet-4-5-20250929",
                max_tokens=2000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}]
            )
            
            return message.content[0].text
        except Exception as e:
            raise Exception(f"Error generating insight: {str(e)}")

