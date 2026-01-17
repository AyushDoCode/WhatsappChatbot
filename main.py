"""
WatchVine WhatsApp Bot - Multi-Agent Architecture
Main entry point with orchestrator for intelligent action handling
"""

import os
import logging
import time
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from typing import Dict
from pymongo import MongoClient
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai import caching

# Import custom modules
from system_prompt_config import get_system_prompt
from tool_calling_config import get_tool_calling_system_prompt
from agent_orchestrator import AgentOrchestrator, ConversationState
from google_sheets_handler import GoogleSheetsHandler, MongoOrderStorage
from google_apps_script_handler import GoogleAppsScriptHandler
from backend_tool_classifier import BackendToolClassifier

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Gemini API Configuration
GOOGLE_API_KEY = os.getenv("Google_api")
GOOGLE_MODEL = os.getenv("google_model", "gemini-1.5-flash-001")

if not GOOGLE_API_KEY:
    logger.warning("⚠️ Google_api not set! AI features may fail.")
else:
    logger.info(f"✅ Using Google Model: {GOOGLE_MODEL}")

# Other configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
MONGODB_DB = os.getenv("MONGODB_DB", "whatsapp_bot")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY")
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "shop-bot")
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL")
STORE_CONTACT_NUMBER = "9016220667"


# ============================================================================
# MONGODB CONVERSATION MANAGER
# ============================================================================

