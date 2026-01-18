"""
Enhanced Backend Tool Classifier AI with MongoDB Vector Search
Analyzes conversation and uses Gemini text embeddings for product search
"""

import os
import json
import logging
import time
from datetime import datetime, timedelta
import google.generativeai as genai
from google.generativeai import caching
from gemini_vector_search import GeminiVectorSearch

logger = logging.getLogger(__name__)

class EnhancedBackendToolClassifier:
    """
    Enhanced Backend AI that classifies user intent and performs vector search
    Uses MongoDB vector search with Gemini text embeddings
    """
    
    def __init__(self):
        """Initialize Enhanced Backend Tool Classifier with Vector Search"""
        self.api_key = os.getenv("Google_api")
        self.mongodb_uri = os.getenv("MONGODB_URI", "mongodb://admin:strongpassword123@72.62.76.36:27017/?authSource=admin")
        
        if not self.api_key:
            logger.warning("⚠️ Google_api not found in environment variables. Please set it.")
            
        if self.api_key:
            genai.configure(api_key=self.api_key)
            
        # Initialize vector search
        try:
            self.vector_search = GeminiVectorSearch(self.mongodb_uri, self.api_key)
            logger.info("✅ Vector search initialized")
        except Exception as e:
            logger.error(f"❌ Vector search initialization failed: {e}")
            self.vector_search = None
            
        # Get model from env or use default
        env_model = os.getenv("google_model", "gemini-1.5-flash-001")
        if not env_model.startswith("models/") and not env_model.startswith("gemini-"):
            self.model_name = f"models/{env_model}"
        else:
            self.model_name = env_model
        
        self.cache_name = "enhanced_classifier_cache_v1"
        self.cached_content = None
        self.last_cache_update = 0
        self.CACHE_TTL = 1800  # 30 minutes refresh
        
        # Rate limit tracking
        self.last_request_time = {}
        self.min_request_interval = 1.0
        
        logger.info(f"✅ Enhanced Backend Classifier initialized with Vector Search ({self.model_name})")

    def enhance_user_query(self, query: str) -> str:
        """Enhanced query processing with Hinglish support for better vector search"""
        try:
            prompt = f"""
            Convert and enhance this user query for watch product search. Handle Hinglish (Hindi + English mix) and informal language.
            
            User query: "{query}"
            
            Instructions:
            1. Convert Hinglish/Hindi words to English:
               - mane/muje = I want
               - joi e/chahiye = want/need  
               - ma = in
               - dikhao/batao = show
               - koi = any/some
               - etc.
            2. Convert informal language to proper English
            3. Add relevant watch search terms based on context
            4. Identify colors, brands, styles, materials mentioned
            5. Keep the original intent but make it search-friendly
            6. Return only the enhanced English query, nothing else
            
            Examples:
            "mane rolex watch black ma joi e" -> "I want black Rolex watch"
            "koi luxury watch show karo" -> "show luxury watches"
            "silver ma koi sports watch" -> "silver sports watch"
            "tommy hilfiger ke gents watch dikhao" -> "show Tommy Hilfiger men's watches"
            
            Enhanced query:
            """
            
            if not self.api_key:
                return query
                
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            enhanced = response.text.strip()
            
            # Clean up the response
            enhanced = enhanced.replace('"', '').replace("Enhanced query:", "").strip()
            
            logger.info(f"Query enhanced: '{query}' -> '{enhanced}'")
            return enhanced
            
        except Exception as e:
            logger.error(f"Error enhancing query: {e}")
            return query

    def classify_and_search(self, user_message: str, conversation_history: list = None, search_context: dict = None) -> dict:
        """
        Main method that classifies user intent and performs search if needed
        Returns enhanced response with vector search results
        """
        # First classify the user intent
        classification = self._classify_user_intent(user_message, conversation_history, search_context)
        
        # If it's product search, enhance and perform vector search
        if classification.get('tool') == 'product_search':
            # Enhance the user query
            enhanced_query = self.enhance_user_query(user_message)
            
            # Perform vector search
            search_results = []
            if self.vector_search:
                try:
                    # Extract any filters from classification
                    filters = self._extract_search_filters(user_message)
                    
                    if filters:
                        # Use hybrid search with filters
                        search_results = self.vector_search.hybrid_search(
                            enhanced_query, 
                            filters=filters, 
                            limit=5
                        )
                    else:
                        # Use simple vector search
                        search_results = self.vector_search.vector_search(
                            enhanced_query, 
                            limit=5
                        )
                    
                    logger.info(f"Vector search found {len(search_results)} results for '{enhanced_query}'")
                    
                except Exception as e:
                    logger.error(f"Vector search error: {e}")
            
            # Format the response with images, prices, and URLs
            response = self._format_product_response(search_results, enhanced_query)
            
            return {
                "tool": "product_search",
                "action": "vector_search_complete",
                "enhanced_query": enhanced_query,
                "original_query": user_message,
                "search_results": search_results,
                "formatted_response": response
            }
        
        # For non-product searches, return original classification
        return classification

    def _classify_user_intent(self, user_message: str, conversation_history: list = None, search_context: dict = None) -> dict:
        """Classify user intent (product search vs general chat)"""
        try:
            prompt = f"""
            Classify this user message as either "product_search" or "general_chat".
            
            User message: "{user_message}"
            
            Rules:
            1. "product_search" if user is asking for watches or products (colors, brands, prices, styles)
            2. "general_chat" if user is greeting, asking questions, or general conversation
            
            Watch-related terms: watch, rolex, luxury, black, gold, silver, sports, formal, etc.
            General chat terms: hi, hello, how are you, thank you, shop timing, delivery, etc.
            
            Return JSON: {{"tool": "product_search"}} or {{"tool": "general_chat"}}
            """
            
            if not self.api_key:
                return {"tool": "general_chat"}
                
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Clean up response
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            
            result = json.loads(result_text)
            return result
            
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return {"tool": "general_chat"}

    def _extract_search_filters(self, user_message: str) -> dict:
        """Extract search filters from user message for hybrid search"""
        filters = {}
        message_lower = user_message.lower()
        
        # Extract colors
        color_patterns = {
            'black': ['black', 'dark'],
            'silver': ['silver', 'steel', 'stainless'],
            'gold': ['gold', 'golden'],
            'blue': ['blue', 'navy'],
            'white': ['white', 'light'],
            'red': ['red', 'burgundy'],
            'brown': ['brown', 'tan'],
            'green': ['green', 'olive']
        }
        
        detected_colors = []
        for color, patterns in color_patterns.items():
            if any(pattern in message_lower for pattern in patterns):
                detected_colors.append(color.title())
        
        if detected_colors:
            filters['colors'] = detected_colors
        
        # Extract brands
        brands = ['rolex', 'omega', 'fossil', 'armani', 'tommy hilfiger', 'casio', 'seiko', 'citizen']
        for brand in brands:
            if brand in message_lower:
                filters['brand'] = brand.title()
                break
        
        # Extract price ranges
        import re
        price_patterns = [
            r'under (\d+)',
            r'below (\d+)', 
            r'less than (\d+)',
            r'(\d+) ni ander',
            r'(\d+) thi niche'
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, message_lower)
            if match:
                filters['price_max'] = int(match.group(1))
                break
        
        return filters

    def _format_product_response(self, search_results: list, query: str = "") -> dict:
        """Format search results for WhatsApp webhook with actual images to send"""
        if not search_results:
            return {
                "message": "Sorry, I couldn't find any watches matching your criteria. Please try different search terms.",
                "products": [],
                "has_results": False,
                "images_to_send": []
            }
        
        formatted_products = []
        images_to_send = []
        
        for i, product in enumerate(search_results[:3], 1):  # Limit to top 3 results
            name = product.get('name', 'Unknown Watch')
            price = product.get('price', '0')
            url = product.get('url', '#')
            images = product.get('image_urls', [])
            brand = product.get('brand', 'Unknown')
            score = product.get('score', 0)
            
            # Get primary image for WhatsApp sending
            primary_image = images[0] if images else None
            
            if primary_image:
                # Create image info for WhatsApp webhook
                image_info = {
                    "image_url": primary_image,
                    "caption": f"*{brand} - {name}*\n💰 Price: ₹{price}\n🔗 Shop: {url}",
                    "product_name": name,
                    "brand": brand,
                    "price": price,
                    "url": url
                }
                images_to_send.append(image_info)
            
            # Create product info for reference
            product_info = {
                "name": name,
                "brand": brand,
                "price": f"₹{price}",
                "url": url,
                "image_url": primary_image,
                "score": score,
                "colors": product.get('colors', []),
                "styles": product.get('styles', []),
                "materials": product.get('materials', [])
            }
            
            formatted_products.append(product_info)
        
        # Create summary message
        summary_message = f"Found {len(search_results)} watches for you! Sending images..."
        
        return {
            "message": summary_message,
            "products": formatted_products,
            "has_results": True,
            "total_found": len(search_results),
            "images_to_send": images_to_send  # Array of images with captions
        }

    def get_search_stats(self) -> dict:
        """Get vector search statistics"""
        if self.vector_search:
            return self.vector_search.get_indexing_stats()
        return {}

    def close(self):
        """Close connections"""
        if self.vector_search:
            self.vector_search.close()

# Backward compatibility - keep original interface
class BackendToolClassifier(EnhancedBackendToolClassifier):
    """Backward compatible interface"""
    
    def analyze_and_classify(self, conversation_history: list, user_message: str, phone_number: str, search_context: dict = None) -> dict:
        """Original interface method"""
        result = self.classify_and_search(user_message, conversation_history, search_context)
        
        # Convert to original format if it's product search
        if result.get('tool') == 'product_search':
            formatted_response = result.get('formatted_response', {})
            if formatted_response.get('has_results'):
                return {
                    "tool": "product_search_complete",
                    "products": formatted_response['products'],
                    "message": formatted_response['message'],
                    "enhanced_query": result.get('enhanced_query', user_message)
                }
            else:
                return {
                    "tool": "ai_chat",
                    "response": formatted_response.get('message', 'No products found.')
                }
        
        # For general chat, use original behavior
        return {"tool": "ai_chat"}