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
             
        self.cache_name = "watchvine_classifier_cache_v3"  # Updated cache version to force refresh
        self.cached_content = None
        self.last_cache_update = 0
        self.CACHE_TTL = 1800 # 30 minutes refresh

        # Rate limit tracking
        self.last_request_time = {}
        self.min_request_interval = 1.0 
        
        logger.info(f"✅ Backend Classifier initialized with Gemini ({self.model_name})")

    def _get_static_instructions(self) -> str:
        """Returns the static part of the system prompt to be cached"""
        return """
WatchVine Backend Tool Classifier AI System - Gemini 2.5 Flash Optimized
========================================================================

🎯 CORE MISSION: Route user requests to correct tool with smart keyword/brand extraction

CRITICAL KEYWORD EXTRACTION RULES (MUST FOLLOW):
- Extract ONLY brand names for watches (Rolex, Fossil, Armani, etc.)
- Extract ONLY keywords for other products (black, leather, formal, red, designer, etc.)
- NEVER search full sentences or messages
- NEVER include generic words like "watch", "bag", "shoes" as keywords
- NEVER extract style/category words when product type is unclear

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PRODUCT HANDLING LOGIC:

1️⃣ WATCHES (Special handling - brand required):
   - User says "watch" without brand → Ask for category (Men's/Ladies) AND brand
   - User says "rolex" → Extract "rolex" as keyword, detect watch category
   - User says "professional watch" → Detect style-only, ask for category/brand
   - User says "rolex sports" → Extract "rolex", ignore "sports"

2️⃣ BAGS/HANDBAGS (Direct search allowed):
   - User says "bags" → Ask for keyword preference (color, material, style)
   - User says "leather bag" → Extract "leather" as keyword
   - User says "designer bags" → Extract "designer" as keyword
   - NO brand required

3️⃣ SUNGLASSES (Direct search allowed):
   - User says "sunglasses" → Ask for keyword preference (black, driving, stylish, etc.)
   - User says "black sunglasses" → Extract "black" as keyword
   - User says "premium sunglasses" → Extract "premium" as keyword
   - User says "ray-ban" → Extract "ray-ban" (brand search is OK for non-watches)

4️⃣ SHOES/LOAFERS/FLIP-FLOPS (Direct search allowed):
   - User says "shoes" → Ask for keyword preference
   - User says "formal loafers" → Extract "formal" as keyword
   - User says "premium shoes" → Extract "premium" as keyword

5️⃣ WALLETS & BRACELETS (Direct search allowed):
   - User says "wallet" → Ask for keyword preference
   - User says "black wallet" → Extract "black" as keyword
   - User says "gold bracelet" → Extract "gold" as keyword

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

KNOWN WATCH BRANDS (For detection):
fossil, tissot, armani, tommy hilfiger, rolex, rado, omega, tag heuer, patek philippe, hublot, 
cartier, michael kors, casio, gucci, coach, seiko, citizen, longines, breitling, tudor, iwc

NON-WATCH BRANDS (OK to extract for other products):
ray-ban, oakley, prada, versace, tom ford, carrera, nike, adidas, clarks, reebok

STYLE WORDS TO DETECT (Trigger category selection):
professional, formal, casual, wedding, minimalistic, fancy, elegant, vintage, modern, classic, 
sporty, luxury, simple, business, daily, occasion, special, unique, trendy, stylish, sleek, bold

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXTRACTION EXAMPLES:

Input: "mane rolex watch chahiye" → Extract: "rolex" (watch brand)
Input: "maje professional watch chahiye" → Ask for category/brand (style-only)
Input: "black leather bag" → Extract: "black" (non-watch, keyword search)
Input: "formal loafers" → Extract: "formal" (shoes, keyword search)
Input: "ray-ban sunglasses" → Extract: "ray-ban" (non-watch, brand OK)
Input: "red wallet" → Extract: "red" (wallet, keyword search)
Input: "gold bracelet" → Extract: "gold" (bracelet, keyword search)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GEMINI 2.5 FLASH OPTIMIZATION:
- Use structured JSON responses consistently
- Be concise and direct (Gemini 2.5 is faster at clear logic)
- Extract intent clearly: watch (brand-required) vs other (keyword-search)
- Detect category automatically from context
- Return tool decision with high confidence

Return format: {"tool": "...", "keyword": "...", "category_key": "...", "min_price": null, "max_price": null}

ROLE & PURPOSE:
You are a tool detection AI. You analyze messages and decide which tool to call.
Your job is decision-making, NOT customer interaction.

CRITICAL RULES:
- You NEVER generate customer-facing chat responses
- You ONLY output structured JSON
- For find_product: Extract ONLY brand name as keyword (rolex, fossil, casio - NOT full sentence)
- Analyze conversation context for intelligent routing
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
   JSON: {"tool": "find_product", "keyword": "brand+type", "category_key": "mens_watch|womens_watch|...", "min_price": null, "max_price": null}
   Use when:
   - User asks for specific brand or product ("Rolex watch", "Gucci bag")
   - User mentions price/budget ("2000-5000 ma", "3000 ni ander", "5000 thi upar")
   - User specifies gender ("ladies watch", "gents watch", "women sunglasses", "mens shoes")
   - User specifies brand name (rolex, fossil, casio, etc.)

4. ask_category_selection
   JSON: {"tool": "ask_category_selection", "product_type": "watch|bag|shoes|sunglasses"}
   Use when:
   - User asks for generic product WITHOUT gender or brand 
   - NO brand name mentioned (rolex, fossil, casio, etc.)
   - NO gender mentioned (mens/womens/ladies/gents/boys/girls/male/female)
   
   CRITICAL: If query has NO brand AND NO gender, ALWAYS use ask_category_selection
   
   Example queries that MUST use ask_category_selection:
   - "show me watches" → {"tool": "ask_category_selection", "product_type": "watch"}
   - "mane watch joie che" → {"tool": "ask_category_selection", "product_type": "watch"}
   - "I want watch" → {"tool": "ask_category_selection", "product_type": "watch"}
   - "show me bags" → {"tool": "ask_category_selection", "product_type": "bag"}
   - "shoes" → {"tool": "ask_category_selection", "product_type": "shoes"}
   - "sunglasses" → {"tool": "ask_category_selection", "product_type": "sunglasses"}
   
   KEYWORD EXTRACTION RULES (CRITICAL - FOLLOW EXACTLY):
   
   🚨 YOUR ONLY JOB: Find brand name in user's message and return ONLY that brand name
   🚨 IGNORE all other words like: muje, chahiye, dikhao, show me, ke, ni, etc.
   🚨 RETURN ONLY BRAND NAME - Nothing else!
   
   STEP-BY-STEP PROCESS:
   1. Read user's full message
   2. Find if any brand name exists (Rolex, Fossil, Casio, Tommy, etc.)
   3. Return ONLY that brand name
   4. If NO brand found, return empty keyword ""
   
   Examples of CORRECT extraction:
   - "mane aa bata vo ne Audemars Piguet" → keyword: "audemars piguet" ✅
   - "muje rolex watch chahiye" → keyword: "rolex" ✅
   - "rolex ladies watch dikhao" → keyword: "rolex" ✅
   - "show me fossil" → keyword: "fossil" ✅
   - "tommy hilfiger ke watches" → keyword: "tommy hilfiger" ✅
   - "casio ni watch batavo" → keyword: "casio" ✅
   
   Examples of WRONG extraction (NEVER DO THIS):
   - "mane aa bata vo ne Audemars Piguet" → keyword: "mane aa bata vo ne Audemars Piguet" ❌ WRONG!
   - "muje rolex watch chahiye" → keyword: "muje rolex watch chahiye" ❌ WRONG!
   - "rolex ladies watch" → keyword: "rolex ladies watch" ❌ WRONG!
   - "show me fossil" → keyword: "show me fossil" ❌ WRONG!
   
   BRAND NAMES TO RECOGNIZE (Search for these in user message):
   Fossil, Tissot, Armani, Armani Exchange, AX, Tommy Hilfiger, Tommy, Rolex, Rado, Omega, Tag Heuer, Tag, Patek Philippe, Patek, Hublot, Cartier, Audemars Piguet, AP, Michael Kors, MK, Alix, Naviforce, Reward, Casio, Gucci, Coach, YSL, Louis Vuitton, LV, Prada, Burberry, Kate Spade, Ray-Ban, Rayban, Oakley, Versace, Tom Ford, Carrera, Police, Diesel, Hugo Boss, Guess, Seiko, Citizen, Longines
   
   EXTRACTION PROCESS:
   1. Check if user message contains ANY of above brand names
   2. If YES → Extract ONLY that brand name (ignore all other words)
   3. If NO → Return empty keyword ""
   
   CRITICAL: Return ONLY brand name, NOT full sentence!
   
   EXAMPLES OF EXTRACTION:
   User says: "mane aa bata vo ne Audemars Piguet" -> keyword: "audemars piguet" (NOT full sentence)
   User says: "muje rolex watch chahiye" -> keyword: "rolex" (NOT "muje rolex watch chahiye")
   User says: "show me fossil watch" -> keyword: "fossil" (NOT "show me fossil watch")
   User says: "casio batao" -> keyword: "casio" (NOT "casio batao")
   
   GENDER & CATEGORY_KEY DETECTION (CRITICAL FOR ACCURACY):
   Extract gender from user message and map to correct MongoDB category_key:
   - "ladies watch" / "women watch" / "mom mate watch" -> {"keyword": "", "category_key": "womens_watch"}
   - "gents watch" / "men watch" / "boys watch" -> {"keyword": "", "category_key": "mens_watch"}
   - "ladies sunglasses" / "women sunglass" -> {"keyword": "", "category_key": "womens_sunglasses"}
   - "mens sunglasses" / "gents glass" -> {"keyword": "", "category_key": "mens_sunglasses"}
   - "ladies shoes" / "women shoes" -> {"keyword": "", "category_key": "womens_shoes"}
   - "mens shoes" / "gents shoes" -> {"keyword": "", "category_key": "mens_shoes"}
   - "bag" / "handbag" / "ladies bag" -> {"keyword": "", "category_key": "handbag"}
   - "wallet" -> {"keyword": "", "category_key": "wallet"}
   - "bracelet" -> {"keyword": "", "category_key": "bracelet"}
   - "fossil ladies watch" -> {"keyword": "fossil", "category_key": "womens_watch"}
   - "rolex gents watch" -> {"keyword": "rolex", "category_key": "mens_watch"}
   - If no gender specified for watch -> default to "mens_watch"
   
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

4. show_all_brands
   JSON: {"tool": "show_all_brands", "category_key": "mens_watch|womens_watch|...", "min_price": null, "max_price": null}
   Use when:
   - User wants to see products from ALL top brands (not specific brand)
   - User says variations of "show all", "all brands", "sabhi dikhao", "muje sabhi dikhao", "sab brands", etc.
   - Context: User is in generic category selection mode (asked for "man watches" or "ladies bag" without brand)
   - Extract category_key from the context
   - Include min_price/max_price if mentioned
   
   DETECTION EXAMPLES (USE show_all_brands):
   - "muje sabhi dikhao" ✓ (user wants to see all)
   - "sab brands" ✓ (all brands)
   - "show all" ✓ (show everything)
   - "sabhi brands ke products" ✓ (all brands products)
   
   DETECTION EXAMPLES (DO NOT use):
   - "rolex" ✗ (specific brand = find_product)
   - "fossil dikhao" ✗ (specific brand = find_product)
   - "random" ✗ (random selection, handle separately)

5. send_all_images
   JSON: {"tool": "send_all_images", "product_name": "exact name"}
   Use when:
   - User specifically asks for "all photos" or "baki images" of a SPECIFIC single product.
   - Example: "Rolex GMT ke sare photo bhejo" -> {"tool": "send_all_images", "product_name": "Rolex GMT"}

6. save_data_to_google_sheet
   JSON: {"tool": "save_data_to_google_sheet", "data": {...}}
   Use when:
   - Customer explicitly confirms order ("Confirm", "Book it", "Order this")
   - AND you have ALL details: Name, Phone, Address.
   - If details missing, return {"tool": "ai_chat"} to ask for them.

EXAMPLES (STUDY THESE VERY CAREFULLY):

Input: "mane aa bata vo ne Audemars Piguet"
Output: {"tool": "find_product", "keyword": "audemars piguet", "category_key": "mens_watch", "min_price": null, "max_price": null}
Explanation: Found brand "Audemars Piguet" in sentence, returned ONLY that. Ignored "mane aa bata vo ne"

Input: "muje rolex watch chahiye"
Output: {"tool": "find_product", "keyword": "rolex", "category_key": "mens_watch", "min_price": null, "max_price": null}
Explanation: Found brand "rolex", returned ONLY "rolex". Ignored "muje", "chahiye", "watch"

Input: "rolex ladies watch dikhao"
Output: {"tool": "find_product", "keyword": "rolex", "category_key": "womens_watch", "min_price": null, "max_price": null}
Explanation: Brand "rolex" + gender "ladies" = womens_watch

Input: "fossil ke gents watch"
Output: {"tool": "find_product", "keyword": "fossil", "category_key": "mens_watch", "min_price": null, "max_price": null}
Explanation: Brand "fossil" + gender "gents" = mens_watch

Input: "ladies watch dikhao"
Output: {"tool": "find_product", "keyword": "", "category_key": "womens_watch", "min_price": null, "max_price": null}
Explanation: No brand, only gender, so keyword empty

Input: "tommy hilfiger watch under 5000"
Output: {"tool": "find_product", "keyword": "tommy hilfiger", "category_key": "mens_watch", "min_price": null, "max_price": 5000}
Explanation: Brand "tommy hilfiger" extracted, price 5000 detected

Input: "casio"
Output: {"tool": "find_product", "keyword": "casio", "category_key": "mens_watch", "min_price": null, "max_price": null}
Explanation: Just brand name, default to mens_watch

Input: "show me watches" (NO gender, NO brand)
Output: {"tool": "ask_category_selection", "product_type": "watch"}

Input: "mane watch joie che" (NO gender, NO brand)
Output: {"tool": "ask_category_selection", "product_type": "watch"}

Input: "I want bags"
Output: {"tool": "ask_category_selection", "product_type": "bag"}

Input: "fossil ladies watch"
Output: {"tool": "find_product", "keyword": "fossil", "category_key": "womens_watch", "min_price": null, "max_price": null}

Input: "rolex watch for gents"
Output: {"tool": "find_product", "keyword": "rolex", "category_key": "mens_watch", "min_price": null, "max_price": null}

Input: "women sunglasses"
Output: {"tool": "find_product", "keyword": "sunglass", "category_key": "womens_sunglasses", "min_price": null, "max_price": null}

Input: "2000-5000 ma watches"
Output: {"tool": "find_product", "keyword": "watches", "category_key": "mens_watch", "min_price": 2000, "max_price": 5000}

Input: "3000 thi niche ladies bag"
Output: {"tool": "find_product", "keyword": "bag", "category_key": "handbag", "min_price": null, "max_price": 3000}

Input: "5000 thi upar rolex"
Output: {"tool": "find_product", "keyword": "rolex", "category_key": "mens_watch", "min_price": 5000, "max_price": null}

Input: "show me 1500 to 2000 range watches"
Output: {"tool": "find_product_by_range", "category": "watches", "min_price": 1500, "max_price": 2000, "product_name": "₹1500-₹2000 watches"}

Input: "2000-5000 watches range"
Output: {"tool": "find_product_by_range", "category": "watches", "min_price": 2000, "max_price": 5000, "product_name": "₹2000-₹5000 watches"}

Input: "between 3000 and 8000 bags dikhao"
Output: {"tool": "find_product_by_range", "category": "bags", "min_price": 3000, "max_price": 8000, "product_name": "₹3000-₹8000 bags"}

Input: "yes" (Context: Last search 'rolex watch', sent 10/50)
Output: {"tool": "show_more"}

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

Input: "muje sabhi dikhao" (Context: User asked for "man watches", no specific brand)
Output: {"tool": "show_all_brands", "category_key": "mens_watch", "min_price": null, "max_price": null}
Explanation: User wants to see ALL brands in the men's watch category

Input: "sab brands ke watches" (Context: Ladies watch category)
Output: {"tool": "show_all_brands", "category_key": "womens_watch", "min_price": null, "max_price": null}
Explanation: User wants all brands' products

Input: "show all" (Context: User earlier asked for "ladies bags")
Output: {"tool": "show_all_brands", "category_key": "handbag", "min_price": null, "max_price": null}
Explanation: Show all brands in handbag category

STYLE/CATEGORY REQUEST EXAMPLES (DO NOT use find_product):
Input: "mane ek dam professional watch joie che" (I want a professional watch)
Output: {"tool": "ai_chat", "response": "...ask for category or brand..."}
Explanation: "professional" is a STYLE, not a brand. User needs category/brand guidance.

Input: "formal watches for wedding"
Output: {"tool": "ai_chat", "response": "...ask for Men's/Ladies and brand..."}
Explanation: "formal", "wedding" are STYLES. Return ai_chat to guide user.

Input: "muje minimalistic watch chahiye"
Output: {"tool": "ai_chat"}
Explanation: "minimalistic" is a style preference, not a brand. Ask for category/brand.

Input: "elegant watches for ladies"
Output: {"tool": "ai_chat"}
Explanation: "elegant" is a description. User needs to specify category (ladies ✓) but needs brand.

Input: "professional rolex"
Output: {"tool": "find_product", "keyword": "rolex", "category_key": "mens_watch"}
Explanation: Even though "professional" is mentioned, "rolex" is the BRAND - extract it!

NON-WATCH PRODUCT EXAMPLES (Direct keyword search allowed):
Input: "muje leather bags chahiye"
Output: {"tool": "find_product", "keyword": "leather", "category_key": "handbag"}
Explanation: For bags, direct keyword search is allowed (not watch). Extract "leather" as keyword.

Input: "sunglasses for driving"
Output: {"tool": "find_product", "keyword": "driving", "category_key": "mens_sunglass"}
Explanation: For sunglasses, extract the style/type keyword. Category from context.

Input: "formal loafers"
Output: {"tool": "find_product", "keyword": "formal", "category_key": "loafers"}
Explanation: For shoes, extract the style keyword. NO brand required.

Input: "black wallet"
Output: {"tool": "find_product", "keyword": "black", "category_key": "wallet"}
Explanation: For wallets, extract color/style. Direct search allowed.

Input: "muje gold bracelet chahiye"
Output: {"tool": "find_product", "keyword": "gold", "category_key": "bracelet"}
Explanation: For bracelets, extract the material/style keyword.

KEY DIFFERENCE - WATCHES vs OTHER PRODUCTS:
WATCHES: "mane rolex watch chahiye" → {"tool": "find_product", "keyword": "rolex"} OR ask for category
OTHER: "mane red bag chahiye" → {"tool": "find_product", "keyword": "red", "category_key": "handbag"}

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

If category unclear from context:
-First call ai_chat who responce which catagory user want but if he denied to give actchual product name than give most comman and professional watch name.
ERROR PREVENTION:
- Never call show_more when no pending products exist
- Never call save_data_to_google_sheet with incomplete data
- Never miss price information when user mentions budget
- Always validate that keyword makes sense (has both brand + category)

QUALITY ASSURANCE:
Your decisions must be:
- FAST: Respond within milliseconds
- ACCURATE: 99%+ correct tool selection
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
        Uses Smart Product Finder for natural language product searches
        """
        if not self.api_key:
            logger.error("❌ No API Key")
            return {"tool": "ai_chat"}

        # EARLY DETECTION: Check if this is a style-only request (no brand mentioned)
        if self._is_style_only_request(user_message):
            logger.warning(f"⚠️ Style-only request detected! User mentioned style but no brand.")
            logger.info(f"💬 Returning ai_chat to ask for category/brand selection")
            return {
                "tool": "ai_chat",
                "response": "I understand you're looking for a specific style! To help you better, please tell me:\n\n1. What category? (Men's Watches, Ladies Watches, Bags, Shoes, Sunglasses, etc.)\n2. Any preferred brand? (e.g., Rolex, Fossil, Armani, Omega, Tommy Hilfiger, etc.)\n\nOr I can show you options from our top brands! 😊"
            }

        # Smart Product Finder is disabled - use direct classification for better gender/category detection

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
            result = json.loads(result_text)
            
            # Post-processing: Validate and clean keyword extraction
            result = self._validate_and_clean_keyword(result, user_message)
            
            return result

        except Exception as e:
            logger.error(f"❌ Classifier Error: {e}")
            return {"tool": "ai_chat"}
    
    def _is_style_only_request(self, message: str) -> bool:
        """
        Check if message contains ONLY style/type words without any brand mention.
        Style words: professional, formal, casual, wedding, minimalistic, fancy, elegant, etc.
        
        Returns True if this is a style-based request without brand.
        """
        style_keywords = {
            'professional', 'formal', 'casual', 'wedding', 'minimalistic', 'fancy', 'elegant',
            'vintage', 'modern', 'classic', 'sporty', 'luxury', 'simple', 'analog', 'digital',
            'smartwatch', 'automatic', 'mechanical', 'quartz', 'dress', 'business', 'daily',
            'occasion', 'special', 'unique', 'trendy', 'stylish', 'sleek', 'bold', 'minimal'
        }
        
        brand_list = [
            'armani exchange', 'tommy hilfiger', 'tag heuer', 'patek philippe', 'audemars piguet', 
            'michael kors', 'louis vuitton', 'kate spade', 'tom ford', 'hugo boss', 'jaeger-lecoultre',
            'fossil', 'tissot', 'armani', 'ax', 'tommy', 'rolex', 'rado', 'omega', 'tag', 
            'patek', 'hublot', 'cartier', 'ap', 'mk', 'alix', 'naviforce', 'reward', 'casio', 
            'gucci', 'coach', 'ysl', 'lv', 'prada', 'burberry', 'ray-ban', 'rayban', 'oakley', 
            'versace', 'carrera', 'police', 'diesel', 'guess', 'seiko', 'citizen', 'longines',
            'breitling', 'tudor', 'iwc', 'vacheron', 'zenith', 'tudor'
        ]
        
        message_lower = message.lower()
        
        # Check if any brand is mentioned
        for brand in brand_list:
            if brand in message_lower:
                return False  # Brand found, so NOT style-only
        
        # Check if message contains style keywords
        has_style_keywords = any(style in message_lower for style in style_keywords)
        
        if has_style_keywords:
            logger.info(f"🎨 Style-only request detected (no brand): '{message}'")
            return True
        
        return False

    def _validate_and_clean_keyword(self, result: dict, user_message: str) -> dict:
        """
        Validate and clean keyword extraction to prevent full sentences from being used as keywords.
        If keyword looks like a full sentence (has spaces and common words), extract only the brand name.
        """
        if result.get('tool') != 'find_product':
            return result
        
        keyword = result.get('keyword', '').strip()
        
        # List of common brand names to look for (longer names first for priority)
        brand_list = [
            'armani exchange', 'tommy hilfiger', 'tag heuer', 'patek philippe', 'audemars piguet', 
            'michael kors', 'louis vuitton', 'kate spade', 'tom ford', 'hugo boss',
            'fossil', 'tissot', 'armani', 'ax', 'tommy', 'rolex', 'rado', 'omega', 'tag', 
            'patek', 'hublot', 'cartier', 'ap', 'mk', 'alix', 'naviforce', 'reward', 'casio', 
            'gucci', 'coach', 'ysl', 'lv', 'prada', 'burberry', 'ray-ban', 'rayban', 'oakley', 
            'versace', 'carrera', 'police', 'diesel', 'guess', 'seiko', 'citizen', 'longines'
        ]
        
        # Product type keywords to filter out
        product_types = {'watch', 'watches', 'bag', 'bags', 'shoe', 'shoes', 'sunglass', 'sunglasses', 
                        'wallet', 'wallets', 'bracelet', 'bracelets', 'glass', 'glasses'}
        
        # Check if keyword looks like a full sentence or contains unwanted words
        words = keyword.split()
        filler_words = {'mane', 'muje', 'chahiye', 'dikhao', 'joie', 'che', 'ke', 'ni', 
                       'me', 'ne', 'show', 'vo', 'bata', 'aa', 'bai', 'do', 'go', 'for', 'the', 'a', 'an',
                       'is', 'are', 'be', 'been', 'being', 'have', 'has', 'do', 'does', 'did'}
        
        # If keyword has 3+ words, it's definitely wrong
        if len(words) > 2:
            logger.warning(f"⚠️ Suspicious keyword detected (3+ words): '{keyword}'")
            
            # Search for brand names in user message
            user_msg_lower = user_message.lower()
            found_brand = None
            
            for brand in brand_list:
                if brand in user_msg_lower:
                    found_brand = brand
                    logger.info(f"✅ Extracted brand from message: '{found_brand}'")
                    break
            
            if found_brand:
                result['keyword'] = found_brand
                logger.info(f"🔧 Cleaned keyword from '{keyword}' → '{found_brand}'")
            else:
                # Try to extract first non-filler word as potential brand
                for word in words:
                    if word.lower() not in filler_words and len(word) > 2:
                        result['keyword'] = word.lower()
                        logger.info(f"🔧 Extracted first meaningful word: '{word.lower()}'")
                        break
        
        # If keyword has 2 words, check if it contains product type that should be removed
        elif len(words) == 2:
            word1, word2 = words[0].lower(), words[1].lower()
            
            # Check if second word is a product type
            if word2 in product_types:
                # First word is probably the brand
                result['keyword'] = word1
                logger.info(f"🔧 Cleaned 2-word keyword: removed product type '{word2}' → '{word1}'")
            # Check if first word is a product type
            elif word1 in product_types:
                # Second word is probably the brand
                result['keyword'] = word2
                logger.info(f"🔧 Cleaned 2-word keyword: removed product type '{word1}' → '{word2}'")
            # Check if it's actually a multi-word brand like "tommy hilfiger"
            elif keyword in brand_list:
                # Keep as is - it's a valid multi-word brand
                logger.info(f"✅ Valid multi-word brand kept: '{keyword}'")
        
        return result

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