class ConversationManager:
    """Manage user conversations in MongoDB"""

    def __init__(self, mongodb_uri: str, db_name: str):
        self.client = MongoClient(mongodb_uri)
        self.db = self.client[db_name]
        self.conversations = self.db.conversations
        self.conversations.create_index("phone_number")

        # Create indexes for product cache
        self.db.product_cache.create_index("phone_number")
        self.db.product_cache.create_index("expires_at")

        logger.info("✅ MongoDB connected with product cache support")

    def get_conversation(self, phone_number: str, limit: int = 10):
        """Get conversation history"""
        try:
            messages = list(
                self.conversations.find(
                    {"phone_number": phone_number}
                ).sort("timestamp", -1).limit(limit)
            )
            messages.reverse()
            return [
                {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                for msg in messages
                if msg.get("content")  # Only include messages with content
            ]
        except Exception as e:
            logger.error(f"Error getting conversation: {e}")
            return []

    def get_history(self, phone_number: str, limit: int = 10):
        """Alias for get_conversation - used by backend tool classifier"""
        return self.get_conversation(phone_number, limit)

    def save_message(self, phone_number: str, role: str, content: str):
        """Save message to history"""
        try:
            self.conversations.insert_one({
                "phone_number": phone_number,
                "role": role,
                "content": content,
                "timestamp": datetime.now()
            })
        except Exception as e:
            logger.error(f"Error saving message: {e}")

    def clear_conversation(self, phone_number: str) -> int:
        """Clear conversation history"""
        try:
            result = self.conversations.delete_many({"phone_number": phone_number})
            return result.deleted_count
        except Exception as e:
            logger.error(f"Error clearing conversation: {e}")
            return 0

# ============================================================================
# CONVERSATION AI AGENT
# ============================================================================

class ConversationAgent:
    """AI Agent for handling customer conversations with tool calling support using Gemini"""

    def __init__(self, api_key=None, model: str = None, system_prompt: str = None,
                 conversation_manager: ConversationManager = None, order_storage=None,
                 api_key_rotator=None):
        """
        Initialize Conversation Agent with Gemini
        """
        self.api_key = api_key or os.getenv("Google_api")

        # Set model name
        env_model = model or os.getenv("google_model", "gemini-1.5-flash-001")
        if not env_model.startswith("models/") and not env_model.startswith("gemini-"):
             self.model_name = f"models/{env_model}"
        else:
             self.model_name = env_model

        self.system_prompt = system_prompt
        self.conversation_manager = conversation_manager
        self.order_storage = order_storage

        if self.api_key:
            genai.configure(api_key=self.api_key)

        # Cache management
        self.cache_name = "watchvine_agent_system_prompt_v1"
        self.cached_content = None
        self.last_cache_update = 0
        self.CACHE_TTL = 3600 # 1 hour

        logger.info(f"✅ Conversation Agent using Gemini API")
        logger.info(f"✅ Conversation Agent initialized with model: {self.model_name}")

    def _get_or_create_cache(self):
        """Creates or retrieves cached content for system instructions"""
        if not self.api_key: return None

        current_time = time.time()
        if self.cached_content and (current_time - self.last_cache_update < self.CACHE_TTL):
            return self.cached_content

        try:
            # Check for existing cache (simplified: just create new one with TTL)
            # In production, you'd list and find by name to avoid duplication
            # For this simplified version, we'll try to create it.

            # Estimate token count (rough: ~4 chars per token)
            estimated_tokens = len(self.system_prompt) / 4
            
            # Only use cache if content is large enough (>1024 tokens required by Google)
            if estimated_tokens < 1000:
                logger.info(f"⚠️ System prompt too small for caching (~{int(estimated_tokens)} tokens, need 1024+)")
                logger.info("✅ Using standard request (no cache) - saves API calls anyway!")
                return None
            
            logger.info(f"🆕 Creating/Updating Agent Context Cache (~{int(estimated_tokens)} tokens)...")
            self.cached_content = caching.CachedContent.create(
                model=self.model_name,
                display_name=self.cache_name,
                system_instruction=self.system_prompt,
                ttl=timedelta(hours=2)
            )
            self.last_cache_update = current_time
            logger.info(f"✅ Agent Cache created: {self.cached_content.name}")
            return self.cached_content
        except Exception as e:
            logger.error(f"❌ Cache creation failed: {e}")
            return None

    def get_response(self, user_message: str, phone_number: str,
                    metadata: dict = None) -> str:
        """Get AI response based on user message and context"""
        try:
            # SECURITY CHECK: Detect troll attempts
            troll_keywords = ['ignore', 'forget', 'override', 'act as', 'pretend', 'role-play', 'jailbreak']
            if any(keyword in user_message.lower() for keyword in troll_keywords):
                logger.warning(f"🚨 Troll attempt detected from {phone_number}")
                return "I'm WatchVine Assistant, here to help with your shopping needs. How may I assist you today? 😊"

            # Get conversation history
            history = self.conversation_manager.get_conversation(phone_number, limit=10)

            # Build context based on metadata
            context = self._build_context(user_message, metadata or {})

            # Construct chat history for Gemini
            chat_history = []
            for msg in history:
                role = "user" if msg['role'] == "user" else "model"
                chat_history.append({"role": role, "parts": [msg['content']]})

            # Try to use cache
            cached_content = self._get_or_create_cache()

            if cached_content:
                model = genai.GenerativeModel.from_cached_content(cached_content=cached_content)
            else:
                model = genai.GenerativeModel(self.model_name, system_instruction=self.system_prompt)

            # Start chat session
            chat = model.start_chat(history=chat_history)

            # Send message with context
            full_message = f"{context}\n\nUser Message: {user_message}" if context else user_message

            response = chat.send_message(full_message, generation_config=genai.types.GenerationConfig(
                temperature=0.5,
                max_output_tokens=450
            ))

            ai_response = response.text

            # Save conversation
            self.conversation_manager.save_message(phone_number, "user", user_message)
            self.conversation_manager.save_message(phone_number, "assistant", ai_response)

            logger.info(f"✅ Response generated for {phone_number}")
            return ai_response

        except Exception as e:
            logger.error(f"Error getting AI response: {e}")
            return "I apologize, but I encountered an error. Please try again."

    def _build_context(self, user_message: str, metadata: dict) -> str:
        """Build context for AI based on intent and state"""
        context = ""
        intent = metadata.get('intent', 'general_query')

        # Check for color requests
        color_keywords = ['blue', 'red', 'black', 'white', 'pink', 'green', 'yellow', 'brown', 'purple', 'orange']
        if any(color in user_message.lower() for color in color_keywords):
            context += "\n\n⚠️ **IMPORTANT:** Customer mentioned a color. DO NOT claim we have that specific color unless confirmed in data. Provide browse URL instead.\n"

        # Intent-specific context
        if intent == 'greeting':
            context += "\n\n**CONTEXT:** This is the customer's first message. Greet them warmly as per system prompt.\n"

        elif intent == 'collect_details':
            context += "\n\n**CONTEXT:** Customer has selected a product. Now collect their details (Name, Phone, Address, Email if available, Quantity). Be friendly and guide them.\n"

        elif intent == 'missing_details':
            missing = metadata.get('missing_fields', [])
            context += f"\n\n**CONTEXT:** Customer tried to confirm but missing details: {', '.join(missing)}. Politely ask for these missing details before proceeding.\n"

        elif intent == 'show_order_summary':
            order_data = metadata.get('order_data', {})
            context += f"\n\n**CONTEXT:** All details collected. Show order summary:\n{self._format_order_summary(order_data)}\n\nAsk for final confirmation.\n"

        elif intent == 'detect_confirmation':
            order_data = metadata.get('order_data', {})
            context += f"""
**CRITICAL INTERNAL TASK - CONFIRMATION DETECTION**
You are now in confirmation detection mode. Analyze the customer's message to determine if they are confirming the order or not.

**Order Summary Being Confirmed:**
{self._format_order_summary(order_data)}

**Your Task:**
1. Carefully read the customer's message
2. Determine if they are confirming/agreeing (yes, ok, correct, sahi hai, theek hai, conform, proceed, etc.) OR if they want to change something/cancel
3. Set the internal status marker based on your analysis:
   - If customer is confirming: Include **INTERNAL_CONFIRMATION_STATUS: TRUE** in your response
   - If customer wants changes/is declining: Include **INTERNAL_CONFIRMATION_STATUS: FALSE** in your response

4. Then provide your normal customer-facing response.
"""
        return context

    def _format_order_summary(self, order_data: dict) -> str:
        """Format order data for display"""
        return f"""
Customer: {order_data.get('customer_name')}
Phone: {order_data.get('phone_number')}
Email: {order_data.get('email', 'N/A')}
Address: {order_data.get('address')}
Product: {order_data.get('product_name', order_data.get('product_url'))}
Quantity: {order_data.get('quantity', 1)}
"""

# ============================================================================
# WHATSAPP HANDLER
# ============================================================================

class WhatsAppHandler:
    """Handle WhatsApp messages via Evolution API"""

    def __init__(self, api_url: str, api_key: str, instance_name: str):
        self.api_url = api_url
        self.api_key = api_key
        self.instance_name = instance_name
        self.headers = {
            "apikey": api_key,
            "Content-Type": "application/json"
        }

    def send_message(self, phone_number: str, message: str, max_retries: int = 3) -> bool:
        """Send WhatsApp message with retry logic"""
        import requests
        from requests.exceptions import Timeout, ConnectionError

        phone_clean = phone_number.replace("+", "").replace("-", "").replace(" ", "")

        # Add country code if not present (assuming Indian numbers)
        if len(phone_clean) == 10:
            phone_clean = "91" + phone_clean

        url = f"{self.api_url}/message/sendText/{self.instance_name}"
        payload = {
            "number": phone_clean,
            "text": message
        }

        for attempt in range(max_retries):
            try:
                timeout = 15 + (attempt * 15)
                logger.info(f"📤 Sending message (attempt {attempt + 1}/{max_retries})...")
                response = requests.post(url, json=payload, headers=self.headers, timeout=timeout)
                if response.status_code in [200, 201]:
                    logger.info(f"✅ Message sent to {phone_number}")
                    return True
                else:
                    logger.warning(f"⚠️ Failed attempt {attempt + 1}: {response.status_code}")
                    if attempt < max_retries - 1: time.sleep(2 ** attempt)
            except Exception as e:
                logger.warning(f"⚠️ Error: {e}")
                if attempt < max_retries - 1: time.sleep(2 ** attempt)
        return False

    def forward_media_with_base64(self, to_number: str, base64_data: str, caption: str, media_type: str = "image", max_retries: int = 3) -> bool:
        """Forward media using base64 data from Evolution API webhook"""
        import requests

        to_clean = to_number.replace("+", "").replace("-", "").replace(" ", "")
        if len(to_clean) == 10: to_clean = "91" + to_clean

        url = f"{self.api_url}/message/sendMedia/{self.instance_name}"
        payload = {
            "number": to_clean,
            "mediatype": media_type,
            "media": base64_data,
            "caption": caption
        }

        for attempt in range(max_retries):
            try:
                timeout = 20 + (attempt * 20)
                logger.info(f"📤 Forwarding {media_type} (attempt {attempt + 1}/{max_retries})...")
                response = requests.post(url, json=payload, headers=self.headers, timeout=timeout)
                if response.status_code in [200, 201]:
                    logger.info(f"✅ {media_type.capitalize()} forwarded!")
                    return True
                else:
                    logger.warning(f"⚠️ Failed attempt {attempt + 1}: {response.status_code}")
                    if attempt < max_retries - 1: time.sleep(2 ** attempt)
            except Exception as e:
                logger.warning(f"⚠️ Error: {e}")
                if attempt < max_retries - 1: time.sleep(2 ** attempt)
        return False

    def send_media_via_url(self, to_number: str, media_url: str, caption: str, media_type: str = "image", max_retries: int = 3) -> bool:
        """Send media using direct URL"""
        import requests

        to_clean = to_number.replace("+", "").replace("-", "").replace(" ", "")
        if len(to_clean) == 10: to_clean = "91" + to_clean

        url = f"{self.api_url}/message/sendMedia/{self.instance_name}"
        payload = {
            "number": to_clean,
            "mediatype": media_type,
            "media": media_url,
            "caption": caption
        }

        for attempt in range(max_retries):
            try:
                timeout = 15 + (attempt * 10)
                logger.info(f"📤 Sending {media_type} via URL (attempt {attempt + 1}/{max_retries})...")
                response = requests.post(url, json=payload, headers=self.headers, timeout=timeout)
                if response.status_code in [200, 201]:
                    logger.info(f"✅ {media_type.capitalize()} sent successfully!")
                    return True
                else:
                    logger.warning(f"⚠️ Failed attempt {attempt + 1}: {response.status_code}")
                    if attempt < max_retries - 1: time.sleep(1)
            except Exception as e:
                logger.warning(f"⚠️ Error: {e}")
                if attempt < max_retries - 1: time.sleep(1)
        return False

# ============================================================================
# FLASK APP
# ============================================================================

app = Flask(__name__)

# Initialize components
logger.info("🚀 Initializing WatchVine Multi-Agent Bot...")

conversation_manager = ConversationManager(MONGODB_URI, MONGODB_DB)
orchestrator = AgentOrchestrator(conversation_manager)
conversation_agent = ConversationAgent(
    api_key=GOOGLE_API_KEY,
    model=GOOGLE_MODEL,
    system_prompt=get_system_prompt(),
    conversation_manager=conversation_manager
)

# Initialize order storage
GOOGLE_APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL")
GOOGLE_APPS_SCRIPT_SECRET = os.getenv("GOOGLE_APPS_SCRIPT_SECRET")

if GOOGLE_APPS_SCRIPT_URL and GOOGLE_APPS_SCRIPT_SECRET:
    logger.info("🔧 Initializing Google Apps Script for order storage...")
    order_storage = GoogleAppsScriptHandler(
        web_app_url=GOOGLE_APPS_SCRIPT_URL,
        secret_key=GOOGLE_APPS_SCRIPT_SECRET
    )
elif os.path.exists("credentials.json") and GOOGLE_SHEET_URL:
    logger.info("🔧 Initializing Google Sheets API for order storage...")
    order_storage = GoogleSheetsHandler(
        credentials_file="credentials.json",
        sheet_url=GOOGLE_SHEET_URL
    )
    order_storage.initialize_sheet_headers()
else:
    logger.warning("⚠️ Using MongoDB storage (Google Sheets not configured).")
    order_storage = MongoOrderStorage(mongodb_uri=MONGODB_URI, db_name=MONGODB_DB)

whatsapp = WhatsAppHandler(EVOLUTION_API_URL, EVOLUTION_API_KEY, INSTANCE_NAME)
conversation_agent.order_storage = order_storage

logger.info("✅ Multi-Agent Bot initialized successfully!")

# ============================================================================
# PRODUCT SEARCH HANDLER (AI-Based)
# ============================================================================

def detect_category_from_query(query: str) -> str:
    """Detect product category from search query"""
    query_lower = query.lower()
    category_map = {
        'mens_watch': ['men watch', 'mens watch', 'gent watch', 'boy watch'],
        'womens_watch': ['ladies watch', 'womens watch', 'women watch', 'girl watch', 'lady watch'],
        'mens_sunglasses': ['men sunglass', 'mens sunglass', 'men glass'],
        'womens_sunglasses': ['ladies sunglass', 'womens sunglass', 'women sunglass'],
        'wallet': ['wallet', 'purse'],
        'handbag': ['bag', 'handbag', 'hand bag'],
        'mens_shoes': ['men shoe', 'mens shoe', 'gent shoe'],
        'womens_shoes': ['ladies shoe', 'womens shoe', 'women shoe'],
        'loafers': ['loafer', 'formal shoe'],
        'flipflops': ['flipflop', 'flip flop', 'slipper'],
        'bracelet': ['bracelet', 'jewellery', 'jewelry']
    }

    for category_key, keywords in category_map.items():
        for keyword in keywords:
            if keyword in query_lower:
                return category_key

    if 'watch' in query_lower: return 'mens_watch'
    return None

def send_product_images_v2(keyword: str, phone_number: str, start_index: int = 0, batch_size: int = 10, min_price: float = None, max_price: float = None, category_key: str = None):
    """OLD WORKING METHOD: Keyword search with category filtering"""
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not keyword or len(keyword.strip()) < 2: 
        return (False, 0, 0)

    logger.info(f"🔍 Keyword search: '{keyword}' | Category: {category_key} (batch: {start_index}-{start_index + batch_size})")

    try:
        # Call keyword-based search API with category filtering
        SEARCH_API_URL = os.getenv("TEXT_SEARCH_API_URL", "http://text_search_api:8001")
        search_payload = {"query": keyword, "max_results": 50}
        
        # Add category filter (CRITICAL for accuracy)
        if category_key:
            search_payload["category_filter"] = category_key
            logger.info(f"✅ Category filter: {category_key}")
        
        # Add price filters
        if min_price is not None:
            search_payload["min_price"] = min_price
        if max_price is not None:
            search_payload["max_price"] = max_price

        response = requests.post(f"{SEARCH_API_URL}/search/images-list", json=search_payload, timeout=30)

        if response.status_code != 200: return (False, 0, 0)

        result = response.json()
        if result.get('status') != 'success' or not result.get('products'): return (False, 0, 0)

        all_products = result.get('products', [])
        total_found = len(all_products)

        end_index = min(start_index + batch_size, total_found)
        products_to_send = all_products[start_index:end_index]

        # Send intro message
        intro_msg = f"""Great! 🎉 Found {total_found} products for '{keyword}'
Showing {len(products_to_send)} products ({start_index+1}-{end_index})...
Please wait... 📸

 vadhare products jova mate 'More' lakho."""
        whatsapp.send_message(phone_number, intro_msg)

        def send_single_product(idx, product):
            product_name = product.get('product_name', 'Unknown')
            price = product.get('price', 'N/A')
            product_url = product.get('product_url', '')
            images = product.get('images_base64', [])

            if not images: return False

            try:
                caption = f"📦 {product_name}\n💰 ₹{price}"
                if product_url: caption += f"\n🔗 {product_url}"
                if len(images) > 1: caption += f"\n\n📸 {len(images)} images available"

                return whatsapp.forward_media_with_base64(phone_number, images[0], caption, "image")
            except Exception: return False

        success_count = 0
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(send_single_product, idx, prod)
                      for idx, prod in enumerate(products_to_send, 1)]
            for future in as_completed(futures):
                if future.result(): success_count += 1

        # Cache products
        orchestrator.cache_product_data(phone_number, all_products)

        # Update sent_count
        try:
            orchestrator.conversation_manager.db.product_cache.update_one(
                {'phone_number': phone_number},
                {'$set': {'sent_count': end_index}}
            )
        except Exception as e: logger.error(f"Error updating sent_count: {e}")

        # Send completion message (UPDATED as per user request)
        if success_count > 0:
            completion_msg = ""

            if end_index < total_found:
                remaining = total_found - end_index
                completion_msg = f"""બીજી પ્રોડક્ટ પણ છે અમારી પાસે, જો તમારે જોવી હોય તો હું બતાવું? 😊
"""

            # Append Gujarati Text (Transliterated instruction followed by Gujarati script)
            completion_msg += """તમે આ વૉચ બે રીતે ઓર્ડર કરી શકો છો
1. અમદાવાદ-બોપલ સ્થિત અમારી સ્ટોર પરથી સીધી આવીને લઈ શકો છો.
2. ઘર બેઠા Open Box Cash on Delivery દ્વારા પણ મંગાવી શકો છો.
3. બીજી watches જોવા માટે 'More' લખો.
તમને કયો વિકલ્પ વધુ યોગ્ય લાગે છે? કૃપા કરીને જણાવશો."""

            whatsapp.send_message(phone_number, completion_msg)

        return (True, total_found, success_count)

    except Exception as e:
        logger.error(f"❌ Error in product search: {e}")
        return (False, 0, 0)

