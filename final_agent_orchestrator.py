"""
Final Agent Orchestrator - Fully Compatible with Existing System
Uses exact same imports as your main.py to avoid conflicts
"""

import json
import logging
import os
import time
import google.generativeai as genai
from datetime import datetime
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# Import exactly what exists in your system
try:
    from google_sheets_handler import GoogleSheetsHandler
except ImportError:
    try:
        from google_apps_script_handler import GoogleSheetsHandler
    except ImportError:
        # Fallback if neither exists
        class GoogleSheetsHandler:
            def save_order(self, order_data):
                return {"success": False, "message": "Sheets handler not available"}

try:
    from enhanced_backend_tool_classifier import BackendToolClassifier
except ImportError:
    # Fallback to basic classification
    class BackendToolClassifier:
        def classify_and_search(self, message, history, context):
            return {"tool": "ai_chat", "formatted_response": {"has_results": False}}
        def close(self):
            pass

class ConversationAgent:
    """Simple conversation agent compatible with main.py"""
    def __init__(self):
        self.api_key = os.getenv("Google_api")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-pro')
        else:
            self.model = None
    
    def generate_response(self, conversation_history: list, user_message: str, phone_number: str, additional_context: str = None) -> str:
        """Generate conversational response"""
        try:
            if not self.model:
                return "I'm here to help with your watch queries!"
            
            prompt = f"""You are a helpful WhatsApp chatbot for a watch store. 
User message: {user_message}
Respond helpfully and conversationally about watches."""
            
            if additional_context:
                prompt += f"\nContext: {additional_context}"
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I'm here to help! Feel free to ask about watches."

class ConversationState:
    """Simple conversation state for compatibility"""
    MENU = "menu"
    PRODUCT_SEARCH = "product_search"
    GENERAL_CHAT = "general_chat"

