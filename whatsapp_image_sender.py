#!/usr/bin/env python3
"""
WhatsApp Image Sender for Product Results
Sends actual product images via WhatsApp webhook
"""

import requests
import logging
from typing import List, Dict
import time

logger = logging.getLogger(__name__)

class WhatsAppImageSender:
    def __init__(self, webhook_url: str = None, api_token: str = None):
        """Initialize WhatsApp image sender"""
        self.webhook_url = webhook_url or "https://api.whatsapp.com/send"
        self.api_token = api_token
        
    def send_product_images(self, phone_number: str, images_data: List[Dict]) -> bool:
        """
        Send product images to WhatsApp
        
        Args:
            phone_number: Recipient phone number
            images_data: List of image data with captions
                [
                    {
                        "image_url": "https://...",
                        "caption": "Brand - Name\nPrice: ₹XXX\nLink: https://...",
                        "product_name": "...",
                        "brand": "...",
                        "price": "...",
                        "url": "..."
                    }
                ]
        """
        try:
            success_count = 0
            
            for image_data in images_data:
                # Send individual image with caption
                if self._send_single_image(phone_number, image_data):
                    success_count += 1
                    time.sleep(1)  # Delay between sends
                else:
                    logger.error(f"Failed to send image for {image_data.get('product_name', 'Unknown')}")
            
            logger.info(f"✅ Sent {success_count}/{len(images_data)} product images to {phone_number}")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ Error sending product images: {e}")
            return False
    
    def _send_single_image(self, phone_number: str, image_data: Dict) -> bool:
        """Send a single product image via WhatsApp"""
        try:
            image_url = image_data.get('image_url')
            caption = image_data.get('caption', '')
            
            if not image_url:
                return False
            
            # WhatsApp API payload for image message
            payload = {
                "messaging_product": "whatsapp",
                "to": phone_number,
                "type": "image",
                "image": {
                    "link": image_url,
                    "caption": caption
                }
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            # Send to WhatsApp Business API
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Image sent: {image_data.get('product_name', 'Product')}")
                return True
            else:
                logger.error(f"❌ WhatsApp API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error sending single image: {e}")
            return False
    
    def send_product_summary(self, phone_number: str, summary_message: str) -> bool:
        """Send summary text message"""
        try:
            payload = {
                "messaging_product": "whatsapp",
                "to": phone_number,
                "type": "text",
                "text": {
                    "body": summary_message
                }
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers=headers,
                timeout=10
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"❌ Error sending summary: {e}")
            return False

# Alternative for Twilio WhatsApp API
class TwilioWhatsAppSender:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        """Initialize Twilio WhatsApp sender"""
        from twilio.rest import Client
        self.client = Client(account_sid, auth_token)
        self.from_number = from_number
        
    def send_product_images(self, phone_number: str, images_data: List[Dict]) -> bool:
        """Send product images via Twilio WhatsApp"""
        try:
            success_count = 0
            
            for image_data in images_data:
                try:
                    message = self.client.messages.create(
                        media_url=[image_data['image_url']],
                        body=image_data['caption'],
                        from_=f'whatsapp:{self.from_number}',
                        to=f'whatsapp:{phone_number}'
                    )
                    
                    if message.sid:
                        success_count += 1
                        logger.info(f"✅ Twilio sent: {image_data.get('product_name', 'Product')}")
                    
                    time.sleep(1)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"❌ Twilio error for image: {e}")
                    continue
            
            logger.info(f"✅ Twilio sent {success_count}/{len(images_data)} images")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ Twilio batch error: {e}")
            return False

# Simple webhook sender (for custom implementations)
class WebhookImageSender:
    def __init__(self, webhook_url: str):
        """Initialize webhook sender"""
        self.webhook_url = webhook_url
        
    def send_product_images(self, phone_number: str, images_data: List[Dict]) -> bool:
        """Send images via custom webhook"""
        try:
            payload = {
                "phone": phone_number,
                "type": "product_images",
                "images": images_data,
                "timestamp": time.time()
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Webhook sent {len(images_data)} images to {phone_number}")
                return True
            else:
                logger.error(f"❌ Webhook error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Webhook sending error: {e}")
            return False