# ============================================================================
# IMAGE HANDLING
# ============================================================================

def handle_image_message(phone_number: str, message_info: dict, instance_name: str = None):
    """Handle incoming image messages and search for products"""
    import requests
    import base64

    logger.info(f"📸 Received image from {phone_number}")
    logger.info(f"🔍 Message info keys: {list(message_info.keys())}")
    whatsapp.send_message(phone_number, "🔍 Searching for similar products... Please wait.")

    try:
        # 1. Extract Image Data
        image_data = None

        # PRIORITY 0: Check if base64 is directly provided (Evolution API often does this if configured)
        # This is usually higher quality than jpegThumbnail
        if 'base64' in message_info:
            logger.info("✅ Found base64 in message_info (HIGHEST QUALITY)")
            try:
                image_data = base64.b64decode(message_info['base64'])
                logger.info(f"✅ Decoded base64 from message_info, size: {len(image_data)} bytes")
            except Exception as e:
                logger.error(f"❌ Error decoding base64: {e}")
                image_data = None

        # If no base64, try to download from URL (if public) or handle otherwise
        elif 'url' in message_info:
            logger.info("✅ Found url in message_info, attempting download...")
            img_url = message_info['url']
            try:
                # This might fail if the URL requires auth, but worth a try if Evolution proxies it
                img_response = requests.get(img_url, timeout=10)
                if img_response.status_code == 200:
                    image_data = img_response.content
                    logger.info(f"✅ Downloaded image from URL, size: {len(image_data)} bytes")
                else:
                    logger.warning(f"❌ Failed to download from URL, status: {img_response.status_code}")
            except Exception as e:
                logger.error(f"❌ Failed to download image from URL: {e}")

        # If still no image data, try to get it from the message object directly (standard WA structure)
        if not image_data and 'imageMessage' in message_info:
             logger.info("✅ Found imageMessage in message_info")
             img_msg = message_info['imageMessage']
             logger.info(f"🔍 ImageMessage keys: {list(img_msg.keys())}")
             
             # PRIORITY 1: Try jpegThumbnail first (it's already decrypted!)
             if 'jpegThumbnail' in img_msg:
                 try:
                     logger.info("📥 Using jpegThumbnail (pre-decrypted)")
                     thumbnail = img_msg['jpegThumbnail']
                     logger.info(f"🔍 jpegThumbnail type: {type(thumbnail)}")
                     
                     # Check if it's a dict with numeric keys (byte array as dict)
                     if isinstance(thumbnail, dict):
                         # Check if keys are numeric (array-like dict)
                         first_key = next(iter(thumbnail.keys())) if thumbnail else None
                         if first_key and first_key.isdigit():
                             logger.info(f"🔍 jpegThumbnail is byte array as dict (length: {len(thumbnail)})")
                             # Convert dict to bytes array
                             byte_array = [thumbnail[str(i)] for i in range(len(thumbnail))]
                             image_data = bytes(byte_array)
                             logger.info(f"✅ Converted dict to bytes, size: {len(image_data)} bytes")
                         elif 'data' in thumbnail:
                             thumbnail = thumbnail['data']
                         elif 'base64' in thumbnail:
                             thumbnail = thumbnail['base64']
                     
                     # If not already converted, try other formats
                     if not image_data:
                         if isinstance(thumbnail, str):
                             image_data = base64.b64decode(thumbnail)
                             logger.info(f"✅ Decoded jpegThumbnail from base64, size: {len(image_data)} bytes")
                         elif isinstance(thumbnail, bytes):
                             image_data = thumbnail
                             logger.info(f"✅ Got jpegThumbnail as bytes, size: {len(image_data)} bytes")
                         else:
                             logger.error(f"❌ jpegThumbnail is unexpected type: {type(thumbnail)}")
                 except Exception as e:
                     logger.error(f"❌ Error processing jpegThumbnail: {e}")
             
             # PRIORITY 2: Try URL download (but note: it's encrypted and needs decryption)
             if not image_data:
                 logger.warning("⚠️ jpegThumbnail not available or failed")
                 logger.warning("⚠️ URL-downloaded images from WhatsApp are encrypted and require decryption")
                 logger.warning("⚠️ Skipping URL download - would need mediaKey to decrypt")
                 # Note: The URL image is encrypted. To use it, you'd need to:
                 # 1. Download the encrypted data
                 # 2. Use mediaKey + fileEncSha256 to decrypt it
                 # This requires WhatsApp's encryption libraries

        if not image_data:
            logger.error(f"Could not extract image data. Keys in message_info: {list(message_info.keys())}")
            if 'imageMessage' in message_info:
                 logger.error(f"Keys in imageMessage: {list(message_info['imageMessage'].keys())}")
            
            whatsapp.send_message(phone_number, "⚠️ Sorry, I couldn't process this image. Please try again.")
            return

        # 2. Call Image Identifier API
        IMAGE_API_URL = os.getenv("IMAGE_IDENTIFIER_API_URL", "http://image_identifier_api:8002")
        files = {'file': ('query_image.jpg', image_data, 'image/jpeg')}

        response = requests.post(f"{IMAGE_API_URL}/search", files=files, timeout=30)

        if response.status_code == 200:
            result = response.json()
            status = result.get('status')

            if status in ['exact_match', 'match_found']:
                # Found a match
                product_name = result.get('product_name')
                price = result.get('price')
                product_url = result.get('product_url')
                confidence = result.get('confidence', 'unknown')

                # Construct message
                msg = f"""🎉 *Product Found!* (Confidence: {confidence.upper()})
📦 *{product_name}*
💰 {price}
🔗 {product_url}"""

                # Add similar results if available
                top_results = result.get('top_5_results', [])
                if top_results and len(top_results) > 1:
                    msg += "\n*Also similar:*\n"
                    for idx, res in enumerate(top_results[1:4], 1):  # Show next 3
                        msg += f"{idx}. {res['product_name']} ({res.get('price', 'N/A')})\n"
                        msg += f"   🔗 {res['product_url']}\n"

                whatsapp.send_message(phone_number, msg)

                # Send the matched image back as confirmation (optional, but good UX)
                matched_image_url = result.get('matched_image_url')
                if matched_image_url:
                    whatsapp.send_media_via_url(phone_number, matched_image_url, "✅ Here is the matched product", "image")

            else:
                whatsapp.send_message(phone_number, "❌ Sorry, I couldn't find an exact match for this product.")

                # Show top guesses anyway if they exist
                top_results = result.get('top_5_results', [])
                if top_results:
                    msg = """*Here are the closest matches I found:*

"""
                    for idx, res in enumerate(top_results[:3], 1):
                        msg += f"{idx}. {res['product_name']} ({res.get('price', 'N/A')})\n"
                        msg += f"   🔗 {res['product_url']}\n"
                    whatsapp.send_message(phone_number, msg)

        else:
            logger.error(f"Image API Error: {response.text}")
            whatsapp.send_message(phone_number, "⚠️ Technical error identifying the image.")

    except Exception as e:
        logger.error(f"Error handling image message: {e}")
        whatsapp.send_message(phone_number, "⚠️ An error occurred while processing your image.")


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

