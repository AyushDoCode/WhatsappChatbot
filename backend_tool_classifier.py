"""
Backend Tool Classifier AI
Analyzes conversation and decides which tool to use
Returns JSON response: {tool: "ai_chat"} or {tool: "save_data_to_google_sheet", data: {...}}
Uses Google Gemini API with Context Caching
"""

import os
import json
import logging
import time
from datetime import datetime, timedelta
import google.generativeai as genai
from google.generativeai import caching

logger = logging.getLogger(__name__)

class BackendToolClassifier:
    """
    Backend AI that classifies user intent and decides which tool to call
    This AI does NOT respond to user - it only decides actions
    Uses Google Gemini API
    """
    
    def __init__(self):
        """
        Initialize Backend Tool Classifier with Gemini
        """
        self.api_key = os.getenv("Google_api")
        if not self.api_key:
            logger.warning("⚠️ Google_api not found in environment variables. Please set it.")
            
        if self.api_key:
            genai.configure(api_key=self.api_key)
            
        # Get model from env or use default
        env_model = os.getenv("google_model", "gemini-1.5-flash-001")
        # Ensure model name has 'models/' prefix if not present (Gemini API often prefers it)
        if not env_model.startswith("models/") and not env_model.startswith("gemini-"):
             self.model_name = f"models/{env_model}"
        else:
             self.model_name = env_model
             
        self.cache_name = "watchvine_classifier_cache_v1"
        self.cached_content = None
        self.last_cache_update = 0
        self.CACHE_TTL = 3600 # 1 hour refresh (cache lives longer, but we refresh ref locally)

        # Rate limit tracking
        self.last_request_time = {}
        self.min_request_interval = 1.0 
        
        logger.info(f"✅ Backend Classifier initialized with Gemini ({self.model_name})")

    def _get_static_instructions(self) -> str:
        """Returns the static part of the system prompt to be cached"""
        return """
WatchVine Backend Tool Classifier AI System
============================================

ROLE & PURPOSE:
You are an intelligent backend AI system designed to analyze customer conversations and determine the optimal tool/action to execute.
Your primary responsibility is decision-making, NOT customer interaction.

CRITICAL RULES:
- You NEVER generate customer-facing chat responses
- You ONLY output structured JSON objects indicating which tool to invoke
- You analyze conversation context, search state, and user intent to make intelligent routing decisions
- You must be highly accurate in detecting user intent to ensure smooth customer experience

SYSTEM ARCHITECTURE:
This is a multi-agent system where:
1. You (Backend Classifier) → Decides which tool to call
2. Conversation Agent → Handles actual customer chat responses  
3. Product Search API → Retrieves product information
4. Google Sheets API → Saves order data

Your decisions directly impact customer satisfaction - choose wisely!

AVAILABLE TOOLS & DECISION LOGIC:
========================================

⚠️ CRITICAL PRIORITY FOR PRICE RANGE DETECTION:
ALWAYS CHECK FOR PRICE RANGE FIRST! If user message contains "range", "between", "to", "thi" with TWO prices and a category, use find_product_by_range.
Examples:
- "2000 thi 2500 watches" → find_product_by_range (NOT find_product!)
- "between 2000 and 2500" → find_product_by_range
- "2000-2500 range watches" → find_product_by_range
- "2000 thi upar rolex" → find_product (only min price, has brand)
- "3000 ni ander" → find_product (only max price, no explicit range)

TOOLS & OUTPUT RULES:

1. ai_chat
   JSON: {"tool": "ai_chat"}
   Use when:
   - User is greeting (Hi, Hello)
   - User asks general questions ("shop open?", "delivery time?")
   - User asks for categories without specific brand ("show watches", "bags dikhao")
   - User is just chatting
   - Search result pagination is complete ("All products shown")
   - User says "yes/no/okay" but there's NO pending search context

2. show_more
   JSON: {"tool": "show_more"}
   Use when:
   - User wants to see more products from CURRENT search
   - User says: "yes", "okay", "ha", "show more", "more", "next", "aur dikhao", "હા"
   - ONLY if SEARCH INFO shows pending products (sent_count < total_found)
   - This is for continuing the SAME search, NOT starting a new one
   
3. find_product
   JSON: {"tool": "find_product", "keyword": "brand+type", "min_price": null, "max_price": null}
   Use when:
   - User asks for specific brand or product ("Rolex watch", "Gucci bag")
   - User mentions price/budget ("2000-5000 ma", "3000 ni ander", "5000 thi upar")
   
   KEYWORD RULES:
   - ALWAYS include the category type.
   - "Rolex" -> "rolex watch"
   - "Gucci" -> "gucci bag" (or context appropriate)
   - If user says "koi bhi" (any): Pick a popular brand + category (e.g., "gucci bag")
   
   PRICE DETECTION (SMART):
   Extract price from user message:
   - "2000-5000 ma watches" -> {"keyword": "watches", "min_price": 2000, "max_price": 5000}
   - "3000 ni ander bag" -> {"keyword": "bag", "max_price": 3000}
   - "5000 thi upar rolex" -> {"keyword": "rolex watch", "min_price": 5000}
   - "under 4000" -> {"max_price": 4000}
   - "above 10000" -> {"min_price": 10000}
   - No price mentioned -> {"min_price": null, "max_price": null}

3. find_product_by_range (PRIORITY #1 FOR PRICE RANGES!)
   JSON: {"tool": "find_product_by_range", "category": "watches", "min_price": 2000, "max_price": 2500, "product_name": "₹2000-₹2500 watches"}
   
   USE THIS WHEN:
   ✓ User message has TWO prices (min AND max) + category
   ✓ Contains keywords: "range", "between", "to", "thi" with prices
   ✓ Pattern: NUMBER + KEYWORD + NUMBER + CATEGORY
   
   DETECTION EXAMPLES (USE find_product_by_range):
   - "2000 thi 2500 watches" ✓
   - "between 2000 and 2500 watches" ✓
   - "2000-2500 range watches" ✓
   - "show me 2000 to 2500 watches" ✓
   - "su tamari jode 2000 thi 2500 ni range ma watches" ✓
   
   DETECTION EXAMPLES (DO NOT use - use find_product instead):
   - "2000 thi upar rolex" ✗ (only min + brand)
   - "3000 ni ander bags" ✗ (only max, no range)
   - "rolex 2000-2500" ✗ (brand + range = find_product)
   
   EXTRACTION RULES:
   - Extract first number as min_price
   - Extract second number as max_price
   - Extract category from end of message (watches, bags, shoes, sunglasses, etc.)
   - Format product_name as "₹{min}-₹{max} {category}"

4. send_all_images
   JSON: {"tool": "send_all_images", "product_name": "exact name"}
   Use when:
   - User specifically asks for "all photos" or "baki images" of a SPECIFIC single product.
   - Example: "Rolex GMT ke sare photo bhejo" -> {"tool": "send_all_images", "product_name": "Rolex GMT"}

5. save_data_to_google_sheet
   JSON: {"tool": "save_data_to_google_sheet", "data": {...}}
   Use when:
   - Customer explicitly confirms order ("Confirm", "Book it", "Order this")
   - AND you have ALL details: Name, Phone, Address.
   - If details missing, return {"tool": "ai_chat"} to ask for them.

EXAMPLES:
Input: "rolex watch"
Output: {"tool": "find_product", "keyword": "rolex watch", "min_price": null, "max_price": null}

Input: "2000-5000 ma watches"
Output: {"tool": "find_product", "keyword": "watches", "min_price": 2000, "max_price": 5000}

Input: "3000 thi niche bag"
Output: {"tool": "find_product", "keyword": "bag", "min_price": null, "max_price": 3000}

Input: "5000 thi upar rolex"
Output: {"tool": "find_product", "keyword": "rolex watch", "min_price": 5000, "max_price": null}

Input: "show me 1500 to 2000 range watches"
Output: {"tool": "find_product_by_range", "category": "watches", "min_price": 1500, "max_price": 2000, "product_name": "₹1500-₹2000 watches"}

Input: "2000-5000 watches range"
Output: {"tool": "find_product_by_range", "category": "watches", "min_price": 2000, "max_price": 5000, "product_name": "₹2000-₹5000 watches"}

Input: "between 3000 and 8000 bags dikhao"
Output: {"tool": "find_product_by_range", "category": "bags", "min_price": 3000, "max_price": 8000, "product_name": "₹3000-₹8000 bags"}

Input: "yes" (Context: Last search 'rolex watch', sent 10/50)
Output: {"tool": "show_more"}

Input: "wholesale karte ho? 100 watches chahiye"
Output: {"tool": "ai_chat"} + Response: "Sorry, amari pase wholesale nahi chalti. Single piece or small quantity per person ke liye hi available che. 😊"

Input: "warranty kevi che?"
Output: {"tool": "ai_chat"} + Response: "Amari pase imported watches par koi warranty nathi. Agar koi issue aave to amari service center par repair thase. Repair charges customer ke na ho."

Input: "ye watches original che ya duplicate?"
Output: {"tool": "ai_chat"} + Response: "Haa, amari watches imported che! Original quality guaranteed. 💎"

Input: "50 pieces bulk order possible?"
Output: {"tool": "ai_chat"} + Response: "Sorry, amari pase wholesale nahi chalti. Single piece or small quantity per person ke liye hi available che. 😊"

Input: "show more" (Context: Last search 'rolex watch', sent 10/50)
Output: {"tool": "show_more"}

Input: "okay" (Context: Last search 'gucci bag', sent 140/150)
Output: {"tool": "show_more"}

Input: "ha" (Context: Last search 'fossil watch', sent 5/45)
Output: {"tool": "show_more"}

Input: "more" (Context: Last search 'rolex watch', sent 150/150)
Output: {"tool": "ai_chat"}

Input: "yes" (Context: No pending products)
Output: {"tool": "ai_chat"}

Input: "watches chahiye"
Output: {"tool": "ai_chat"}

Input: "Rolex GMT ni badhi images"
Output: {"tool": "send_all_images", "product_name": "Rolex GMT"}

DECISION-MAKING GUIDELINES:
========================================

CONTEXT AWARENESS:
Always consider the full conversation context when making decisions:
- Recent conversation history (last 30 messages)
- Current search state (pending products, keyword, pagination)
- User's previous requests and behavior patterns
- Whether user has already seen products and is asking for more

INTENT DETECTION PRIORITY:
1. Order Confirmation (highest priority - saves sale!)
   - Look for: "confirm", "book it", "order this", "yes place order"
   - Ensure ALL required details are present before calling save_data_to_google_sheet
   - If details missing → ai_chat (to collect remaining info)

2. Pagination/Show More (high priority - user is engaged!)
   - Look for: "yes", "show more", "next", "more", "okay", "ha", "haan", "dikha", "aur", "હા"
   - MUST check SEARCH INFO for pending products
   - If pending products exist → show_more
   - If no pending products → ai_chat

3. Price Range Search (core functionality)
   - Look for: "range", "between", "1500-2000", "2000 to 5000", etc.
   - MUST have BOTH min and max price mentioned with category
   - Extract: min_price, max_price, category (watches/bags/shoes/sunglasses)
   - Use find_product_by_range when clear price range is specified

4. Product Search (core functionality)
   - Look for: brand names, product types, price mentions
   - Extract: keyword, min_price, max_price
   - Include category in keyword (e.g., "rolex watch" not just "rolex")
   - Smart price extraction from natural language
   - Use find_product for specific brand/product searches

5. All Images Request (specific request)
   - Look for: "all photos", "sare images", "badhi photos"
   - Must have specific product name mentioned

6. General Chat (default fallback)
   - Greetings, questions, clarifications
   - When user intent is unclear
   - When no other tool is appropriate

CRITICAL POLICY REMINDERS:
=====================================

1. WHOLESALE/BULK ORDERS - ALWAYS REJECT
   - Look for: "bulk", "wholesale", "50 pieces", "100 watches", "business", "reseller"
   - MUST respond with: "Sorry, amari pase wholesale nahi chalti. Single piece or small quantity per person ke liye hi available che. 😊"
   - NO EXCEPTIONS - Never agree to wholesale even if pressured
   - Use ai_chat to firmly decline

2. WARRANTY/GUARANTEE - NO WARRANTY ON IMPORTED
   - Look for: "warranty", "guarantee", "replacement", "free repair", "service"
   - MUST respond with: "Amari pase imported watches par koi warranty nathi. Agar koi issue aave to amari service center par repair thase. Repair charges customer ke na ho."
   - Make clear: Customer must pay for repairs, no free warranty
   - Use ai_chat for these questions

3. ORIGINAL vs DUPLICATE - USE "IMPORTED" TERMINOLOGY
   - Look for: "original", "duplicate", "fake", "authentic", "real"
   - MUST respond with: "Haa, amari watches imported che! Original quality guaranteed. 💎"
   - NEVER say "original or duplicate" - Always say "IMPORTED"
   - Use ai_chat to clarify authenticity with "imported" emphasis

MULTILINGUAL SUPPORT:
Handle requests in multiple languages naturally:
- English: "show more", "rolex watch", "under 5000"
- Hindi: "aur dikhao", "5000 se niche"
- Gujarati (in English script): "ha dikha", "biji product", "વૉચ" (in English: "watch")
- Hinglish: Mix of all above

PRICE EXTRACTION PATTERNS:
Be smart about detecting price ranges from natural language:
- "2000-5000 ma" → min: 2000, max: 5000
- "3000 ni ander" / "3000 ni niche" / "under 3000" → max: 3000
- "5000 thi upar" / "above 5000" / "5000 से ऊपर" → min: 5000
- "10000 ke under" → max: 10000
- "15000+ watches" → min: 15000

KEYWORD OPTIMIZATION:
Always include product category with brand for accurate search:
- "Rolex" → "rolex watch" (not just "rolex")
- "Gucci" → "gucci bag" (context-dependent: could be bag, wallet, sunglasses)
- "Ray-Ban" → "ray-ban sunglasses"
- "Nike" → "nike shoes"

If category unclear from context, pick most common:
- Rolex, Fossil, Tommy → watches
- Gucci, Coach, Michael Kors → bags (most common)
- Ray-Ban, Oakley → sunglasses

ERROR PREVENTION:
- Never call show_more when no pending products exist
- Never call save_data_to_google_sheet with incomplete data
- Never miss price information when user mentions budget
- Always validate that keyword makes sense (has both brand + category)

QUALITY ASSURANCE:
Your decisions must be:
- FAST: Respond within milliseconds
- ACCURATE: 95%+ correct tool selection
- CONTEXTUAL: Consider full conversation flow
- CONSISTENT: Same input patterns → same outputs

OUTPUT FORMAT:
Always return VALID JSON only. No explanations, no markdown, no extra text.
Just pure JSON: {"tool": "tool_name", "additional_params": "values"}

Return ONLY JSON.
"""

    def _get_or_create_cache(self):
        """Creates or retrieves cached content for system instructions"""
        if not self.api_key:
            return None
            
        current_time = time.time()
        
        # specific name for the cache
        cache_name = self.cache_name
        
        # If we have a valid local reference, return it
        if self.cached_content and (current_time - self.last_cache_update < self.CACHE_TTL):
            return self.cached_content

        try:
            # Check if cache exists (by iterating or specific name if API supported retrieval by name easily)
            # For simplicity in this implementation, we'll try to create it. 
            # If it exists, we might get an error or a new one. 
            # Ideally we list and find.
            
            # Listing caches to find ours
            existing_cache = None
            for c in caching.CachedContent.list():
                if c.display_name == cache_name:
                    existing_cache = c
                    break
            
            if existing_cache:
                # Update expiration? Or just use it.
                # existing_cache.update(ttl=timedelta(hours=2))
                logger.info(f"♻️ Using existing cache: {existing_cache.name}")
                self.cached_content = existing_cache
            else:
                # Create new cache
                system_instruction = self._get_static_instructions()
                
                # Estimate token count (rough: ~4 chars per token)
                estimated_tokens = len(system_instruction) / 4
                
                # Only use cache if content is large enough (>1024 tokens required)
                if estimated_tokens < 1000:
                    logger.info(f"⚠️ Content too small for caching (~{int(estimated_tokens)} tokens, need 1024+)")
                    logger.info("✅ Using standard request (no cache)")
                    self.cached_content = None
                else:
                    logger.info(f"🆕 Creating new context cache (~{int(estimated_tokens)} tokens)...")
                    self.cached_content = caching.CachedContent.create(
                        model=self.model_name,
                        display_name=cache_name,
                        system_instruction=system_instruction,
                        ttl=timedelta(hours=2) # Cache for 2 hours
                    )
                    logger.info(f"✅ Cache created: {self.cached_content.name}")
            
            self.last_cache_update = current_time
            return self.cached_content
            
        except Exception as e:
            logger.error(f"❌ Cache operation failed: {e}")
            return None

    def analyze_and_classify(self, conversation_history: list, user_message: str, phone_number: str, search_context: dict = None) -> dict:
        """
        Analyze conversation and return tool decision in JSON format
        """
        if not self.api_key:
            logger.error("❌ No API Key")
            return {"tool": "ai_chat"}

        # Rate limiting
        if phone_number in self.last_request_time:
            time_since_last = time.time() - self.last_request_time[phone_number]
            if time_since_last < self.min_request_interval:
                time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time[phone_number] = time.time()

        # Build dynamic context
        context_str = self._build_context_string(conversation_history, user_message, search_context)
        
        try:
            # Try to use cache
            cached_content = self._get_or_create_cache()
            
            if cached_content:
                # Use model with cache
                model = genai.GenerativeModel.from_cached_content(cached_content=cached_content)
                response = model.generate_content(
                    context_str,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
            else:
                # Fallback to non-cached standard request
                logger.warning("⚠️ Cache unavailable, using standard request")
                model = genai.GenerativeModel(self.model_name)
                full_prompt = self._get_static_instructions() + "\n\n" + context_str
                response = model.generate_content(
                    full_prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
            
            # Parse result
            result_text = response.text.strip()
            # Clean up markdown code blocks if present
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
                
            logger.info(f"🔍 Classifier Decision: {result_text}")
            return json.loads(result_text)

        except Exception as e:
            logger.error(f"❌ Classifier Error: {e}")
            return {"tool": "ai_chat"}

    def _build_context_string(self, history: list, current_message: str, search_context: dict) -> str:
        """Builds the dynamic string for the request"""
        # Format history - increased to 30 messages for better context
        hist_str = ""
        for msg in history[-30:]:
            role = msg.get('role', 'user')
            content = msg.get('content', '')
            hist_str += f"{role.upper()}: {content}\n"
            
        # Format search info
        search_info = ""
        if search_context:
            keyword = search_context.get('keyword', '')
            sent_count = search_context.get('sent_count', 0)
            total_found = search_context.get('total_found', 0)
            
            if keyword and total_found > 0:
                remaining = total_found - sent_count
                if remaining > 0:
                    search_info = f"\n[SEARCH INFO - PENDING PRODUCTS]\nLast Search: '{keyword}'\nProducts Sent: {sent_count}/{total_found}\nRemaining: {remaining} products\nSTATUS: User has PENDING products from '{keyword}' search\n"
                else:
                    search_info = f"\n[SEARCH INFO - COMPLETE]\nLast Search: '{keyword}'\nAll {total_found} products already shown\nSTATUS: No pending products\n"

        return f"""
CONVERSATION HISTORY:
{hist_str}

{search_info}

CURRENT MESSAGE:
{current_message}
"""

    def extract_order_data_from_history(self, conversation_history: list, phone_number: str) -> dict:
        """
        Extract order data from conversation history
        Simple regex extraction as fallback or helper
        """
        order_data = {
            "customer_name": "",
            "phone_number": phone_number,
            "email": "",
            "address": "",
            "product_name": "",
            "product_url": "",
            "quantity": 1
        }
        
        # Simple extraction logic (similar to previous)
        for msg in conversation_history:
            content = msg.get('content', '').lower()
            if 'http' in content:
                 import re
                 url = re.search(r'https?://[^\s]+', content)
                 if url: order_data['product_url'] = url.group()
                 
        return order_data