class AgentOrchestrator:
    """Enhanced orchestrator with vector search - fully compatible version"""
    
    def __init__(self):
        """Initialize the enhanced agent orchestrator"""
        try:
            self.conversation_agent = ConversationAgent()
            self.google_sheets_handler = GoogleSheetsHandler()
            
            # Search context tracking
            self.search_contexts = {}
            
            logger.info("Enhanced Agent Orchestrator initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Agent Orchestrator: {e}")
            # Continue with basic functionality
            self.conversation_agent = ConversationAgent()
            self.google_sheets_handler = None
            self.search_contexts = {}

    def process_message(self, conversation_history: List[Dict], user_message: str, phone_number: str) -> Dict:
        """Main orchestration method with vector search integration"""
        try:
            logger.info(f"📨 Processing message from {phone_number}: {user_message[:50]}...")
            
            # Try enhanced classification first
            try:
                classifier = BackendToolClassifier()
                
                # Classify and search using vector search system
                classification = classifier.classify_and_search(
                    user_message,
                    conversation_history,
                    {}
                )
                
                tool = classification.get('tool', 'ai_chat')
                logger.info(f"🔍 Tool classified: {tool}")
                
                # Handle product search with Evolution API
                if tool == 'product_search':
                    result = self._handle_vector_search_response(
                        classification,
                        conversation_history,
                        user_message,
                        phone_number
                    )
                    classifier.close()
                    return result
                
                classifier.close()
                
            except Exception as e:
                logger.warning(f"Enhanced classification failed, using fallback: {e}")
            
            # Fallback to general chat
            response = self.conversation_agent.generate_response(
                conversation_history,
                user_message,
                phone_number
            )
            
            return {
                "response": response,
                "timestamp": datetime.now().isoformat(),
                "tool_used": "ai_chat"
            }
                
        except Exception as e:
            logger.error(f"❌ Error in process_message: {e}")
            return {
                "response": "I'm having trouble processing your request. Please try again.",
                "timestamp": datetime.now().isoformat(),
                "tool_used": "error"
            }

    def _handle_vector_search_response(self, classification: dict, conversation_history: list, user_message: str, phone_number: str) -> dict:
        """Handle vector search response by sending actual images via Evolution API"""
        try:
            formatted_response = classification.get('formatted_response', {})
            images_to_send = formatted_response.get('images_to_send', [])
            summary_message = formatted_response.get('message', 'Found products for you!')
            
            if images_to_send:
                logger.info(f"📱 Sending {len(images_to_send)} product images to {phone_number}")
                
                # Send images using your Evolution API
                image_sent = self._send_watch_images(phone_number, images_to_send, summary_message)
                
                if image_sent:
                    response_text = f"✅ Found {len(images_to_send)} watches! Sent images with prices and shop links."
                else:
                    # Fallback to text response
                    response_parts = [f"Found {len(images_to_send)} watches for you:"]
                    for i, img_data in enumerate(images_to_send, 1):
                        response_parts.append(f"\n{i}. {img_data.get('caption', 'Watch')}")
                    response_text = "\n".join(response_parts)
                
                return {
                    "response": response_text,
                    "timestamp": datetime.now().isoformat(),
                    "tool_used": "vector_search_with_images",
                    "images_sent": image_sent,
                    "products_count": len(images_to_send)
                }
            else:
                # No images found
                response = "Sorry, I couldn't find any watches matching your search. Try terms like 'black watch', 'Rolex', or 'luxury watch'."
                
                return {
                    "response": response,
                    "timestamp": datetime.now().isoformat(),
                    "tool_used": "vector_search_no_results"
                }
                
        except Exception as e:
            logger.error(f"❌ Error handling vector search response: {e}")
            
            # Fallback response
            return {
                "response": "I found some watches for you, but had trouble sending the images. Please try again.",
                "timestamp": datetime.now().isoformat(),
                "tool_used": "vector_search_error"
            }

    def _send_watch_images(self, phone_number: str, images_to_send: list, summary_message: str) -> bool:
        """Send watch images using Evolution API"""
        try:
            # Send summary message first
            try:
                from whatsapp_sender import send_whatsapp_text
                send_whatsapp_text(phone_number, summary_message)
                logger.info(f"📤 Sent summary message")
            except Exception as e:
                logger.error(f"❌ Error sending summary: {e}")
            
            # Send each product image
            success_count = 0
            for img_data in images_to_send:
                try:
                    image_url = img_data.get('image_url')
                    caption = img_data.get('caption', 'Watch')
                    
                    if not image_url:
                        continue
                    
                    # Download and convert image to base64
                    import requests
                    import base64
                    
                    img_response = requests.get(image_url, timeout=10)
                    if img_response.status_code == 200:
                        image_base64 = base64.b64encode(img_response.content).decode('utf-8')
                        
                        # Use your existing Evolution API function
                        from whatsapp_sender import send_whatsapp_image
                        result = send_whatsapp_image(phone_number, image_base64, caption)
                        
                        if result and result.get('success', False):
                            success_count += 1
                            logger.info(f"✅ Sent image for {img_data.get('product_name', 'Product')}")
                        else:
                            logger.error(f"❌ Evolution API failed for {img_data.get('product_name', 'Product')}")
                    else:
                        logger.error(f"❌ Failed to download image: {image_url}")
                    
                    # Small delay between images
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Error sending image: {e}")
                    continue
            
            logger.info(f"📱 Evolution API sent {success_count}/{len(images_to_send)} images")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error in send_watch_images: {e}")
            return False
    
    def get_search_context(self, phone_number: str) -> Dict:
        """Get search context for user"""
        return self.search_contexts.get(phone_number, {})
    
    def update_search_context(self, phone_number: str, context: Dict):
        """Update search context for user"""
        self.search_contexts[phone_number] = context

    def save_order_to_sheets(self, order_data: Dict) -> Dict:
        """Save order data to Google Sheets"""
        try:
            if self.google_sheets_handler:
                result = self.google_sheets_handler.save_order(order_data)
                if result and result.get('success'):
                    return {
                        "success": True,
                        "order_id": result.get('order_id'),
                        "message": "Order saved successfully!"
                    }
            
            return {
                "success": False,
                "message": "Failed to save order."
            }
        except Exception as e:
            logger.error(f"Error saving order: {e}")
            return {
                "success": False,
                "message": "Error saving order."
            }