# ============================================================================
# WEBHOOK ENDPOINT
# ============================================================================

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle incoming WhatsApp messages"""
    try:
        data = request.json
        if data.get('event') == 'messages.upsert':
            message_data = data.get('data', {})
            message_info = message_data.get('message', {})
            key_info = message_data.get('key', {})
            from_me = key_info.get('fromMe', False)
            remote_jid = key_info.get('remoteJid', '')

            if from_me or not remote_jid: return jsonify({"status": "success"}), 200

            phone_number = remote_jid.split('@')[0]

            # Check for Image Message
            # Evolution API structure might vary, checking multiple places
            is_image = False
            msg_type = message_data.get('messageType', '')

            if msg_type == 'imageMessage' or 'imageMessage' in message_info:
                is_image = True
            elif 'ephemeralMessage' in message_info:
                if 'imageMessage' in message_info['ephemeralMessage'].get('message', {}):
                    is_image = True
                    # Normalize structure
                    message_info = message_info['ephemeralMessage']['message']['imageMessage']

            if is_image and not from_me:
                # Pass the correct data part that contains 'base64' or 'url'
                # Evolution often puts 'base64' in the root of 'data' or inside 'message' depending on config
                # We'll pass both `message_data` (root) and `message_info` (nested) merged or just handle in function
                # Ideally, look for where base64 is.

                logger.info(f"🖼️ Image message detected, preparing to handle...")
                logger.info(f"🔍 message_data keys: {list(message_data.keys())}")
                
                # Checking if base64 is at root data level (common in Evolution)
                payload_to_pass = message_info
                if 'base64' in message_data:
                    logger.info("✅ base64 found in message_data root")
                    payload_to_pass = message_data # Use root data if it has base64
                else:
                    logger.info("⚠️ base64 NOT in message_data root, using message_info")

                handle_image_message(phone_number, payload_to_pass, INSTANCE_NAME)
                return jsonify({"status": "success"}), 200

            # Handle Text Messages
            conversation = (
                message_info.get('conversation') or
                message_info.get('extendedTextMessage', {}).get('text', '')
            )

            if not from_me and conversation:
                logger.info(f"Message from {phone_number}: {conversation[:50]}...")

                # ===== CHECK IF USER WANTS MORE PRODUCTS (AI-BASED) =====
                # First check if there's a pending search context
                search_ctx = orchestrator.get_search_context(phone_number)
                
                if search_ctx and search_ctx.get('sent_count', 0) < search_ctx.get('total_found', 0):
                    # User has pending products - check if they want to see more using AI
                    keyword = search_ctx.get('keyword', '')
                    sent_count = search_ctx.get('sent_count', 0)
                    total_found = search_ctx.get('total_found', 0)
                    
                    logger.info(f"📋 Pending products context: {keyword} ({sent_count}/{total_found})")
                    logger.info(f"🤖 Asking AI to check if user wants more products...")
                    
                    # Use AI to detect if user wants more (backend classifier uses search_context automatically)
                    action, metadata = orchestrator.analyze_message(conversation, phone_number)
                    
                    logger.info(f"Action: {action}")
                    
                    # If AI detected user wants more from current search
                    if action == 'show_more':
                        logger.info(f"🤖 AI detected: User wants to see more {keyword} products!")
                        logger.info(f"📊 Current progress: {sent_count}/{total_found} products already sent")
                        
                        # Check if there are more products to send
                        if sent_count >= total_found:
                            logger.warning(f"⚠️ No more products! Already sent all {total_found} products")
                            whatsapp.send_message(phone_number, f"😔 Sorry, you've seen all {total_found} {keyword} products we have!")
                            return jsonify({"status": "success"}), 200
                        
                        # Send next batch of products (price filters from original search context if stored)
                        success, new_total, new_sent = send_product_images_v2(
                            keyword, phone_number, start_index=sent_count, batch_size=10,
                            min_price=search_ctx.get('min_price'), max_price=search_ctx.get('max_price'),
                            category_key=search_ctx.get('category_key')
                        )
                        
                        if success:
                            # Calculate cumulative sent count (previous + newly sent in this batch)
                            cumulative_sent = sent_count + new_sent
                            logger.info(f"✅ Sent {new_sent} more products. Total: {cumulative_sent}/{new_total}")
                            orchestrator.save_search_context(phone_number, keyword, new_total, cumulative_sent, 
                                                           min_price=search_ctx.get('min_price'), 
                                                           max_price=search_ctx.get('max_price'),
                                                           category_key=search_ctx.get('category_key'))
                        else:
                            logger.error(f"❌ Failed to send more products for {keyword}")
                        
                        return jsonify({"status": "success"}), 200
                # ===== END PAGINATION CHECK =====
                else:
                    # No pending products - check if in question flow
                    user_state = orchestrator.user_states.get(phone_number)
                    
                    # Handle category selection response
                    if isinstance(user_state, dict) and user_state.get('waiting_for') == 'category_or_brand':
                        response = conversation.strip()
                        product_type = user_state.get('product_type', 'watch')
                        categories = user_state.get('categories', [])
                        
                        if response.isdigit():
                            selection = int(response)
                            if 1 <= selection <= len(categories):
                                category_key = categories[selection - 1]
                                logger.info(f"✅ User selected category: {category_key}")
                                
                                brand_message = f"Perfect! Now, would you like to see a specific brand or any brand?\n\n"
                                brand_message += f"Reply with:\n• Brand name (e.g., Rolex, Fossil, Casio)\n• 'Any' or 'Koi bhi' for random selection"
                                
                                orchestrator.user_states[phone_number] = {
                                    'waiting_for': 'brand_selection',
                                    'product_type': product_type,
                                    'category_key': category_key,
                                    'timestamp': time.time()
                                }
                                
                                whatsapp.send_message(phone_number, brand_message)
                                return jsonify({"status": "success"}), 200
                        else:
                            # User entered brand name directly
                            category_key = categories[0] if categories else 'mens_watch'
                            success, total_found, sent_count = send_product_images_v2(
                                response, phone_number, start_index=0, batch_size=10, category_key=category_key
                            )
                            if success:
                                orchestrator.save_search_context(phone_number, response, total_found, sent_count)
                            else:
                                whatsapp.send_message(phone_number, f"Sorry, no {response} {product_type}s found 😔")
                            del orchestrator.user_states[phone_number]
                            return jsonify({"status": "success"}), 200
                    
                    # Handle non-watch keyword search (for bags, sunglasses, shoes, etc.)
                    if isinstance(user_state, dict) and user_state.get('waiting_for') == 'non_watch_keyword_search':
                        keyword = conversation.strip().lower()
                        category_key = user_state.get('category_key')
                        min_price = user_state.get('min_price')
                        max_price = user_state.get('max_price')
                        
                        logger.info(f"🛍️ Non-watch keyword search: keyword='{keyword}', category={category_key}")
                        
                        if keyword:
                            # Direct keyword search for non-watch products
                            success, total_found, sent_count = send_product_images_v2(
                                keyword, phone_number, start_index=0, batch_size=10, 
                                category_key=category_key, min_price=min_price, max_price=max_price
                            )
                            
                            if success:
                                logger.info(f"✅ Found {total_found} products for '{keyword}' in {category_key}")
                                orchestrator.save_search_context(phone_number, keyword, total_found, sent_count,
                                                               min_price=min_price, max_price=max_price,
                                                               category_key=category_key)
                            else:
                                logger.warning(f"⚠️ No products found for '{keyword}' in {category_key}")
                                whatsapp.send_message(phone_number, f"Sorry, no {keyword} {category_key.replace('_', ' ')} found 😔\n\nTry another keyword!")
                        else:
                            whatsapp.send_message(phone_number, "Please tell me what you're looking for! 😊")
                        
                        del orchestrator.user_states[phone_number]
                        return jsonify({"status": "success"}), 200
                    
                    # Handle generic brand selection (for "man watches" type queries)
                    # Now the AI classifier will handle this via show_all_brands or find_product tools
                    # This state is kept for backward compatibility but logic moved to classifier
                    if isinstance(user_state, dict) and user_state.get('waiting_for') == 'generic_brand_selection':
                        response = conversation.strip().lower()
                        category_key = user_state.get('category_key')
                        min_price = user_state.get('min_price')
                        max_price = user_state.get('max_price')
                        
                        logger.info(f"💬 Generic brand selection state - passing to classifier for intelligent routing")
                        
                        # Let the classifier handle this response intelligently
                        # It will detect "sabhi", "all", "random", specific brands, etc.
                        action, metadata = orchestrator.analyze_message(response, phone_number)
                        logger.info(f"🤖 Classifier returned action: {action}")
                        
                        # Handle show_all_brands from classifier
                        if action == 'show_all_brands':
                            metadata['category_key'] = category_key
                            metadata['min_price'] = min_price
                            metadata['max_price'] = max_price
                            
                            logger.info(f"🎯 show_all_brands detected! Category: {category_key}")
                            priority_brands = ['fossil', 'rolex', 'armani', 'omega']
                            
                            whatsapp.send_message(phone_number, "🎉 Great! Showing you 2-3 products from our top brands...\n\nPlease wait... 📸")
                            
                            total_products_sent = 0
                            for brand in priority_brands:
                                success, total_found, sent_count = send_product_images_v2(
                                    brand, phone_number, start_index=0, batch_size=3, 
                                    category_key=category_key, min_price=min_price, max_price=max_price
                                )
                                if success:
                                    total_products_sent += sent_count
                                    time.sleep(2)
                            
                            if total_products_sent == 0:
                                whatsapp.send_message(phone_number, "Sorry, couldn't find products from these brands 😔")
                        
                        elif action == 'find_product':
                            # User wants a specific brand
                            keyword = metadata.get('keyword', '').strip()
                            if keyword:
                                success, total_found, sent_count = send_product_images_v2(
                                    keyword, phone_number, start_index=0, batch_size=10, category_key=category_key,
                                    min_price=min_price, max_price=max_price
                                )
                                if success:
                                    orchestrator.save_search_context(phone_number, keyword, total_found, sent_count)
                                else:
                                    whatsapp.send_message(phone_number, f"Sorry, no {keyword} {category_key.replace('_', ' ')}s found 😔")
                            else:
                                whatsapp.send_message(phone_number, "Please specify a brand name 😊")
                        else:
                            # AI chat response
                            ai_response = conversation_agent.get_response(response, phone_number)
                            whatsapp.send_message(phone_number, ai_response)
                        
                        del orchestrator.user_states[phone_number]
                        return jsonify({"status": "success"}), 200
                   
                    # Handle brand selection response (from category selection flow)
                    if isinstance(user_state, dict) and user_state.get('waiting_for') == 'brand_selection':
                        response = conversation.strip().lower()
                        category_key = user_state.get('category_key')
                        product_type = user_state.get('product_type', 'watch')
                        
                        if response in ['any', 'koi bhi', 'koi bhi chalega', 'random']:
                            from pymongo import MongoClient
                            MONGO_URI = os.getenv("MONGO_URI")
                            client = MongoClient(MONGO_URI)
                            db = client[os.getenv("DATABASE_NAME", "watchvine_refined")]
                            collection = db[os.getenv("COLLECTION_NAME", "products")]
                            
                            pipeline = [{"$match": {"category_key": category_key}}, {"$sample": {"size": 1}}]
                            random_product = list(collection.aggregate(pipeline))
                            
                            if random_product:
                                brand = random_product[0].get('name', '').split()[0]
                                success, total_found, sent_count = send_product_images_v2(
                                    brand, phone_number, start_index=0, batch_size=10, category_key=category_key
                                )
                                if success:
                                    orchestrator.save_search_context(phone_number, brand, total_found, sent_count)
                            else:
                                whatsapp.send_message(phone_number, f"Sorry, no products found 😔")
                        else:
                            success, total_found, sent_count = send_product_images_v2(
                                response, phone_number, start_index=0, batch_size=10, category_key=category_key
                            )
                            if success:
                                orchestrator.save_search_context(phone_number, response, total_found, sent_count)
                            else:
                                whatsapp.send_message(phone_number, f"Sorry, no {response} {product_type}s found 😔")
                        
                        del orchestrator.user_states[phone_number]
                        return jsonify({"status": "success"}), 200
                    
                    # Normal flow - Analyze with Orchestrator (BackendToolClassifier)
                    action, metadata = orchestrator.analyze_message(conversation, phone_number)
                    logger.info(f"Action: {action}")

                if action == 'show_all_brands':
                    category_key = metadata.get('category_key')
                    min_price = metadata.get('min_price')
                    max_price = metadata.get('max_price')
                    
                    logger.info(f"🎯 show_all_brands detected! Category: {category_key}")
                    
                    # Prioritize top 4 brands: Fossil, Rolex, Armani, Omega
                    priority_brands = ['fossil', 'rolex', 'armani', 'omega']
                    
                    whatsapp.send_message(phone_number, "🎉 Great! Showing you 2-3 products from our top brands...\n\nPlease wait... 📸")
                    
                    total_products_sent = 0
                    for brand in priority_brands:
                        success, total_found, sent_count = send_product_images_v2(
                            brand, phone_number, start_index=0, batch_size=3, 
                            category_key=category_key, min_price=min_price, max_price=max_price
                        )
                        if success:
                            total_products_sent += sent_count
                            time.sleep(2)  # Small delay between brand batches
                    
                    if total_products_sent == 0:
                        whatsapp.send_message(phone_number, "Sorry, couldn't find products from these brands 😔")
                    
                    return jsonify({"status": "success"}), 200

                if action == 'find_product':
                    keyword = metadata.get('keyword', '').strip()
                    min_price = metadata.get('min_price')
                    max_price = metadata.get('max_price')
                    category_key = metadata.get('category_key')  # AI-detected category_key
                    
                    # WATCH-SPECIFIC LOGIC: If keyword is empty but category_key exists (generic search like "man watches")
                    # Ask user which brand they prefer instead of showing all
                    # This ONLY applies to watches - other products allow direct keyword search
                    watch_categories = ['mens_watch', 'womens_watch', 'mens_watches', 'womens_watches', 'men_watch', 'women_watch']
                    
                    if not keyword and category_key and category_key in watch_categories:
                        logger.info(f"🔍 Generic WATCH category search detected: {category_key}")
                        logger.info(f"💬 Asking user to specify brand preference...")
                        
                        # Ask user which brand they prefer for WATCHES
                        brand_preference_msg = f"""Great! 👕 You're looking for {category_key.replace('_', ' ')}.

