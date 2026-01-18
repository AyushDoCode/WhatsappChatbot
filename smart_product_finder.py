"""
Smart Product Finder - AI-powered natural language product search
Understands: Product names, Company names, Price ranges, Combinations
Uses Gemini AI to intelligently parse user queries
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple
import google.generativeai as genai

logger = logging.getLogger(__name__)

# Initialize Gemini - will be configured in __init__
# This allows the module to be imported even without API key set

class SmartProductFinder:
    """
    AI-powered product finder that understands:
    - Product names: "rolex", "omega", "omega watch"
    - Company names: "Gucci bag", "Michael Kors"
    - Price ranges: "under 2k", "between 2k to 5k", "5000-10000"
    - Combinations: "rolex watch under 5k", "gucci bag between 3k and 8k"
    """
    
    def __init__(self):
        # Configure API key on initialization
        api_key = os.getenv('GEMINI_API_KEY') or os.getenv('Google_api') or os.getenv('GOOGLE_API_KEY')
        if api_key:
            genai.configure(api_key=api_key)
        else:
            logger.warning("⚠️ No Gemini API key found. Smart product finder will not work.")
        
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        self.cache = {}
        
    def extract_search_parameters(self, user_message: str) -> Dict:
        """
        Use AI to intelligently extract search parameters from natural language
        
        Returns:
        {
            "search_type": "product_name" | "company_name" | "price_range" | "compound",
            "product_name": str or None,
            "company_name": str or None,
            "category": "watches" | "bags" | "shoes" | "sunglasses" | None,
            "min_price": int or None,
            "max_price": int or None,
            "confidence": float (0-1),
            "explanation": str
        }
        """
        
        prompt = f"""You are a smart product search AI for WatchVine - a luxury watch and accessories store.

Analyze this customer message and extract search parameters:
"{user_message}"

Return JSON with:
1. search_type: "product_name" | "company_name" | "price_range" | "compound" | "none"
2. product_name: extracted product name (e.g., "Rolex", "Gucci bag") or null
3. company_name: extracted company/brand name (e.g., "Rolex", "Gucci") or null
4. category: detected category ("watches", "bags", "shoes", "sunglasses", "accessories") or null
5. gender: detected target gender ("mens" | "womens" | "unisex" | null)
6. category_key: MongoDB category_key field for filtering (see rules below)
7. min_price: minimum price if mentioned (extract numbers) or null
8. max_price: maximum price if mentioned or null
9. confidence: how confident you are (0.0 to 1.0)
10. explanation: why you classified it this way

IMPORTANT PRICE EXTRACTION RULES:
- "under 2k" → max_price: 2000
- "below 5000" → max_price: 5000
- "above 10k" → min_price: 10000
- "between 2k to 5k" → min_price: 2000, max_price: 5000
- "2000-5000" → min_price: 2000, max_price: 5000
- "2000 thi 5000" → min_price: 2000, max_price: 5000
- "3000 ni niche" → max_price: 3000

CATEGORY DETECTION:
- If mention watch/time/ghadi → "watches"
- If mention bag/purse/jode → "bags"
- If mention shoe/footwear/juta → "shoes"
- If mention sunglass/shades → "sunglasses"
- If mention ring/bracelet/chain → "accessories"

GENDER DETECTION (CRITICAL FOR ACCURACY):
- "mens" if: men, gents, boys, male, men's, gent, mardo, purush, પુરુષ
- "womens" if: women, ladies, girls, female, women's, lady, ladies', महिला, સ્ત્રી, bahen, ladki
- "unisex" if: unisex, everyone, anyone
- null if not specified

CATEGORY_KEY MAPPING (MongoDB field for precise filtering):
Based on gender + category, determine the exact MongoDB category_key:

WATCHES:
- mens + watches → "mens_watch"
- womens + watches → "womens_watch"
- watches (no gender) → "mens_watch" (default)

SUNGLASSES:
- mens + sunglasses → "mens_sunglasses"
- womens + sunglasses → "womens_sunglasses"
- sunglasses (no gender) → "mens_sunglasses" (default)

SHOES:
- mens + shoes → "mens_shoes"
- womens + shoes → "womens_shoes"
- shoes (no gender) → "mens_shoes" (default)
- loafers → "loafers"
- flipflops → "flipflops"

BAGS & ACCESSORIES:
- bags → "handbag"
- wallet → "wallet"
- bracelet → "bracelet"

EXAMPLES - These show the expected output format:

Query: "show me ladies watch"
Expected: search_type=product_name, gender=womens, category_key=womens_watch

Query: "rolex watch for gents" 
Expected: company_name=rolex, gender=mens, category_key=mens_watch

Query: "fossil ladies watch under 5000"
Expected: company_name=fossil, gender=womens, category_key=womens_watch, max_price=5000

Query: "gucci bag for women"
Expected: company_name=gucci, category=bags, category_key=handbag

Query: "mens sunglasses"
Expected: gender=mens, category=sunglasses, category_key=mens_sunglasses

