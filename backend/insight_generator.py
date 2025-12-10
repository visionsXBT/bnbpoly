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
            context_parts.append("CRITICAL: These markets were found by searching Polymarket using the user's exact query. These ARE the relevant markets - analyze them directly. Do NOT claim they are unrelated or wrong.")
            context_parts.append("If these markets don't seem to match the query, still analyze them using the actual data provided. Do NOT make up or reference other markets that weren't provided.")
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
                # Try multiple field names that Polymarket might use
                outcomes = (market.get('outcomes') or 
                           market.get('tokens') or 
                           market.get('conditions') or
                           market.get('markets') or
                           market.get('selections') or
                           market.get('options'))
                if outcomes:
                    if isinstance(outcomes, list):
                        choice_list = []
                        for o in outcomes:
                            if isinstance(o, dict):
                                choice_name = (o.get('name') or 
                                             o.get('title') or 
                                             o.get('tokenName') or
                                             o.get('label') or
                                             o.get('outcome') or
                                             o.get('option') or
                                             'Unknown')
                                choice_list.append(str(choice_name))
                            else:
                                choice_list.append(str(o))
                        if choice_list:
                            context_parts.append(f"  Choices: {', '.join(choice_list)}")
                    elif isinstance(outcomes, dict):
                        choices = []
                        for k, v in outcomes.items():
                            if isinstance(v, dict):
                                choice_name = (v.get('name') or 
                                             v.get('title') or 
                                             v.get('tokenName') or
                                             v.get('label') or
                                             k)
                                choices.append(str(choice_name))
                            else:
                                choices.append(str(k))
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
            
            # Extract and format end date for time calculations
            end_date = (market_details.get('endDate') or 
                       market_details.get('end_date') or 
                       market_details.get('endDateIso') or
                       market_details.get('umaEndDate') or
                       market_details.get('umaEndDateIso'))
            if end_date:
                context_parts.append(f"Market End Date: {end_date}")
                context_parts.append("IMPORTANT: Use this end date with the current date provided to calculate time remaining until market resolution.")
            
            # Extract outcomes/choices from market_details
            # Try multiple field names that Polymarket might use
            outcomes_data = (market_details.get('outcomes') or 
                           market_details.get('tokens') or 
                           market_details.get('conditions') or 
                           market_details.get('prices') or
                           market_details.get('markets') or  # Sometimes outcomes are nested in markets
                           market_details.get('selections') or  # Alternative field name
                           market_details.get('options'))  # Another possible field name
            
            if outcomes_data:
                context_parts.append(f"\nMarket Choices/Outcomes:")
                if isinstance(outcomes_data, list):
                    for i, outcome in enumerate(outcomes_data):
                        if isinstance(outcome, dict):
                            outcome_name = (outcome.get('name') or 
                                          outcome.get('title') or 
                                          outcome.get('outcome') or 
                                          outcome.get('tokenName') or  # Common in Polymarket
                                          outcome.get('label') or
                                          outcome.get('option') or
                                          f"Choice {i+1}")
                            outcome_price = (outcome.get('price') or 
                                           outcome.get('probability') or
                                           outcome.get('yesPrice') or  # Polymarket uses yesPrice
                                           outcome.get('noPrice'))
                            outcome_volume = (outcome.get('volume') or
                                            outcome.get('volumeNum') or
                                            outcome.get('liquidity') or
                                            outcome.get('liquidityNum'))
                            
                            outcome_str = f"- {outcome_name}"
                            if outcome_price is not None:
                                # Format price as percentage if it's a decimal
                                if isinstance(outcome_price, (int, float)):
                                    if outcome_price <= 1:
                                        outcome_str += f" | Probability: {outcome_price*100:.1f}%"
                                    else:
                                        outcome_str += f" | Price: {outcome_price}"
                                else:
                                    outcome_str += f" | Price: {outcome_price}"
                            if outcome_volume is not None:
                                outcome_str += f" | Volume: ${float(outcome_volume):,.0f}" if isinstance(outcome_volume, (int, float)) else f" | Volume: {outcome_volume}"
                            context_parts.append(outcome_str)
                        elif isinstance(outcome, str):
                            context_parts.append(f"- {outcome}")
                        else:
                            context_parts.append(f"- Choice {i+1}: {outcome}")
                elif isinstance(outcomes_data, dict):
                    for key, value in outcomes_data.items():
                        if isinstance(value, dict):
                            outcome_name = value.get('name') or value.get('title') or value.get('tokenName') or key
                            outcome_price = (value.get('price') or 
                                           value.get('probability') or
                                           value.get('yesPrice') or
                                           value.get('noPrice'))
                            outcome_volume = (value.get('volume') or
                                            value.get('volumeNum') or
                                            value.get('liquidity') or
                                            value.get('liquidityNum'))
                            
                            outcome_str = f"- {outcome_name}"
                            if outcome_price is not None:
                                if isinstance(outcome_price, (int, float)):
                                    if outcome_price <= 1:
                                        outcome_str += f" | Probability: {outcome_price*100:.1f}%"
                                    else:
                                        outcome_str += f" | Price: {outcome_price}"
                                else:
                                    outcome_str += f" | Price: {outcome_price}"
                            if outcome_volume is not None:
                                outcome_str += f" | Volume: ${float(outcome_volume):,.0f}" if isinstance(outcome_volume, (int, float)) else f" | Volume: {outcome_volume}"
                            context_parts.append(outcome_str)
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
        
        # If no market data provided, don't mention it - just provide intelligent analysis
        context = "\n".join(context_parts) if context_parts else ""
        
        # Determine response language - prioritize query language detection
        # Always detect from the user's query first, then use language parameter as fallback
        is_chinese_query = any('\u4e00' <= char <= '\u9fff' for char in user_query)
        
        if is_chinese_query:
            # Query contains Chinese characters - respond in Chinese
            response_language = 'Chinese (Simplified)'
        elif language == 'zh':
            # No Chinese in query but language parameter is Chinese - respond in Chinese
            response_language = 'Chinese (Simplified)'
        elif language == 'en':
            # Language parameter is English - respond in English
            response_language = 'English'
        else:
            # Default to English if unclear
            response_language = 'English'
        
        system_prompt = f"""You are a professional prediction market analyst specializing in Polymarket. Provide structured, data-driven insights with intelligent predictions.

LANGUAGE REQUIREMENT: Respond in {response_language}. If the user writes in Chinese, respond in Chinese. If the user writes in English, respond in English. Always match the user's language preference.

CRITICAL RULES - READ CAREFULLY:
- **USE PROVIDED MARKET DATA WHEN AVAILABLE**: If market data is provided in the "Market data context" section, analyze it and base your insights on that actual data. The markets provided were found by searching Polymarket using the user's query.
- **NEVER mention that markets weren't found or that search failed**: Even if no market data is provided, do NOT say "no markets found" or "search didn't return results". Just provide intelligent analysis based on general knowledge.
- **If market data is provided, analyze it directly** - use the actual data for metrics, probabilities, and recommendations.
- **If NO market data is provided, provide intelligent predictions anyway**: Use your knowledge of current events, trends, historical patterns, and general market dynamics to provide thoughtful analysis. Don't mention the absence of market data - just provide the best analysis you can.
- **CRITICAL: DATE AND TIME CALCULATIONS**: The current date and time is provided in the user message. You MUST use this exact date to calculate all time differences, time windows, and time remaining. 
- **DO NOT estimate, guess, or use a different date**. If the current date is 2025-01-15 and an event is in June 2025, calculate: June 2025 - January 2025 = 5 months (not 6 months).
- **ALWAYS calculate time differences accurately**: If current date is 2025-01-15 and something ends "before 2026", calculate: 2026-01-01 - 2025-01-15 = approximately 11.5 months (not 12 months).
- **Include the actual current date in your response** when showing time windows or time remaining.
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
- **When showing time until resolution or time windows, you MUST calculate from the current date provided above. Show the calculation explicitly.**
- Example: If current date is 2025-01-15 and event is June 2025, write: "Time Window: ~5 months (June 2025 - January 2025, from current date 2025-01-15)"
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
        
        # Get current date and time (UTC)
        current_datetime = datetime.utcnow()
        current_date_str = current_datetime.strftime("%Y-%m-%d")
        current_time_str = current_datetime.strftime("%H:%M:%S UTC")
        current_datetime_str = f"{current_date_str} {current_time_str}"
        current_year = current_datetime.year
        current_month = current_datetime.month
        current_day = current_datetime.day
        
        # Build user message - only include market data context if it exists
        if context:
            user_message = f"""=== CURRENT DATE AND TIME (USE THIS FOR ALL CALCULATIONS) ===
Current Date: {current_date_str} ({current_year}-{current_month:02d}-{current_day:02d})
Current Time: {current_time_str}
Current Year: {current_year}
Current Month: {current_month} ({current_datetime.strftime('%B')})
Current Day: {current_day}

IMPORTANT: Use the EXACT current date above to calculate all time differences. Do not estimate or use a different date.

{conversation_context}

User query: {user_query}

Market data context:
{context}

Please provide insights based on the above information. When calculating time windows or time remaining, use the current date provided above."""
        else:
            # No market data - provide intelligent analysis without mentioning it
            user_message = f"""=== CURRENT DATE AND TIME (USE THIS FOR ALL CALCULATIONS) ===
Current Date: {current_date_str} ({current_year}-{current_month:02d}-{current_day:02d})
Current Time: {current_time_str}
Current Year: {current_year}
Current Month: {current_month} ({current_datetime.strftime('%B')})
Current Day: {current_day}

IMPORTANT: Use the EXACT current date above to calculate all time differences. Do not estimate or use a different date.

{conversation_context}

User query: {user_query}

Please provide intelligent analysis and predictions based on current events, trends, historical patterns, and market dynamics. Use your knowledge to make educated predictions. When calculating time windows or time remaining, use the current date provided above."""
        
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