Which brand would you prefer?

Popular Options:
1. 🏆 *Fossil* - Classic & Affordable
2. ⌚ *Rolex* - Premium & Luxury
3. 🎨 *Armani* - Stylish & Elegant
4. ⏱️ *Omega* - Quality & Precision

Or reply with:
• Any specific brand name (Casio, TAG Heuer, Patek Philippe, etc.)
• 'All' or 'Sabhi' to see 2-3 watches from each top brand
• 'Random' or 'Koi bhi' for random selection"""
                        
                        orchestrator.user_states[phone_number] = {
                            'waiting_for': 'generic_brand_selection',
                            'category_key': category_key,
                            'min_price': min_price,
                            'max_price': max_price,
                            'timestamp': time.time()
                        }
                        
                        whatsapp.send_message(phone_number, brand_preference_msg)
                        return jsonify({"status": "success"}), 200
                    
                    # NON-WATCH PRODUCTS: If keyword is empty but category_key exists for NON-WATCH items
                    # Ask for category selection but allow direct search (no brand required)
                    if not keyword and category_key and category_key not in watch_categories:
                        logger.info(f"🛍️ Generic NON-WATCH category search detected: {category_key}")
                        
                        # For non-watch products, just ask to narrow down or search directly
                        category_names = {
                            'handbag': 'Hand Bags',
                            'sunglass': 'Sunglasses',
                            'mens_sunglass': "Men's Sunglasses",
                            'womens_sunglass': "Ladies' Sunglasses",
                            'shoes': 'Shoes',
                            'mens_shoes': "Men's Shoes",
                            'womens_shoes': "Ladies' Shoes",
                            'loafers': 'Loafers',
                            'flipflops': 'Flip-Flops',
                            'wallet': 'Wallets',
                            'bracelet': 'Bracelets'
                        }
                        
                        cat_display = category_names.get(category_key, category_key.replace('_', ' '))
                        
                        category_msg = f"""Great! We have {cat_display} in our collection.