Return ONLY valid JSON with the structure specified above, no extra text."""

        try:
            response = self.model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Clean JSON if wrapped in markdown code blocks
            if result_text.startswith('```json'):
                result_text = result_text[7:]
            if result_text.startswith('```'):
                result_text = result_text[3:]
            if result_text.endswith('```'):
                result_text = result_text[:-3]
            
            result = json.loads(result_text.strip())
            logger.info(f"🧠 AI Extraction Result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"❌ AI extraction error: {e}")
            return {
                "search_type": "none",
                "product_name": None,
                "company_name": None,
                "category": None,
                "min_price": None,
                "max_price": None,
                "confidence": 0.0,
                "explanation": f"Error: {str(e)}"
            }
    
    def build_search_query(self, params: Dict) -> Dict:
        """
        Convert extracted parameters into a backend search query
        
        Returns query for text_search_api or find_product_by_range with category_key filtering
        """
        search_type = params.get('search_type', 'none')
        
        if search_type == 'none':
            return {
                "tool": "ai_chat",
                "message": "I couldn't understand what you're looking for. Could you please describe the product? (e.g., 'rolex watch', 'gucci bag under 5000')"
            }
        
        # Extract common parameters
        company_name = (params.get('company_name') or '').lower().strip()
        product_name = (params.get('product_name') or '').lower().strip()
        category = (params.get('category') or 'watches').lower().strip()
        gender = params.get('gender')  # mens, womens, unisex, or None
        category_key = params.get('category_key')  # MongoDB category_key field
        min_price = params.get('min_price')
        max_price = params.get('max_price')
        
        # Type 1: Pure product/company name search
        if search_type == 'product_name' or search_type == 'company_name':
            keyword = product_name or company_name
            
            # Smart keyword construction
            if company_name:
                # If we have brand + category_key, search brand only and filter by category_key
                keyword = company_name
            else:
                # Generic search like "ladies watch" or "show me women watches"
                # When no brand specified, use category as keyword and filter by category_key
                if category:
                    # Map category to search keyword
                    if category == 'watches':
                        keyword = 'watch'
                    elif category == 'sunglasses':
                        keyword = 'sunglass'
                    elif category == 'bags':
                        keyword = 'bag'
                    elif category == 'shoes':
                        keyword = 'shoe'
                    else:
                        keyword = category
                else:
                    # No category detected, default to 'watch'
                    keyword = 'watch'
            
            return {
                "tool": "find_product",
                "keyword": keyword,
                "category_key": category_key,  # Pass category_key for MongoDB filtering
                "min_price": min_price,
                "max_price": max_price
            }
        
        # Type 2: Price range search (both min and max specified)
        elif search_type == 'price_range':
            if min_price and max_price:
                return {
                    "tool": "find_product_by_range",
                    "category": category,
                    "category_key": category_key,  # Pass category_key for filtering
                    "min_price": min_price,
                    "max_price": max_price,
                    "product_name": f"₹{min_price}-₹{max_price} {category}"
                }
            # If only one price, use find_product instead
            elif min_price or max_price:
                return {
                    "tool": "find_product",
                    "keyword": category,
                    "category_key": category_key,
                    "min_price": min_price,
                    "max_price": max_price
                }
        
        # Type 3: Compound query (name + price)
        elif search_type == 'compound':
            keyword = company_name or product_name
            
            # If we have brand, search by brand only with category_key filter
            if company_name:
                keyword = company_name
            
            # If price range is clear, use find_product_by_range
            if min_price and max_price:
                return {
                    "tool": "find_product_by_range",
                    "keyword": keyword if company_name else None,
                    "category": category,
                    "category_key": category_key,
                    "min_price": min_price,
                    "max_price": max_price,
                    "product_name": f"{keyword} ₹{min_price}-₹{max_price}" if keyword else f"₹{min_price}-₹{max_price} {category}"
                }
            else:
                return {
                    "tool": "find_product",
                    "keyword": keyword,
                    "category_key": category_key,
                    "min_price": min_price,
                    "max_price": max_price
                }
        
        return {
            "tool": "ai_chat",
            "message": "Sorry, I couldn't process your request. Please try again."
        }
    
    def process_query(self, user_message: str) -> Dict:
        """
        Complete pipeline: Extract → Build Query
        
        Returns final search query for the backend
        """
        logger.info(f"🔍 Processing query: {user_message}")
        
        # Step 1: Extract parameters using AI
        params = self.extract_search_parameters(user_message)
        
        # Step 2: Build search query
        query = self.build_search_query(params)
        
        logger.info(f"📋 Final Query: {query}")
        return query


# Global instance
finder = SmartProductFinder()


def get_smart_search_query(user_message: str) -> Dict:
    """
    Public function to get smart search query from user message
    
    Usage:
    query = get_smart_search_query("rolex watch under 5k")
    # Returns: {"tool": "find_product_by_range", "keyword": "rolex", ...}
    """
    return finder.process_query(user_message)


if __name__ == "__main__":
    # Test examples
    test_queries = [
        "rolex watch",
        "gucci bag",
        "watches under 2k",
        "between 2000 and 5000 watches",
        "rolex watch under 5000",
        "gucci bag between 3k and 8k",
        "fossil ke smartwatch",
        "michael kors bag 2000-3000",
        "show me shoes above 10000",
        "casual watches under 1500",
    ]
    
    print("🧪 Testing Smart Product Finder\n")
    for query in test_queries:
        print(f"User: {query}")
        result = finder.process_query(query)
        print(f"Result: {json.dumps(result, indent=2)}")
        print("-" * 80)
