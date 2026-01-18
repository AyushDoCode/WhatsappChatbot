"""
Enhanced Agent Orchestrator with WhatsApp Image Sending
Handles MongoDB vector search and sends actual product images
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Any
from conversation_agent import ConversationAgent
from google_apps_script_handler import GoogleSheetsHandler
from enhanced_backend_tool_classifier import BackendToolClassifier
# WhatsApp functions imported as needed

logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """
    Enhanced orchestrator that coordinates between conversation agent and vector search
    Sends actual product images via WhatsApp webhook
    """
    
    def __init__(self):
        """Initialize the enhanced agent orchestrator"""
        self.conversation_agent = ConversationAgent()
        self.google_sheets_handler = GoogleSheetsHandler()
        
        # Evolution API functions will be imported as needed
        logger.info("✅ Evolution API functions ready for use")
        
        # Search context tracking
        self.search_contexts = {}
        
        logger.info("Enhanced Agent Orchestrator with Image Sending initialized")

    def process_message(self, conversation_history: List[Dict], user_message: str, phone_number: str) -> Dict:
        """
        Main orchestration method - processes user message and coordinates response
        Now handles vector search with actual image sending
        """
        try:
            logger.info(f"📨 Processing message from {phone_number}: {user_message[:100]}...")
            
            # Initialize enhanced classifier
            classifier = BackendToolClassifier()
            
            # Classify and search using vector search system
            classification = classifier.classify_and_search(
                user_message,
                conversation_history,
                {}
            )
            
            tool = classification.get('tool', 'ai_chat')
            logger.info(f"🔍 Tool classified: {tool}")
            
            # Handle product search with image sending
            if tool == 'product_search':
                result = self._handle_vector_search_response(
                    classification,
                    conversation_history,
                    user_message,
                    phone_number
                )
                classifier.close()
                return result
            
            # Handle general chat
            else:
                response = self.conversation_agent.generate_response(
                    conversation_history,
                    user_message,
                    phone_number
                )
                
                classifier.close()
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
        """Handle vector search response by sending actual images via WhatsApp"""
        try:
            formatted_response = classification.get('formatted_response', {})
            images_to_send = formatted_response.get('images_to_send', [])
            summary_message = formatted_response.get('message', 'Found products for you!')
            
            if images_to_send:
                logger.info(f"📱 Sending {len(images_to_send)} product images to {phone_number}")
                
                # Send actual product images via Evolution API
                image_sent = False
                
                # Send summary message first using your Evolution API
                from whatsapp_sender import send_whatsapp_text
                try:
                    send_whatsapp_text(phone_number, summary_message)
                    logger.info(f"📤 Sent summary message")
                except Exception as e:
                    logger.error(f"❌ Error sending summary: {e}")
                
                # Send each product image with caption using your Evolution API
                success_count = 0
                for img_data in images_to_send:
                    try:
                        # Get image URL and convert to base64 for Evolution API
                        image_url = img_data['image_url']
                        caption = img_data['caption']
                        
                        # Download image and convert to base64
                        import requests
                        import base64
                        
                        img_response = requests.get(image_url, timeout=10)
                        if img_response.status_code == 200:
                            image_base64 = base64.b64encode(img_response.content).decode('utf-8')
                            
                            # Use your existing Evolution API function
                            from whatsapp_sender import send_whatsapp_image
                            result = send_whatsapp_image(phone_number, image_base64, caption)
                            
                            if result.get('success', False):
                                success_count += 1
                                logger.info(f"✅ Sent image for {img_data.get('product_name', 'Product')}")
                            else:
                                logger.error(f"❌ Evolution API failed for {img_data.get('product_name', 'Product')}")
                        else:
                            logger.error(f"❌ Failed to download image: {image_url}")
                        
                        # Small delay between images
                        import time
                        time.sleep(1)
                        
                    except Exception as e:
                        logger.error(f"❌ Error sending image for {img_data.get('product_name', 'Product')}: {e}")
                        continue
                
                image_sent = success_count > 0
                logger.info(f"📱 Evolution API sent {success_count}/{len(images_to_send)} images")
                
                if image_sent:
                    response_text = f"✅ Found {len(images_to_send)} watches! Sent images with prices and shop links."
                    logger.info(f"✅ Successfully sent {len(images_to_send)} product images")
                else:
                    # Fallback to text response with image URLs and details
                    response_parts = [f"Found {len(images_to_send)} watches for you:"]
                    for i, img_data in enumerate(images_to_send, 1):
                        response_parts.append(f"\n{i}. {img_data['caption']}")
                        response_parts.append(f"📸 Image: {img_data['image_url']}")
                    
                    response_text = "\n".join(response_parts)
                    logger.warning("📱 Image sending failed, using text fallback")
                
                return {
                    "response": response_text,
                    "timestamp": datetime.now().isoformat(),
                    "tool_used": "vector_search_with_images",
                    "images_sent": image_sent,
                    "products_count": len(images_to_send),
                    "images_data": images_to_send  # Include for external processing
                }
            else:
                # No images found
                response = "Sorry, I couldn't find any watches with images matching your search. Please try different terms like 'black watch', 'Rolex', or 'luxury watch'."
                
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
    
    def get_search_context(self, phone_number: str) -> Dict:
        """Get search context for user"""
        return self.search_contexts.get(phone_number, {})
    
    def update_search_context(self, phone_number: str, context: Dict):
        """Update search context for user"""
        self.search_contexts[phone_number] = context

    def save_order_to_sheets(self, order_data: Dict) -> Dict:
        """Save order data to Google Sheets"""
        try:
            result = self.google_sheets_handler.save_order(order_data)
            if result.get('success'):
                return {
                    "success": True,
                    "order_id": result.get('order_id'),
                    "message": "Order saved successfully!"
                }
            else:
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