You can:
1. Tell me what style/color/material you prefer (e.g., 'black', 'leather', 'formal', 'casual')
2. Or just type a keyword to search!

What would you like? 😊"""
                        
                        orchestrator.user_states[phone_number] = {
                            'waiting_for': 'non_watch_keyword_search',
                            'category_key': category_key,
                            'min_price': min_price,
                            'max_price': max_price,
                            'timestamp': time.time()
                        }
                        
                        whatsapp.send_message(phone_number, category_msg)
                        return jsonify({"status": "success"}), 200
                    
                    # If still no keyword, cannot search
                    if not keyword:
                        logger.warning("⚠️ No keyword provided")
                        whatsapp.send_message(phone_number, "Please specify what product you're looking for 😊")
                        return jsonify({"status": "success"}), 200
                    
                    logger.info(f"🔍 Product search: '{keyword}' | Category: {category_key}")
                    
                    # OLD WORKING SEARCH with category filtering
                    success, total_found, sent_count = send_product_images_v2(
                        keyword, phone_number, start_index=0, batch_size=10,
                        min_price=min_price, max_price=max_price, category_key=category_key
                    )
                    if success:
                        orchestrator.save_search_context(phone_number, keyword, total_found, sent_count)
                    else:
                        whatsapp.send_message(phone_number, f"Sorry, no products found for '{keyword}' 😔")

                elif action == 'ask_category_selection':
                    # User asked for generic product (e.g., "show me watches")
                    # Ask for category selection (mens/womens)
                    product_type = metadata.get('product_type', 'watch')
                    
                    # Get available categories for this product type
                    if product_type == 'watch':
                        categories_available = ["Men's Watches", "Ladies' Watches"]
                        category_keys = ["mens_watch", "womens_watch"]
                    elif product_type == 'sunglasses':
                        categories_available = ["Men's Sunglasses", "Ladies' Sunglasses"]
                        category_keys = ["mens_sunglasses", "womens_sunglasses"]
                    elif product_type == 'shoes':
                        categories_available = ["Men's Shoes", "Ladies' Shoes"]
                        category_keys = ["mens_shoes", "womens_shoes"]
                    elif product_type == 'bag':
                        categories_available = ["Hand Bags"]
                        category_keys = ["handbag"]
                    else:
                        categories_available = ["Available Products"]
                        category_keys = [product_type]
                    
                    # Build category selection message
                    message = f"Great! We have {product_type}s in these categories:\n\n"
                    for idx, cat in enumerate(categories_available, 1):
                        message += f"{idx}. {cat}\n"
                    message += f"\nPlease select a category (1-{len(categories_available)}) or specify a brand name (e.g., Rolex, Fossil, Casio)."
                    
                    # Store context for next message
                    orchestrator.user_states[phone_number] = {
                        'waiting_for': 'category_or_brand',
                        'product_type': product_type,
                        'categories': category_keys,
                        'timestamp': time.time()
                    }
                    
                    whatsapp.send_message(phone_number, message)
                    logger.info(f"📋 Asked category selection for {product_type}")

                elif action == 'find_product_by_range':
                    # Price range search - call text_search_api endpoint
                    category = metadata.get('category', 'watches')
                    min_price = metadata.get('min_price')
                    max_price = metadata.get('max_price')
                    product_name = metadata.get('product_name', f"₹{min_price}-₹{max_price} {category}")
                    
                    logger.info(f"💰 PRICE RANGE SEARCH: {category} between ₹{min_price} - ₹{max_price}")
                    
                    try:
                        # Call text_search_api range search endpoint
                        import requests
                        from concurrent.futures import ThreadPoolExecutor, as_completed
                        
                        text_search_url = os.getenv('TEXT_SEARCH_API_URL', 'http://localhost:8001')
                        response = requests.post(
                            f"{text_search_url}/search/range",
                            json={
                                "category": category,
                                "min_price": min_price,
                                "max_price": max_price,
                                "max_results": 50
                            },
                            timeout=30
                        )
                        
                        if response.status_code == 200:
                            search_result = response.json()
                            if search_result.get('status') == 'success':
                                all_products = search_result.get('products', [])
                                total_found = search_result.get('total_products', 0)
                                
                                logger.info(f"✅ Found {total_found} products in {category} range ₹{min_price}-{max_price}")
                                
                                # Send products to user (batch of 10)
                                if all_products:
                                    batch_size = 10
                                    products_to_send = all_products[:batch_size]
                                    sent_count = len(products_to_send)
                                    
                                    # Send intro message
                                    intro_msg = f"""🎉 Found {total_found} products in {category} (₹{min_price}-₹{max_price})
Showing {sent_count} products... Please wait 📸"""
                                    whatsapp.send_message(phone_number, intro_msg)
                                    
                                    # Send each product
                                    def send_single_product(idx, product):
                                        product_name_item = product.get('product_name', 'Unknown')
                                        price = product.get('price', 'N/A')
                                        product_url = product.get('product_url', '')
                                        images = product.get('images', [])
                                        
                                        if not images: return False
                                        
                                        try:
                                            caption = f"📦 {product_name_item}\n💰 ₹{price}"
                                            if product_url: caption += f"\n🔗 {product_url}"
                                            if len(images) > 1: caption += f"\n\n📸 {len(images)} images available"
                                            
                                            return whatsapp.forward_media(phone_number, images[0], caption, "image")
                                        except Exception as e:
                                            logger.error(f"Error sending product {idx}: {e}")
                                            return False
                                    
                                    success_count = 0
                                    with ThreadPoolExecutor(max_workers=3) as executor:
                                        futures = [executor.submit(send_single_product, idx, prod)
                                                  for idx, prod in enumerate(products_to_send, 1)]
                                        for future in as_completed(futures):
                                            if future.result(): success_count += 1
                                    
                                    # Cache products for pagination
                                    orchestrator.cache_product_data(phone_number, all_products)
                                    
                                    if success_count > 0:
                                        orchestrator.save_search_context(phone_number, product_name, total_found, sent_count)
                                        
                                        # Send completion message
                                        if sent_count < total_found:
                                            completion_msg = f"""બીજી પ્રોડક્ટ પણ છે અમારી પાસે, જો તમારે જોવી હોય તો હું બતાવું? 😊

તમે આ વૉચ બે રીતે ઓર્ડર કરી શકો છો
1. અમદાવાદ-બોપલ સ્થિત અમારી સ્ટોર પરથી સીધી આવીને લઈ શકો છો.
2. ઘર બેઠા Open Box Cash on Delivery દ્વારા પણ મંગાવી શકો છો.
3. બીજી watches જોવા માટે 'More' લખો.
તમને કયો વિકલ્પ વધુ યોગ્ય લાગે છે? કૃપા કરીને જણાવશો."""
                                        else:
                                            completion_msg = """તમે આ વૉચ બે રીતે ઓર્ડર કરી શકો છો
1. અમદાવાદ-બોપલ સ્થિત અમારી સ્ટોર પરથી સીધી આવીને લઈ શકો છો.
2. ઘર બેઠા Open Box Cash on Delivery દ્વારા પણ મંગાવી શકો છો.
3. બીજી watches જોવા માટે 'More' લખો.
તમને કયો વિકલ્પ વધુ યોગ્ય લાગે છે? કૃપા કરીને જણાવશો."""
                                        
                                        whatsapp.send_message(phone_number, completion_msg)
                                else:
                                    whatsapp.send_message(phone_number, f"❌ No products found in {category} between ₹{min_price} - ₹{max_price}")
                            else:
                                whatsapp.send_message(phone_number, f"❌ {search_result.get('message', 'Search failed')}")
                        else:
                            logger.error(f"❌ Text search API error: {response.status_code}")
                            whatsapp.send_message(phone_number, f"Sorry, couldn't search products in that range 😔")
                            
                    except Exception as e:
                        logger.error(f"❌ Price range search error: {e}")
                        whatsapp.send_message(phone_number, f"Technical error during search 😔")

                elif action == 'send_all_images':
                    # User wants to see all images for a specific product
                    product_name = metadata.get('product_name', '')
                    
                    logger.info(f"📸 USER WANTS ALL IMAGES for: {product_name}")
                    
                    try:
                        # Search for the product to get all its images
                        import requests
                        from concurrent.futures import ThreadPoolExecutor, as_completed
                        
                        text_search_url = os.getenv('TEXT_SEARCH_API_URL', 'http://localhost:8001')
                        response = requests.post(
                            f"{text_search_url}/search",
                            json={
                                "query": product_name,
                                "max_results": 10
                            },
                            timeout=30
                        )
                        
                        if response.status_code == 200:
                            search_result = response.json()
                            if search_result.get('status') == 'success':
                                products = search_result.get('products', [])
                                
                                # Find exact product match (case-insensitive)
                                matching_product = None
                                for prod in products:
                                    if prod.get('product_name', '').lower() == product_name.lower():
                                        matching_product = prod
                                        break
                                
                                # If exact match not found, use first result
                                if not matching_product and products:
                                    matching_product = products[0]
                                
                                if matching_product:
                                    # Get image_urls (the API returns image_urls, not images)
                                    image_urls = matching_product.get('images', [])
                                    if not image_urls:
                                        image_urls = matching_product.get('image_urls', [])
                                    
                                    product_price = matching_product.get('price', 'N/A')
                                    product_url = matching_product.get('product_url', '')
                                    actual_product_name = matching_product.get('product_name', product_name)
                                    
                                    logger.info(f"📸 Found product: {actual_product_name}")
                                    logger.info(f"📷 Total images: {len(image_urls)}")
                                    
                                    if image_urls:
                                        # Send intro message
                                        intro_msg = f"""📸 All Images for {actual_product_name}
💰 Price: ₹{product_price}
📷 Total Images: {len(image_urls)}

Bhej raha hoon sare images... 🚀"""
                                        whatsapp.send_message(phone_number, intro_msg)
                                        
                                        # Send all images concurrently
                                        def send_product_image(idx, image_url):
                                            try:
                                                caption = f"📸 Image {idx + 1}/{len(image_urls)}"
                                                result = whatsapp.send_media_via_url(phone_number, image_url, caption, "image")
                                                logger.info(f"✅ Sent image {idx + 1}/{len(image_urls)}")
                                                return result
                                            except Exception as e:
                                                logger.error(f"❌ Error sending image {idx + 1}: {e}")
                                                return False
                                        
                                        success_count = 0
                                        with ThreadPoolExecutor(max_workers=4) as executor:
                                            futures = [executor.submit(send_product_image, idx, img_url)
                                                      for idx, img_url in enumerate(image_urls)]
                                            for future in as_completed(futures):
                                                if future.result(): 
                                                    success_count += 1
                                        
                                        logger.info(f"✅ Completed! Sent {success_count}/{len(image_urls)} images")
                                        
                                        # Send completion message
                                        completion_msg = f"""✅ {success_count}/{len(image_urls)} images sent!

💰 Price: ₹{product_price}
{f'🔗 More info: {product_url}' if product_url else ''}

Koi aur product chahiye? 😊"""
                                        whatsapp.send_message(phone_number, completion_msg)
                                    else:
                                        logger.warning(f"⚠️ No images found for product: {actual_product_name}")
                                        whatsapp.send_message(phone_number, f"Sorry, no images found for '{actual_product_name}' 😔")
                                else:
                                    logger.warning(f"⚠️ Product not found: {product_name}")
                                    whatsapp.send_message(phone_number, f"Product '{product_name}' not found in our database 😔")
                            else:
                                logger.error(f"Search API error: {search_result.get('message')}")
                                whatsapp.send_message(phone_number, f"❌ {search_result.get('message', 'Search failed')}")
                        else:
                            logger.error(f"❌ Text search API error: {response.status_code}")
                            whatsapp.send_message(phone_number, f"Sorry, couldn't retrieve product images 😔")
                            
                    except Exception as e:
                        logger.error(f"❌ Send all images error: {str(e)}")
                        whatsapp.send_message(phone_number, f"Technical error retrieving images 😔")

                elif action == 'ai_chat' or action == 'ai_response':
                    response = conversation_agent.get_response(conversation, phone_number, metadata)
                    whatsapp.send_message(phone_number, response)

                elif action == 'save_order_direct' or action == 'save_data_to_google_sheet':
                    # Save order directly
                    order_data = metadata.get('order_data', metadata.get('data', {}))
                    
                    # Map classifier field names to validation expected names
                    logger.info(f"📋 Raw order data from classifier: {order_data}")
                    
                    # Normalize field names - classifier might return 'name', 'phone' but we need 'customer_name', 'phone_number'
                    if 'name' in order_data and 'customer_name' not in order_data:
                        order_data['customer_name'] = order_data.pop('name')
                    if 'phone' in order_data and 'phone_number' not in order_data:
                        order_data['phone_number'] = order_data.pop('phone')
                    
                    logger.info(f"✅ Normalized order data: {order_data}")
                    
                    order_data['order_id'] = f"WV{datetime.now().strftime('%Y%m%d%H%M%S')}{phone_number[-4:]}"
                    order_data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    order_data['status'] = 'Pending'

                    success = order_storage.save_order(order_data)

                    if success:
                        response = "*Order Confirmed!* Our team will contact you within 24 hours. Thank you! 🙏"
                        whatsapp.send_message(phone_number, response)
                        orchestrator.clear_user_data(phone_number)
                    else:
                        whatsapp.send_message(phone_number, "Technical issue saving order. Please call us.")

        return jsonify({"status": "success"}), 200

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    logger.info("🚀 STARTING WATCHVINE MAIN APPLICATION")
    app.run(host='0.0.0.0', port=5000, debug=False)
